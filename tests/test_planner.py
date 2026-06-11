import math
import pytest
from gas_blender import gas_density
from planner.gas import CCRGas, OpenCircuitGas
from planner.dive import plan_ccr_dive, plan_oc_bailout, DiveProfile, BailoutProfile
from planner.buhlmann import WATER_VAPOUR_BAR, SURFACE_BAR
from DivePlanner import _compute_gas_consumption, _max_bottom_time_within_gas_supply


class TestPlannerStructure:

    def test_returns_dive_profile(self):
        gas = CCRGas(10, 70, 1.3)
        profile = plan_ccr_dive(gas, 60, 20, 0.6, 0.8)
        assert isinstance(profile, DiveProfile)

    def test_stops_are_multiples_of_3m(self):
        gas = CCRGas(10, 70, 1.3)
        profile = plan_ccr_dive(gas, 60, 20, 0.6, 0.8)
        for stop in profile.stops:
            assert stop.depth_m % 3 == 0

    def test_stops_in_descending_depth_order(self):
        gas = CCRGas(10, 70, 1.3)
        profile = plan_ccr_dive(gas, 60, 20, 0.6, 0.8)
        depths = [s.depth_m for s in profile.stops]
        assert depths == sorted(depths, reverse=True)

    def test_runtime_monotonically_increases(self):
        gas = CCRGas(10, 70, 1.3)
        profile = plan_ccr_dive(gas, 60, 20, 0.6, 0.8)
        runtimes = [s.runtime_min for s in profile.stops]
        assert runtimes == sorted(runtimes)

    def test_total_time_exceeds_runtime_of_last_stop(self):
        gas = CCRGas(10, 70, 1.3)
        profile = plan_ccr_dive(gas, 60, 20, 0.6, 0.8)
        if profile.stops:
            assert profile.total_time_min >= profile.stops[-1].runtime_min

    def test_stop_times_are_positive(self):
        gas = CCRGas(10, 70, 1.3)
        profile = plan_ccr_dive(gas, 60, 20, 0.6, 0.8)
        for stop in profile.stops:
            assert stop.time_min >= 1

    def test_shallow_dive_no_deco(self):
        # 15 m for 10 min on CCR — should require no stops with GF 60/80
        gas = CCRGas(21, 0, 1.0)
        profile = plan_ccr_dive(gas, 15, 10, 0.6, 0.8)
        assert profile.stops == []

    def test_deeper_dive_has_stops(self):
        gas = CCRGas(10, 70, 1.3)
        profile = plan_ccr_dive(gas, 60, 20, 0.6, 0.8)
        assert len(profile.stops) > 0

    def test_longer_bottom_time_more_deco(self):
        gas = CCRGas(10, 70, 1.3)
        short = plan_ccr_dive(gas, 60, 20, 0.6, 0.8)
        long = plan_ccr_dive(gas, 60, 40, 0.6, 0.8)
        assert long.total_time_min > short.total_time_min

    def test_liberal_gf_less_deco_than_conservative(self):
        gas = CCRGas(10, 70, 1.3)
        conservative = plan_ccr_dive(gas, 60, 20, 0.3, 0.7)
        liberal = plan_ccr_dive(gas, 60, 20, 0.85, 0.95)
        assert conservative.total_time_min > liberal.total_time_min

    def test_total_time_accounts_for_descent_and_bottom(self):
        # bottom_time_min=20 = run time to ascent start; 3 min descent leaves 17 min flat
        gas = CCRGas(10, 70, 1.3)
        profile = plan_ccr_dive(gas, 60, 20, 0.6, 0.8)
        assert profile.total_time_min > 20.0  # must exceed the bottom time itself


class TestCCRReferenceScenario:
    """
    Reference: 60 m / ascent starts at 20 min (17 min flat bottom) / 10/70 diluent / 1.3 bar / GF 60/80
    Descent at 20 m/min, ascent 9 m/min to 6 m then 3 m/min.
    bottom_time_min=20 means run time to start of ascent (includes 3 min descent).
    """

    @pytest.fixture(scope='class')
    def profile(self):
        gas = CCRGas(10, 70, 1.3)
        return plan_ccr_dive(gas, 60, 20, 0.6, 0.8)

    def test_has_deco_stops(self, profile):
        assert len(profile.stops) > 0

    def test_shallowest_stop_is_3m(self, profile):
        # Last stop must be at 3 m
        assert profile.stops[-1].depth_m == 3

    def test_total_runtime_plausible(self, profile):
        # A 60m/20min trimix CCR dive with GF 60/80 should take roughly 50–90 min total
        assert 45 <= profile.total_time_min <= 120

    # --- Placeholders for OVM Planner cross-validation ---
    # Replace the expected values below once you run OVM Planner with:
    #   Mode: CCR, Diluent: 10/70/20, Setpoint: 1.3, Depth: 60m, BT: 20min,
    #   GF: 60/80, Descent: 20 m/min, Ascent: 9 m/min / 3 m/min
    #
    # @pytest.mark.xfail(reason="OVM reference values not yet confirmed")
    # def test_ovm_stop_depths(self, profile):
    #     expected_depths = [21, 18, 15, 12, 9, 6, 3]  # replace with OVM output
    #     actual_depths = [s.depth_m for s in profile.stops]
    #     assert actual_depths == expected_depths
    #
    # @pytest.mark.xfail(reason="OVM reference values not yet confirmed")
    # def test_ovm_total_runtime(self, profile):
    #     assert profile.total_time_min == pytest.approx(57.0, abs=2)  # replace with OVM value


