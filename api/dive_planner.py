import logging
import math
from typing import List, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from gas_blender import density_depth, gas_density
from planner.dive import plan_ccr_dive, plan_oc_bailout, plan_oc_dive
from planner.gas import CCRGas, OpenCircuitGas
from DivePlanner import (
    _binary_search_bottom_time,
    _cns_rate,
    _compute_gas_consumption,
    _oc_cns_otu,
    _otu_rate,
)

router = APIRouter()


# ── Request / response models ──────────────────────────────────────────────────

class BailoutGasInput(BaseModel):
    o2: float = Field(ge=1, le=100, description="O₂ (%)")
    he: float = Field(default=0.0, ge=0, le=100, description="He (%)")
    mod_m: float = Field(gt=0, description="Maximum Operating Depth (m)")
    ppo2_limit: float = Field(default=1.4, ge=1.0, le=1.6, description="ppO₂ working limit used to set MOD (bar)")
    cyl_l: Optional[float] = Field(default=None, gt=0, description="Cylinder water volume (L)")
    cyl_bar: Optional[float] = Field(default=None, gt=0, description="Fill pressure (bar)")


class DivePlannerRequest(BaseModel):
    """CCR/OC decompression planning parameters (Bühlmann ZHL-16C with gradient factors)."""
    mode: Literal["ccr", "oc"] = Field(default="ccr", description="Dive mode: 'ccr' or 'oc'")
    diluent_o2: Optional[float] = Field(default=None, ge=1, le=100, description="Diluent O₂ (%; CCR only)")
    diluent_he: Optional[float] = Field(default=None, ge=0, le=100, description="Diluent He (%; CCR only)")
    setpoint: Optional[float] = Field(default=None, gt=0, le=2.0, description="CCR setpoint (bar ppO₂; CCR only)")
    depth_m: float = Field(gt=0, description="Bottom depth (m)")
    bottom_time_min: float = Field(gt=0, description="Bottom time (min)")
    gf_low: float = Field(default=60.0, ge=1.0, le=100.0, description="GF Low (%)")
    gf_high: float = Field(default=80.0, ge=1.0, le=100.0, description="GF High (%)")
    desc_rate_mpm: float = Field(default=20.0, ge=1.0, le=50.0, description="Descent rate (m/min)")
    asc_rate_deep_mpm: float = Field(default=9.0, ge=1.0, le=30.0, description="Ascent rate above 6 m (m/min)")
    asc_rate_shallow_mpm: float = Field(default=3.0, ge=1.0, le=30.0, description="Ascent rate ≤6 m (m/min)")
    last_stop_m: Literal[3, 4, 5, 6, 9] = Field(default=3, description="Shallowest deco stop depth (m)")
    cns_warn_pct: float = Field(default=80.0, ge=50.0, le=100.0, description="CNS O₂ toxicity warning threshold (%)")
    bailout_gf_low: Optional[float] = Field(default=None, ge=1.0, le=100.0, description="Bailout GF Low (%; CCR only, defaults to gf_low)")
    bailout_gf_high: Optional[float] = Field(default=None, ge=1.0, le=100.0, description="Bailout GF High (%; CCR only, defaults to gf_high)")
    bailout_gases: List[BailoutGasInput] = Field(default=[], description="OC bailout/deco gases")
    sac_bottom_lpm: float = Field(default=25.0, ge=2.0, le=200.0, description="Bottom SAC / RMV (L/min)")
    sac_deco_lpm: float = Field(default=15.0, ge=2.0, le=200.0, description="Deco SAC / RMV (L/min)")
    reserve_bar: float = Field(default=50.0, ge=0.0, le=300.0, description="Cylinder reserve (bar)")

    @model_validator(mode='after')
    def check_diluent(self):
        if self.mode == 'ccr':
            if self.diluent_o2 is None or self.diluent_he is None or self.setpoint is None:
                raise ValueError("diluent_o2, diluent_he, and setpoint are required for CCR mode.")
            if not (0 < self.diluent_o2 + self.diluent_he <= 100):
                raise ValueError("Invalid diluent composition.")
        return self

    @model_validator(mode='after')
    def check_oc_gases(self):
        if self.mode == 'oc' and not self.bailout_gases:
            raise ValueError("At least one deco gas is required for OC mode.")
        return self

    @model_validator(mode='after')
    def check_gf_ordering(self):
        if self.gf_low > self.gf_high:
            raise ValueError("GF Low must be ≤ GF High.")
        return self

    @model_validator(mode='after')
    def check_bottom_time(self):
        if self.bottom_time_min <= self.depth_m / self.desc_rate_mpm:
            raise ValueError("Bottom time must exceed descent time.")
        return self

    @model_validator(mode='after')
    def check_bailout_gf(self):
        bg_low  = self.bailout_gf_low  if self.bailout_gf_low  is not None else self.gf_low
        bg_high = self.bailout_gf_high if self.bailout_gf_high is not None else self.gf_high
        if bg_low > bg_high:
            raise ValueError("Bailout GF Low must be ≤ Bailout GF High.")
        return self


