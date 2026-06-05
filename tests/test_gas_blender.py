import json
import pytest
from gas_blender import Gas, BlendStep, TrimixBlend, topup_blend


class TestGas:

    def test_components(self):
        g = Gas(200, 21, 35)
        assert g.n2 == pytest.approx(44)
        # bar_* uses absolute pressure (gauge + 1 bar)
        assert g.bar_o2 == pytest.approx(201 * 0.21)
        assert g.bar_he == pytest.approx(201 * 0.35)
        assert g.bar_n2 == pytest.approx(201 * 0.44)

    def test_short_name_pure_o2(self):
        assert Gas(200, 100, 0).short_name() == "O2"

    def test_short_name_pure_he(self):
        assert Gas(200, 0, 100).short_name() == "He"

    def test_short_name_air(self):
        assert Gas(200, 21, 0).short_name() == "Air"

    def test_short_name_nitrox(self):
        assert Gas(200, 32, 0).short_name() == "N32.0%"

    def test_short_name_trimix(self):
        assert Gas(200, 21, 35).short_name() == "21.0/35.0"


class TestTopupBlend:

    b_half_2250 = Gas(120, 22, 50)
    b_full_air  = Gas(250, 21,  0)
    b_min_air   = Gas(50,  21,  0)
    b_empty_air = Gas(1,   21,  0)
    b_half_1840 = Gas(120, 18, 40)
    b_full_1050 = Gas(250, 10, 50)

    def test_mix_plus_mix(self):
        result = topup_blend(self.b_half_1840, self.b_full_1050)
        assert result.o2 == pytest.approx(13.9, abs=0.5)
        assert result.he == pytest.approx(45.2, abs=0.5)

    def test_mix_plus_air(self):
        result = topup_blend(self.b_half_1840, self.b_full_air)
        assert result.o2 == pytest.approx(19.6, abs=0.5)
        assert result.he == pytest.approx(19.3, abs=0.5)

    def test_mix2_plus_air(self):
        result = topup_blend(self.b_half_2250, self.b_full_air)
        assert result.o2 == pytest.approx(21.5, abs=0.5)
        assert result.he == pytest.approx(24.1, abs=0.5)

    def test_air_plus_air(self):
        result = topup_blend(self.b_empty_air, self.b_full_air)
        assert result.o2 == pytest.approx(21, abs=0.5)
        assert result.he == pytest.approx(0,  abs=0.5)

    def test_min_air_plus_trimix(self):
        result = topup_blend(self.b_min_air, self.b_half_2250)
        assert result.o2 == pytest.approx(21.6, abs=0.5)
        assert result.he == pytest.approx(28.9, abs=0.5)

    def test_default_bar_uses_topup_bar(self):
        result = topup_blend(self.b_empty_air, self.b_full_air)
        assert result.bar == self.b_full_air.bar

    def test_explicit_bar_override(self):
        result = topup_blend(self.b_half_1840, self.b_full_1050, bar=200)
        assert result.bar == 200


