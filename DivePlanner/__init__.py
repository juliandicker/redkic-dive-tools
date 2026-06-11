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


def _gas_label(g):
    o2 = round(g.fo2 * 100)
    he = round(g.fhe * 100)
    if he > 0:
        return f'Tx{o2}/{he}'
    if o2 == 100:
        return 'O₂'
    if o2 == 21:
        return 'Air'
    return f'Nx{o2}'


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


def _compute_gas_consumption(bailout_profile, sorted_gases, sac_bottom_lpm, sac_deco_lpm):
    """Return surface-equivalent litres consumed per gas (indexed same as sorted_gases).

    sorted_gases must be sorted by mod_m ascending (shallowest MOD first).
    Stop segments (constant depth) use sac_deco_lpm; transit segments use sac_bottom_lpm.
    """
    def select_idx(depth_m):
        for i, g in enumerate(sorted_gases):
            if depth_m <= g.mod_m:
                return i
        return len(sorted_gases) - 1

    consumption = [0.0] * len(sorted_gases)
    pts = bailout_profile.profile_points
    for k in range(len(pts) - 1):
        d1, d2 = pts[k]['d'], pts[k + 1]['d']
        dt = pts[k + 1]['t'] - pts[k]['t']
        if dt <= 0:
            continue
        avg_depth = (d1 + d2) / 2.0
        p_abs = avg_depth / 10.0 + 1.013
        idx = select_idx(avg_depth)
        sac = sac_deco_lpm if abs(d1 - d2) < 0.05 else sac_bottom_lpm
        consumption[idx] += sac * p_abs * dt

    return [round(c) for c in consumption]


