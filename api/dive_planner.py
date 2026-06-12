import logging
import math
from typing import List, Optional, Tuple

from fastapi import APIRouter, HTTPException

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
from api.dive_planner_models import (
    BailoutPlan,
    DecoStop,
    DensityAnalysis,
    DivePlannerRequest,
    DivePlannerResponse,
    GasSupplyEntry,
    GasSwitch,
    ProfilePoint,
    Warning,
)

router = APIRouter()


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


def _density_warnings(description: str, depth_m: float, d: float) -> List[Warning]:
    if d > 6.3:
        return [Warning(
            level='danger',
            message=(
                f'{description} at {depth_m:.0f} m: '
                f'gas density {d:.2f} g/L exceeds the upper limit (6.3 g/L). '
                f'This gas cannot be safely breathed at this depth — '
                f'consider a less dense alternative or reducing planned depth.'
            ),
        )]
    if d > 5.2:
        return [Warning(
            level='warning',
            message=(
                f'{description} at {depth_m:.0f} m: '
                f'gas density {d:.2f} g/L exceeds the recommended limit (5.2 g/L). '
                f'Increased work of breathing and CO₂ retention risk.'
            ),
        )]
    return []


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
        warnings.extend(_density_warnings(f'{gas_type} {label}', use_depth, d))
    return warnings


def _build_plan_warnings(
    req,
    mode: str,
    cns_pct: float,
    gas_infeasible: bool,
    gas_infeasible_msg,
    bottom_time_shortened: bool,
    bottom_time_actual: float,
    diluent_ppo2: float = None,  # CCR only
    density_gl: float = None,    # CCR only
) -> List[Warning]:
    warnings: List[Warning] = []

    if mode == 'ccr':
        diluent_label = OpenCircuitGas(req.diluent_o2, req.diluent_he, req.depth_m).label

        floor_fires = diluent_ppo2 > req.setpoint + 0.05 and diluent_ppo2 <= 1.6
        if floor_fires:
            warnings.append(Warning(
                level='warning',
                message=(
                    f'Diluent ppO₂ at {req.depth_m:.0f} m is {diluent_ppo2:.2f} bar — '
                    f'exceeds setpoint ({req.setpoint:.2f} bar). '
                    f'The CCR cannot reduce ppO₂ below the diluent floor; '
                    f'actual ppO₂ at depth will be {diluent_ppo2:.2f} bar.'
                ),
            ))
        if diluent_ppo2 > 1.6:
            warnings.append(Warning(
                level='danger',
                message=(
                    f'Diluent {diluent_label} at {req.depth_m:.0f} m: '
                    f'ppO₂ {diluent_ppo2:.2f} bar exceeds the absolute maximum (1.6 bar). '
                    f'Unsafe to flush the loop or bail out on this diluent at this depth — '
                    f'CNS O₂ toxicity risk.'
                ),
            ))
        elif not floor_fires and diluent_ppo2 > 1.4:
            warnings.append(Warning(
                level='warning',
                message=(
                    f'Diluent {diluent_label} at {req.depth_m:.0f} m: '
                    f'ppO₂ {diluent_ppo2:.2f} bar exceeds the 1.4 bar working limit. '
                    f'Safe in normal CCR operation but approach diluent flushes and OC bailout with caution.'
                ),
            ))
        warnings.extend(_density_warnings(f'Diluent {diluent_label}', req.depth_m, density_gl))

    supply_phrase = 'insufficient bailout gas supply' if mode == 'ccr' else 'insufficient gas supply'
    if gas_infeasible:
        warnings.append(Warning(level='danger', message=gas_infeasible_msg))
    elif bottom_time_shortened:
        warnings.append(Warning(
            level='warning',
            message=(
                f'Bottom time shortened from {req.bottom_time_min:.0f} min to {bottom_time_actual:.0f} min '
                f'— {supply_phrase} for the requested dive time.'
            ),
        ))

    if req.bailout_gases:
        first_gas_type = 'Bailout gas' if mode == 'ccr' else 'Back gas'
        other_gas_type = 'Bailout gas' if mode == 'ccr' else 'Deco gas'
        warnings.extend(_gas_warnings(
            req.bailout_gases, req.depth_m,
            first_gas_type=first_gas_type,
            other_gas_type=other_gas_type,
            skip_first_density=False,
        ))

    if cns_pct >= req.cns_warn_pct:
        warnings.append(Warning(
            level='warning',
            message=f'CNS O₂ toxicity is {cns_pct:.1f}% — exceeds the warning threshold of {req.cns_warn_pct:.0f}%.',
        ))

    return warnings


