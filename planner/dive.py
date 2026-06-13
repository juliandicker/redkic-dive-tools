import copy
import math
from dataclasses import dataclass, field
from .buhlmann import BuhlmannModel, SURFACE_BAR, WATER_VAPOUR_BAR, ZHL16C
from gas_blender import gas_density as _gas_density_pct

_DENSITY_SWITCH_LIMIT_GL = 5.2  # g/L — don't switch to a richer gas above this density
MIN_PPO2_BAR = 0.18             # hypoxic planning floor: gas must reach this ppO2 to be breathable


@dataclass
class DecoStop:
    depth_m: int
    time_min: int
    runtime_min: float


@dataclass
class DiveProfile:
    stops: list = field(default_factory=list)
    total_time_min: float = 0.0
    profile_points: list = field(default_factory=list)  # [{t, d, c, sats}] time/depth/ceiling (m)
    tissue_saturations: list = field(default_factory=list)  # saturation ratio per compartment
    gas_switches: list = field(default_factory=list)  # [{depth_m, label}]


def _gas_density_at_depth(gas, depth_m: float) -> float:
    return _gas_density_pct(gas.fo2 * 100, gas.fhe * 100, depth_m)


_CNS_TABLE = [
    (0.50, 0.0),
    (0.60, 100.0 / 720),
    (0.70, 100.0 / 570),
    (0.80, 100.0 / 450),
    (0.90, 100.0 / 360),
    (1.00, 100.0 / 300),
    (1.10, 100.0 / 270),
    (1.20, 100.0 / 240),
    (1.30, 100.0 / 210),
    (1.40, 100.0 / 180),
    (1.50, 100.0 / 150),
    (1.60, 100.0 / 120),
]


def _cns_rate_pm(ppo2):
    if ppo2 <= 0.5:
        return 0.0
    if ppo2 >= 1.6:
        return 100.0 / 120
    for i in range(len(_CNS_TABLE) - 1):
        p0, r0 = _CNS_TABLE[i]
        p1, r1 = _CNS_TABLE[i + 1]
        if p0 <= ppo2 <= p1:
            return r0 + (ppo2 - p0) / (p1 - p0) * (r1 - r0)
    return 0.0


def _otu_rate_pm(ppo2):
    if ppo2 <= 0.5:
        return 0.0
    return ((ppo2 - 0.5) / 0.5) ** (5.0 / 6)


def _ccr_loop_density(ccr_gas, depth_m):
    """Gas density of CCR loop at depth, accounting for setpoint-adjusted O2 fraction."""
    p_amb = depth_m / 10.0 + 1.0  # matches gas_blender.gas_density convention
    fO2_loop = min(ccr_gas.setpoint / p_amb, ccr_gas.fo2)
    inert_dil = ccr_gas.fn2 + ccr_gas.fhe
    remaining = 1.0 - fO2_loop
    fHe_loop = ccr_gas.fhe / inert_dil * remaining if inert_dil > 0 else 0.0
    return _gas_density_pct(fO2_loop * 100, fHe_loop * 100, depth_m)


def _annotate_physics(profile_points, ppO2_at_depth, density_at_depth):
    """Annotate each profile point with ppO2, gf99, cumulative cns/otu, and gas density.

    ppO2_at_depth(depth_m, index) and density_at_depth(depth_m, index) accept both
    depth and point index so callers can vary gas by phase (descent vs ascent).
    """
    def _gf99(inert, depth_m):
        p_amb = depth_m / 10.0 + SURFACE_BAR
        worst = -math.inf
        for coeff, (pn2, phe) in zip(ZHL16C, inert):
            _, a_n2, b_n2, _, a_he, b_he = coeff
            p = pn2 + phe
            if p <= 0:
                continue
            a = (a_n2 * pn2 + a_he * phe) / p
            b = (b_n2 * pn2 + b_he * phe) / p
            m = p_amb / b + a
            denom = m - p_amb
            if abs(denom) < 1e-9:
                continue
            gf = (p - p_amb) / denom * 100.0
            if gf > worst:
                worst = gf
        return round(worst, 1) if math.isfinite(worst) else 0.0

    ppo2s = [ppO2_at_depth(pt['d'], i) for i, pt in enumerate(profile_points)]
    cum_cns = 0.0
    cum_otu = 0.0

    for i, pt in enumerate(profile_points):
        pt['gf99'] = _gf99(pt.get('inert', []), pt['d'])
        pt['ppO2'] = round(ppo2s[i], 3)
        pt['density_gl'] = density_at_depth(pt['d'], i)
        pt['cns'] = round(cum_cns, 2)
        pt['otu'] = round(cum_otu, 2)
        if i < len(profile_points) - 1:
            dt = profile_points[i + 1]['t'] - pt['t']
            avg_ppo2 = (ppo2s[i] + ppo2s[i + 1]) / 2
            cum_cns += _cns_rate_pm(avg_ppo2) * dt
            cum_otu += _otu_rate_pm(avg_ppo2) * dt


