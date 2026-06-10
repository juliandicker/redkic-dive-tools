import json
import logging
import math
import azure.functions as func
from gas_blender import gas_density
from planner.gas import CCRGas, OpenCircuitGas
from planner.dive import plan_ccr_dive, plan_oc_bailout

# NOAA single-dive CNS table: (ppO2, % per minute)
_CNS_TABLE = [
    (0.50, 0.0),
    (0.60, 100 / 720),
    (0.70, 100 / 570),
    (0.80, 100 / 450),
    (0.90, 100 / 360),
    (1.00, 100 / 300),
    (1.10, 100 / 270),
    (1.20, 100 / 240),
    (1.30, 100 / 210),
    (1.40, 100 / 180),
    (1.50, 100 / 150),
    (1.60, 100 / 120),
]


def _cns_rate(ppo2):
    """CNS % per minute at given ppO2 (NOAA single-dive table, linear interpolation)."""
    if ppo2 <= 0.5:
        return 0.0
    if ppo2 >= 1.6:
        return 100 / 120
    for i in range(len(_CNS_TABLE) - 1):
        p0, r0 = _CNS_TABLE[i]
        p1, r1 = _CNS_TABLE[i + 1]
        if p0 <= ppo2 <= p1:
            return r0 + (ppo2 - p0) / (p1 - p0) * (r1 - r0)
    return 0.0


def _otu_rate(ppo2):
    """OTU per minute at given ppO2."""
    if ppo2 <= 0.5:
        return 0.0
    return ((ppo2 - 0.5) / 0.5) ** (5 / 6)