def _build_profile_points(profile_points) -> List[ProfilePoint]:
    return [
        ProfilePoint(t=pp['t'], d=pp['d'], c=pp['c'], sats=pp['sats'], inert=pp.get('inert', []))
        for pp in profile_points
    ]


def _build_deco_stops(stops) -> List[DecoStop]:
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


def _prepare_oc_gas_supply(oc_gases, oc_gas_volumes, reserve_bar):
    sorted_gases = sorted(oc_gases, key=lambda g: g.mod_m)
    sorted_volumes = sorted(zip(oc_gases, oc_gas_volumes), key=lambda x: x[0].mod_m)
    available_L = [
        (v['cyl_l'] * max(0.0, v['cyl_bar'] - reserve_bar))
        if (v['cyl_l'] and v['cyl_bar']) else math.inf
        for _, v in sorted_volumes
    ]
    return sorted_gases, sorted_volumes, available_L


def _run_gas_constrained_bottom_time(planner_fn, req, sorted_gases, sorted_volumes, available_L, prefix='Gas'):
    bottom_time_actual    = req.bottom_time_min
    bottom_time_shortened = False
    infeasible            = False
    infeasible_msg        = None

    if any(a < math.inf for a in available_L):
        result_bt, shortened = _binary_search_bottom_time(
            planner_fn=planner_fn,
            depth_m=req.depth_m,
            requested_bt=req.bottom_time_min,
            desc_rate_mpm=req.desc_rate_mpm,
            sorted_gases=sorted_gases,
            available_L=available_L,
            sac_bottom=req.sac_bottom_lpm,
            sac_deco=req.sac_deco_lpm,
        )
        if result_bt is None:
            infeasible = True
            infeasible_msg = _infeasibility_msg(sorted_volumes, req.reserve_bar, req.depth_m, prefix=prefix)
        else:
            bottom_time_actual, bottom_time_shortened = result_bt, shortened

    return bottom_time_actual, bottom_time_shortened, infeasible, infeasible_msg


def _build_bailout_plan(
    gas, req, sorted_gases, sorted_volumes, bottom_time_actual, bailout_gf_low, bailout_gf_high,
) -> Tuple[Optional[BailoutPlan], Optional[str]]:
    try:
        bailout = plan_oc_bailout(
            ccr_gas=gas,
            bottom_depth_m=req.depth_m,
            bottom_time_min=bottom_time_actual,
            desc_rate_mpm=req.desc_rate_mpm,
            bailout_gases=sorted_gases,
            gf_low=bailout_gf_low,
            gf_high=bailout_gf_high,
            asc_rate_deep_mpm=req.asc_rate_deep_mpm,
            asc_rate_shallow_mpm=req.asc_rate_shallow_mpm,
            last_stop_m=req.last_stop_m,
        )
        oc_cns, oc_otu = _oc_cns_otu(bailout, sorted_gases)
        loop_cns = _cns_rate(req.setpoint) * bottom_time_actual
        loop_otu = _otu_rate(req.setpoint) * bottom_time_actual
        bailout_supply = _build_gas_supply(bailout, sorted_gases, sorted_volumes, req)
        return BailoutPlan(
            stops=_build_deco_stops(bailout.stops),
            total_time_min=bailout.total_time_min,
            tts_min=round(max(0.0, bailout.total_time_min - bottom_time_actual), 1),
            cns_pct=round(loop_cns + oc_cns, 1),
            otu=round(loop_otu + oc_otu, 1),
            gas_switches=[GasSwitch(depth_m=gs['depth_m'], label=gs['label']) for gs in bailout.gas_switches],
            profile_points=_build_profile_points(bailout.profile_points),
            tissue_saturations=bailout.tissue_saturations,
            gas_supply=bailout_supply,
        ), None
    except Exception as e:
        logging.exception("Bailout planning error")
        return None, str(e)


