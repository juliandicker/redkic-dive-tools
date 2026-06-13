"""Unit tests for OC descent/ascent gas selection rules.

Rules (per decompression expert analysis):
  - Breathable window: MIN_PPO2_BAR (0.18) ≤ ppO2 ≤ MOD cap (1.4 bottom / 1.6 deco)
  - Travel gas on descent: surface-breathable gas with deepest MOD that can reach
    the back-gas floor depth; chosen to minimise narcosis (most helium).
  - Back-gas switch: ceil to next 3 m grid ≥ floor_depth of back gas.
  - Ascent gas: richest gas (highest fO2) within the breathable window at current depth.
"""
import math
import pytest

from planner.buhlmann import SURFACE_BAR, WATER_VAPOUR_BAR
from planner.gas import OpenCircuitGas
from planner.dive import (
    MIN_PPO2_BAR,
    _gas_floor_depth,
    _make_select_gas,
    _round_up_to_3m,
    _select_travel_gas,
    plan_oc_dive,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def gas_13_75():
    """Hypoxic deep trimix — cannot be breathed at the surface."""
    return OpenCircuitGas(13, 75, 114)  # MOD at ~1.4 bar: ~114m


@pytest.fixture
def gas_21_35():
    """Normoxic travel trimix — breathable at the surface, narc-reducing."""
    return OpenCircuitGas(21, 35, 57)


@pytest.fixture
def gas_50_0():
    """N50 deco gas."""
    return OpenCircuitGas(50, 0, 22)


@pytest.fixture
def gas_100():
    """Pure O2 deco gas."""
    return OpenCircuitGas(100, 0, 6)


# ── _gas_floor_depth ──────────────────────────────────────────────────────────

class TestGasFloorDepth:

    def test_hypoxic_13_75_has_positive_floor(self, gas_13_75):
        # 13% O2: ppO2 at surface ≈ 0.124 bar < 0.18 → floor is positive
        floor = _gas_floor_depth(gas_13_75)
        assert floor > 0

    def test_13_75_floor_depth_value(self, gas_13_75):
        # p_abs at floor = MIN_PPO2_BAR / fo2 + WATER_VAPOUR_BAR
        # depth = 10 * (p_abs - SURFACE_BAR) = 10*(0.18/0.13 + 0.0627 - 1.013)
        expected = 10.0 * (MIN_PPO2_BAR / 0.13 + WATER_VAPOUR_BAR - SURFACE_BAR)
        assert _gas_floor_depth(gas_13_75) == pytest.approx(expected, abs=0.01)

    def test_normoxic_21_35_has_negative_floor(self, gas_21_35):
        # 21% O2: ppO2 at surface ≈ 0.200 bar > 0.18 → breathable at surface
        assert _gas_floor_depth(gas_21_35) < 0

    def test_n50_has_negative_floor(self, gas_50_0):
        # 50% O2 well above floor at any sensible depth
        assert _gas_floor_depth(gas_50_0) < 0

    def test_floor_depth_at_exact_threshold(self, gas_13_75):
        # At the floor depth the gas must reach exactly MIN_PPO2_BAR
        floor_d = _gas_floor_depth(gas_13_75)
        p_abs = floor_d / 10.0 + SURFACE_BAR
        ppo2 = gas_13_75.pp_o2(p_abs)
        assert ppo2 == pytest.approx(MIN_PPO2_BAR, abs=1e-6)

    def test_not_breathable_1m_above_floor(self, gas_13_75):
        floor_d = _gas_floor_depth(gas_13_75)
        shallower = floor_d - 1.0
        p_abs = shallower / 10.0 + SURFACE_BAR
        assert gas_13_75.pp_o2(p_abs) < MIN_PPO2_BAR

    def test_breathable_1m_below_floor(self, gas_13_75):
        floor_d = _gas_floor_depth(gas_13_75)
        deeper = floor_d + 1.0
        p_abs = deeper / 10.0 + SURFACE_BAR
        assert gas_13_75.pp_o2(p_abs) > MIN_PPO2_BAR

    def test_18_45_floor_below_one_grid_stop(self):
        # 18/45 trimix: floor depth ≈ 0.5 m — less than one 3 m grid stop
        gas = OpenCircuitGas(18, 45, 90)
        floor = _gas_floor_depth(gas)
        assert 0 < floor < 3.0


# ── _select_travel_gas ────────────────────────────────────────────────────────

class TestSelectTravelGas:

    def _make_sorted(self, gases):
        return sorted(gases, key=lambda g: g.mod_m)

    def test_picks_deepest_mod_surface_breathable(self, gas_13_75, gas_21_35, gas_50_0, gas_100):
        # 13/75 back gas floor ≈ 4.3 m → switch depth = 6 m
        switch_depth = _round_up_to_3m(_gas_floor_depth(gas_13_75))
        gases = self._make_sorted([gas_13_75, gas_21_35, gas_50_0, gas_100])
        travel = _select_travel_gas(gases, switch_depth)
        # 21/35 has deepest MOD (57m) among surface-breathable candidates
        assert travel is gas_21_35

    def test_does_not_pick_hypoxic_back_gas_as_travel(self, gas_13_75, gas_21_35, gas_50_0, gas_100):
        switch_depth = _round_up_to_3m(_gas_floor_depth(gas_13_75))
        gases = self._make_sorted([gas_13_75, gas_21_35, gas_50_0, gas_100])
        travel = _select_travel_gas(gases, switch_depth)
        assert travel is not gas_13_75

    def test_does_not_pick_gas_with_too_shallow_mod(self, gas_13_75, gas_100):
        # Only O2 (MOD 6m) and 13/75 configured; switch depth = 6m.
        # O2 has MOD=6 >= switch_depth=6 so it qualifies, but no trimix available.
        switch_depth = _round_up_to_3m(_gas_floor_depth(gas_13_75))
        gases = self._make_sorted([gas_13_75, gas_100])
        travel = _select_travel_gas(gases, switch_depth)
        assert travel is gas_100  # only surface-breathable candidate with MOD >= switch_depth

    def test_returns_none_when_no_surface_breathable_gas(self, gas_13_75):
        # Gas list contains only the hypoxic back gas
        gases = [gas_13_75]
        travel = _select_travel_gas(gases, 6)
        assert travel is None

    def test_normoxic_only_dive_no_travel_gas_needed(self, gas_21_35):
        # 21/35 is surface-breathable: _gas_floor_depth < 0 → no travel gas logic triggered
        assert _gas_floor_depth(gas_21_35) < 0

    def test_switch_depth_for_13_75_is_6m(self, gas_13_75):
        # floor ≈ 4.3 m → ceil to 3m grid → 6 m
        floor = _gas_floor_depth(gas_13_75)
        switch = _round_up_to_3m(floor)
        assert switch == 6

    def test_back_gas_breathable_at_switch_depth(self, gas_13_75):
        switch = _round_up_to_3m(_gas_floor_depth(gas_13_75))
        p_abs = switch / 10.0 + SURFACE_BAR
        assert gas_13_75.pp_o2(p_abs) >= MIN_PPO2_BAR


# ── _make_select_gas (window test) ────────────────────────────────────────────

class TestMakeSelectGasWindowTest:

    def test_hypoxic_gas_excluded_at_surface(self, gas_13_75, gas_21_35):
        sorted_gases = sorted([gas_13_75, gas_21_35], key=lambda g: g.mod_m)
        select_gas = _make_select_gas(sorted_gases)
        # At surface: 13/75 ppO2 < 0.18 → excluded; 21/35 selected
        result = select_gas(0)
        assert result is gas_21_35

    def test_hypoxic_gas_excluded_above_its_floor(self, gas_13_75, gas_21_35):
        sorted_gases = sorted([gas_13_75, gas_21_35], key=lambda g: g.mod_m)
        select_gas = _make_select_gas(sorted_gases)
        # 3m is above the 13/75 floor (~4.3m); still excluded
        result = select_gas(3)
        assert result is gas_21_35

    def test_back_gas_selected_at_its_floor_depth(self, gas_13_75, gas_21_35):
        sorted_gases = sorted([gas_13_75, gas_21_35], key=lambda g: g.mod_m)
        select_gas = _make_select_gas(sorted_gases)
        # At grid switch depth (6m) 13/75 is breathable; 21/35 is richer → 21/35 selected
        result = select_gas(6)
        assert result is gas_21_35

    def test_richest_gas_within_mod_on_ascent(self, gas_50_0, gas_100):
        # At 6m both 50/0 and O2 are within MOD; O2 is richer
        sorted_gases = sorted([gas_50_0, gas_100], key=lambda g: g.mod_m)
        select_gas = _make_select_gas(sorted_gases)
        result = select_gas(6)
        assert result is gas_100

    def test_gas_outside_mod_excluded_on_ascent(self, gas_50_0, gas_100):
        # At 9m O2 (MOD 6m) is too deep; only 50/0 (MOD 22m) is valid
        sorted_gases = sorted([gas_50_0, gas_100], key=lambda g: g.mod_m)
        select_gas = _make_select_gas(sorted_gases)
        result = select_gas(9)
        assert result is gas_50_0


# ── plan_oc_dive with hypoxic back gas ────────────────────────────────────────

class TestPlanOcDiveHypoxicBackGas:
    """Integration tests: hypoxic 13/75 back gas + 21/35 travel + 50/0 + O2."""

    def _gases(self):
        return [
            OpenCircuitGas(13, 75, 114),  # back gas
            OpenCircuitGas(21, 35, 57),   # travel gas
            OpenCircuitGas(50, 0, 22),    # deco
            OpenCircuitGas(100, 0, 6),    # deco O2
        ]

    def test_profile_includes_switch_depth_point(self):
        # A profile point at the travel→back gas switch depth (6m) must exist
        profile = plan_oc_dive(self._gases(), 60, 25, 0.5, 0.8)
        depths = [pt['d'] for pt in profile.profile_points]
        assert 6.0 in depths

    def test_surface_point_ppo2_uses_travel_gas(self):
        # At d=0, the gas is the travel (21/35); ppO2 ≈ 0.21*(SURFACE_BAR-WVB)
        profile = plan_oc_dive(self._gases(), 60, 25, 0.5, 0.8)
        surface_pt = profile.profile_points[0]
        assert surface_pt['d'] == 0.0
        expected_ppo2 = 0.21 * (SURFACE_BAR - WATER_VAPOUR_BAR)
        assert surface_pt['ppO2'] == pytest.approx(expected_ppo2, abs=0.002)

    def test_surface_point_ppo2_not_hypoxic(self):
        profile = plan_oc_dive(self._gases(), 60, 25, 0.5, 0.8)
        surface_ppo2 = profile.profile_points[0]['ppO2']
        assert surface_ppo2 >= MIN_PPO2_BAR

    def test_back_gas_breathable_at_switch_point(self):
        # At the switch depth profile point, ppO2 must be ≥ MIN_PPO2_BAR
        profile = plan_oc_dive(self._gases(), 60, 25, 0.5, 0.8)
        switch_pt = next(pt for pt in profile.profile_points if pt['d'] == 6.0)
        assert switch_pt['ppO2'] >= MIN_PPO2_BAR

    def test_returns_valid_profile(self):
        profile = plan_oc_dive(self._gases(), 60, 25, 0.5, 0.8)
        assert len(profile.stops) > 0
        assert profile.total_time_min > 25

    def test_stops_remain_multiples_of_3m(self):
        profile = plan_oc_dive(self._gases(), 60, 25, 0.5, 0.8)
        for stop in profile.stops:
            assert stop.depth_m % 3 == 0


class TestPlanOcDiveNormoxicBackGas:
    """No travel gas needed when the back gas is surface-breathable."""

    def test_no_extra_switch_point_for_normoxic_back_gas(self):
        # 21/35 only — no travel gas → profile has surface point, bottom point, ascent
        gases = [OpenCircuitGas(21, 35, 57)]
        profile = plan_oc_dive(gases, 50, 25, 0.5, 0.8)
        # The first non-surface point should be at bottom, not at an intermediate switch depth
        pts = profile.profile_points
        assert pts[0]['d'] == 0.0
        assert pts[1]['d'] == 50.0  # jump straight to bottom

    def test_surface_point_ppo2_for_normoxic(self):
        gases = [OpenCircuitGas(21, 35, 57)]
        profile = plan_oc_dive(gases, 50, 25, 0.5, 0.8)
        surface_pt = profile.profile_points[0]
        expected = 0.21 * (SURFACE_BAR - WATER_VAPOUR_BAR)
        assert surface_pt['ppO2'] == pytest.approx(expected, abs=0.002)
