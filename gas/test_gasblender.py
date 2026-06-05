import math
import sys
import os
import unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'gasblender'))
from gas_blender import *

b_half_2250 = Gas(120, 22, 50)
b_full_air = Gas(250, 21, 0)
b_min_air = Gas(50, 21, 0)
b_empty_air = Gas(1, 21, 0)
b_half_1840 = Gas(120, 18, 40)
b_full_1840 = Gas(250, 18, 40)
b_full_n36 = Gas(250, 36, 0)
b_half_1050 = Gas(120, 10, 50)
b_full_1050 = Gas(250, 10, 50)
b_full_he_poor = Gas(250, 2.1, 90)
b_full_he = Gas(250, 0, 100)

class GasBlenderTestCases(unittest.TestCase):

    def test_topup_mix_mix(self):
        expected = Gas(250, 13.9, 45.2)
        result = topup_blend(b_half_1840, b_full_1050)
        self.assertAlmostEqual(result.o2, expected.o2, 0)
        self.assertAlmostEqual(result.he, expected.he, 0)
        self.assertAlmostEqual(result.bar, expected.bar, 0)

    def test_topup_mix_air(self):
        expected = Gas(250, 19.6, 19.3)
        result = topup_blend(b_half_1840, b_full_air)
        self.assertAlmostEqual(result.o2, expected.o2, 0)
        self.assertAlmostEqual(result.he, expected.he, 0)
        self.assertAlmostEqual(result.bar, expected.bar, 0)

    def test_topup_mix2_air(self):
        expected = Gas(250, 21.5, 24.1)
        result = topup_blend(b_half_2250, b_full_air)
        self.assertAlmostEqual(result.o2, expected.o2, 0)
        self.assertAlmostEqual(result.he, expected.he, 0)
        self.assertAlmostEqual(result.bar, expected.bar, 0)

    def test_topup_air_air(self):
        expected = Gas(250, 21, 0)
        result = topup_blend(b_empty_air, b_full_air)
        self.assertAlmostEqual(result.o2, expected.o2, 0)
        self.assertAlmostEqual(result.he, expected.he, 0)
        self.assertAlmostEqual(result.bar, expected.bar, 0)

    def test_topup_min_air_half_2250(self):
        expected = Gas(120, 21.6, 28.9)
        result = topup_blend(b_min_air, b_half_2250)
        self.assertAlmostEqual(result.o2, expected.o2, 0)
        self.assertAlmostEqual(result.he, expected.he, 0)
        self.assertAlmostEqual(result.bar, expected.bar, 0)

    def test_trimix3(self):
        result = TrimixBlend(b_empty_air, b_full_1840, b_full_he)
        expected = [
            Gas(104.1, -1, -1),
            Gas(121.6, 16.2, -1),
            Gas(250, 18, 40)
        ]
        self.trimix_test(result, expected)
    
    def test_trimix4(self):
        result = TrimixBlend(b_empty_air, b_full_1840, b_half_1050)
        expected = [
            Gas(120, 10.2, 49.2),
            Gas(162.1, -1, -1),
            Gas(179.8, 17.4, -1),
            Gas(250, 18, 40)
        ]
        self.trimix_test(result, expected)

    def test_trimix5(self):
        result = TrimixBlend(b_empty_air, b_full_1840, b_full_1050)
        expected = [
            Gas(200.8, 10.1, 49.8),
            Gas(218.3, 17.7, -1),
            Gas(250, 18, 40)
        ]
        self.trimix_test(result, expected)

    def test_trimix_poor(self):
        result = TrimixBlend(b_empty_air, b_full_1840, b_full_he_poor)
        expected = [
            Gas(111.6, 2.3, 89.2),
            Gas(128.3, 15.6, -1),
            Gas(250, 18, 40)
        ]
        self.trimix_test(result, expected)

    def test_nitrox36(self):
        result = TrimixBlend(b_empty_air, b_full_n36, b_full_he)
        expected = [
            Gas(48.1, -1, -1),
            Gas(250, 36, -1)
        ]
        self.trimix_test(result, expected)
    
    def trimix_test(self, result, expected):
        self.assertEqual(len(result.steps), len(expected))
        for i in range(len(expected)):
            if expected[i].o2 > -1:
                self.assertLess(abs(result.steps[i].result_gas.o2 - expected[i].o2), 2)
            if expected[i].he > -1:
                self.assertLess(abs(result.steps[i].result_gas.he - expected[i].he), 2)
            self.assertLess(abs(result.steps[i].result_gas.bar - expected[i].bar), 5)