# ── OC planning path ───────────────────────────────────────────────────────────

def _plan_oc(req, gf_low, gf_high, oc_gases, oc_gas_volumes):
    sorted_gases, sorted_volumes, available_L = _prepare_oc_gas_supply(oc_gases, oc_gas_volumes, req.reserve_bar)

    bottom_time_actual, bottom_time_shortened, gas_infeasible, gas_infeasible_msg = (
        _run_gas_constrained_bottom_time(
            planner_fn=lambda bt: plan_oc_dive(
                oc_gases, req.depth_m, bt, gf_low, gf_high,
                desc_rate_mpm=req.desc_rate_mpm,
                asc_rate_deep_mpm=req.asc_rate_deep_mpm,
                asc_rate_shallow_mpm=req.asc_rate_shallow_mpm,
                last_stop_m=req.last_stop_m,
            ),
            req=req,
            sorted_gases=sorted_gases,
            sorted_volumes=sorted_volumes,
            available_L=available_L,
            prefix='Gas',
        )
    )

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

    tts_min = round(max(0.0, profile.total_time_min - bottom_time_actual), 1)
    oc_cns, oc_otu = _oc_cns_otu(profile, sorted_gases)
    cns_pct = round(oc_cns, 1)
    otu     = round(oc_otu, 1)

    warnings = _build_plan_warnings(
        req, 'oc', cns_pct,
        gas_infeasible, gas_infeasible_msg,
        bottom_time_shortened, bottom_time_actual,
    )

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
        sorted_gases, sorted_volumes, available_L = _prepare_oc_gas_supply(oc_gases, oc_gas_volumes, req.reserve_bar)
        bottom_time_actual, bottom_time_shortened, bailout_infeasible, bailout_infeasible_msg = (
            _run_gas_constrained_bottom_time(
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
                req=req,
                sorted_gases=sorted_gases,
                sorted_volumes=sorted_volumes,
                available_L=available_L,
                prefix='Bailout gas',
            )
        )

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

    density_gl   = gas_density(req.diluent_o2, req.diluent_he, req.depth_m)
    diluent_ppo2 = (req.diluent_o2 / 100.0) * (req.depth_m / 10.0 + 1.0)

    tts_min   = round(max(0.0, profile.total_time_min - bottom_time_actual), 1)
    _eff_ppo2 = max(req.setpoint, diluent_ppo2)
    cns_pct   = round(_cns_rate(_eff_ppo2) * bottom_time_actual + _cns_rate(req.setpoint) * tts_min, 1)
    otu       = round(_otu_rate(_eff_ppo2) * bottom_time_actual + _otu_rate(req.setpoint) * tts_min, 1)

    warnings = _build_plan_warnings(
        req, 'ccr', cns_pct,
        bailout_infeasible, bailout_infeasible_msg,
        bottom_time_shortened, bottom_time_actual,
        diluent_ppo2=diluent_ppo2,
        density_gl=density_gl,
    )

    bailout_plan: Optional[BailoutPlan] = None
    if oc_gases and not bailout_infeasible:
        bailout_plan, bailout_error = _build_bailout_plan(
            gas, req, sorted_gases, sorted_volumes, bottom_time_actual, bailout_gf_low, bailout_gf_high,
        )
        if bailout_error:
            warnings.append(Warning(level='warning', message=f'Bailout plan could not be computed: {bailout_error}'))

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
