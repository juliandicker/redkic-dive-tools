import logging
import math
from typing import List, Literal, Optional

import azure.functions as func
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, model_validator

from gas_blender import Gas, TrimixBlend, density_depth, end_depth, gas_density, mod_m
from planner.dive import plan_ccr_dive, plan_oc_bailout
from planner.gas import CCRGas, OpenCircuitGas
from DivePlanner import (
    _cns_rate,
    _compute_gas_consumption,
    _gas_label,
    _max_bottom_time_within_gas_supply,
    _oc_cns_otu,
    _otu_rate,
)

# ── Shared models ──────────────────────────────────────────────────────────────

class GasComposition(BaseModel):
    bar: float
    o2: float
    he: float


class BlendStep(BaseModel):
    name: str
    start_gas: GasComposition
    result_gas: GasComposition


class GasAnalysis(BaseModel):
    mod_1_2: float = Field(description="MOD at ppO₂ 1.2 bar (m)")
    mod_1_4: float = Field(description="MOD at ppO₂ 1.4 bar (m)")
    mod_1_6: float = Field(description="MOD at ppO₂ 1.6 bar (m)")
    density_max_depth: float = Field(description="Depth at BSAC recommended density limit 5.2 g/L (m)")
    density_limit_depth: float = Field(description="Depth at BSAC upper density limit 6.3 g/L (m)")
    end_30_depth: float = Field(description="Depth where END reaches 30 m (m)")
    end_40_depth: float = Field(description="Depth where END reaches 40 m (m)")


# ── TrimixBlend ────────────────────────────────────────────────────────────────

class TrimixBlendRequest(BaseModel):
    """Cylinder fill parameters for a trimix top-up sequence."""
    start_bar: float = Field(gt=0, description="Starting cylinder pressure (bar)")
    start_o2: float = Field(ge=0, le=100, description="Starting O₂ (%)")
    start_he: float = Field(ge=0, le=100, description="Starting He (%)")
    finish_bar: float = Field(gt=0, description="Target cylinder pressure (bar)")
    finish_o2: float = Field(ge=0, le=100, description="Target O₂ (%)")
    finish_he: float = Field(ge=0, le=100, description="Target He (%)")
    helium_bar: float = Field(default=250.0, gt=0, description="Helium source pressure (bar)")
    helium_o2: float = Field(default=0.0, ge=0, le=100, description="Helium source O₂ (%)")
    helium_he: float = Field(default=100.0, ge=0, le=100, description="Helium source He (%)")


class TrimixBlendResponse(BaseModel):
    """Fill steps and gas analysis for the requested blend."""
    start_gas: GasComposition
    finish_gas: GasComposition
    he_gas: GasComposition
    steps: List[BlendStep]
    analysis: GasAnalysis


# ── DivePlanner ────────────────────────────────────────────────────────────────

class BailoutGasInput(BaseModel):
    o2: float = Field(ge=1, le=100, description="O₂ (%)")
    he: float = Field(default=0.0, ge=0, le=100, description="He (%)")
    mod_m: float = Field(gt=0, description="Maximum Operating Depth (m)")
    ppo2_limit: float = Field(default=1.4, ge=1.0, le=1.6, description="ppO₂ working limit used to set MOD (bar)")
    cyl_l: Optional[float] = Field(default=None, gt=0, description="Cylinder water volume (L)")
    cyl_bar: Optional[float] = Field(default=None, gt=0, description="Fill pressure (bar)")