class Warning(BaseModel):
    level: str = Field(description="Severity: 'warning' or 'danger'")
    message: str


class DecoStop(BaseModel):
    depth_m: float
    time_min: float
    runtime_min: float


class DensityAnalysis(BaseModel):
    density_gl: float
    exceeded_recommended: bool
    exceeded_limit: bool


class ProfilePoint(BaseModel):
    t: float = Field(description="Runtime (min)")
    d: float = Field(description="Depth (m)")
    c: float = Field(description="Ceiling (m)")
    sats: List[float] = Field(description="Tissue saturation ratios (16 compartments)")
    inert: List[List[float]] = Field(default_factory=list, description="Inert gas loads [[pn2, phe]] per compartment")


class GasSwitch(BaseModel):
    depth_m: float
    label: str


class GasSupplyEntry(BaseModel):
    o2: float
    he: float
    mod_m: float
    consumed_L: float
    available_L: Optional[float] = None
    pct: Optional[float] = None


class BailoutPlan(BaseModel):
    stops: List[DecoStop]
    total_time_min: float
    tts_min: float
    cns_pct: float
    otu: float
    gas_switches: List[GasSwitch]
    profile_points: List[ProfilePoint]
    tissue_saturations: List[float]
    gas_supply: Optional[List[GasSupplyEntry]] = None


class DivePlannerResponse(BaseModel):
    """CCR/OC decompression schedule with toxicity data and optional CCR bailout plan."""
    stops: List[DecoStop]
    total_time_min: float
    warnings: List[Warning]
    density_analysis: DensityAnalysis
    profile_points: List[ProfilePoint]
    tissue_saturations: List[float]
    tts_min: float
    cns_pct: float
    otu: float
    bottom_time_actual: float
    gas_switches: List[GasSwitch] = Field(default=[], description="Gas switches during the dive (OC mode)")
    gas_supply: Optional[List[GasSupplyEntry]] = Field(default=None, description="Gas supply summary (OC mode)")
    bailout: Optional[BailoutPlan] = None


# ── Endpoint ───────────────────────────────────────────────────────────────────

@router.post(
    "/api/DivePlanner",
    response_model=DivePlannerResponse,
    summary="CCR/OC decompression plan",
    description=(
        "Plans a CCR or OC decompression dive using the Bühlmann ZHL-16C algorithm with gradient "
        "factors. Returns the deco schedule, tissue saturations, CNS/OTU toxicity data, gas density "
        "analysis, and (in CCR mode) an optional OC bailout plan."
    ),
    responses={400: {"description": "Invalid inputs", "content": {"text/plain": {}}}},
)
def dive_planner(req: DivePlannerRequest) -> DivePlannerResponse:
    logging.info("DivePlanner request received.")

    gf_low  = req.gf_low  / 100.0
    gf_high = req.gf_high / 100.0

    oc_gases: List[OpenCircuitGas] = []
    oc_gas_volumes = []
    for g in req.bailout_gases:
        if not (0 < g.o2 + g.he <= 100):
            raise HTTPException(status_code=400, detail=f"Invalid composition for gas O₂={g.o2} He={g.he}.")
        oc_gases.append(OpenCircuitGas(g.o2, g.he, g.mod_m))
        oc_gas_volumes.append({'cyl_l': g.cyl_l, 'cyl_bar': g.cyl_bar})

    if req.mode == 'oc':
        return _plan_oc(req, gf_low, gf_high, oc_gases, oc_gas_volumes)
    else:
        return _plan_ccr(req, gf_low, gf_high, oc_gases, oc_gas_volumes)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _infeasibility_msg(sorted_volumes, reserve_bar, depth_m, prefix='Gas') -> str:
    empty_gases = [
        g.label for g, v in sorted_volumes
        if v['cyl_l'] and v['cyl_bar']
        and v['cyl_l'] * max(0.0, v['cyl_bar'] - reserve_bar) == 0
    ]
    if empty_gases:
        have = 'has' if len(empty_gases) == 1 else 'have'
        return (
            f"{prefix} supply error: {', '.join(empty_gases)} {have} no usable gas after "
            f"deducting the {reserve_bar:.0f} bar reserve. "
            f"Increase cylinder pressure or reduce the tank reserve setting."
        )
    return (
        f"{prefix} supply is insufficient even for the minimum possible dive time "
        f"at {depth_m:.0f} m. Increase cylinder sizes, pressure, or reduce the "
        f"{reserve_bar:.0f} bar reserve."
    )