def _gas_floor_depth(gas):
    """Depth (m) where gas ppO2 first reaches MIN_PPO2_BAR.

    Negative means the gas is breathable at the surface.  Derived from
    OpenCircuitGas.pp_o2: (p_abs - WATER_VAPOUR_BAR) * fo2 = MIN_PPO2_BAR,
    with p_abs = depth/10 + SURFACE_BAR.
    """
    if gas.fo2 <= 0:
        return float('inf')
    return 10.0 * (MIN_PPO2_BAR / gas.fo2 + WATER_VAPOUR_BAR - SURFACE_BAR)


def _select_travel_gas(sorted_gases, switch_depth_m):
    """Return the surface-breathable gas with the deepest MOD that can reach switch_depth_m.

    Picks the least-narcotic (most helium) surface-breathable option, matching
    real-world practice of descending on a normoxic trimix travel mix.
    Returns None if no configured gas passes the surface-breathability test.
    """
    candidates = [
        g for g in sorted_gases
        if g.pp_o2(SURFACE_BAR) >= MIN_PPO2_BAR and g.mod_m >= switch_depth_m
    ]
    return max(candidates, key=lambda g: g.mod_m) if candidates else None


def _make_select_gas(sorted_gases):
    """Return a _select_gas(depth_m) that picks the richest breathable gas (window
    test: ppO2 floor ≤ gas ≤ MOD cap) at each depth, skipping gases that exceed
    the density switch limit when a less-dense alternative is still available."""
    def _select_gas(depth_m: float):
        p_abs = depth_m / 10.0 + SURFACE_BAR
        available = [
            g for g in sorted_gases
            if depth_m <= g.mod_m and g.pp_o2(p_abs) >= MIN_PPO2_BAR
        ]
        if not available:
            available = [g for g in sorted_gases if depth_m <= g.mod_m]
        if not available:
            return sorted_gases[-1]
        for g in available:
            if _gas_density_at_depth(g, depth_m) <= _DENSITY_SWITCH_LIMIT_GL:
                return g
        return min(available, key=lambda g: _gas_density_at_depth(g, depth_m))
    return _select_gas


def _round_up_to_3m(depth_m):
    return int(math.ceil(depth_m / 3.0)) * 3


def _build_bottom_model(gas, bottom_depth_m, bottom_time_min, desc_rate_mpm, gf_low, gf_high,
                         travel_gas=None, travel_switch_depth_m=None):
    """Run descent + flat bottom time.

    If travel_gas and travel_switch_depth_m are given the descent is split:
    travel_gas from 0→switch depth, then gas (back gas) from switch depth→bottom.
    This correctly models hypoxic back gases that cannot be breathed near the surface.

    Returns (model, runtime_min, profile_points) so the caller can fork the tissue
    state before the ascent: one branch for CCR, one for OC bailout.
    """
    model = BuhlmannModel()
    runtime_min = 0.0
    profile_points = []

    def rec(depth, ceiling):
        profile_points.append({
            't': round(runtime_min, 2),
            'd': round(float(depth), 1),
            'c': round(max(0.0, float(ceiling)), 1),
            'sats': model.tissue_saturations(gf_high),
            'inert': [[round(t.pn2, 4), round(t.phe, 4)] for t in model.tissues],
        })

    rec(0.0, 0.0)
    total_desc_time = bottom_depth_m / desc_rate_mpm
    flat_bottom_time = bottom_time_min - total_desc_time
    if flat_bottom_time < 0:
        raise ValueError("bottom_time_min must exceed descent time")

    if travel_gas is not None and travel_switch_depth_m:
        switch_time = travel_switch_depth_m / desc_rate_mpm
        model.load_segment(travel_gas, 0.0, travel_switch_depth_m, switch_time)
        runtime_min += switch_time
        rec(travel_switch_depth_m, model.ceiling_m(gf_low))
        model.load_segment(gas, travel_switch_depth_m, bottom_depth_m, total_desc_time - switch_time)
        runtime_min += total_desc_time - switch_time
    else:
        model.load_segment(gas, 0.0, bottom_depth_m, total_desc_time)
        runtime_min += total_desc_time

    rec(bottom_depth_m, model.ceiling_m(gf_low))

    # Bottom time — 5-min chunks so long bottom times show gradual tissue loading
    remaining = flat_bottom_time
    while remaining > 0:
        chunk = min(5.0, remaining)
        model.load_segment(gas, bottom_depth_m, bottom_depth_m, chunk)
        runtime_min += chunk
        remaining -= chunk
        rec(bottom_depth_m, model.ceiling_m(gf_low))

    return model, runtime_min, profile_points


