import copy
import math
from dataclasses import dataclass, field
from .buhlmann import BuhlmannModel, SURFACE_BAR


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


@dataclass
class BailoutProfile:
    stops: list = field(default_factory=list)
    total_time_min: float = 0.0
    profile_points: list = field(default_factory=list)
    tissue_saturations: list = field(default_factory=list)
    gas_switches: list = field(default_factory=list)  # [{depth_m, label}]


def _depth_to_p(depth_m):
    return depth_m / 10.0 + SURFACE_BAR


def _round_up_to_3m(depth_m):
    return int(math.ceil(depth_m / 3.0)) * 3


def _build_bottom_model(gas, bottom_depth_m, bottom_time_min, desc_rate_mpm, gf_low, gf_high):
    """Run descent + flat bottom time.

    Returns (model, runtime_min, profile_points) so the caller can fork the
    tissue state before the ascent: one branch for CCR, one for OC bailout.
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
    desc_time = bottom_depth_m / desc_rate_mpm
    flat_bottom_time = bottom_time_min - desc_time
    if flat_bottom_time < 0:
        raise ValueError("bottom_time_min must exceed descent time")
    model.load_segment(gas, 0.0, bottom_depth_m, desc_time)
    runtime_min += desc_time
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

    Selects the deepest-MOD gas for the bottom phase; switches to richer gases
    by MOD on ascent. Returns a DiveProfile with gas_switches populated.
    """
    sorted_gases = sorted(oc_gases, key=lambda g: g.mod_m)

    def _select_gas(depth_m):
        for g in sorted_gases:
            if depth_m <= g.mod_m:
                return g
        return sorted_gases[-1]

    bottom_gas = _select_gas(bottom_depth_m)
    model, runtime_min, profile_points = _build_bottom_model(
        bottom_gas, bottom_depth_m, bottom_time_min, desc_rate_mpm, gf_low, gf_high
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

    # Shallowest-MOD gas first: at any depth the diver uses the highest-O2 gas whose MOD is deep enough.
    sorted_gases = sorted(bailout_gases, key=lambda g: g.mod_m)

    def _select_gas(depth_m):
        for g in sorted_gases:
            if depth_m <= g.mod_m:
                return g
        return sorted_gases[-1]  # fallback: deepest-MOD gas (no valid gas above, use deepest available)

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

    return BailoutProfile(
        stops=profile.stops,
        total_time_min=profile.total_time_min,
        profile_points=profile.profile_points,
        tissue_saturations=profile.tissue_saturations,
        gas_switches=gas_switches,
    )