def _gas_warnings(
    gases, bottom_depth_m,
    first_gas_type='Back gas', other_gas_type='Deco gas',
    skip_first_density=True,
) -> List[Warning]:
    warnings: List[Warning] = []
    for i, bg in enumerate(sorted(gases, key=lambda g: g.mod_m, reverse=True)):
        use_depth = bottom_depth_m if i == 0 else min(bg.mod_m, density_depth(bg.o2, bg.he, 5.2))
        fo2 = bg.o2 / 100.0
        d = gas_density(bg.o2, bg.he, use_depth)
        label = OpenCircuitGas(bg.o2, bg.he, bg.mod_m).label
        ppo2 = fo2 * (use_depth / 10.0 + 1.0)
        ppo2_r = round(ppo2, 2)
        gas_type = first_gas_type if i == 0 else other_gas_type
        if ppo2_r > 1.6:
            warnings.append(Warning(
                level='danger',
                message=(
                    f'{gas_type} {label} at {use_depth:.0f} m: '
                    f'ppO₂ {ppo2:.2f} bar exceeds the absolute maximum (1.6 bar). '
                    f'This gas cannot be safely breathed at this depth.'
                ),
            ))
        elif ppo2_r > bg.ppo2_limit:
            warnings.append(Warning(
                level='warning',
                message=(
                    f'{gas_type} {label} at {use_depth:.0f} m: '
                    f'ppO₂ {ppo2:.2f} bar exceeds the working limit ({bg.ppo2_limit:.1f} bar). '
                    f'Consider a lower O₂ fraction or shallower planned depth.'
                ),
            ))
        if skip_first_density and i == 0:
            continue
        if d > 6.3:
            warnings.append(Warning(
                level='danger',
                message=(
                    f'{gas_type} {label} at {use_depth:.0f} m: '
                    f'gas density {d:.2f} g/L exceeds the upper limit (6.3 g/L). '
                    f'This gas cannot be safely breathed at this depth — '
                    f'consider a less dense alternative or reducing planned depth.'
                ),
            ))
        elif d > 5.2:
            warnings.append(Warning(
                level='warning',
                message=(
                    f'{gas_type} {label} at {use_depth:.0f} m: '
                    f'gas density {d:.2f} g/L exceeds the recommended limit (5.2 g/L). '
                    f'Increased work of breathing.'
                ),
            ))
    return warnings


def _build_profile_points(profile_points):
    return [
        ProfilePoint(t=pp['t'], d=pp['d'], c=pp['c'], sats=pp['sats'], inert=pp.get('inert', []))
        for pp in profile_points
    ]


def _build_deco_stops(stops):
    return [DecoStop(depth_m=s.depth_m, time_min=s.time_min, runtime_min=s.runtime_min) for s in stops]


def _build_gas_supply(profile, sorted_gases, sorted_volumes, req) -> Optional[List[GasSupplyEntry]]:
    if not any(v['cyl_l'] and v['cyl_bar'] for _, v in sorted_volumes):
        return None
    consumed = _compute_gas_consumption(profile, sorted_gases, req.sac_bottom_lpm, req.sac_deco_lpm)
    supply = []
    for i, (g, v) in enumerate(sorted_volumes):
        entry = GasSupplyEntry(
            o2=round(g.fo2 * 100),
            he=round(g.fhe * 100),
            mod_m=g.mod_m,
            consumed_L=consumed[i],
        )
        if v['cyl_l'] and v['cyl_bar']:
            usable = v['cyl_l'] * max(0.0, v['cyl_bar'] - req.reserve_bar)
            entry.available_L = round(usable)
            entry.pct = round(consumed[i] / usable * 100) if usable > 0 else 100
        supply.append(entry)
    return supply