def _run_deco_ascent(
    model,
    start_depth,
    gf_low,
    gf_high,
    gas_at_depth,
    asc_rate_deep_mpm,
    asc_rate_shallow_mpm,
    last_stop_m,
    runtime_min,
    profile_points,
):
    """Run the grid-walk ascent + deco stop loop.

    gas_at_depth(depth_m) -> gas object, called before each segment.
    Does NOT record a point at start_depth — caller has already done so
    (CCR: via _build_bottom_model; bailout: first while loop iteration does it).
    Returns (DiveProfile, gas_switches).
    """
    def asc_rate(depth):
        return asc_rate_shallow_mpm if depth <= 6.0 else asc_rate_deep_mpm

    def rec(depth, ceiling):
        profile_points.append({
            't': round(runtime_min, 2),
            'd': round(float(depth), 1),
            'c': round(max(0.0, float(ceiling)), 1),
            'sats': model.tissue_saturations(gf_high),
            'inert': [[round(t.pn2, 4), round(t.phe, 4)] for t in model.tissues],
        })

    current_depth = float(start_depth)
    gas_switches = []
    _cur_gas = gas_at_depth(current_depth)

    # Align to the standard 3 m stop grid (handles non-multiple bottom depths)
    grid_depth = int(math.floor(current_depth / 3.0)) * 3
    if grid_depth < current_depth:
        seg_time = (current_depth - float(grid_depth)) / asc_rate_deep_mpm
        model.load_segment(_cur_gas, current_depth, float(grid_depth), seg_time)
        runtime_min += seg_time
        current_depth = float(grid_depth)

    # Walk up the grid until the ceiling catches us (= first deco stop).
    # Record a profile point at each step so the chart shows the ceiling rising.
    first_stop_depth = None
    while True:
        ceiling = model.ceiling_m(gf_low)
        rec(current_depth, ceiling)
        if ceiling > 0.0 and _round_up_to_3m(ceiling) >= current_depth:
            first_stop_depth = max(last_stop_m, int(current_depth))
            break
        if current_depth <= last_stop_m:
            if ceiling > 0.0:
                first_stop_depth = last_stop_m
            break
        next_depth = current_depth - 3.0
        next_gas = gas_at_depth(next_depth)
        seg_time = 3.0 / asc_rate(current_depth)
        model.load_segment(_cur_gas, current_depth, next_depth, seg_time)
        runtime_min += seg_time
        current_depth = next_depth
        if next_gas is not _cur_gas:
            gas_switches.append({'depth_m': next_depth, 'label': next_gas.label if hasattr(next_gas, 'label') else ''})
            _cur_gas = next_gas

    if first_stop_depth is None:
        if current_depth > 0.0:
            asc_time = current_depth / asc_rate(current_depth)
            model.load_segment(_cur_gas, current_depth, 0.0, asc_time)
            runtime_min += asc_time
        rec(0.0, 0.0)
        profile = DiveProfile(
            stops=[],
            total_time_min=round(runtime_min, 1),
            profile_points=profile_points,
            tissue_saturations=model.tissue_saturations(gf_high),
        )
        return profile, gas_switches

    # Work through stops from first_stop_depth down to last_stop_m.
    stops = []
    stop_depth = first_stop_depth
    while stop_depth >= last_stop_m:
        gf = gf_low + (gf_high - gf_low) * (first_stop_depth - stop_depth) / first_stop_depth
        gf = max(gf_low, min(gf_high, gf))

        next_stop = stop_depth - 3 if stop_depth > last_stop_m else 0
        def _raw_ceiling_m(g):
            return (model.ceiling_bar(g) - SURFACE_BAR) * 10.0

        g = gas_at_depth(float(stop_depth))
        if g is not _cur_gas:
            gas_switches.append({'depth_m': float(stop_depth), 'label': g.label if hasattr(g, 'label') else ''})
            _cur_gas = g

        rec(stop_depth, model.ceiling_m(gf))  # start of stop

        stop_minutes = 0
        while _raw_ceiling_m(gf) >= next_stop - 0.5:
            model.load_segment(g, stop_depth, stop_depth, 1.0)
            runtime_min += 1.0
            stop_minutes += 1
            if stop_minutes % 5 == 0:
                rec(stop_depth, model.ceiling_m(gf))
            if stop_minutes > 300:
                break  # safety guard against runaway

        if stop_minutes % 5 != 0:
            rec(stop_depth, model.ceiling_m(gf))  # end of stop

        if stop_minutes > 0:
            stops.append(DecoStop(
                depth_m=stop_depth,
                time_min=stop_minutes,
                runtime_min=round(runtime_min, 1),
            ))

        next_depth = stop_depth - 3 if stop_depth > last_stop_m else 0
        if next_depth > 0:
            asc_time = 3.0 / asc_rate(stop_depth)
            model.load_segment(_cur_gas, stop_depth, next_depth, asc_time)
            runtime_min += asc_time
        current_depth = float(next_depth)
        stop_depth = next_depth

    # Final ascent from last_stop_m to surface
    asc_time = last_stop_m / asc_rate_shallow_mpm
    model.load_segment(_cur_gas, float(last_stop_m), 0.0, asc_time)
    runtime_min += asc_time

    profile_points.append({
        't': round(runtime_min, 2),
        'd': 0.0,
        'c': 0.0,
        'sats': model.tissue_saturations(gf_high),
        'inert': [[round(t.pn2, 4), round(t.phe, 4)] for t in model.tissues],
    })

    profile = DiveProfile(
        stops=stops,
        total_time_min=round(runtime_min, 1),
        profile_points=profile_points,
        tissue_saturations=model.tissue_saturations(gf_high),
    )
    return profile, gas_switches


