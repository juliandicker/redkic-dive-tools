import logging
import math
from typing import List, Optional, Tuple

from fastapi import APIRouter, HTTPException

from gas_blender import gas_density
from planner.dive import plan_ccr_dive, plan_oc_bailout, plan_oc_dive
from planner.gas import CCRGas, OpenCircuitGas
from DivePlanner import (
    _binary_search_bottom_time,
    _cns_rate,
    _oc_cns_otu,
    _otu_rate,
)
from api.dive_planner_models import (
    BailoutPlan,
    DensityAnalysis,
    DivePlannerRequest,
    DivePlannerResponse,
    GasSwitch,
    Warning,
)
from api.dive_planner_warnings import PlanWarnings
from api.dive_planner_builders import build_deco_stops, build_gas_supply, build_profile_points

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


# ── Gas supply helpers ─────────────────────────────────────────────────────────

def _prepare_oc_gas_supply(oc_gases, oc_gas_volumes, reserve_bar):
    sorted_gases = sorted(oc_gases, key=lambda g: g.mod_m)
    sorted_volumes = sorted(zip(oc_gases, oc_gas_volumes), key=lambda x: x[0].mod_m)
    available_L = [
        (v['cyl_l'] * max(0.0, v['cyl_bar'] - reserve_bar))
        if (v['cyl_l'] and v['cyl_bar']) else math.inf
        for _, v in sorted_volumes
    ]
    return sorted_gases, sorted_volumes, available_L


def _run_gas_constrained_bottom_time(planner_fn, req, sorted_gases, available_L):
    bottom_time_actual    = req.bottom_time_min
    bottom_time_shortened = False
    infeasible            = False

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
        else:
            bottom_time_actual, bottom_time_shortened = result_bt, shortened

    return bottom_time_actual, bottom_time_shortened, infeasible


# ── Bailout plan ───────────────────────────────────────────────────────────────

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
        return BailoutPlan(
            stops=build_deco_stops(bailout.stops),
            total_time_min=bailout.total_time_min,
            tts_min=round(bailout.total_time_min, 1),
            cns_pct=round(loop_cns + oc_cns, 1),
            otu=round(loop_otu + oc_otu, 1),
            gas_switches=[GasSwitch(depth_m=gs['depth_m'], label=gs['label']) for gs in bailout.gas_switches],
            profile_points=build_profile_points(bailout.profile_points),
            tissue_saturations=bailout.tissue_saturations,
            gas_supply=build_gas_supply(bailout, sorted_gases, sorted_volumes, req),
        ), None
    except Exception as e:
        logging.exception("Bailout planning error")
        return None, str(e)


# ── OC planning path ───────────────────────────────────────────────────────────

def _plan_oc(req, gf_low, gf_high, oc_gases, oc_gas_volumes):
    sorted_gases, sorted_volumes, available_L = _prepare_oc_gas_supply(oc_gases, oc_gas_volumes, req.reserve_bar)

    bottom_time_actual, bottom_time_shortened, gas_infeasible = _run_gas_constrained_bottom_time(
        planner_fn=lambda bt: plan_oc_dive(
            oc_gases, req.depth_m, bt, gf_low, gf_high,
            desc_rate_mpm=req.desc_rate_mpm,
            asc_rate_deep_mpm=req.asc_rate_deep_mpm,
            asc_rate_shallow_mpm=req.asc_rate_shallow_mpm,
            last_stop_m=req.last_stop_m,
        ),
        req=req,
        sorted_gases=sorted_gases,
        available_L=available_L,
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

    w = PlanWarnings(req, 'oc')
    w.add_supply(gas_infeasible, bottom_time_shortened, bottom_time_actual, sorted_volumes)
    w.add_oc_gases()
    w.add_cns(cns_pct)

    return DivePlannerResponse(
        stops=build_deco_stops(profile.stops),
        total_time_min=profile.total_time_min,
        warnings=w.items,
        density_analysis=DensityAnalysis(
            density_gl=density_gl,
            exceeded_recommended=density_gl > 5.2,
            exceeded_limit=density_gl > 6.3,
        ),
        profile_points=build_profile_points(profile.profile_points),
        tissue_saturations=profile.tissue_saturations,
        tts_min=tts_min,
        cns_pct=cns_pct,
        otu=otu,
        bottom_time_actual=bottom_time_actual,
        gas_switches=[GasSwitch(depth_m=gs['depth_m'], label=gs['label']) for gs in profile.gas_switches],
        gas_supply=build_gas_supply(profile, sorted_gases, sorted_volumes, req) if not gas_infeasible else None,
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
    sorted_gases = sorted_volumes = None

    if oc_gases:
        sorted_gases, sorted_volumes, available_L = _prepare_oc_gas_supply(oc_gases, oc_gas_volumes, req.reserve_bar)
        bottom_time_actual, bottom_time_shortened, bailout_infeasible = _run_gas_constrained_bottom_time(
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
            available_L=available_L,
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

    w = PlanWarnings(req, 'ccr')
    w.add_diluent(diluent_ppo2, density_gl)
    if oc_gases:
        w.add_supply(bailout_infeasible, bottom_time_shortened, bottom_time_actual, sorted_volumes)
    w.add_oc_gases()
    w.add_cns(cns_pct)

    bailout_plan: Optional[BailoutPlan] = None
    if oc_gases and not bailout_infeasible:
        bailout_plan, bailout_error = _build_bailout_plan(
            gas, req, sorted_gases, sorted_volumes, bottom_time_actual, bailout_gf_low, bailout_gf_high,
        )
        if bailout_error:
            w.add_bailout_error(bailout_error)

    return DivePlannerResponse(
        stops=build_deco_stops(profile.stops),
        total_time_min=profile.total_time_min,
        warnings=w.items,
        density_analysis=DensityAnalysis(
            density_gl=density_gl,
            exceeded_recommended=density_gl > 5.2,
            exceeded_limit=density_gl > 6.3,
        ),
        profile_points=build_profile_points(profile.profile_points),
        tissue_saturations=profile.tissue_saturations,
        tts_min=tts_min,
        cns_pct=cns_pct,
        otu=otu,
        bottom_time_actual=bottom_time_actual,
        bailout=bailout_plan,
    )
