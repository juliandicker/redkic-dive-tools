"""
OVM Planner reference data — recorded 2026-06-08 using Playwright.
Source: https://www.ovm-planner.com/  (Bühlmann ZHL-16C with GF — CCR mode)

OVM settings applied to every case
-----------------------------------
  circuit                   : CCR
  descent_rate_mpm          : 20
  ascent_rate_mpm           : 9   (single rate — no shallow/deep split)
  descend_counts_as_bt      : False  (BT is flat time at depth, descent separate)
  water_type                : salt
  surface_pressure_bar      : 1.013
  last_stop_depth_m         : 3
  setpoint_low = high = deco: test setpoint value
  setpoint_switch_depth_m   : 0
  bailout_mixes             : none

Convention note
-----------------------------------
  Our planner uses "run time to ascent start" for bottom_time_min (descent included).
  OVM's BT is flat time at depth. Each bottom_time_min below = OVM flat BT + depth/20
  so the tissue loading passed to plan_ccr_dive() is identical to the OVM scenario.

Known divergence from our planner
-----------------------------------
  * OVM single 9 m/min ascent rate; our planner uses 9 m/min >6 m, 3 m/min ≤6 m
    (tests pass the same 9 m/min for both to isolate algorithm differences)
  * At the 6 m stop our model exits ~1 min earlier than OVM in heavily-saturated
    dives; this propagates to 2–3 extra min at 3 m because off-gassing at 3 m is
    slower (inspired ppN₂ = 0 at SP 1.3).  Root cause is a minor numerical
    difference in tissue state — exact OVM algorithm not public.
  * Tests tolerate ±3 min/stop and ±3 min total runtime.

gf_low / gf_high in the input dict are fractions (0.0–1.0), matching plan_ccr_dive().
"""

OVM_SETTINGS = {
    "circuit": "CCR",
    "descent_rate_mpm": 20,
    "ascent_rate_mpm": 9,
    "descend_counts_as_bottom_time": False,
    "water_type": "salt",
    "surface_pressure_bar": 1.013,
    "last_stop_depth_m": 3,
    "setpoint_switch_depth_m": 0,
    "no_bailout_mixes": True,
}

