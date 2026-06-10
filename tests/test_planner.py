import pytest
from gas_blender import gas_density
from planner.gas import CCRGas
from planner.dive import plan_ccr_dive, DiveProfile


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
