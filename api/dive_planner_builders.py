import math
from typing import List, Optional

from planner.buhlmann import SURFACE_BAR
from api.dive_planner_models import DecoStop, GasSupplyEntry, ProfilePoint


def _compute_gas_consumption(profile, sorted_gases, sac_bottom_lpm, sac_deco_lpm):
    """Return surface-equivalent litres consumed per gas (indexed same as sorted_gases).

    sorted_gases sorted by mod_m ascending. Stop segments use sac_deco_lpm; transit uses sac_bottom_lpm.
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
    """Binary-search the max bottom time where gas consumption fits available supply."""
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


def build_profile_points(profile_points) -> List[ProfilePoint]:
    return [
        ProfilePoint(
            t=pp['t'], d=pp['d'], c=pp['c'], sats=pp['sats'],
            inert=pp.get('inert', []), tts=pp.get('tts'),
            gf99=pp.get('gf99'), ppO2=pp.get('ppO2'),
            cns=pp.get('cns'), otu=pp.get('otu'),
            density_gl=pp.get('density_gl'),
            gas_o2=pp.get('gas_o2'), gas_he=pp.get('gas_he'),
            ndl=pp.get('ndl'),
        )
        for pp in profile_points
    ]


def build_deco_stops(stops) -> List[DecoStop]:
    return [DecoStop(depth_m=s.depth_m, time_min=s.time_min, runtime_min=s.runtime_min) for s in stops]


def build_gas_supply(profile, sorted_gases, sorted_volumes, req) -> Optional[List[GasSupplyEntry]]:
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
