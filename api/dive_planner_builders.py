from typing import List, Optional

from DivePlanner import _compute_gas_consumption
from api.dive_planner_models import DecoStop, GasSupplyEntry, ProfilePoint


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
