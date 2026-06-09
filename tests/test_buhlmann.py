import math
import pytest
from planner.buhlmann import (
    Tissue, BuhlmannModel, schreiner,
    ZHL16C, WATER_VAPOUR_BAR, SURFACE_BAR, _FN2_AIR,
)
from planner.gas import CCRGas


class _ConstGas:
    """Minimal gas stub for testing: constant inspired pp regardless of depth."""
    def __init__(self, pp_n2, pp_he=0.0):
        self._pp_n2 = pp_n2
        self._pp_he = pp_he

    def pp_n2(self, p_abs):
        return self._pp_n2

    def pp_he(self, p_abs):
        return self._pp_he


class TestSchreiner:

    def test_constant_depth_equilibrium(self):
        # After many half-times at constant pressure the tissue approaches p_gas
        p_gas = 2.5
        result = schreiner(0.0, p_gas, 500.0, 5.0, 0.0)
        assert result == pytest.approx(p_gas, abs=0.001)

    def test_constant_depth_partial_loading(self):
        # After exactly one half-time at constant depth, halfway between start and p_gas
        ht = 8.0
        p_begin = 0.0
        p_gas = 1.0
        result = schreiner(p_begin, p_gas, ht, ht, 0.0)
        assert result == pytest.approx(0.5, abs=0.001)

    def test_zero_duration_returns_start(self):
        assert schreiner(1.23, 2.0, 0.0, 5.0, 0.0) == pytest.approx(1.23, abs=1e-9)

    def test_ascent_rate(self):
        # Rising at 0.1 bar/min for 10 min from 3 bar inspired, starting at 2 bar tissue
        # Rate lowers inspired pp over time — result should be between 2 and 3 bar
        result = schreiner(2.0, 3.0, 10.0, 27.0, -0.1)
        assert 2.0 < result < 3.0


class TestTissue:

    def test_surface_initialisation(self):
        t = Tissue(*ZHL16C[0])
        expected = _FN2_AIR * (SURFACE_BAR - WATER_VAPOUR_BAR)
        assert t.pn2 == pytest.approx(expected, abs=1e-6)
        assert t.phe == pytest.approx(0.0)

    def test_ceiling_gf1_n2_only(self):
        # Saturate fastest tissue at 7 bar N2, verify ceiling formula by hand
        t = Tissue(*ZHL16C[0])
        t.pn2 = 7.0
        t.phe = 0.0
        ht_n2, a_n2, b_n2 = ZHL16C[0][0], ZHL16C[0][1], ZHL16C[0][2]
        expected = (7.0 - a_n2) / (1.0 / b_n2 - 1.0 + 1.0)  # gf=1 simplifies denominator
        # Bühlmann formula: (p - a*gf) / (gf/b - gf + 1) with gf=1 → (p - a) / (1/b)
        expected = (7.0 - a_n2) * b_n2
        assert t.ceiling(1.0) == pytest.approx(expected, abs=0.001)

    def test_ceiling_lower_gf_produces_deeper_ceiling(self):
        t = Tissue(*ZHL16C[0])
        t.pn2 = 5.0
        assert t.ceiling(0.3) > t.ceiling(1.0)

    def test_ceiling_unsaturated_tissue_near_zero(self):
        t = Tissue(*ZHL16C[0])
        # Surface saturation — ceiling should be at or below surface
        assert t.ceiling(1.0) <= SURFACE_BAR + 0.01

    def test_load_increases_pn2_at_depth(self):
        t = Tissue(*ZHL16C[0])
        initial = t.pn2
        pp = 2.0  # higher than surface
        t.load(pp, 0.0, pp, 0.0, 30.0)
        assert t.pn2 > initial

    def test_mixed_gas_weighted_ab(self):
        # Equal N2 and He loading → a/b weighted 50/50
        t = Tissue(*ZHL16C[0])
        t.pn2 = 1.0
        t.phe = 1.0
        expected_a = (t.a_n2 * 1.0 + t.a_he * 1.0) / 2.0
        expected_b = (t.b_n2 * 1.0 + t.b_he * 1.0) / 2.0
        ceiling_bar = (2.0 - expected_a * 1.0) / (1.0 / expected_b - 1.0 + 1.0)
        assert t.ceiling(1.0) == pytest.approx(ceiling_bar, abs=0.001)


class TestBuhlmannModel:

    def test_surface_init_all_tissues(self):
        model = BuhlmannModel()
        expected_pn2 = _FN2_AIR * (SURFACE_BAR - WATER_VAPOUR_BAR)
        for t in model.tissues:
            assert t.pn2 == pytest.approx(expected_pn2, abs=1e-6)
            assert t.phe == pytest.approx(0.0)

    def test_ceiling_m_at_surface_is_zero(self):
        model = BuhlmannModel()
        assert model.ceiling_m(1.0) == pytest.approx(0.0, abs=0.01)

    def test_load_segment_increases_ceiling(self):
        # pp_n2=4.0 saturates fast tissues above M-value, producing a positive deco ceiling
        model = BuhlmannModel()
        gas = _ConstGas(pp_n2=4.0)
        model.load_segment(gas, 30.0, 30.0, 60.0)
        assert model.ceiling_m(1.0) > 0.0

    def test_copy_is_independent(self):
        model = BuhlmannModel()
        gas = _ConstGas(pp_n2=2.0)
        model.load_segment(gas, 30.0, 30.0, 20.0)
        clone = model.copy()
        model.load_segment(gas, 30.0, 30.0, 100.0)
        assert model.ceiling_m(1.0) > clone.ceiling_m(1.0)

    def test_sixteen_compartments(self):
        model = BuhlmannModel()
        assert len(model.tissues) == 16


class TestCCRGas:

    def test_pp_n2_at_depth(self):
        # 10/70 diluent, 1.3 bar setpoint, at 7 bar abs (60 m)
        gas = CCRGas(10, 70, 1.3)
        p_abs = 7.0
        pp_inert = p_abs - 1.3 - WATER_VAPOUR_BAR
        fn2 = 0.20
        fhe = 0.70
        expected = pp_inert * fn2 / (fn2 + fhe)
        assert gas.pp_n2(p_abs) == pytest.approx(expected, abs=1e-6)

    def test_pp_he_at_depth(self):
        gas = CCRGas(10, 70, 1.3)
        p_abs = 7.0
        pp_inert = p_abs - 1.3 - WATER_VAPOUR_BAR
        fn2 = 0.20
        fhe = 0.70
        expected = pp_inert * fhe / (fn2 + fhe)
        assert gas.pp_he(p_abs) == pytest.approx(expected, abs=1e-6)

    def test_pp_inert_zero_at_setpoint(self):
        gas = CCRGas(10, 70, 1.3)
        # At p_abs = setpoint + water_vapour, inert = 0
        p_abs = 1.3 + WATER_VAPOUR_BAR
        assert gas.pp_n2(p_abs) == pytest.approx(0.0, abs=1e-9)
        assert gas.pp_he(p_abs) == pytest.approx(0.0, abs=1e-9)

    def test_pp_inert_clamped_to_zero_below_setpoint(self):
        gas = CCRGas(10, 70, 1.3)
        assert gas.pp_n2(0.5) == pytest.approx(0.0)
        assert gas.pp_he(0.5) == pytest.approx(0.0)

    def test_n2_he_ratio_preserved(self):
        gas = CCRGas(10, 70, 1.3)
        p_abs = 5.0
        ratio = gas.pp_n2(p_abs) / gas.pp_he(p_abs)
        assert ratio == pytest.approx(0.20 / 0.70, abs=1e-6)
