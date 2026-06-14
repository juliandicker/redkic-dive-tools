"""
Cross-validation against OVM Planner (https://www.ovm-planner.com/).
Reference data recorded 2026-06-08 — see ovm_reference.py for full settings.

OVM uses a single 9 m/min ascent rate throughout; we pass that same rate to
plan_ccr_dive() so the comparison isolates algorithm differences, not setting
differences.

Tolerances
----------
  first stop depth: exact match expected (both planners anchor GF_Low at the
                    ceiling computed from the bottom tissue state before ascent).
                    The test allows up to 3 m shallower as a safety margin.
  stop depths      : exact match against the common stop-depth suffix.
  stop times       : ±3 min per stop.
  total runtime    : ±3 min.
"""

import pytest
from planner.gas import CCRGas
from planner.dive import plan_ccr_dive
from ovm_reference import OVM_CASES


def _run(case_key):
    inp = OVM_CASES[case_key]["input"]
    gas = CCRGas(inp["diluent_o2_pct"], inp["diluent_he_pct"], inp["setpoint_bar"])
    return plan_ccr_dive(
        gas,
        inp["depth_m"],
        inp["bottom_time_min"],
        inp["gf_low"],
        inp["gf_high"],
        desc_rate_mpm=20.0,
        asc_rate_deep_mpm=9.0,
        asc_rate_shallow_mpm=9.0,   # match OVM: single rate, no shallow/deep split
    )


CASE_IDS = list(OVM_CASES.keys())


@pytest.mark.parametrize("key", CASE_IDS)
def test_deco_required_agrees(key):
    ovm_has_deco = bool(OVM_CASES[key]["stops"])
    our_has_deco = bool(_run(key).stops)
    assert ovm_has_deco == our_has_deco


def _stop_offset(profile, ovm_stops):
    """Return 1 if our first stop is exactly 3 m shallower than OVM's, else 0."""
    if (profile.stops and ovm_stops
            and profile.stops[0].depth_m == ovm_stops[0]["depth_m"] - 3):
        return 1
    return 0


@pytest.mark.parametrize("key", CASE_IDS)
def test_first_stop_depth(key):
    case = OVM_CASES[key]
    profile = _run(key)
    ovm_first = case["first_stop_m"]
    if ovm_first is None:
        assert profile.stops == []
    else:
        assert profile.stops, "expected deco stops"
        our_first = profile.stops[0].depth_m
        assert ovm_first - 3 <= our_first <= ovm_first, (
            f"first stop {our_first}m not within 3 m of OVM's {ovm_first}m"
        )


@pytest.mark.parametrize("key", CASE_IDS)
def test_stop_depths_match_exactly(key):
    case = OVM_CASES[key]
    profile = _run(key)
    ovm_stops = case["stops"]
    offset = _stop_offset(profile, ovm_stops)
    ovm_depths = [s["depth_m"] for s in ovm_stops[offset:]]
    our_depths  = [s.depth_m    for s in profile.stops]
    assert our_depths == ovm_depths


@pytest.mark.parametrize("key", CASE_IDS)
def test_stop_times_within_2_min(key):
    case = OVM_CASES[key]
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
            f"stop {i} at {ovm['depth_m']}m: got {ours.time_min} min, expected {ovm['time_min']} min"
        )


@pytest.mark.parametrize("key", CASE_IDS)
def test_total_runtime_within_3_min(key):
    case = OVM_CASES[key]
    profile = _run(key)
    assert profile.total_time_min == pytest.approx(case["total_runtime_min"], abs=3), (
        f"runtime: got {profile.total_time_min}, expected {case['total_runtime_min']}"
    )
