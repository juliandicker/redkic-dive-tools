"""
OVM Planner OC bailout reference data — recorded 2026-06-11 using Playwright.
Source: https://www.ovm-planner.com/ (Bühlmann ZHL-16C with GF — CCR + Bailout mode)

OVM settings applied to every case
------------------------------------
  circuit              : CCR
  setpoint low/high/deco: 1.3
  setpoint_switch_depth_m: 0
  descent_rate_mpm     : 20
  ascent_rate_mpm      : 9   (single rate; tests pass same rate for deep & shallow)
  water_type           : salt
  surface_pressure_bar : 1.013
  last_stop_depth_m    : 3

Convention note
------------------------------------
  bottom_time_min = OVM flat BT + depth/20, same as ovm_reference.py.
  Bailout profile times are relative to bailout start (t=0), matching
  plan_oc_bailout() which resets runtime to 0.0.

  Bailout gas MODs use ppO2_limit=1.6, surface_pressure=1.0 (simplified):
    MOD = (1.6 / fO2 - 1) * 10
  Tx 21/35 → 66 m, EAN50 → 22 m.

Known divergence
------------------------------------
  Same minor numerical differences as the CCR suite (see ovm_reference.py).
  Tests tolerate ±3 min per stop and ±3 min total runtime.
"""

OVM_BAILOUT_CASES = {
    "B1_40m_tx1555_gf6080": {
        "ccr_input": {
            "depth_m": 40,
            "bottom_time_min": 47.0,
            "diluent_o2_pct": 15,
            "diluent_he_pct": 55,
            "setpoint_bar": 1.3,
            "gf_low": 0.60,
            "gf_high": 0.80,
        },
        "bailout_gases": [
            {"o2_pct": 21, "he_pct": 35, "mod_m": 66},
            {"o2_pct": 50, "he_pct":  0, "mod_m": 22},
        ],
        "stops": [
            {"depth_m": 15, "time_min":  2, "runtime_min":  5},
            {"depth_m": 12, "time_min":  4, "runtime_min": 10},
            {"depth_m":  9, "time_min":  6, "runtime_min": 16},
            {"depth_m":  6, "time_min": 12, "runtime_min": 28},
            {"depth_m":  3, "time_min": 25, "runtime_min": 54},
        ],
        "total_deco_min": 49,
        "total_runtime_min": 54,
        "first_stop_m": 15,
    },
    "B2_55m_tx1070_gf6080": {
        "ccr_input": {
            "depth_m": 55,
            "bottom_time_min": 35.75,
            "diluent_o2_pct": 10,
            "diluent_he_pct": 70,
            "setpoint_bar": 1.3,
            "gf_low": 0.60,
            "gf_high": 0.80,
        },
        "bailout_gases": [
            {"o2_pct": 21, "he_pct": 35, "mod_m": 66},
            {"o2_pct": 50, "he_pct":  0, "mod_m": 22},
        ],
        "stops": [
            {"depth_m": 24, "time_min":  2, "runtime_min":  6},
            {"depth_m": 21, "time_min":  2, "runtime_min":  8},
            {"depth_m": 18, "time_min":  3, "runtime_min": 12},
            {"depth_m": 15, "time_min":  3, "runtime_min": 15},
            {"depth_m": 12, "time_min":  6, "runtime_min": 21},
            {"depth_m":  9, "time_min":  9, "runtime_min": 31},
            {"depth_m":  6, "time_min": 16, "runtime_min": 47},
            {"depth_m":  3, "time_min": 33, "runtime_min": 80},
        ],
        "total_deco_min": 74,
        "total_runtime_min": 81,
        "first_stop_m": 24,
    },
    "B3_43m_tx1535_gf4070": {
        "ccr_input": {
            "depth_m": 43,
            "bottom_time_min": 52.15,
            "diluent_o2_pct": 15,
            "diluent_he_pct": 35,
            "setpoint_bar": 1.3,
            "gf_low": 0.40,
            "gf_high": 0.70,
        },
        "bailout_gases": [
            {"o2_pct": 21, "he_pct": 35, "mod_m": 66},
            {"o2_pct": 50, "he_pct":  0, "mod_m": 22},
        ],
        "stops": [
            {"depth_m": 21, "time_min":  1, "runtime_min":  4},
            {"depth_m": 18, "time_min":  2, "runtime_min":  6},
            {"depth_m": 15, "time_min":  4, "runtime_min": 11},
            {"depth_m": 12, "time_min":  5, "runtime_min": 16},
            {"depth_m":  9, "time_min":  9, "runtime_min": 25},
            {"depth_m":  6, "time_min": 17, "runtime_min": 43},
            {"depth_m":  3, "time_min": 34, "runtime_min": 77},
        ],
        "total_deco_min": 72,
        "total_runtime_min": 77,
        "first_stop_m": 21,
    },
}