def _project_tts(inert, depth_m, gf_low, gf_high, gas_at_depth, asc_rate_deep_mpm, asc_rate_shallow_mpm, last_stop_m):
    """Return the TTS (minutes) from a given tissue state and depth.

    Mirrors _run_deco_ascent's grid-walk and stop loop on a throwaway model
    copy so it is self-consistent with the planner's own schedule.
    """
    model = BuhlmannModel()
    for i, (pn2, phe) in enumerate(inert):
        model.tissues[i].pn2 = pn2
        model.tissues[i].phe = phe

    def asc_rate(d):
        return asc_rate_shallow_mpm if d <= 6.0 else asc_rate_deep_mpm

    time = 0.0
    current_depth = float(depth_m)
    _cur_gas = gas_at_depth(current_depth)

    # Align to 3 m grid
    grid_depth = int(math.floor(current_depth / 3.0)) * 3
    if grid_depth < current_depth:
        seg = (current_depth - float(grid_depth)) / asc_rate_deep_mpm
        model.load_segment(_cur_gas, current_depth, float(grid_depth), seg)
        time += seg
        current_depth = float(grid_depth)

    # Walk up to find first stop (or surface if NDL)
    first_stop_depth = None
    while True:
        ceiling = model.ceiling_m(gf_low)
        if ceiling > 0.0 and _round_up_to_3m(ceiling) >= current_depth:
            first_stop_depth = max(last_stop_m, int(current_depth))
            break
        if current_depth <= last_stop_m:
            if ceiling > 0.0:
                first_stop_depth = last_stop_m
            break
        next_depth = current_depth - 3.0
        seg = 3.0 / asc_rate(current_depth)
        next_gas = gas_at_depth(next_depth)
        model.load_segment(_cur_gas, current_depth, next_depth, seg)
        time += seg
        current_depth = next_depth
        if next_gas is not _cur_gas:
            _cur_gas = next_gas

    if first_stop_depth is None:
        if current_depth > 0.0:
            time += current_depth / asc_rate(current_depth)
        return round(time, 1)

    # Stop loop
    stop_depth = first_stop_depth
    while stop_depth >= last_stop_m:
        gf = gf_low + (gf_high - gf_low) * (first_stop_depth - stop_depth) / first_stop_depth
        gf = max(gf_low, min(gf_high, gf))
        next_stop = stop_depth - 3 if stop_depth > last_stop_m else 0

        def _raw_ceiling_m(g):
            return (model.ceiling_bar(g) - SURFACE_BAR) * 10.0

        g = gas_at_depth(float(stop_depth))
        _cur_gas = g
        stop_minutes = 0
        while _raw_ceiling_m(gf) >= next_stop - 0.5:
            model.load_segment(g, stop_depth, stop_depth, 1.0)
            time += 1.0
            stop_minutes += 1
            if stop_minutes > 300:
                break

        next_depth = stop_depth - 3 if stop_depth > last_stop_m else 0
        if next_depth > 0:
            model.load_segment(_cur_gas, stop_depth, next_depth, 3.0 / asc_rate(stop_depth))
            time += 3.0 / asc_rate(stop_depth)
        stop_depth = next_depth

    time += last_stop_m / asc_rate_shallow_mpm
    return round(time, 1)