class TestTrimixBlend:

    b_empty_air    = Gas(1,   21,   0)
    b_full_1840    = Gas(250, 18,  40)
    b_full_n36     = Gas(250, 36,   0)
    b_half_1050    = Gas(120, 10,  50)
    b_full_1050    = Gas(250, 10,  50)
    b_full_he_poor = Gas(250,  2.1, 90)
    b_full_he      = Gas(250,  0,  100)

    def _check_steps(self, result, expected):
        assert len(result.steps) == len(expected)
        for i, exp in enumerate(expected):
            actual = result.steps[i].result_gas
            if exp.o2 >= 0:
                assert abs(actual.o2 - exp.o2) < 2
            if exp.he >= 0:
                assert abs(actual.he - exp.he) < 2
            assert abs(actual.bar - exp.bar) < 5

    def test_trimix_full_he_bank(self):
        result = TrimixBlend(self.b_empty_air, self.b_full_1840, self.b_full_he)
        self._check_steps(result, [Gas(104.1, -1, -1), Gas(121.6, 16.2, -1), Gas(250, 18, 40)])

    def test_trimix_full_low_pressure_bank(self):
        result = TrimixBlend(self.b_empty_air, self.b_full_1840, self.b_full_1050)
        self._check_steps(result, [Gas(200.8, 10.1, 49.8), Gas(218.3, 17.7, -1), Gas(250, 18, 40)])

    def test_trimix_poor_he_bank(self):
        result = TrimixBlend(self.b_empty_air, self.b_full_1840, self.b_full_he_poor)
        self._check_steps(result, [Gas(111.6, 2.3, 89.2), Gas(128.3, 15.6, -1), Gas(250, 18, 40)])

    def test_nitrox(self):
        result = TrimixBlend(self.b_empty_air, self.b_full_n36, self.b_full_he)
        self._check_steps(result, [Gas(48.1, -1, -1), Gas(250, 36, -1)])

    def test_bank_exhaustion_adds_extra_he_step(self):
        result = TrimixBlend(self.b_empty_air, self.b_full_1840, self.b_half_1050)
        self._check_steps(result, [
            Gas(120,   10.2, 49.2),
            Gas(162.1, -1,   -1),
            Gas(179.8, 17.4, -1),
            Gas(250,   18,   40),
        ])

    def test_default_he_gas_is_250_bar(self):
        result = TrimixBlend(self.b_empty_air, self.b_full_1840)
        assert result.he_gas.bar == 250
        assert result.he_gas.he == 100

    def test_he_bank_zero_helium_raises(self):
        with pytest.raises(ValueError):
            TrimixBlend(self.b_empty_air, self.b_full_1840, Gas(250, 21, 0))

    def test_nitrox_has_no_he_step(self):
        result = TrimixBlend(self.b_empty_air, self.b_full_n36, self.b_full_he)
        names = [s.name for s in result.steps]
        assert "He" not in names
        assert names == ["O2", "Air"]

    def test_trimix_step_order(self):
        result = TrimixBlend(self.b_empty_air, self.b_full_1840, self.b_full_he)
        assert [s.name for s in result.steps] == ["He", "O2", "Air"]

    def test_final_step_reaches_target_pressure(self):
        result = TrimixBlend(self.b_empty_air, self.b_full_1840, self.b_full_he)
        assert abs(result.steps[-1].result_gas.bar - 250) < 5

    def test_final_step_reaches_target_mix(self):
        result = TrimixBlend(self.b_empty_air, self.b_full_1840, self.b_full_he)
        final = result.steps[-1].result_gas
        assert final.o2 == pytest.approx(18, abs=0.5)
        assert final.he == pytest.approx(40, abs=0.5)

    def test_pressure_increases_at_each_step(self):
        result = TrimixBlend(self.b_empty_air, self.b_full_1840, self.b_full_he)
        pressures = [s.result_gas.bar for s in result.steps]
        assert pressures == sorted(pressures)

    def test_json_output_is_valid(self):
        result = TrimixBlend(self.b_empty_air, self.b_full_1840, self.b_full_he)
        data = json.loads(result.toJSON())
        assert "steps" in data
        assert isinstance(data["steps"], list)
        assert len(data["steps"]) == len(result.steps)

    def test_json_step_contains_gas_fields(self):
        result = TrimixBlend(self.b_empty_air, self.b_full_1840, self.b_full_he)
        step = json.loads(result.toJSON())["steps"][0]
        assert "result_gas" in step
        assert "bar" in step["result_gas"]
        assert "o2" in step["result_gas"]
        assert "he" in step["result_gas"]

    def test_start_gas_recorded_in_each_step(self):
        result = TrimixBlend(self.b_empty_air, self.b_full_1840, self.b_full_he)
        for i in range(1, len(result.steps)):
            assert result.steps[i].start_gas.bar == pytest.approx(
                result.steps[i - 1].result_gas.bar, abs=0.1
            )
