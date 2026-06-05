import json
import unittest
from gas_blender import Gas, BlendStep, TrimixBlend, topup_blend


class GasTests(unittest.TestCase):

    def test_gas_components(self):
        g = Gas(200, 21, 35)
        self.assertAlmostEqual(g.n2, 44)
        # bar_* uses absolute pressure (gauge + 1 bar)
        self.assertAlmostEqual(g.bar_o2, 201 * 0.21)
        self.assertAlmostEqual(g.bar_he, 201 * 0.35)
        self.assertAlmostEqual(g.bar_n2, 201 * 0.44)

    def test_gas_short_name_pure_o2(self):
        self.assertEqual(Gas(200, 100, 0).short_name(), "O2")

    def test_gas_short_name_pure_he(self):
        self.assertEqual(Gas(200, 0, 100).short_name(), "He")

    def test_gas_short_name_air(self):
        self.assertEqual(Gas(200, 21, 0).short_name(), "Air")

    def test_gas_short_name_nitrox(self):
        self.assertEqual(Gas(200, 32, 0).short_name(), "N32.0%")

    def test_gas_short_name_trimix(self):
        self.assertEqual(Gas(200, 21, 35).short_name(), "21.0/35.0")


class TopupBlendTests(unittest.TestCase):

    b_half_2250 = Gas(120, 22, 50)
    b_full_air  = Gas(250, 21, 0)
    b_min_air   = Gas(50,  21, 0)
    b_empty_air = Gas(1,   21, 0)
    b_half_1840 = Gas(120, 18, 40)
    b_full_1050 = Gas(250, 10, 50)

    def test_mix_plus_mix(self):
        result = topup_blend(self.b_half_1840, self.b_full_1050)
        self.assertAlmostEqual(result.o2, 13.9, 0)
        self.assertAlmostEqual(result.he, 45.2, 0)

    def test_mix_plus_air(self):
        result = topup_blend(self.b_half_1840, self.b_full_air)
        self.assertAlmostEqual(result.o2, 19.6, 0)
        self.assertAlmostEqual(result.he, 19.3, 0)

    def test_mix2_plus_air(self):
        result = topup_blend(self.b_half_2250, self.b_full_air)
        self.assertAlmostEqual(result.o2, 21.5, 0)
        self.assertAlmostEqual(result.he, 24.1, 0)

    def test_air_plus_air(self):
        result = topup_blend(self.b_empty_air, self.b_full_air)
        self.assertAlmostEqual(result.o2, 21, 0)
        self.assertAlmostEqual(result.he, 0, 0)

    def test_min_air_plus_trimix(self):
        result = topup_blend(self.b_min_air, self.b_half_2250)
        self.assertAlmostEqual(result.o2, 21.6, 0)
        self.assertAlmostEqual(result.he, 28.9, 0)

    def test_default_bar_uses_topup_bar(self):
        result = topup_blend(self.b_empty_air, self.b_full_air)
        self.assertEqual(result.bar, self.b_full_air.bar)

    def test_explicit_bar_override(self):
        result = topup_blend(self.b_half_1840, self.b_full_1050, bar=200)
        self.assertEqual(result.bar, 200)