def _annotate_tts(profile_points, total_time_min, gf_low, gf_high, gas_at_depth, asc_rate_deep_mpm, asc_rate_shallow_mpm, last_stop_m):
    """Annotate each profile point with TTS (minutes).

    Bottom-phase points use a forward projection from the current tissue state
    so TTS rises as tissues load — the key teaching behaviour. Ascent/deco-phase
    points use remaining plan time, which is self-consistent with the planner's
    own GF gradient and stop schedule.
    """
    max_depth = max((pt['d'] for pt in profile_points), default=0)
    for pt in profile_points:
        if pt['d'] <= 0:
            pt['tts'] = 0.0
        elif pt['d'] >= max_depth:
            pt['tts'] = _project_tts(
                pt['inert'], pt['d'], gf_low, gf_high, gas_at_depth,
                asc_rate_deep_mpm, asc_rate_shallow_mpm, last_stop_m,
            )
        else:
            pt['tts'] = round(max(0.0, total_time_min - pt['t']), 1)


def plan_ccr_dive(
    gas,
    bottom_depth_m,
    bottom_time_min,
    gf_low,
    gf_high,
    desc_rate_mpm=20.0,
    asc_rate_deep_mpm=9.0,
    asc_rate_shallow_mpm=3.0,
    last_stop_m=3,
):
    """Plan a CCR dive and return a DiveProfile with deco stops.

    bottom_time_min: run time from dive start until ascent begins (includes descent).
    gf_low and gf_high are fractions (0.0–1.0).
    Stops are at 3 m multiples, shallowest at last_stop_m (3 or 6).
    """
    model, runtime_min, profile_points = _build_bottom_model(
        gas, bottom_depth_m, bottom_time_min, desc_rate_mpm, gf_low, gf_high
    )
    profile, gas_switches = _run_deco_ascent(
        model=model,
        start_depth=bottom_depth_m,
        gf_low=gf_low,
        gf_high=gf_high,
        gas_at_depth=lambda _: gas,
        asc_rate_deep_mpm=asc_rate_deep_mpm,
        asc_rate_shallow_mpm=asc_rate_shallow_mpm,
        last_stop_m=last_stop_m,
        runtime_min=runtime_min,
        profile_points=profile_points,
    )
    profile.gas_switches = gas_switches
    _annotate_tts(profile.profile_points, profile.total_time_min, gf_low, gf_high, lambda _: gas,
                  asc_rate_deep_mpm, asc_rate_shallow_mpm, last_stop_m)
    _annotate_physics(
        profile.profile_points,
        ppO2_at_depth=lambda d, _i: min(gas.setpoint, max(0.0, d / 10.0 + SURFACE_BAR - WATER_VAPOUR_BAR)),
        density_at_depth=lambda d, _i: _ccr_loop_density(gas, d),
    )
    return profile