def _oc_cns_otu(bailout_profile, sorted_gases):
    """Compute CNS% and OTU for an OC bailout plan by integrating per-segment ppO2.

    sorted_gases must be sorted by mod_m ascending (shallowest-MOD first).
    """
    def select_gas(depth_m):
        for g in sorted_gases:
            if depth_m <= g.mod_m:
                return g
        return sorted_gases[-1]

    cns = 0.0
    otu = 0.0
    pts = bailout_profile.profile_points
    for i in range(len(pts) - 1):
        d1, d2 = pts[i]['d'], pts[i + 1]['d']
        t1, t2 = pts[i]['t'], pts[i + 1]['t']
        dt = t2 - t1
        if dt <= 0:
            continue
        avg_depth = (d1 + d2) / 2.0
        p_abs = avg_depth / 10.0 + 1.013
        ppo2 = select_gas(avg_depth).fo2 * p_abs
        cns += _cns_rate(ppo2) * dt
        otu += _otu_rate(ppo2) * dt
    return round(cns, 1), round(otu, 1)


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('DivePlanner function processed a request.')

    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse("Request body must be valid JSON.", status_code=400)

    required = ['diluent_o2', 'diluent_he', 'setpoint', 'depth_m', 'bottom_time_min']
    missing = [k for k in required if body.get(k) is None]
    if missing:
        return func.HttpResponse(
            f"Missing required parameters: {', '.join(missing)}.",
            status_code=400,
        )

    diluent_o2 = float(body['diluent_o2'])
    diluent_he = float(body['diluent_he'])
    setpoint = float(body['setpoint'])
    depth_m = float(body['depth_m'])
    bottom_time_min = float(body['bottom_time_min'])
    gf_low = float(body.get('gf_low', 60)) / 100.0
    gf_high = float(body.get('gf_high', 80)) / 100.0
    desc_rate_mpm = float(body.get('desc_rate_mpm', 20.0))
    asc_rate_deep_mpm = float(body.get('asc_rate_deep_mpm', 9.0))
    asc_rate_shallow_mpm = float(body.get('asc_rate_shallow_mpm', 3.0))
    last_stop_m = int(body.get('last_stop_m', 3))
    cns_warn_pct = float(body.get('cns_warn_pct', 80))

    # Bailout gases (optional)
    bailout_gases_raw = body.get('bailout_gases') or []
    bailout_gf_low = float(body.get('bailout_gf_low', body.get('gf_low', 60))) / 100.0
    bailout_gf_high = float(body.get('bailout_gf_high', body.get('gf_high', 80))) / 100.0

    if not (0 < diluent_o2 + diluent_he <= 100):
        return func.HttpResponse("Invalid diluent composition.", status_code=400)
    if not (0.0 < setpoint <= 2.0):
        return func.HttpResponse("Setpoint must be between 0.0 and 2.0 bar.", status_code=400)
    if depth_m <= 0 or bottom_time_min <= 0:
        return func.HttpResponse("Depth and bottom time must be positive.", status_code=400)
    if not (0 < gf_low <= gf_high <= 1.0):
        return func.HttpResponse("GF Low must be ≤ GF High, both between 1 and 100.", status_code=400)
    if not (1.0 <= desc_rate_mpm <= 50.0) or not (1.0 <= asc_rate_deep_mpm <= 30.0) or not (1.0 <= asc_rate_shallow_mpm <= 30.0):
        return func.HttpResponse("Ascent/descent rates out of range.", status_code=400)
    if last_stop_m not in (3, 6):
        return func.HttpResponse("last_stop_m must be 3 or 6.", status_code=400)
    if not (1 <= cns_warn_pct <= 100):
        return func.HttpResponse("cns_warn_pct must be between 1 and 100.", status_code=400)
    if bottom_time_min <= depth_m / desc_rate_mpm:
        return func.HttpResponse("Bottom time must exceed descent time.", status_code=400)
    if not (0 < bailout_gf_low <= bailout_gf_high <= 1.0):
        return func.HttpResponse("Bailout GF Low must be ≤ GF High, both between 1 and 100.", status_code=400)

    # Validate bailout gases
    oc_gases = []
    for i, g in enumerate(bailout_gases_raw):
        try:
            o2 = float(g['o2'])
            he = float(g.get('he', 0))
            mod_m = float(g['mod_m'])
        except (KeyError, TypeError, ValueError):
            return func.HttpResponse(f"Invalid bailout gas at index {i}.", status_code=400)
        if not (0 < o2 + he <= 100):
            return func.HttpResponse(f"Invalid composition for bailout gas {i}.", status_code=400)
        if mod_m <= 0:
            return func.HttpResponse(f"Bailout gas {i} MOD must be positive.", status_code=400)
        oc_gases.append(OpenCircuitGas(o2, he, mod_m))

    try:
        gas = CCRGas(diluent_o2, diluent_he, setpoint)
        profile = plan_ccr_dive(
            gas, depth_m, bottom_time_min, gf_low, gf_high,
            desc_rate_mpm=desc_rate_mpm,
            asc_rate_deep_mpm=asc_rate_deep_mpm,
            asc_rate_shallow_mpm=asc_rate_shallow_mpm,
            last_stop_m=last_stop_m,
        )
    except Exception as e:
        logging.exception("Planning error")
        return func.HttpResponse(str(e), status_code=500)

    density_gl = gas_density(diluent_o2, diluent_he, depth_m)
    density_analysis = {
        'density_gl': density_gl,
        'exceeded_recommended': density_gl > 5.2,
        'exceeded_limit': density_gl > 6.3,
    }

    warnings = []
    diluent_ppo2 = (diluent_o2 / 100.0) * (depth_m / 10.0 + 1.0)
    if diluent_ppo2 > setpoint:
        warnings.append({
            'level': 'danger',
            'message': (
                f'Diluent ppO₂ at {depth_m:.0f} m is {diluent_ppo2:.2f} bar — '
                f'exceeds setpoint ({setpoint:.2f} bar). '
                f'The CCR cannot reduce ppO₂ below the diluent floor; '
                f'actual ppO₂ at depth will be {diluent_ppo2:.2f} bar.'
            ),
        })
    if density_analysis['exceeded_limit']:
        warnings.append({
            'level': 'danger',
            'message': (
                f'Gas density exceeds the BSAC upper limit '
                f'({density_gl:.2f} g/L — limit 6.3 g/L). '
                f'This diluent is not safe to breathe at this depth.'
            ),
        })
    elif density_analysis['exceeded_recommended']:
        warnings.append({
            'level': 'warning',
            'message': (
                f'Gas density exceeds the BSAC recommended limit '
                f'({density_gl:.2f} g/L — recommended ≤5.2 g/L). '
                f'Increased work of breathing and CO₂ retention risk.'
            ),
        })

    # TTS = time from ascent start to surface (bottom_time_min is run time when ascent begins)
    tts_min = round(max(0.0, profile.total_time_min - bottom_time_min), 1)
    cns_pct = round(_cns_rate(setpoint) * profile.total_time_min, 1)
    otu = round(_otu_rate(setpoint) * profile.total_time_min, 1)

    if cns_pct >= cns_warn_pct:
        warnings.append({
            'level': 'warning',
            'message': (
                f'CNS O₂ toxicity is {cns_pct:.1f}% — '
                f'exceeds the warning threshold of {cns_warn_pct:.0f}%.'
            ),
        })

    # Bailout plan
    bailout_response = None
    if oc_gases:
        try:
            bailout = plan_oc_bailout(
                ccr_gas=gas,
                bottom_depth_m=depth_m,
                bottom_time_min=bottom_time_min,
                desc_rate_mpm=desc_rate_mpm,
                bailout_gases=oc_gases,
                gf_low=bailout_gf_low,
                gf_high=bailout_gf_high,
                asc_rate_deep_mpm=asc_rate_deep_mpm,
                asc_rate_shallow_mpm=asc_rate_shallow_mpm,
                last_stop_m=last_stop_m,
            )
            sorted_oc = sorted(oc_gases, key=lambda g: g.mod_m)
            bailout_cns, bailout_otu = _oc_cns_otu(bailout, sorted_oc)
            bailout_tts = round(bailout.total_time_min, 1)
            bailout_response = {
                'stops': [
                    {
                        'depth_m': s.depth_m,
                        'time_min': s.time_min,
                        'runtime_min': s.runtime_min,
                    }
                    for s in bailout.stops
                ],
                'total_time_min': bailout.total_time_min,
                'tts_min': bailout_tts,
                'cns_pct': bailout_cns,
                'otu': bailout_otu,
                'gas_switches': bailout.gas_switches,
                'profile_points': bailout.profile_points,
            }
        except Exception as e:
            logging.exception("Bailout planning error")
            warnings.append({'level': 'warning', 'message': f'Bailout plan could not be computed: {e}'})

    response = {
        'stops': [
            {
                'depth_m': s.depth_m,
                'time_min': s.time_min,
                'runtime_min': s.runtime_min,
            }
            for s in profile.stops
        ],
        'total_time_min': profile.total_time_min,
        'warnings': warnings,
        'density_analysis': density_analysis,
        'profile_points': profile.profile_points,
        'tissue_saturations': profile.tissue_saturations,
        'tts_min': tts_min,
        'cns_pct': cns_pct,
        'otu': otu,
        'bailout': bailout_response,
    }

    return func.HttpResponse(json.dumps(response), mimetype="application/json")