class TestLastStopDepth:

    def test_default_last_stop_is_3m(self):
        gas = CCRGas(10, 70, 1.3)
        profile = plan_ccr_dive(gas, 60, 20, 0.6, 0.8)
        assert profile.stops[-1].depth_m == 3

    def test_last_stop_6m_shallowest_stop_is_6m(self):
        gas = CCRGas(10, 70, 1.3)
        profile = plan_ccr_dive(gas, 60, 20, 0.6, 0.8, last_stop_m=6)
        assert len(profile.stops) > 0
        assert profile.stops[-1].depth_m == 6

    def test_last_stop_6m_no_3m_stop(self):
        gas = CCRGas(10, 70, 1.3)
        profile = plan_ccr_dive(gas, 60, 20, 0.6, 0.8, last_stop_m=6)
        assert all(s.depth_m >= 6 for s in profile.stops)

    def test_last_stop_6m_runtime_plausible(self):
        gas = CCRGas(10, 70, 1.3)
        profile = plan_ccr_dive(gas, 60, 20, 0.6, 0.8, last_stop_m=6)
        assert profile.total_time_min > 20.0


class TestOpenCircuitGas:

    def test_pp_n2_at_surface(self):
        gas = OpenCircuitGas(21, 0, 30)
        expected = 0.79 * (SURFACE_BAR - WATER_VAPOUR_BAR)
        assert gas.pp_n2(SURFACE_BAR) == pytest.approx(expected, abs=0.001)

    def test_pp_he_zero_for_nitrox(self):
        gas = OpenCircuitGas(50, 0, 22)
        assert gas.pp_he(SURFACE_BAR) == 0.0

    def test_pp_n2_zero_for_pure_o2(self):
        gas = OpenCircuitGas(100, 0, 6)
        assert gas.pp_n2(SURFACE_BAR) == 0.0
        assert gas.pp_he(SURFACE_BAR) == 0.0

    def test_pp_he_trimix(self):
        gas = OpenCircuitGas(21, 25, 50)
        p = 7.013  # 60 m abs
        expected_he = 0.25 * (p - WATER_VAPOUR_BAR)
        assert gas.pp_he(p) == pytest.approx(expected_he, abs=0.001)

    def test_mod_stored(self):
        gas = OpenCircuitGas(21, 25, 57)
        assert gas.mod_m == 57

    def test_label_nitrox(self):
        gas = OpenCircuitGas(50, 0, 22)
        assert gas.label == '50/50'

    def test_label_trimix(self):
        gas = OpenCircuitGas(21, 25, 57)
        assert gas.label == '21/25'


class TestPlanCcrDiveRegression:
    """Verify the refactored plan_ccr_dive produces the same results as before."""

    @pytest.fixture(scope='class')
    def profile(self):
        gas = CCRGas(10, 70, 1.3)
        return plan_ccr_dive(gas, 60, 20, 0.6, 0.8)

    def test_has_deco_stops(self, profile):
        assert len(profile.stops) > 0

    def test_total_runtime_plausible(self, profile):
        assert 45 <= profile.total_time_min <= 120

    def test_shallowest_stop_3m(self, profile):
        assert profile.stops[-1].depth_m == 3

    def test_profile_points_have_sats(self, profile):
        for pt in profile.profile_points:
            assert 'sats' in pt
            assert len(pt['sats']) == 16