def plan_oc_dive(
    oc_gases,
    bottom_depth_m,
    bottom_time_min,
    gf_low,
    gf_high,
    desc_rate_mpm=20.0,
    asc_rate_deep_mpm=9.0,
    asc_rate_shallow_mpm=3.0,
    last_stop_m=3,
):
    """Plan a full OC dive from surface to surface.

    Selects the deepest-MOD gas for the bottom phase; switches to richer gases by
    MOD on ascent.  If the back gas is hypoxic at the surface (ppO2 < MIN_PPO2_BAR)
    a travel gas is selected automatically — the surface-breathable gas with the
    deepest MOD — and used for the descent until the back gas becomes breathable.
    Returns a DiveProfile with gas_switches populated.
    """
    sorted_gases = sorted(oc_gases, key=lambda g: g.mod_m)
    _select_gas = _make_select_gas(sorted_gases)

    bottom_gas = _select_gas(bottom_depth_m)

    # Travel-gas logic: if back gas is hypoxic near the surface, switch at the
    # shallowest 3 m grid depth where it becomes breathable.
    _floor_d = _gas_floor_depth(bottom_gas)
    _travel_gas = None
    _switch_depth = None
    if _floor_d > 0:
        _switch_depth = _round_up_to_3m(_floor_d)
        _travel_gas = _select_travel_gas(sorted_gases, _switch_depth)

    model, runtime_min, profile_points = _build_bottom_model(
        bottom_gas, bottom_depth_m, bottom_time_min, desc_rate_mpm, gf_low, gf_high,
        travel_gas=_travel_gas, travel_switch_depth_m=_switch_depth,
    )
    profile, gas_switches = _run_deco_ascent(
        model=model,
        start_depth=bottom_depth_m,
        gf_low=gf_low,
        gf_high=gf_high,
        gas_at_depth=_select_gas,
        asc_rate_deep_mpm=asc_rate_deep_mpm,
        asc_rate_shallow_mpm=asc_rate_shallow_mpm,
        last_stop_m=last_stop_m,
        runtime_min=runtime_min,
        profile_points=profile_points,
    )
    profile.gas_switches = gas_switches
    _annotate_tts(profile.profile_points, profile.total_time_min, gf_low, gf_high, _select_gas,
                  asc_rate_deep_mpm, asc_rate_shallow_mpm, last_stop_m)

    # Assign the correct gas to each profile point for ppO2/density annotation:
    # travel gas during pre-switch descent (if any), back gas during the remaining
    # descent and flat bottom, _select_gas on the ascent.
    _max_d = max((pt['d'] for pt in profile.profile_points), default=0)
    _seen_bottom = False
    _gas_per_pt = []
    for pt in profile.profile_points:
        if pt['d'] >= _max_d - 0.05:
            _seen_bottom = True
            _gas_per_pt.append(bottom_gas)
        elif not _seen_bottom:
            if _travel_gas is not None and pt['d'] < _switch_depth:
                _gas_per_pt.append(_travel_gas)
            else:
                _gas_per_pt.append(bottom_gas)
        else:
            _gas_per_pt.append(_select_gas(pt['d']))

    _annotate_physics(
        profile.profile_points,
        ppO2_at_depth=lambda d, i: _gas_per_pt[i].pp_o2(d / 10.0 + SURFACE_BAR),
        density_at_depth=lambda d, i: _gas_density_at_depth(_gas_per_pt[i], d),
    )
    return profile


def plan_oc_bailout(
    ccr_gas,
    bottom_depth_m,
    bottom_time_min,
    desc_rate_mpm,
    bailout_gases,
    gf_low,
    gf_high,
    asc_rate_deep_mpm=9.0,
    asc_rate_shallow_mpm=3.0,
    last_stop_m=3,
):
    """Plan an OC bailout ascent assuming the diver bails out at the end of bottom time.

    Rebuilds the tissue state from the CCR bottom phase, then runs the ascent
    on OC gases switching by MOD. Profile times are relative to bailout start (t=0).
    Returns BailoutProfile.
    """
    # Rebuild tissue state at end of CCR bottom
    model, _, _ = _build_bottom_model(
        ccr_gas, bottom_depth_m, bottom_time_min, desc_rate_mpm, gf_low, gf_high
    )

    sorted_gases = sorted(bailout_gases, key=lambda g: g.mod_m)
    _select_gas = _make_select_gas(sorted_gases)

    profile_points = []
    profile, gas_switches = _run_deco_ascent(
        model=model,
        start_depth=bottom_depth_m,
        gf_low=gf_low,
        gf_high=gf_high,
        gas_at_depth=_select_gas,
        asc_rate_deep_mpm=asc_rate_deep_mpm,
        asc_rate_shallow_mpm=asc_rate_shallow_mpm,
        last_stop_m=last_stop_m,
        runtime_min=0.0,
        profile_points=profile_points,
    )

    profile.gas_switches = gas_switches
    _annotate_physics(
        profile.profile_points,
        ppO2_at_depth=lambda d, _i: _select_gas(d).pp_o2(d / 10.0 + SURFACE_BAR),
        density_at_depth=lambda d, _i: _gas_density_at_depth(_select_gas(d), d),
    )
    return profile