def _max_bottom_time_within_gas_supply(
    ccr_gas, depth_m, requested_bt, desc_rate_mpm,
    oc_gases, sorted_gases, available_L,
    gf_low, gf_high, asc_rate_deep, asc_rate_shallow, last_stop_m,
    sac_bottom, sac_deco,
):
    """Binary-search for the max bottom_time_min where all gases fit cylinder supply.

    available_L: list of floats indexed same as sorted_gases (math.inf = unlimited).
    Returns (bottom_time_min, shortened: bool).
    """
    def fits(bt):
        try:
            b = plan_oc_bailout(
                ccr_gas=ccr_gas, bottom_depth_m=depth_m, bottom_time_min=bt,
                desc_rate_mpm=desc_rate_mpm, bailout_gases=oc_gases,
                gf_low=gf_low, gf_high=gf_high,
                asc_rate_deep_mpm=asc_rate_deep, asc_rate_shallow_mpm=asc_rate_shallow,
                last_stop_m=last_stop_m,
            )
            consumed = _compute_gas_consumption(b, sorted_gases, sac_bottom, sac_deco)
            return all(consumed[i] <= available_L[i] for i in range(len(sorted_gases)))
        except Exception:
            return False

    if fits(requested_bt):
        return requested_bt, False

    lo = depth_m / desc_rate_mpm + 1.0

    # If even the minimum viable bottom time is infeasible, no solution exists
    if not fits(lo):
        return None, True

    hi = requested_bt
    for _ in range(12):
        mid = (lo + hi) / 2.0
        if fits(mid):
            lo = mid
        else:
            hi = mid
        if hi - lo < 0.25:
            break

    return round(lo, 1), True


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

    sac_bottom_lpm = float(body.get('sac_bottom_lpm', 20.0))
    sac_deco_lpm   = float(body.get('sac_deco_lpm',   15.0))
    reserve_bar    = float(body.get('reserve_bar', 50.0))
    if not (1 <= sac_bottom_lpm <= 100) or not (1 <= sac_deco_lpm <= 100):
        return func.HttpResponse("SAC rates must be between 1 and 100 L/min.", status_code=400)
    if not (0 <= reserve_bar <= 300):
        return func.HttpResponse("reserve_bar must be between 0 and 300.", status_code=400)

    # Validate bailout gases
    oc_gases = []
    oc_gas_volumes = []   # parallel list: {cyl_l, cyl_bar} per gas (None if not supplied)
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
        try:
            cyl_l   = float(g['cyl_l'])   if g.get('cyl_l')   else None
            cyl_bar = float(g['cyl_bar']) if g.get('cyl_bar') else None
        except (TypeError, ValueError):
            cyl_l, cyl_bar = None, None
        oc_gases.append(OpenCircuitGas(o2, he, mod_m))
        oc_gas_volumes.append({'cyl_l': cyl_l, 'cyl_bar': cyl_bar})

    # Check gas supply limits before planning — may shorten bottom_time_min
    bottom_time_actual = bottom_time_min
    bottom_time_shortened = False
    bailout_infeasible = False
    bailout_infeasible_msg = None
    if oc_gases:
        sorted_gases = sorted(oc_gases, key=lambda g: g.mod_m)
        sorted_volumes = sorted(
            zip(oc_gases, oc_gas_volumes), key=lambda x: x[0].mod_m
        )
        available_L = [
            (v['cyl_l'] * max(0.0, v['cyl_bar'] - reserve_bar)) if (v['cyl_l'] and v['cyl_bar']) else math.inf
            for _, v in sorted_volumes
        ]
        if any(a < math.inf for a in available_L):
            result_bt, shortened = _max_bottom_time_within_gas_supply(
                ccr_gas=CCRGas(diluent_o2, diluent_he, setpoint),
                depth_m=depth_m,
                requested_bt=bottom_time_min,
                desc_rate_mpm=desc_rate_mpm,
                oc_gases=oc_gases,
                sorted_gases=sorted_gases,
                available_L=available_L,
                gf_low=bailout_gf_low,
                gf_high=bailout_gf_high,
                asc_rate_deep=asc_rate_deep_mpm,
                asc_rate_shallow=asc_rate_shallow_mpm,
                last_stop_m=last_stop_m,
                sac_bottom=sac_bottom_lpm,
                sac_deco=sac_deco_lpm,
            )
            if result_bt is None:
                bailout_infeasible = True
                empty_gases = [
                    _gas_label(g) for g, v in sorted_volumes
                    if v['cyl_l'] and v['cyl_bar'] and v['cyl_l'] * max(0.0, v['cyl_bar'] - reserve_bar) == 0
                ]
                if empty_gases:
                    bailout_infeasible_msg = (
                        f"Bailout gas supply error: {', '.join(empty_gases)} "
                        f"{'has' if len(empty_gases) == 1 else 'have'} no usable gas after "
                        f"deducting the {reserve_bar:.0f} bar reserve. "
                        f"Increase cylinder pressure or reduce the tank reserve setting."
                    )
                else:
                    bailout_infeasible_msg = (
                        f"Bailout gas supply is insufficient even for the minimum possible dive time "
                        f"at {depth_m:.0f} m. Increase cylinder sizes, pressure, or reduce the "
                        f"{reserve_bar:.0f} bar reserve."
                    )
            else:
                bottom_time_actual, bottom_time_shortened = result_bt, shortened

    try:
        gas = CCRGas(diluent_o2, diluent_he, setpoint)
        profile = plan_ccr_dive(
            gas, depth_m, bottom_time_actual, gf_low, gf_high,
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

    if bailout_infeasible:
        warnings.append({'level': 'danger', 'message': bailout_infeasible_msg})
    elif bottom_time_shortened:
        warnings.append({
            'level': 'warning',
            'message': (
                f'Bottom time shortened from {bottom_time_min:.0f} min to {bottom_time_actual:.1f} min '
                f'— insufficient bailout gas supply for the requested dive time.'
            ),
        })

    # TTS = time from ascent start to surface (bottom_time_actual is run time when ascent begins)
    tts_min = round(max(0.0, profile.total_time_min - bottom_time_actual), 1)
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

    # Bailout gas density warnings — deepest gas used at depth_m; each
    # subsequent gas is first used when ascending to its own MOD.
    if oc_gases:
        sorted_desc = sorted(oc_gases, key=lambda g: g.mod_m, reverse=True)
        for i, g in enumerate(sorted_desc):
            use_depth = depth_m if i == 0 else g.mod_m
            d = gas_density(g.fo2 * 100, g.fhe * 100, use_depth)
            label = _gas_label(g)
            ppo2 = g.fo2 * (use_depth / 10.0 + 1.0)
            if ppo2 > 1.6:
                warnings.append({
                    'level': 'danger',
                    'message': (
                        f'Bailout gas {label} at {use_depth:.0f} m: '
                        f'ppO₂ {ppo2:.2f} bar exceeds the absolute maximum (1.6 bar). '
                        f'This gas cannot be safely breathed at this depth.'
                    ),
                })
            elif ppo2 >= 1.4:
                warnings.append({
                    'level': 'warning',
                    'message': (
                        f'Bailout gas {label} at {use_depth:.0f} m: '
                        f'ppO₂ {ppo2:.2f} bar is at or above the working limit (1.4 bar). '
                        f'Consider a lower O₂ fraction or shallower planned depth.'
                    ),
                })
            if d > 6.3:
                warnings.append({
                    'level': 'danger',
                    'message': (
                        f'Bailout gas {label} at {use_depth:.0f} m: '
                        f'gas density {d:.2f} g/L exceeds the upper limit (6.3 g/L). '
                        f'This gas cannot be safely breathed at this depth — '
                        f'consider a less dense alternative or reducing planned depth.'
                    ),
                })
            elif d > 5.2:
                warnings.append({
                    'level': 'warning',
                    'message': (
                        f'Bailout gas {label} at {use_depth:.0f} m: '
                        f'gas density {d:.2f} g/L exceeds the recommended limit (5.2 g/L). '
                        f'Increased work of breathing at bailout depth.'
                    ),
                })

    # Bailout plan
    bailout_response = None
    if oc_gases and not bailout_infeasible:
        try:
            bailout = plan_oc_bailout(
                ccr_gas=gas,
                bottom_depth_m=depth_m,
                bottom_time_min=bottom_time_actual,
                desc_rate_mpm=desc_rate_mpm,
                bailout_gases=oc_gases,
                gf_low=bailout_gf_low,
                gf_high=bailout_gf_high,
                asc_rate_deep_mpm=asc_rate_deep_mpm,
                asc_rate_shallow_mpm=asc_rate_shallow_mpm,
                last_stop_m=last_stop_m,
            )
            sorted_oc = sorted(oc_gases, key=lambda g: g.mod_m)
            sorted_oc_volumes = sorted(
                zip(oc_gases, oc_gas_volumes), key=lambda x: x[0].mod_m
            )
            bailout_cns, bailout_otu = _oc_cns_otu(bailout, sorted_oc)
            bailout_tts = round(bailout.total_time_min, 1)

            gas_supply = None
            if any(v['cyl_l'] and v['cyl_bar'] for _, v in sorted_oc_volumes):
                consumed = _compute_gas_consumption(bailout, sorted_oc, sac_bottom_lpm, sac_deco_lpm)
                gas_supply = []
                for i, (g, v) in enumerate(sorted_oc_volumes):
                    entry = {
                        'o2': round(g.fo2 * 100),
                        'he': round(g.fhe * 100),
                        'mod_m': g.mod_m,
                        'consumed_L': consumed[i],
                    }
                    if v['cyl_l'] and v['cyl_bar']:
                        usable = v['cyl_l'] * max(0.0, v['cyl_bar'] - reserve_bar)
                        entry['available_L'] = round(usable)
                        entry['pct'] = round(consumed[i] / usable * 100) if usable > 0 else 100
                    gas_supply.append(entry)

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
                'tissue_saturations': bailout.tissue_saturations,
                'gas_supply': gas_supply,
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
        'bottom_time_actual': bottom_time_actual,
        'bailout': bailout_response,
    }

    return func.HttpResponse(json.dumps(response), mimetype="application/json")
