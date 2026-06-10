import json
import logging
import math
import azure.functions as func
from gas_blender import gas_density
from planner.gas import CCRGas
from planner.dive import plan_ccr_dive

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
    if bottom_time_min <= depth_m / desc_rate_mpm:
        return func.HttpResponse("Bottom time must exceed descent time.", status_code=400)

    try:
        gas = CCRGas(diluent_o2, diluent_he, setpoint)
        profile = plan_ccr_dive(
            gas, depth_m, bottom_time_min, gf_low, gf_high,
            desc_rate_mpm=desc_rate_mpm,
            asc_rate_deep_mpm=asc_rate_deep_mpm,
            asc_rate_shallow_mpm=asc_rate_shallow_mpm,
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

    # TTS = time from ascent start to surface (bottom_time_min is run time when ascent begins)
    tts_min = round(max(0.0, profile.total_time_min - bottom_time_min), 1)
    cns_pct = round(_cns_rate(setpoint) * profile.total_time_min, 1)
    otu = round(_otu_rate(setpoint) * profile.total_time_min, 1)

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
        'density_analysis': density_analysis,
        'profile_points': profile.profile_points,
        'tissue_saturations': profile.tissue_saturations,
        'tts_min': tts_min,
        'cns_pct': cns_pct,
        'otu': otu,
    }

    return func.HttpResponse(json.dumps(response), mimetype="application/json")