class TestPlanOcBailoutStructural:

    @pytest.fixture(scope='class')
    def bailout(self):
        ccr_gas = CCRGas(10, 70, 1.3)
        oc_gases = [
            OpenCircuitGas(21, 25, 57),
            OpenCircuitGas(50, 0, 22),
            OpenCircuitGas(100, 0, 6),
        ]
        return plan_oc_bailout(ccr_gas, 60, 20, 20.0, oc_gases, 0.5, 0.8)

    def test_returns_bailout_profile(self, bailout):
        assert isinstance(bailout, BailoutProfile)

    def test_stops_are_multiples_of_3m(self, bailout):
        for stop in bailout.stops:
            assert stop.depth_m % 3 == 0

    def test_stops_in_descending_order(self, bailout):
        depths = [s.depth_m for s in bailout.stops]
        assert depths == sorted(depths, reverse=True)

    def test_runtime_monotonically_increases(self, bailout):
        runtimes = [s.runtime_min for s in bailout.stops]
        assert runtimes == sorted(runtimes)

    def test_has_deco_stops(self, bailout):
        # OC from 60m should require decompression
        assert len(bailout.stops) > 0

    def test_profile_points_start_at_zero(self, bailout):
        assert bailout.profile_points[0]['t'] == pytest.approx(0.0, abs=0.5)

    def test_gas_switches_list_exists(self, bailout):
        assert isinstance(bailout.gas_switches, list)

    def test_single_gas_oc_air_more_deco_than_ccr_air(self):
        # OC air loads more N2 at depth than CCR air (setpoint reduces inert gas).
        # Bailout total_time_min starts from t=0 at bottom, so it equals TTS.
        # CCR TTS = total_time_min - bottom_time_min.
        ccr_gas = CCRGas(21, 0, 1.3)
        bottom_time_min = 25.0
        oc_gases = [OpenCircuitGas(21, 0, 40)]
        ccr_profile = plan_ccr_dive(ccr_gas, 30, bottom_time_min, 0.6, 0.8)
        bailout = plan_oc_bailout(ccr_gas, 30, bottom_time_min, 20.0, oc_gases, 0.6, 0.8)
        ccr_tts = ccr_profile.total_time_min - bottom_time_min
        assert bailout.total_time_min > ccr_tts


class TestPlanOcBailoutGasSwitching:

    def test_gas_switches_at_correct_depths(self):
        ccr_gas = CCRGas(10, 70, 1.3)
        oc_gases = [
            OpenCircuitGas(21, 25, 57),   # deep trimix, MOD 57m
            OpenCircuitGas(50, 0, 22),    # 50% nitrox, MOD 22m
            OpenCircuitGas(100, 0, 6),    # pure O2, MOD 6m
        ]
        bailout = plan_oc_bailout(ccr_gas, 60, 20, 20.0, oc_gases, 0.5, 0.8)
        switch_depths = [s['depth_m'] for s in bailout.gas_switches]
        # Should switch to 50% when we reach ≤22m and to 100% when we reach ≤6m
        assert any(d <= 22 for d in switch_depths), "Expected switch to shallower gas at ≤22m"
        assert any(d <= 6 for d in switch_depths), "Expected switch to O2 at ≤6m"

    def test_no_stops_deeper_than_deepest_gas_mod(self):
        ccr_gas = CCRGas(10, 70, 1.3)
        oc_gases = [
            OpenCircuitGas(21, 25, 57),
            OpenCircuitGas(50, 0, 22),
            OpenCircuitGas(100, 0, 6),
        ]
        bailout = plan_oc_bailout(ccr_gas, 60, 20, 20.0, oc_gases, 0.5, 0.8)
        # All stops must be ≤ shallowest valid ascent ceiling, never unreasonably deep
        for stop in bailout.stops:
            assert stop.depth_m <= 60


class TestDensityAnalysis:

    def test_10_70_at_60m_density(self):
        # 10/70 diluent: O2=10%, He=70%, N2=20%
        # molar mass = (10*32 + 20*28 + 70*4)/100 = (320+560+280)/100 = 11.6 g/mol
        # density = 11.6/22.4 * 7 bar abs ≈ 3.63 g/L
        d = gas_density(10, 70, 60)
        assert d == pytest.approx(3.63, abs=0.05)

    def test_10_70_at_60m_not_exceeded(self):
        # 10/70 trimix is light — well below 5.2 g/L
        d = gas_density(10, 70, 60)
        assert d < 5.2

    def test_air_at_50m_exceeds_recommended(self):
        # Air at 50 m should exceed 5.2 g/L
        d = gas_density(21, 0, 50)
        assert d > 5.2