class DivePlannerRequest(BaseModel):
    """CCR decompression planning parameters (Bühlmann ZHL-16C with gradient factors)."""
    diluent_o2: float = Field(ge=1, le=100, description="Diluent O₂ (%)")
    diluent_he: float = Field(ge=0, le=100, description="Diluent He (%)")
    setpoint: float = Field(gt=0, le=2.0, description="CCR setpoint (bar ppO₂)")
    depth_m: float = Field(gt=0, description="Bottom depth (m)")
    bottom_time_min: float = Field(gt=0, description="Bottom time (min)")
    gf_low: float = Field(default=60.0, ge=1.0, le=100.0, description="GF Low (%)")
    gf_high: float = Field(default=80.0, ge=1.0, le=100.0, description="GF High (%)")
    desc_rate_mpm: float = Field(default=20.0, ge=1.0, le=50.0, description="Descent rate (m/min)")
    asc_rate_deep_mpm: float = Field(default=9.0, ge=1.0, le=30.0, description="Ascent rate above 6 m (m/min)")
    asc_rate_shallow_mpm: float = Field(default=3.0, ge=1.0, le=30.0, description="Ascent rate ≤6 m (m/min)")
    last_stop_m: Literal[3, 4, 5, 6, 9] = Field(default=3, description="Shallowest deco stop depth (m)")
    cns_warn_pct: float = Field(default=80.0, ge=50.0, le=100.0, description="CNS O₂ toxicity warning threshold (%)")
    bailout_gf_low: Optional[float] = Field(default=None, ge=1.0, le=100.0, description="Bailout GF Low (%; defaults to gf_low)")
    bailout_gf_high: Optional[float] = Field(default=None, ge=1.0, le=100.0, description="Bailout GF High (%; defaults to gf_high)")
    bailout_gases: List[BailoutGasInput] = Field(default=[], description="OC bailout gases")
    sac_bottom_lpm: float = Field(default=25.0, ge=2.0, le=200.0, description="Bottom SAC / RMV (L/min)")
    sac_deco_lpm: float = Field(default=15.0, ge=2.0, le=200.0, description="Deco SAC / RMV (L/min)")
    reserve_bar: float = Field(default=50.0, ge=0.0, le=300.0, description="Cylinder reserve (bar)")

    @model_validator(mode='after')
    def check_diluent(self):
        if not (0 < self.diluent_o2 + self.diluent_he <= 100):
            raise ValueError("Invalid diluent composition.")
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
    """CCR decompression schedule with toxicity data and optional OC bailout plan."""
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
    bailout: Optional[BailoutPlan] = None


# ── FastAPI app ────────────────────────────────────────────────────────────────

fastapi_app = FastAPI(
    title="GasBlender API",
    description=(
        "Technical diving tools: trimix fill-sequence calculator and "
        "CCR decompression planner (Bühlmann ZHL-16C with gradient factors)."
    ),
    version="1.0.0",
    contact={"name": "GasBlender", "url": "https://gasblender.redkic.co.uk"},
)


@fastapi_app.exception_handler(HTTPException)
async def _http_exc(request, exc):
    return PlainTextResponse(str(exc.detail), status_code=exc.status_code)


@fastapi_app.exception_handler(RequestValidationError)
async def _validation_exc(request, exc):
    errors = "; ".join(
        f"{' > '.join(str(loc) for loc in e['loc'])}: {e['msg']}"
        for e in exc.errors()
    )
    return PlainTextResponse(f"Validation error: {errors}", status_code=400)


# ── Endpoints ──────────────────────────────────────────────────────────────────