OVM_CASES = {
    "01_no_deco": {
        "input": {
            "depth_m": 20, "bottom_time_min": 26.0,
            "diluent_o2_pct": 21, "diluent_he_pct": 0,
            "setpoint_bar": 1.3, "gf_low": 0.60, "gf_high": 0.80,
        },
        "stops": [],
        "total_deco_min": 0,
        "total_runtime_min": 29,
        "first_stop_m": None,
    },
    "02_shallow_light_deco": {
        "input": {
            "depth_m": 25, "bottom_time_min": 41.25,
            "diluent_o2_pct": 21, "diluent_he_pct": 0,
            "setpoint_bar": 1.3, "gf_low": 0.60, "gf_high": 0.80,
        },
        "stops": [
            {"depth_m": 3, "time_min": 4, "runtime_min": 49},
        ],
        "total_deco_min": 4,
        "total_runtime_min": 49,
        "first_stop_m": 3,
    },
    "03_shallow_moderate_deco": {
        "input": {
            "depth_m": 30, "bottom_time_min": 51.5,
            "diluent_o2_pct": 21, "diluent_he_pct": 0,
            "setpoint_bar": 1.3, "gf_low": 0.60, "gf_high": 0.80,
        },
        "stops": [
            {"depth_m": 9, "time_min": 1, "runtime_min": 55},
            {"depth_m": 6, "time_min": 5, "runtime_min": 61},
            {"depth_m": 3, "time_min": 8, "runtime_min": 69},
        ],
        "total_deco_min": 14,
        "total_runtime_min": 69,
        "first_stop_m": 9,
    },
    "04_reference_43m_trimix": {
        "input": {
            "depth_m": 43, "bottom_time_min": 52.15,
            "diluent_o2_pct": 15, "diluent_he_pct": 35,
            "setpoint_bar": 1.3, "gf_low": 0.60, "gf_high": 0.80,
        },
        "stops": [
            {"depth_m": 18, "time_min":  1, "runtime_min":  56},
            {"depth_m": 15, "time_min":  4, "runtime_min":  61},
            {"depth_m": 12, "time_min":  5, "runtime_min":  66},
            {"depth_m":  9, "time_min":  8, "runtime_min":  74},
            {"depth_m":  6, "time_min": 12, "runtime_min":  87},
            {"depth_m":  3, "time_min": 20, "runtime_min": 107},
        ],
        "total_deco_min": 50,
        "total_runtime_min": 107,
        "first_stop_m": 18,
    },
    "05_deep_trimix_55m": {
        "input": {
            "depth_m": 55, "bottom_time_min": 27.75,
            "diluent_o2_pct": 10, "diluent_he_pct": 70,
            "setpoint_bar": 1.3, "gf_low": 0.60, "gf_high": 0.80,
        },
        "stops": [
            {"depth_m": 24, "time_min":  1, "runtime_min":  33},
            {"depth_m": 21, "time_min":  2, "runtime_min":  35},
            {"depth_m": 18, "time_min":  2, "runtime_min":  37},
            {"depth_m": 15, "time_min":  4, "runtime_min":  42},
            {"depth_m": 12, "time_min":  5, "runtime_min":  47},
            {"depth_m":  9, "time_min":  7, "runtime_min":  54},
            {"depth_m":  6, "time_min": 11, "runtime_min":  66},
            {"depth_m":  3, "time_min": 19, "runtime_min":  85},
        ],
        "total_deco_min": 51,
        "total_runtime_min": 85,
        "first_stop_m": 24,
    },
    "06_deep_trimix_70m": {
        "input": {
            "depth_m": 70, "bottom_time_min": 23.5,
            "diluent_o2_pct": 10, "diluent_he_pct": 70,
            "setpoint_bar": 1.3, "gf_low": 0.60, "gf_high": 0.80,
        },
        "stops": [
            {"depth_m": 30, "time_min":  2, "runtime_min":  30},
            {"depth_m": 27, "time_min":  1, "runtime_min":  32},
            {"depth_m": 24, "time_min":  2, "runtime_min":  34},
            {"depth_m": 21, "time_min":  3, "runtime_min":  37},
            {"depth_m": 18, "time_min":  4, "runtime_min":  42},
            {"depth_m": 15, "time_min":  5, "runtime_min":  47},
            {"depth_m": 12, "time_min":  6, "runtime_min":  53},
            {"depth_m":  9, "time_min": 10, "runtime_min":  64},
            {"depth_m":  6, "time_min": 14, "runtime_min":  78},
            {"depth_m":  3, "time_min": 23, "runtime_min": 101},
        ],
        "total_deco_min": 70,
        "total_runtime_min": 102,
        "first_stop_m": 30,
    },
    "07_conservative_gf_40_70": {
        "input": {
            "depth_m": 43, "bottom_time_min": 52.15,
            "diluent_o2_pct": 15, "diluent_he_pct": 35,
            "setpoint_bar": 1.3, "gf_low": 0.40, "gf_high": 0.70,
        },
        "stops": [
            {"depth_m": 21, "time_min":  1, "runtime_min":  56},
            {"depth_m": 18, "time_min":  3, "runtime_min":  59},
            {"depth_m": 15, "time_min":  5, "runtime_min":  65},
            {"depth_m": 12, "time_min":  6, "runtime_min":  71},
            {"depth_m":  9, "time_min":  8, "runtime_min":  79},
            {"depth_m":  6, "time_min": 14, "runtime_min":  94},
            {"depth_m":  3, "time_min": 23, "runtime_min": 117},
        ],
        "total_deco_min": 60,
        "total_runtime_min": 117,
        "first_stop_m": 21,
    },
    "08_liberal_gf_85_85": {
        "input": {
            "depth_m": 43, "bottom_time_min": 52.15,
            "diluent_o2_pct": 15, "diluent_he_pct": 35,
            "setpoint_bar": 1.3, "gf_low": 0.85, "gf_high": 0.85,
        },
        "stops": [
            {"depth_m": 15, "time_min":  1, "runtime_min":  57},
            {"depth_m": 12, "time_min":  5, "runtime_min":  62},
            {"depth_m":  9, "time_min":  7, "runtime_min":  69},
            {"depth_m":  6, "time_min": 11, "runtime_min":  81},
            {"depth_m":  3, "time_min": 18, "runtime_min":  99},
        ],
        "total_deco_min": 42,
        "total_runtime_min": 99,
        "first_stop_m": 15,
    },
    "09_low_setpoint_1_2": {
        "input": {
            "depth_m": 43, "bottom_time_min": 52.15,
            "diluent_o2_pct": 15, "diluent_he_pct": 35,
            "setpoint_bar": 1.2, "gf_low": 0.60, "gf_high": 0.80,
        },
        "stops": [
            {"depth_m": 18, "time_min":  2, "runtime_min":  57},
            {"depth_m": 15, "time_min":  4, "runtime_min":  62},
            {"depth_m": 12, "time_min":  6, "runtime_min":  68},
            {"depth_m":  9, "time_min":  9, "runtime_min":  77},
            {"depth_m":  6, "time_min": 13, "runtime_min":  91},
            {"depth_m":  3, "time_min": 23, "runtime_min": 114},
        ],
        "total_deco_min": 57,
        "total_runtime_min": 114,
        "first_stop_m": 18,
    },
    "10_high_setpoint_1_4": {
        "input": {
            "depth_m": 43, "bottom_time_min": 52.15,
            "diluent_o2_pct": 15, "diluent_he_pct": 35,
            "setpoint_bar": 1.4, "gf_low": 0.60, "gf_high": 0.80,
        },
        "stops": [
            {"depth_m": 15, "time_min":  4, "runtime_min":  60},
            {"depth_m": 12, "time_min":  5, "runtime_min":  65},
            {"depth_m":  9, "time_min":  7, "runtime_min":  72},
            {"depth_m":  6, "time_min": 11, "runtime_min":  84},
            {"depth_m":  3, "time_min": 18, "runtime_min": 102},
        ],
        "total_deco_min": 45,
        "total_runtime_min": 102,
        "first_stop_m": 15,
    },
    "11_long_bottom_time": {
        "input": {
            "depth_m": 40, "bottom_time_min": 77.0,
            "diluent_o2_pct": 18, "diluent_he_pct": 45,
            "setpoint_bar": 1.3, "gf_low": 0.60, "gf_high": 0.80,
        },
        "stops": [
            {"depth_m": 18, "time_min":  2, "runtime_min":  82},
            {"depth_m": 15, "time_min":  5, "runtime_min":  87},
            {"depth_m": 12, "time_min":  9, "runtime_min":  97},
            {"depth_m":  9, "time_min": 11, "runtime_min": 108},
            {"depth_m":  6, "time_min": 19, "runtime_min": 127},
            {"depth_m":  3, "time_min": 30, "runtime_min": 158},
        ],
        "total_deco_min": 76,
        "total_runtime_min": 158,
        "first_stop_m": 18,
    },
    "12_deep_long_trimix": {
        "input": {
            "depth_m": 60, "bottom_time_min": 38.0,
            "diluent_o2_pct": 10, "diluent_he_pct": 70,
            "setpoint_bar": 1.3, "gf_low": 0.60, "gf_high": 0.80,
        },
        "stops": [
            {"depth_m": 30, "time_min":  1, "runtime_min":  43},
            {"depth_m": 27, "time_min":  2, "runtime_min":  45},
            {"depth_m": 24, "time_min":  3, "runtime_min":  49},
            {"depth_m": 21, "time_min":  4, "runtime_min":  53},
            {"depth_m": 18, "time_min":  5, "runtime_min":  58},
            {"depth_m": 15, "time_min":  7, "runtime_min":  66},
            {"depth_m": 12, "time_min":  9, "runtime_min":  75},
            {"depth_m":  9, "time_min": 13, "runtime_min":  88},
            {"depth_m":  6, "time_min": 19, "runtime_min": 108},
            {"depth_m":  3, "time_min": 31, "runtime_min": 139},
        ],
        "total_deco_min": 94,
        "total_runtime_min": 139,
        "first_stop_m": 30,
    },
    # --- Cases 13-16 inspired by MVPlan2 debug scenarios (recorded 2026-06-09) ---
    "13_mvplan_deep_tx1555_gf5080": {
        "input": {
            "depth_m": 75, "bottom_time_min": 30.75,
            "diluent_o2_pct": 15, "diluent_he_pct": 55,
            "setpoint_bar": 1.3, "gf_low": 0.50, "gf_high": 0.80,
        },
        "stops": [
            {"depth_m": 39, "time_min":  1, "runtime_min":  36},
            {"depth_m": 36, "time_min":  1, "runtime_min":  38},
            {"depth_m": 33, "time_min":  2, "runtime_min":  40},
            {"depth_m": 30, "time_min":  2, "runtime_min":  42},
            {"depth_m": 27, "time_min":  3, "runtime_min":  46},
            {"depth_m": 24, "time_min":  4, "runtime_min":  50},
            {"depth_m": 21, "time_min":  4, "runtime_min":  54},
            {"depth_m": 18, "time_min":  6, "runtime_min":  61},
            {"depth_m": 15, "time_min":  7, "runtime_min":  68},
            {"depth_m": 12, "time_min": 10, "runtime_min":  78},
            {"depth_m":  9, "time_min": 14, "runtime_min":  93},
            {"depth_m":  6, "time_min": 21, "runtime_min": 114},
            {"depth_m":  3, "time_min": 34, "runtime_min": 148},
        ],
        "total_deco_min": 109,
        "total_runtime_min": 149,
        "first_stop_m": 39,
    },
    "14_tx1535_gf5080": {
        "input": {
            "depth_m": 43, "bottom_time_min": 52.15,
            "diluent_o2_pct": 15, "diluent_he_pct": 35,
            "setpoint_bar": 1.3, "gf_low": 0.50, "gf_high": 0.80,
        },
        "stops": [
            {"depth_m": 18, "time_min":  3, "runtime_min":  58},
            {"depth_m": 15, "time_min":  4, "runtime_min":  63},
            {"depth_m": 12, "time_min":  5, "runtime_min":  68},
            {"depth_m":  9, "time_min":  8, "runtime_min":  76},
            {"depth_m":  6, "time_min": 12, "runtime_min":  89},
            {"depth_m":  3, "time_min": 20, "runtime_min": 109},
        ],
        "total_deco_min": 52,
        "total_runtime_min": 109,
        "first_stop_m": 18,
    },
    "15_ean28_nitrox_diluent": {
        "input": {
            "depth_m": 43, "bottom_time_min": 52.15,
            "diluent_o2_pct": 28, "diluent_he_pct": 0,
            "setpoint_bar": 1.3, "gf_low": 0.60, "gf_high": 0.80,
        },
        "stops": [
            {"depth_m": 18, "time_min":  1, "runtime_min":  56},
            {"depth_m": 15, "time_min":  4, "runtime_min":  61},
            {"depth_m": 12, "time_min":  6, "runtime_min":  67},
            {"depth_m":  9, "time_min":  8, "runtime_min":  75},
            {"depth_m":  6, "time_min": 12, "runtime_min":  88},
            {"depth_m":  3, "time_min": 18, "runtime_min": 106},
        ],
        "total_deco_min": 49,
        "total_runtime_min": 106,
        "first_stop_m": 18,
    },
    "16_tx2135_gf5080": {
        "input": {
            "depth_m": 50, "bottom_time_min": 22.5,
            "diluent_o2_pct": 21, "diluent_he_pct": 35,
            "setpoint_bar": 1.3, "gf_low": 0.50, "gf_high": 0.80,
        },
        "stops": [
            {"depth_m": 18, "time_min":  1, "runtime_min":  28},
            {"depth_m": 15, "time_min":  2, "runtime_min":  30},
            {"depth_m": 12, "time_min":  2, "runtime_min":  32},
            {"depth_m":  9, "time_min":  3, "runtime_min":  36},
            {"depth_m":  6, "time_min":  6, "runtime_min":  42},
            {"depth_m":  3, "time_min": 10, "runtime_min":  52},
        ],
        "total_deco_min": 24,
        "total_runtime_min": 53,
        "first_stop_m": 18,
    },
}
