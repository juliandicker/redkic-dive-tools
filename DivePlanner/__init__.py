import math
from planner.dive import plan_oc_bailout, plan_oc_dive

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
    return f'N{o2}'


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
    return cns, otu


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

    return math.floor(lo), True


def _max_bottom_time_within_gas_supply_oc(
    depth_m, requested_bt, desc_rate_mpm,
    oc_gases, sorted_gases, available_L,
    gf_low, gf_high, asc_rate_deep, asc_rate_shallow, last_stop_m,
    sac_bottom, sac_deco,
):
    """Binary-search for max bottom_time_min on a full OC dive.

    Same contract as _max_bottom_time_within_gas_supply but plans the entire dive
    with plan_oc_dive (bottom phase burns OC gas, not CCR diluent).
    """
    def fits(bt):
        try:
            profile = plan_oc_dive(
                oc_gases=oc_gases, bottom_depth_m=depth_m, bottom_time_min=bt,
                gf_low=gf_low, gf_high=gf_high,
                desc_rate_mpm=desc_rate_mpm,
                asc_rate_deep_mpm=asc_rate_deep, asc_rate_shallow_mpm=asc_rate_shallow,
                last_stop_m=last_stop_m,
            )
            consumed = _compute_gas_consumption(profile, sorted_gases, sac_bottom, sac_deco)
            return all(consumed[i] <= available_L[i] for i in range(len(sorted_gases)))
        except Exception:
            return False

    if fits(requested_bt):
        return requested_bt, False

    lo = depth_m / desc_rate_mpm + 1.0

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

    return math.floor(lo), True