# ── OC planning path ───────────────────────────────────────────────────────────

def _plan_oc(req, gf_low, gf_high, oc_gases, oc_gas_volumes):
    sorted_gases = sorted(oc_gases, key=lambda g: g.mod_m)
    sorted_volumes = sorted(zip(oc_gases, oc_gas_volumes), key=lambda x: x[0].mod_m)
    available_L = [
        (v['cyl_l'] * max(0.0, v['cyl_bar'] - req.reserve_bar))
        if (v['cyl_l'] and v['cyl_bar']) else math.inf
        for _, v in sorted_volumes
    ]

    bottom_time_actual = req.bottom_time_min
    bottom_time_shortened = False
    gas_infeasible = False
    gas_infeasible_msg = None

    if any(a < math.inf for a in available_L):
        result_bt, shortened = _binary_search_bottom_time(
            planner_fn=lambda bt: plan_oc_dive(
                oc_gases, req.depth_m, bt, gf_low, gf_high,
                desc_rate_mpm=req.desc_rate_mpm,
                asc_rate_deep_mpm=req.asc_rate_deep_mpm,
                asc_rate_shallow_mpm=req.asc_rate_shallow_mpm,
                last_stop_m=req.last_stop_m,
            ),
            depth_m=req.depth_m,
            requested_bt=req.bottom_time_min,
            desc_rate_mpm=req.desc_rate_mpm,
            sorted_gases=sorted_gases,
            available_L=available_L,
            sac_bottom=req.sac_bottom_lpm,
            sac_deco=req.sac_deco_lpm,
        )
        if result_bt is None:
            gas_infeasible = True
            gas_infeasible_msg = _infeasibility_msg(sorted_volumes, req.reserve_bar, req.depth_m, prefix='Gas')
        else:
            bottom_time_actual, bottom_time_shortened = result_bt, shortened

    try:
        profile = plan_oc_dive(
            oc_gases, req.depth_m, bottom_time_actual, gf_low, gf_high,
            desc_rate_mpm=req.desc_rate_mpm,
            asc_rate_deep_mpm=req.asc_rate_deep_mpm,
            asc_rate_shallow_mpm=req.asc_rate_shallow_mpm,
            last_stop_m=req.last_stop_m,
        )
    except Exception as e:
        logging.exception("OC planning error")
        raise HTTPException(status_code=500, detail=str(e))

    bottom_gas_input = max(req.bailout_gases, key=lambda g: g.mod_m)
    density_gl = gas_density(bottom_gas_input.o2, bottom_gas_input.he, req.depth_m)
    warnings: List[Warning] = []

    if gas_infeasible:
        warnings.append(Warning(level='danger', message=gas_infeasible_msg))
    elif bottom_time_shortened:
        warnings.append(Warning(
            level='warning',
            message=(
                f'Bottom time shortened from {req.bottom_time_min:.0f} min to {bottom_time_actual:.0f} min '
                f'— insufficient gas supply for the requested dive time.'
            ),
        ))

    warnings.extend(_gas_warnings(
        req.bailout_gases, req.depth_m,
        first_gas_type='Back gas', other_gas_type='Deco gas',
        skip_first_density=False,
    ))

    tts_min = round(max(0.0, profile.total_time_min - bottom_time_actual), 1)
    oc_cns, oc_otu = _oc_cns_otu(profile, sorted_gases)
    cns_pct = round(oc_cns, 1)
    otu     = round(oc_otu, 1)

    if cns_pct >= req.cns_warn_pct:
        warnings.append(Warning(
            level='warning',
            message=(
                f'CNS O₂ toxicity is {cns_pct:.1f}% — '
                f'exceeds the warning threshold of {req.cns_warn_pct:.0f}%.'
            ),
        ))

    gas_supply = _build_gas_supply(profile, sorted_gases, sorted_volumes, req) if not gas_infeasible else None

    return DivePlannerResponse(
        stops=_build_deco_stops(profile.stops),
        total_time_min=profile.total_time_min,
        warnings=warnings,
        density_analysis=DensityAnalysis(
            density_gl=density_gl,
            exceeded_recommended=density_gl > 5.2,
            exceeded_limit=density_gl > 6.3,
        ),
        profile_points=_build_profile_points(profile.profile_points),
        tissue_saturations=profile.tissue_saturations,
        tts_min=tts_min,
        cns_pct=cns_pct,
        otu=otu,
        bottom_time_actual=bottom_time_actual,
        gas_switches=[GasSwitch(depth_m=gs['depth_m'], label=gs['label']) for gs in profile.gas_switches],
        gas_supply=gas_supply,
        bailout=None,
    )


