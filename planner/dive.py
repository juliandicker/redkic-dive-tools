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
    profile_points: list = field(default_factory=list)  # [{t, d, c}] time/depth/ceiling (m)
    tissue_saturations: list = field(default_factory=list)  # saturation ratio per compartment


def _depth_to_p(depth_m):
    return depth_m / 10.0 + SURFACE_BAR


def _round_up_to_3m(depth_m):
    return int(math.ceil(depth_m / 3.0)) * 3


def plan_ccr_dive(
    gas,
    bottom_depth_m,
    bottom_time_min,
    gf_low,
    gf_high,
    desc_rate_mpm=20.0,
    asc_rate_deep_mpm=9.0,
    asc_rate_shallow_mpm=3.0,
):
    """Plan a CCR dive and return a DiveProfile with deco stops.

    bottom_time_min: run time from dive start until ascent begins (includes descent).
    gf_low and gf_high are fractions (0.0–1.0).
    Stops are at 3 m multiples, minimum 1 min each.
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
        })

    # Descent
    rec(0.0, 0.0)
    desc_time = bottom_depth_m / desc_rate_mpm
    flat_bottom_time = bottom_time_min - desc_time
    if flat_bottom_time < 0:
        raise ValueError("bottom_time_min must exceed descent time")
    model.load_segment(gas, 0.0, bottom_depth_m, desc_time)
    runtime_min += desc_time
    rec(bottom_depth_m, model.ceiling_m(gf_low))

    # Bottom time
    model.load_segment(gas, bottom_depth_m, bottom_depth_m, flat_bottom_time)
    runtime_min += flat_bottom_time
    rec(bottom_depth_m, model.ceiling_m(gf_low))

    # Ascent — step up the 3 m deco grid, loading tissues at each step.
    # The first deco stop emerges from the live ceiling rather than a snapshot
    # at the bottom, giving credit for off-gassing during the initial climb.
    stops = []
    current_depth = float(bottom_depth_m)

    def asc_rate(depth):
        return asc_rate_shallow_mpm if depth <= 6.0 else asc_rate_deep_mpm

    # Align to the standard 3 m stop grid (handles non-multiple bottom depths)
    grid_depth = int(math.floor(current_depth / 3.0)) * 3
    if grid_depth < current_depth:
        seg_time = (current_depth - float(grid_depth)) / asc_rate_deep_mpm
        model.load_segment(gas, current_depth, float(grid_depth), seg_time)
        runtime_min += seg_time
        current_depth = float(grid_depth)

    # Walk up the grid until the ceiling catches us (= first deco stop).
    # Record a profile point at each step so the chart shows the ceiling rising.
    first_stop_depth = None
    while True:
        ceiling = model.ceiling_m(gf_low)
        rec(current_depth, ceiling)
        if ceiling > 0.0 and _round_up_to_3m(ceiling) >= current_depth:
            first_stop_depth = max(3, int(current_depth))
            break
        if current_depth <= 3.0:
            break  # ceiling never caught us — no deco required
        next_depth = current_depth - 3.0
        seg_time = 3.0 / asc_rate(current_depth)
        model.load_segment(gas, current_depth, next_depth, seg_time)
        runtime_min += seg_time
        current_depth = next_depth

    if first_stop_depth is None:
        if current_depth > 0.0:
            seg_time = current_depth / asc_rate(current_depth)
            model.load_segment(gas, current_depth, 0.0, seg_time)
            runtime_min += seg_time
        rec(0.0, 0.0)
        return DiveProfile(
            stops=[],
            total_time_min=round(runtime_min, 1),
            profile_points=profile_points,
            tissue_saturations=model.tissue_saturations(gf_high),
        )

    # Work through stops from first_stop_depth down to 3 m.
    # At each stop, wait until the ceiling (unclamped, can go below surface) clears
    # the NEXT stop depth minus 0.5 m.
    stop_depth = first_stop_depth
    while stop_depth >= 3:
        # GF interpolated linearly from gf_low at first_stop_depth to gf_high at surface
        gf = gf_low + (gf_high - gf_low) * (first_stop_depth - stop_depth) / first_stop_depth
        gf = max(gf_low, min(gf_high, gf))

        next_stop = stop_depth - 3  # 0 for the final 3 m stop
        def _raw_ceiling_m(g):
            return (model.ceiling_bar(g) - SURFACE_BAR) * 10.0

        rec(stop_depth, model.ceiling_m(gf))  # start of stop

        stop_minutes = 0
        while _raw_ceiling_m(gf) >= next_stop - 0.5:
            model.load_segment(gas, stop_depth, stop_depth, 1.0)
            runtime_min += 1.0
            stop_minutes += 1
            if stop_minutes > 300:
                break  # safety guard against runaway

        rec(stop_depth, model.ceiling_m(gf))  # end of stop

        if stop_minutes > 0:
            stops.append(DecoStop(
                depth_m=stop_depth,
                time_min=stop_minutes,
                runtime_min=round(runtime_min, 1),
            ))

        next_depth = stop_depth - 3
        if next_depth > 0:
            asc_time = 3.0 / asc_rate(stop_depth)
            model.load_segment(gas, stop_depth, next_depth, asc_time)
            runtime_min += asc_time
        current_depth = float(next_depth)
        stop_depth = next_depth

    # Final ascent from 3 m (or current_depth) to surface
    if current_depth > 0.0:
        asc_time = current_depth / asc_rate_shallow_mpm
        model.load_segment(gas, current_depth, 0.0, asc_time)
        runtime_min += asc_time

    # Surface arrival (3 m → surface, ~1 min, shown on chart but not in total_time_min)
    profile_points.append({
        't': round(runtime_min + 3.0 / asc_rate_shallow_mpm, 2),
        'd': 0.0,
        'c': 0.0,
        'sats': model.tissue_saturations(gf_high),
    })

    return DiveProfile(
        stops=stops,
        total_time_min=round(runtime_min, 1),
        profile_points=profile_points,
        tissue_saturations=model.tissue_saturations(gf_high),
    )