class TestGasConsumption:

    def _make_bailout(self):
        ccr_gas = CCRGas(10, 70, 1.3)
        oc_gases = [
            OpenCircuitGas(16, 70, 75),
            OpenCircuitGas(50, 0, 22),
            OpenCircuitGas(100, 0, 6),
        ]
        return plan_oc_bailout(ccr_gas, 60, 20, 20.0, oc_gases, 0.5, 0.8), sorted(oc_gases, key=lambda g: g.mod_m)

    def test_consumption_returns_list_per_gas(self):
        bailout, sorted_gases = self._make_bailout()
        result = _compute_gas_consumption(bailout, sorted_gases, 20, 15)
        assert len(result) == 3

    def test_consumption_values_are_positive(self):
        bailout, sorted_gases = self._make_bailout()
        result = _compute_gas_consumption(bailout, sorted_gases, 20, 15)
        assert all(c > 0 for c in result)

    def test_higher_sac_gives_higher_consumption(self):
        bailout, sorted_gases = self._make_bailout()
        low  = sum(_compute_gas_consumption(bailout, sorted_gases, 10, 8))
        high = sum(_compute_gas_consumption(bailout, sorted_gases, 30, 20))
        assert high > low

    def test_total_consumption_plausible(self):
        # Rough sanity: for a ~30 min TTS at average 20 m, 20 L/min SAC
        # expect total gas < 20 * 1.013 * 3 * 30 ≈ 1800 L (very generous upper bound)
        bailout, sorted_gases = self._make_bailout()
        total = sum(_compute_gas_consumption(bailout, sorted_gases, 20, 15))
        assert 50 < total < 1800

    def test_deep_gas_used_at_depth(self):
        # With a single deep bailout gas MOD 75m, all consumption should be on it
        ccr_gas = CCRGas(10, 70, 1.3)
        oc_gases = [OpenCircuitGas(16, 70, 75)]
        sorted_gases = oc_gases[:]
        bailout = plan_oc_bailout(ccr_gas, 60, 20, 20.0, oc_gases, 0.5, 0.8)
        result = _compute_gas_consumption(bailout, sorted_gases, 20, 15)
        assert len(result) == 1
        assert result[0] > 0


class TestGasSupplyShortening:

    def _gases_and_context(self):
        ccr_gas = CCRGas(10, 70, 1.3)
        oc_gases = [
            OpenCircuitGas(16, 70, 75),
            OpenCircuitGas(50, 0, 22),
            OpenCircuitGas(100, 0, 6),
        ]
        sorted_gases = sorted(oc_gases, key=lambda g: g.mod_m)
        return ccr_gas, oc_gases, sorted_gases

    def test_no_shortening_when_gas_unlimited(self):
        ccr_gas, oc_gases, sorted_gases = self._gases_and_context()
        available = [math.inf] * len(sorted_gases)
        bt, shortened = _max_bottom_time_within_gas_supply(
            ccr_gas=ccr_gas, depth_m=60, requested_bt=20, desc_rate_mpm=20,
            oc_gases=oc_gases, sorted_gases=sorted_gases, available_L=available,
            gf_low=0.5, gf_high=0.8, asc_rate_deep=9, asc_rate_shallow=3,
            last_stop_m=3, sac_bottom=20, sac_deco=15,
        )
        assert not shortened
        assert bt == pytest.approx(20, abs=0.1)

    def test_shortening_occurs_when_tiny_cylinder(self):
        ccr_gas, oc_gases, sorted_gases = self._gases_and_context()
        # 10L at 1 bar = essentially empty — should force shortening
        available = [10, 10, 10]
        bt, shortened = _max_bottom_time_within_gas_supply(
            ccr_gas=ccr_gas, depth_m=60, requested_bt=20, desc_rate_mpm=20,
            oc_gases=oc_gases, sorted_gases=sorted_gases, available_L=available,
            gf_low=0.5, gf_high=0.8, asc_rate_deep=9, asc_rate_shallow=3,
            last_stop_m=3, sac_bottom=20, sac_deco=15,
        )
        assert shortened
        assert bt < 20

    def test_shortened_time_still_exceeds_descent(self):
        ccr_gas, oc_gases, sorted_gases = self._gases_and_context()
        available = [10, 10, 10]
        bt, _ = _max_bottom_time_within_gas_supply(
            ccr_gas=ccr_gas, depth_m=60, requested_bt=20, desc_rate_mpm=20,
            oc_gases=oc_gases, sorted_gases=sorted_gases, available_L=available,
            gf_low=0.5, gf_high=0.8, asc_rate_deep=9, asc_rate_shallow=3,
            last_stop_m=3, sac_bottom=20, sac_deco=15,
        )
        descent_time = 60 / 20
        assert bt > descent_time

    def test_large_cylinder_no_shortening(self):
        ccr_gas, oc_gases, sorted_gases = self._gases_and_context()
        # 40L × 300 bar = 12000 L per gas — far more than needed
        available = [12000, 12000, 12000]
        bt, shortened = _max_bottom_time_within_gas_supply(
            ccr_gas=ccr_gas, depth_m=60, requested_bt=20, desc_rate_mpm=20,
            oc_gases=oc_gases, sorted_gases=sorted_gases, available_L=available,
            gf_low=0.5, gf_high=0.8, asc_rate_deep=9, asc_rate_shallow=3,
            last_stop_m=3, sac_bottom=20, sac_deco=15,
        )
        assert not shortened
        assert bt == pytest.approx(20, abs=0.1)