# ── CCR planning path ──────────────────────────────────────────────────────────

def _plan_ccr(req, gf_low, gf_high, oc_gases, oc_gas_volumes):
    bailout_gf_low  = (req.bailout_gf_low  if req.bailout_gf_low  is not None else req.gf_low)  / 100.0
    bailout_gf_high = (req.bailout_gf_high if req.bailout_gf_high is not None else req.gf_high) / 100.0

    gas = CCRGas(req.diluent_o2, req.diluent_he, req.setpoint)

    bottom_time_actual    = req.bottom_time_min
    bottom_time_shortened = False
    bailout_infeasible    = False
    bailout_infeasible_msg = None

    if oc_gases:
        sorted_gases = sorted(oc_gases, key=lambda g: g.mod_m)
        sorted_volumes = sorted(zip(oc_gases, oc_gas_volumes), key=lambda x: x[0].mod_m)
        available_L = [
            (v['cyl_l'] * max(0.0, v['cyl_bar'] - req.reserve_bar))
            if (v['cyl_l'] and v['cyl_bar']) else math.inf
            for _, v in sorted_volumes
        ]
        if any(a < math.inf for a in available_L):
            result_bt, shortened = _binary_search_bottom_time(
                planner_fn=lambda bt: plan_oc_bailout(
                    ccr_gas=gas,
                    bottom_depth_m=req.depth_m,
                    bottom_time_min=bt,
                    desc_rate_mpm=req.desc_rate_mpm,
                    bailout_gases=oc_gases,
                    gf_low=bailout_gf_low,
                    gf_high=bailout_gf_high,
                    asc_rate_deep_mpm=req.asc_rate_deep_mpm,
                    asc_rate_shallow_mpm=req.asc_rate_shallow_mpm,
                    last_stop_m=req.last_stop_m,
                ),
                depth_m=req.depth_m,
                requested_bt=req.bottom_time_min,
                desc_rate_mpm=req.desc_rate_mpm,
                sorted_gases=sorted_gases,
                available_L=available_L,
                sac_bottom=req.sac_bottom_lpm,
                sac_deco=req.sac_deco_lpm,
            )
            if result_bt is None:
                bailout_infeasible = True
                bailout_infeasible_msg = _infeasibility_msg(sorted_volumes, req.reserve_bar, req.depth_m, prefix='Bailout gas')
            else:
                bottom_time_actual, bottom_time_shortened = result_bt, shortened

    try:
        profile = plan_ccr_dive(
            gas, req.depth_m, bottom_time_actual, gf_low, gf_high,
            desc_rate_mpm=req.desc_rate_mpm,
            asc_rate_deep_mpm=req.asc_rate_deep_mpm,
            asc_rate_shallow_mpm=req.asc_rate_shallow_mpm,
            last_stop_m=req.last_stop_m,
        )
    except Exception as e:
        logging.exception("CCR planning error")
        raise HTTPException(status_code=500, detail=str(e))

    density_gl = gas_density(req.diluent_o2, req.diluent_he, req.depth_m)
    warnings: List[Warning] = []

    diluent_ppo2 = (req.diluent_o2 / 100.0) * (req.depth_m / 10.0 + 1.0)
    if diluent_ppo2 > req.setpoint + 0.05:
        level = 'danger' if diluent_ppo2 > 1.6 else 'warning'
        warnings.append(Warning(
            level=level,
            message=(
                f'Diluent ppO₂ at {req.depth_m:.0f} m is {diluent_ppo2:.2f} bar — '
                f'exceeds setpoint ({req.setpoint:.2f} bar). '
                f'The CCR cannot reduce ppO₂ below the diluent floor; '
                f'actual ppO₂ at depth will be {diluent_ppo2:.2f} bar.'
            ),
        ))
    if density_gl > 6.3:
        warnings.append(Warning(
            level='danger',
            message=(
                f'Gas density exceeds the BSAC upper limit '
                f'({density_gl:.2f} g/L — limit 6.3 g/L). '
                f'This diluent is not safe to breathe at this depth.'
            ),
        ))
    elif density_gl > 5.2:
        warnings.append(Warning(
            level='warning',
            message=(
                f'Gas density exceeds the BSAC recommended limit '
                f'({density_gl:.2f} g/L — recommended ≤5.2 g/L). '
                f'Increased work of breathing and CO₂ retention risk.'
            ),
        ))

    if bailout_infeasible:
        warnings.append(Warning(level='danger', message=bailout_infeasible_msg))
    elif bottom_time_shortened:
        warnings.append(Warning(
            level='warning',
            message=(
                f'Bottom time shortened from {req.bottom_time_min:.0f} min to {bottom_time_actual:.0f} min '
                f'— insufficient bailout gas supply for the requested dive time.'
            ),
        ))

    tts_min   = round(max(0.0, profile.total_time_min - bottom_time_actual), 1)
    _eff_ppo2 = max(req.setpoint, diluent_ppo2)
    cns_pct   = round(_cns_rate(_eff_ppo2) * bottom_time_actual + _cns_rate(req.setpoint) * tts_min, 1)
    otu       = round(_otu_rate(_eff_ppo2) * bottom_time_actual + _otu_rate(req.setpoint) * tts_min, 1)

    if cns_pct >= req.cns_warn_pct:
        warnings.append(Warning(
            level='warning',
            message=(
                f'CNS O₂ toxicity is {cns_pct:.1f}% — '
                f'exceeds the warning threshold of {req.cns_warn_pct:.0f}%.'
            ),
        ))

    if oc_gases:
        warnings.extend(_gas_warnings(
            req.bailout_gases, req.depth_m,
            first_gas_type='Bailout gas', other_gas_type='Bailout gas',
            skip_first_density=False,
        ))

    bailout_plan: Optional[BailoutPlan] = None
    if oc_gases and not bailout_infeasible:
        try:
            sorted_gases_asc  = sorted(oc_gases, key=lambda g: g.mod_m)
            sorted_oc_volumes = sorted(zip(oc_gases, oc_gas_volumes), key=lambda x: x[0].mod_m)
            bailout = plan_oc_bailout(
                ccr_gas=gas,
                bottom_depth_m=req.depth_m,
                bottom_time_min=bottom_time_actual,
                desc_rate_mpm=req.desc_rate_mpm,
                bailout_gases=oc_gases,
                gf_low=bailout_gf_low,
                gf_high=bailout_gf_high,
                asc_rate_deep_mpm=req.asc_rate_deep_mpm,
                asc_rate_shallow_mpm=req.asc_rate_shallow_mpm,
                last_stop_m=req.last_stop_m,
            )
            oc_cns, oc_otu = _oc_cns_otu(bailout, sorted_gases_asc)
            loop_cns = _cns_rate(req.setpoint) * bottom_time_actual
            loop_otu = _otu_rate(req.setpoint) * bottom_time_actual
            bailout_cns = round(loop_cns + oc_cns, 1)
            bailout_otu = round(loop_otu + oc_otu, 1)

            bailout_supply = _build_gas_supply(bailout, sorted_gases_asc, sorted_oc_volumes, req)

            bailout_plan = BailoutPlan(
                stops=_build_deco_stops(bailout.stops),
                total_time_min=bailout.total_time_min,
                tts_min=round(max(0.0, bailout.total_time_min - bottom_time_actual), 1),
                cns_pct=bailout_cns,
                otu=bailout_otu,
                gas_switches=[
                    GasSwitch(depth_m=gs['depth_m'], label=gs['label'])
                    for gs in bailout.gas_switches
                ],
                profile_points=_build_profile_points(bailout.profile_points),
                tissue_saturations=bailout.tissue_saturations,
                gas_supply=bailout_supply,
            )
        except Exception as e:
            logging.exception("Bailout planning error")
            warnings.append(Warning(level='warning', message=f'Bailout plan could not be computed: {e}'))

    return DivePlannerResponse(
        stops=_build_deco_stops(profile.stops),
        total_time_min=profile.total_time_min,
        warnings=warnings,
        density_analysis=DensityAnalysis(
            density_gl=density_gl,
            exceeded_recommended=density_gl > 5.2,
            exceeded_limit=density_gl > 6.3,
        ),
        profile_points=_build_profile_points(profile.profile_points),
        tissue_saturations=profile.tissue_saturations,
        tts_min=tts_min,
        cns_pct=cns_pct,
        otu=otu,
        bottom_time_actual=bottom_time_actual,
        bailout=bailout_plan,
    )