class TrimixBlendTests(unittest.TestCase):

    b_empty_air  = Gas(1,   21, 0)
    b_full_1840  = Gas(250, 18, 40)
    b_full_n36   = Gas(250, 36, 0)
    b_half_1050  = Gas(120, 10, 50)
    b_full_1050  = Gas(250, 10, 50)
    b_full_he_poor = Gas(250, 2.1, 90)
    b_full_he    = Gas(250, 0, 100)

    def _check_steps(self, result, expected):
        self.assertEqual(len(result.steps), len(expected))
        for i, exp in enumerate(expected):
            actual = result.steps[i].result_gas
            if exp.o2 >= 0:
                self.assertLess(abs(actual.o2 - exp.o2), 2)
            if exp.he >= 0:
                self.assertLess(abs(actual.he - exp.he), 2)
            self.assertLess(abs(actual.bar - exp.bar), 5)

    # --- ported from gas/test_gasblender.py ---

    def test_trimix_full_he_bank(self):
        result = TrimixBlend(self.b_empty_air, self.b_full_1840, self.b_full_he)
        expected = [Gas(104.1, -1, -1), Gas(121.6, 16.2, -1), Gas(250, 18, 40)]
        self._check_steps(result, expected)

    def test_trimix_full_low_pressure_bank(self):
        result = TrimixBlend(self.b_empty_air, self.b_full_1840, self.b_full_1050)
        expected = [Gas(200.8, 10.1, 49.8), Gas(218.3, 17.7, -1), Gas(250, 18, 40)]
        self._check_steps(result, expected)

    def test_trimix_poor_he_bank(self):
        result = TrimixBlend(self.b_empty_air, self.b_full_1840, self.b_full_he_poor)
        expected = [Gas(111.6, 2.3, 89.2), Gas(128.3, 15.6, -1), Gas(250, 18, 40)]
        self._check_steps(result, expected)

    def test_nitrox(self):
        result = TrimixBlend(self.b_empty_air, self.b_full_n36, self.b_full_he)
        expected = [Gas(48.1, -1, -1), Gas(250, 36, -1)]
        self._check_steps(result, expected)

    # --- new tests ---

    def test_default_he_gas_is_250_bar(self):
        result = TrimixBlend(self.b_empty_air, self.b_full_1840)
        self.assertEqual(result.he_gas.bar, 250)
        self.assertEqual(result.he_gas.he, 100)

    def test_he_bank_zero_helium_raises(self):
        air_bank = Gas(250, 21, 0)
        with self.assertRaises(ValueError):
            TrimixBlend(self.b_empty_air, self.b_full_1840, air_bank)

    def test_bank_exhaustion_adds_extra_he_step(self):
        # b_half_1050 has only 120 bar; not enough He for a 250-bar 18/40 blend
        result = TrimixBlend(self.b_empty_air, self.b_full_1840, self.b_half_1050)
        expected = [
            Gas(120,   10.2, 49.2),
            Gas(162.1, -1,   -1),
            Gas(179.8, 17.4, -1),
            Gas(250,   18,   40),
        ]
        self._check_steps(result, expected)

    def test_nitrox_has_no_he_step(self):
        result = TrimixBlend(self.b_empty_air, self.b_full_n36, self.b_full_he)
        names = [s.name for s in result.steps]
        self.assertNotIn("He", names)
        self.assertEqual(names, ["O2", "Air"])

    def test_trimix_step_order(self):
        result = TrimixBlend(self.b_empty_air, self.b_full_1840, self.b_full_he)
        names = [s.name for s in result.steps]
        self.assertEqual(names, ["He", "O2", "Air"])

    def test_final_step_reaches_target_pressure(self):
        result = TrimixBlend(self.b_empty_air, self.b_full_1840, self.b_full_he)
        self.assertLess(abs(result.steps[-1].result_gas.bar - 250), 5)

    def test_final_step_reaches_target_mix(self):
        result = TrimixBlend(self.b_empty_air, self.b_full_1840, self.b_full_he)
        final = result.steps[-1].result_gas
        self.assertAlmostEqual(final.o2, 18, 0)
        self.assertAlmostEqual(final.he, 40, 0)

    def test_pressure_increases_at_each_step(self):
        result = TrimixBlend(self.b_empty_air, self.b_full_1840, self.b_full_he)
        pressures = [s.result_gas.bar for s in result.steps]
        self.assertEqual(pressures, sorted(pressures))

    def test_json_output_is_valid(self):
        result = TrimixBlend(self.b_empty_air, self.b_full_1840, self.b_full_he)
        data = json.loads(result.toJSON())
        self.assertIn("steps", data)
        self.assertIsInstance(data["steps"], list)
        self.assertEqual(len(data["steps"]), len(result.steps))

    def test_json_step_contains_gas_fields(self):
        result = TrimixBlend(self.b_empty_air, self.b_full_1840, self.b_full_he)
        step = json.loads(result.toJSON())["steps"][0]
        self.assertIn("result_gas", step)
        self.assertIn("bar", step["result_gas"])
        self.assertIn("o2", step["result_gas"])
        self.assertIn("he", step["result_gas"])

    def test_start_gas_recorded_in_each_step(self):
        result = TrimixBlend(self.b_empty_air, self.b_full_1840, self.b_full_he)
        # each step's start_gas should equal the previous step's result_gas
        for i in range(1, len(result.steps)):
            self.assertAlmostEqual(
                result.steps[i].start_gas.bar,
                result.steps[i - 1].result_gas.bar, 1
            )


if __name__ == "__main__":
    unittest.main()
