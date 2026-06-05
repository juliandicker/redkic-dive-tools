import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'gasblender'))
from gas_blender import *

def test_trimixblend(start, finish, he):
    mix = TrimixBlend(start, finish, he)
    print(f"Start:\t{start}")
    print(f"Finish:\t{finish}")
    print(f"He:\t{he}")
    print(mix)
    print()

def test_topup(start_gas, topup_gas):
    mix_gas = topup_blend(start_gas, topup_gas)
    print(f"Start: {start_gas}")
    print(f"Topup: {topup_gas}")
    print(f"Result:{mix_gas}")
    print()

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

test_trimixblend(b_empty_air, b_full_1840, b_full_he)
test_trimixblend(b_half_2250, b_full_1840, b_full_he)
test_trimixblend(b_empty_air, b_full_1840, b_full_he_poor)
test_trimixblend(b_empty_air, b_full_1840, b_full_1050)
test_trimixblend(b_empty_air, b_full_1840, b_half_1050)
test_trimixblend(b_empty_air, b_full_n36, b_full_he)

test_topup(b_half_1840, b_full_1050)
test_topup(b_half_2250, b_full_air)
test_topup(b_empty_air, b_full_air)
test_topup(b_min_air, b_half_2250)

