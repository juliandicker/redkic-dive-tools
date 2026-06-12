import math
from planner.buhlmann import SURFACE_BAR
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


def _oc_cns_otu(profile, sorted_gases):
    """Compute CNS% and OTU for an OC plan by integrating per-segment ppO2.

    sorted_gases must be sorted by mod_m ascending (shallowest-MOD first).
    """
    def select_gas(depth_m):
        for g in sorted_gases:
            if depth_m <= g.mod_m:
                return g
        return sorted_gases[-1]

    cns = 0.0
    otu = 0.0
    pts = profile.profile_points
    for i in range(len(pts) - 1):
        d1, d2 = pts[i]['d'], pts[i + 1]['d']
        t1, t2 = pts[i]['t'], pts[i + 1]['t']
        dt = t2 - t1
        if dt <= 0:
            continue
        avg_depth = (d1 + d2) / 2.0
        p_abs = avg_depth / 10.0 + SURFACE_BAR
        ppo2 = select_gas(avg_depth).fo2 * p_abs
        cns += _cns_rate(ppo2) * dt
        otu += _otu_rate(ppo2) * dt
    return cns, otu


def _compute_gas_consumption(profile, sorted_gases, sac_bottom_lpm, sac_deco_lpm):
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
    pts = profile.profile_points
    for k in range(len(pts) - 1):
        d1, d2 = pts[k]['d'], pts[k + 1]['d']
        dt = pts[k + 1]['t'] - pts[k]['t']
        if dt <= 0:
            continue
        avg_depth = (d1 + d2) / 2.0
        p_abs = avg_depth / 10.0 + SURFACE_BAR
        idx = select_idx(avg_depth)
        sac = sac_deco_lpm if abs(d1 - d2) < 0.05 else sac_bottom_lpm
        consumption[idx] += sac * p_abs * dt

    return [round(c) for c in consumption]


def _binary_search_bottom_time(
    planner_fn, depth_m, requested_bt, desc_rate_mpm,
    sorted_gases, available_L, sac_bottom, sac_deco,
):
    """Binary-search the max bottom time where gas consumption fits available supply.

    planner_fn: (bt: float) -> profile with .profile_points
    Returns (bottom_time_min, shortened: bool) or (None, True) if infeasible.
    """
    def fits(bt):
        try:
            profile = planner_fn(bt)
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
