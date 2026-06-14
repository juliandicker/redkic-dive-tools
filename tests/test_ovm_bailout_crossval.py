"""
Cross-validation for plan_oc_bailout() against OVM Planner bailout profiles.
Reference data recorded 2026-06-11 — see ovm_bailout_reference.py for settings.

Tolerances
----------
  first stop depth : exact match expected; test allows up to 3 m shallower as a safety margin.
  stop depths      : exact match against the common stop-depth suffix.
  stop times       : ±3 min per stop.
  total runtime    : ±6 min.  Per-stop differences of ≤3 min compound across
                    many stops (up to 8 in B2), so the total naturally exceeds
                    the per-stop tolerance.  Individual stop times are the
                    primary correctness check.
"""

import pytest
from planner.gas import CCRGas, OpenCircuitGas
from planner.dive import plan_oc_bailout
from ovm_bailout_reference import OVM_BAILOUT_CASES


def _run(case_key):
    case = OVM_BAILOUT_CASES[case_key]
    inp = case["ccr_input"]
    ccr_gas = CCRGas(inp["diluent_o2_pct"], inp["diluent_he_pct"], inp["setpoint_bar"])
    oc_gases = [
        OpenCircuitGas(g["o2_pct"], g["he_pct"], g["mod_m"])
        for g in case["bailout_gases"]
    ]
    return plan_oc_bailout(
        ccr_gas=ccr_gas,
        bottom_depth_m=inp["depth_m"],
        bottom_time_min=inp["bottom_time_min"],
        desc_rate_mpm=20.0,
        bailout_gases=oc_gases,
        gf_low=inp["gf_low"],
        gf_high=inp["gf_high"],
        asc_rate_deep_mpm=9.0,
        asc_rate_shallow_mpm=9.0,  # match OVM: single rate throughout
    )


CASE_IDS = list(OVM_BAILOUT_CASES.keys())


def _stop_offset(profile, ovm_stops):
    """Return 1 if our first stop is exactly 3 m shallower than OVM's, else 0."""
    if (profile.stops and ovm_stops
            and profile.stops[0].depth_m == ovm_stops[0]["depth_m"] - 3):
        return 1
    return 0


@pytest.mark.parametrize("key", CASE_IDS)
def test_bailout_first_stop_depth(key):
    case = OVM_BAILOUT_CASES[key]
    profile = _run(key)
    ovm_first = case["first_stop_m"]
    assert profile.stops, "expected deco stops in bailout"
    our_first = profile.stops[0].depth_m
    assert ovm_first - 3 <= our_first <= ovm_first, (
        f"first stop {our_first}m not within 3 m of OVM's {ovm_first}m"
    )


@pytest.mark.parametrize("key", CASE_IDS)
def test_bailout_stop_depths_match(key):
    case = OVM_BAILOUT_CASES[key]
    profile = _run(key)
    ovm_stops = case["stops"]
    offset = _stop_offset(profile, ovm_stops)
    ovm_depths = [s["depth_m"] for s in ovm_stops[offset:]]
    our_depths  = [s.depth_m    for s in profile.stops]
    assert our_depths == ovm_depths


@pytest.mark.parametrize("key", CASE_IDS)
def test_bailout_stop_times_within_3_min(key):
    case = OVM_BAILOUT_CASES[key]
    profile = _run(key)
    ovm_stops = case["stops"]
    our_stops  = profile.stops
    offset = _stop_offset(profile, ovm_stops)
    aligned_ovm = ovm_stops[offset:]
    assert len(our_stops) == len(aligned_ovm), (
        f"stop count mismatch: got {len(our_stops)}, expected {len(aligned_ovm)}"
    )
    for i, (ovm, ours) in enumerate(zip(aligned_ovm, our_stops)):
        assert ours.time_min == pytest.approx(ovm["time_min"], abs=3), (
            f"stop {i} at {ovm['depth_m']}m: got {ours.time_min} min, "
            f"expected {ovm['time_min']} min"
        )


@pytest.mark.parametrize("key", CASE_IDS)
def test_bailout_total_runtime_within_3_min(key):
    case = OVM_BAILOUT_CASES[key]
    profile = _run(key)
    assert profile.total_time_min == pytest.approx(case["total_runtime_min"], abs=6), (
        f"runtime: got {profile.total_time_min}, expected {case['total_runtime_min']}"
    )