@fastapi_app.post(
    "/api/TrimixBlend",
    response_model=TrimixBlendResponse,
    summary="Trimix fill sequence",
    description=(
        "Computes the helium → O₂ → air fill steps required to reach the target "
        "trimix from the starting cylinder contents."
    ),
    responses={400: {"description": "Invalid inputs or infeasible blend", "content": {"text/plain": {}}}},
)
def trimix_blend(req: TrimixBlendRequest) -> TrimixBlendResponse:
    logging.info("TrimixBlend request received.")
    start_gas  = Gas(req.start_bar,  req.start_o2,  req.start_he)
    finish_gas = Gas(req.finish_bar, req.finish_o2, req.finish_he)
    helium_gas = Gas(req.helium_bar, req.helium_o2, req.helium_he)
    try:
        result = TrimixBlend(start_gas, finish_gas, helium_gas)
    except (ValueError, ZeroDivisionError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return TrimixBlendResponse(
        start_gas=GasComposition(bar=result.start_gas.bar, o2=result.start_gas.o2, he=result.start_gas.he),
        finish_gas=GasComposition(bar=result.finish_gas.bar, o2=result.finish_gas.o2, he=result.finish_gas.he),
        he_gas=GasComposition(bar=result.he_gas.bar, o2=result.he_gas.o2, he=result.he_gas.he),
        steps=[
            BlendStep(
                name=s.name,
                start_gas=GasComposition(bar=s.start_gas.bar, o2=s.start_gas.o2, he=s.start_gas.he),
                result_gas=GasComposition(bar=s.result_gas.bar, o2=s.result_gas.o2, he=s.result_gas.he),
            )
            for s in result.steps
        ],
        analysis=GasAnalysis(
            mod_1_2=mod_m(req.finish_o2, 1.2),
            mod_1_4=mod_m(req.finish_o2, 1.4),
            mod_1_6=mod_m(req.finish_o2, 1.6),
            density_max_depth=density_depth(req.finish_o2, req.finish_he, 5.2),
            density_limit_depth=density_depth(req.finish_o2, req.finish_he, 6.3),
            end_30_depth=end_depth(req.finish_o2, req.finish_he, 30),
            end_40_depth=end_depth(req.finish_o2, req.finish_he, 40),
        ),
    )


@fastapi_app.post(
    "/api/DivePlanner",
    response_model=DivePlannerResponse,
    summary="CCR decompression plan",
    description=(
        "Plans a closed-circuit rebreather (CCR) decompression dive using the Bühlmann ZHL-16C "
        "algorithm with gradient factors. Returns the deco schedule, tissue saturations, "
        "CNS/OTU toxicity data, gas density analysis, and an optional OC bailout plan."
    ),
    responses={400: {"description": "Invalid inputs", "content": {"text/plain": {}}}},
)
def dive_planner(req: DivePlannerRequest) -> DivePlannerResponse:
    logging.info("DivePlanner request received.")

    gf_low  = req.gf_low  / 100.0
    gf_high = req.gf_high / 100.0
    bailout_gf_low  = (req.bailout_gf_low  if req.bailout_gf_low  is not None else req.gf_low)  / 100.0
    bailout_gf_high = (req.bailout_gf_high if req.bailout_gf_high is not None else req.gf_high) / 100.0

    gas = CCRGas(req.diluent_o2, req.diluent_he, req.setpoint)

    oc_gases: List[OpenCircuitGas] = []
    oc_gas_volumes = []
    for g in req.bailout_gases:
        if not (0 < g.o2 + g.he <= 100):
            raise HTTPException(status_code=400, detail=f"Invalid composition for bailout gas O₂={g.o2} He={g.he}.")
        oc_gases.append(OpenCircuitGas(g.o2, g.he, g.mod_m))
        oc_gas_volumes.append({'cyl_l': g.cyl_l, 'cyl_bar': g.cyl_bar})

    bottom_time_actual   = req.bottom_time_min
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
            result_bt, shortened = _max_bottom_time_within_gas_supply(
                ccr_gas=gas,
                depth_m=req.depth_m,
                requested_bt=req.bottom_time_min,
                desc_rate_mpm=req.desc_rate_mpm,
                oc_gases=oc_gases,
                sorted_gases=sorted_gases,
                available_L=available_L,
                gf_low=bailout_gf_low,
                gf_high=bailout_gf_high,
                asc_rate_deep=req.asc_rate_deep_mpm,
                asc_rate_shallow=req.asc_rate_shallow_mpm,
                last_stop_m=req.last_stop_m,
                sac_bottom=req.sac_bottom_lpm,
                sac_deco=req.sac_deco_lpm,
            )
            if result_bt is None:
                bailout_infeasible = True
                empty_gases = [
                    _gas_label(g) for g, v in sorted_volumes
                    if v['cyl_l'] and v['cyl_bar']
                    and v['cyl_l'] * max(0.0, v['cyl_bar'] - req.reserve_bar) == 0
                ]
                if empty_gases:
                    bailout_infeasible_msg = (
                        f"Bailout gas supply error: {', '.join(empty_gases)} "
                        f"{'has' if len(empty_gases) == 1 else 'have'} no usable gas after "
                        f"deducting the {req.reserve_bar:.0f} bar reserve. "
                        f"Increase cylinder pressure or reduce the tank reserve setting."
                    )
                else:
                    bailout_infeasible_msg = (
                        f"Bailout gas supply is insufficient even for the minimum possible dive time "
                        f"at {req.depth_m:.0f} m. Increase cylinder sizes, pressure, or reduce the "
                        f"{req.reserve_bar:.0f} bar reserve."
                    )
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
    if diluent_ppo2 > req.setpoint:
        warnings.append(Warning(
            level='danger',
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

    tts_min = round(max(0.0, profile.total_time_min - bottom_time_actual), 1)
    cns_pct = round(_cns_rate(req.setpoint) * profile.total_time_min, 1)
    otu     = round(_otu_rate(req.setpoint) * profile.total_time_min, 1)

    if cns_pct >= req.cns_warn_pct:
        warnings.append(Warning(
            level='warning',
            message=(
                f'CNS O₂ toxicity is {cns_pct:.1f}% — '
                f'exceeds the warning threshold of {req.cns_warn_pct:.0f}%.'
            ),
        ))

    if oc_gases:
        for i, bg in enumerate(sorted(req.bailout_gases, key=lambda g: g.mod_m, reverse=True)):
            use_depth = req.depth_m if i == 0 else bg.mod_m
            fo2   = bg.o2 / 100.0
            d     = gas_density(bg.o2, bg.he, use_depth)
            label = _gas_label(OpenCircuitGas(bg.o2, bg.he, bg.mod_m))
            ppo2  = fo2 * (use_depth / 10.0 + 1.0)
            if ppo2 > 1.6:
                warnings.append(Warning(
                    level='danger',
                    message=(
                        f'Bailout gas {label} at {use_depth:.0f} m: '
                        f'ppO₂ {ppo2:.2f} bar exceeds the absolute maximum (1.6 bar). '
                        f'This gas cannot be safely breathed at this depth.'
                    ),
                ))
            elif ppo2 > bg.ppo2_limit:
                warnings.append(Warning(
                    level='warning',
                    message=(
                        f'Bailout gas {label} at {use_depth:.0f} m: '
                        f'ppO₂ {ppo2:.2f} bar exceeds the working limit ({bg.ppo2_limit:.1f} bar). '
                        f'Consider a lower O₂ fraction or shallower planned depth.'
                    ),
                ))
            if d > 6.3:
                warnings.append(Warning(
                    level='danger',
                    message=(
                        f'Bailout gas {label} at {use_depth:.0f} m: '
                        f'gas density {d:.2f} g/L exceeds the upper limit (6.3 g/L). '
                        f'This gas cannot be safely breathed at this depth — '
                        f'consider a less dense alternative or reducing planned depth.'
                    ),
                ))
            elif d > 5.2:
                warnings.append(Warning(
                    level='warning',
                    message=(
                        f'Bailout gas {label} at {use_depth:.0f} m: '
                        f'gas density {d:.2f} g/L exceeds the recommended limit (5.2 g/L). '
                        f'Increased work of breathing at bailout depth.'
                    ),
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
            # Add CCR loop exposure accumulated before bailout (descent + bottom)
            loop_cns = _cns_rate(req.setpoint) * bottom_time_actual
            loop_otu = _otu_rate(req.setpoint) * bottom_time_actual
            bailout_cns = round(loop_cns + oc_cns, 1)
            bailout_otu = round(loop_otu + oc_otu, 1)

            gas_supply: Optional[List[GasSupplyEntry]] = None
            if any(v['cyl_l'] and v['cyl_bar'] for _, v in sorted_oc_volumes):
                consumed = _compute_gas_consumption(
                    bailout, sorted_gases_asc, req.sac_bottom_lpm, req.sac_deco_lpm
                )
                gas_supply = []
                for i, (g, v) in enumerate(sorted_oc_volumes):
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
                    gas_supply.append(entry)

            bailout_plan = BailoutPlan(
                stops=[
                    DecoStop(depth_m=s.depth_m, time_min=s.time_min, runtime_min=s.runtime_min)
                    for s in bailout.stops
                ],
                total_time_min=bailout.total_time_min,
                tts_min=round(bailout.total_time_min, 1),
                cns_pct=bailout_cns,
                otu=bailout_otu,
                gas_switches=[
                    GasSwitch(depth_m=gs['depth_m'], label=gs['label'])
                    for gs in bailout.gas_switches
                ],
                profile_points=[
                    ProfilePoint(t=pp['t'], d=pp['d'], c=pp['c'], sats=pp['sats'])
                    for pp in bailout.profile_points
                ],
                tissue_saturations=bailout.tissue_saturations,
                gas_supply=gas_supply,
            )
        except Exception as e:
            logging.exception("Bailout planning error")
            warnings.append(Warning(level='warning', message=f'Bailout plan could not be computed: {e}'))

    return DivePlannerResponse(
        stops=[
            DecoStop(depth_m=s.depth_m, time_min=s.time_min, runtime_min=s.runtime_min)
            for s in profile.stops
        ],
        total_time_min=profile.total_time_min,
        warnings=warnings,
        density_analysis=DensityAnalysis(
            density_gl=density_gl,
            exceeded_recommended=density_gl > 5.2,
            exceeded_limit=density_gl > 6.3,
        ),
        profile_points=[
            ProfilePoint(t=pp['t'], d=pp['d'], c=pp['c'], sats=pp['sats'])
            for pp in profile.profile_points
        ],
        tissue_saturations=profile.tissue_saturations,
        tts_min=tts_min,
        cns_pct=cns_pct,
        otu=otu,
        bottom_time_actual=bottom_time_actual,
        bailout=bailout_plan,
    )


# ── Azure Functions ASGI wrapper ───────────────────────────────────────────────

app = func.AsgiFunctionApp(app=fastapi_app, http_auth_level=func.AuthLevel.ANONYMOUS)
