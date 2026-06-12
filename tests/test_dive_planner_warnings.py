import pytest
from api.dive_planner_models import BailoutGasInput, DivePlannerRequest, Warning
from api.dive_planner_warnings import (
    PlanWarnings,
    _density_warnings,
    _gas_warnings,
    _infeasibility_msg,
)
from planner.gas import OpenCircuitGas


# ── Factories ─────────────────────────────────────────────────────────────────

def _ccr_req(**kwargs) -> DivePlannerRequest:
    defaults = dict(
        mode='ccr', diluent_o2=18, diluent_he=45, setpoint=1.3,
        depth_m=60, bottom_time_min=20,
    )
    defaults.update(kwargs)
    return DivePlannerRequest(**defaults)


def _oc_req(**kwargs) -> DivePlannerRequest:
    defaults = dict(
        mode='oc', depth_m=40, bottom_time_min=5,
        bailout_gases=[BailoutGasInput(o2=21, he=0, mod_m=40)],
    )
    defaults.update(kwargs)
    return DivePlannerRequest(**defaults)


def _unlimited_volumes():
    return [(OpenCircuitGas(21, 0, 40), {'cyl_l': None, 'cyl_bar': None})]


# ── _density_warnings ─────────────────────────────────────────────────────────

class TestDensityWarnings:

    def test_above_upper_limit_is_danger(self):
        warnings = _density_warnings('Back gas Air', 60, 6.5)
        assert len(warnings) == 1
        assert warnings[0].level == 'danger'
        assert '6.3 g/L' in warnings[0].message

    def test_above_recommended_limit_is_warning(self):
        warnings = _density_warnings('Back gas Air', 60, 5.5)
        assert len(warnings) == 1
        assert warnings[0].level == 'warning'
        assert '5.2 g/L' in warnings[0].message
        assert 'CO₂ retention risk' in warnings[0].message

    def test_within_limits_returns_empty(self):
        assert _density_warnings('Back gas Air', 60, 4.0) == []

    def test_exactly_at_6_3_is_warning_not_danger(self):
        warnings = _density_warnings('Gas', 30, 6.3)
        assert len(warnings) == 1
        assert warnings[0].level == 'warning'

    def test_exactly_at_5_2_returns_empty(self):
        assert _density_warnings('Gas', 30, 5.2) == []

    def test_description_and_depth_appear_in_message(self):
        warnings = _density_warnings('Diluent 18/45', 60, 6.5)
        assert 'Diluent 18/45' in warnings[0].message
        assert '60' in warnings[0].message

    def test_density_value_in_message(self):
        warnings = _density_warnings('Gas', 30, 5.8)
        assert '5.80' in warnings[0].message


# ── _infeasibility_msg ────────────────────────────────────────────────────────

class TestInfeasibilityMsg:

    def test_empty_gas_message_when_no_usable_volume_after_reserve(self):
        g = OpenCircuitGas(21, 0, 40)
        volumes = [(g, {'cyl_l': 12.0, 'cyl_bar': 50.0})]
        msg = _infeasibility_msg(volumes, reserve_bar=50.0, depth_m=40)
        assert g.label in msg
        assert 'no usable gas' in msg

    def test_insufficient_supply_message_when_gas_is_unlimited(self):
        g = OpenCircuitGas(21, 0, 40)
        volumes = [(g, {'cyl_l': None, 'cyl_bar': None})]
        msg = _infeasibility_msg(volumes, reserve_bar=50.0, depth_m=40)
        assert 'insufficient' in msg.lower()
        assert '40' in msg

    def test_custom_prefix_applied(self):
        volumes = [(OpenCircuitGas(21, 0, 40), {'cyl_l': None, 'cyl_bar': None})]
        msg = _infeasibility_msg(volumes, reserve_bar=50.0, depth_m=40, prefix='Bailout gas')
        assert msg.startswith('Bailout gas')

    def test_singular_has_for_one_empty_gas(self):
        g = OpenCircuitGas(21, 0, 40)
        volumes = [(g, {'cyl_l': 12.0, 'cyl_bar': 50.0})]
        msg = _infeasibility_msg(volumes, reserve_bar=50.0, depth_m=40)
        assert ' has ' in msg

    def test_plural_have_for_two_empty_gases(self):
        g1 = OpenCircuitGas(21, 0, 40)
        g2 = OpenCircuitGas(50, 0, 21)
        volumes = [
            (g1, {'cyl_l': 12.0, 'cyl_bar': 50.0}),
            (g2, {'cyl_l': 11.0, 'cyl_bar': 50.0}),
        ]
        msg = _infeasibility_msg(volumes, reserve_bar=50.0, depth_m=40)
        assert ' have ' in msg


# ── PlanWarnings.add_diluent ──────────────────────────────────────────────────

class TestAddDiluent:

    def test_floor_check_fires_when_diluent_exceeds_setpoint(self):
        req = _ccr_req(setpoint=1.3, depth_m=40, bottom_time_min=5)
        w = PlanWarnings(req, 'ccr')
        # 1.4 > 1.35 and 1.4 <= 1.6 → floor fires
        w.add_diluent(diluent_ppo2=1.4, density_gl=3.0)
        floor_warnings = [x for x in w.items if 'exceeds setpoint' in x.message]
        assert len(floor_warnings) == 1
        assert floor_warnings[0].level == 'warning'

    def test_floor_warning_message_contains_depth_and_ppo2(self):
        req = _ccr_req(setpoint=1.3, depth_m=40, bottom_time_min=5)
        w = PlanWarnings(req, 'ccr')
        w.add_diluent(diluent_ppo2=1.4, density_gl=3.0)
        msg = next(x.message for x in w.items if 'exceeds setpoint' in x.message)
        assert '40' in msg
        assert '1.40' in msg

    def test_oxtox_danger_fires_above_1_6(self):
        req = _ccr_req(setpoint=1.3, depth_m=40, bottom_time_min=5)
        w = PlanWarnings(req, 'ccr')
        w.add_diluent(diluent_ppo2=1.7, density_gl=3.0)
        dangers = [x for x in w.items if x.level == 'danger']
        assert len(dangers) == 1
        assert 'flush' in dangers[0].message or 'bail out' in dangers[0].message.lower()

    def test_oxtox_danger_suppresses_floor_warning(self):
        # ppo2=1.7 also exceeds setpoint+0.05, but the oxtox branch takes over
        req = _ccr_req(setpoint=1.3, depth_m=40, bottom_time_min=5)
        w = PlanWarnings(req, 'ccr')
        w.add_diluent(diluent_ppo2=1.7, density_gl=3.0)
        floor_warnings = [x for x in w.items if 'exceeds setpoint' in x.message]
        assert floor_warnings == []

    def test_advisory_fires_for_high_setpoint_masking_case(self):
        # setpoint=1.5: floor_fires = 1.55 > 1.55 → False; oxtox = 1.55 > 1.6 → False
        # advisory fires because not floor_fires and 1.55 > 1.4
        req = _ccr_req(setpoint=1.5, depth_m=40, bottom_time_min=5)
        w = PlanWarnings(req, 'ccr')
        w.add_diluent(diluent_ppo2=1.55, density_gl=3.0)
        advisory = [x for x in w.items if '1.4 bar working limit' in x.message]
        assert len(advisory) == 1
        assert advisory[0].level == 'warning'

    def test_no_ppo2_warning_when_diluent_below_advisory_threshold(self):
        # setpoint=1.2: ppo2=1.24 ≤ setpoint+0.05=1.25 so floor doesn't fire,
        # 1.24 ≤ 1.4 so advisory doesn't fire, 1.24 ≤ 1.6 so no danger
        req = _ccr_req(setpoint=1.2, depth_m=40, bottom_time_min=5)
        w = PlanWarnings(req, 'ccr')
        w.add_diluent(diluent_ppo2=1.24, density_gl=3.0)
        assert w.items == []

    def test_no_ppo2_warning_when_diluent_exactly_at_setpoint(self):
        req = _ccr_req(setpoint=1.3, depth_m=40, bottom_time_min=5)
        w = PlanWarnings(req, 'ccr')
        w.add_diluent(diluent_ppo2=1.3, density_gl=3.0)
        assert w.items == []

    def test_density_danger_included(self):
        req = _ccr_req(setpoint=1.3, depth_m=40, bottom_time_min=5)
        w = PlanWarnings(req, 'ccr')
        w.add_diluent(diluent_ppo2=1.3, density_gl=6.5)
        dangers = [x for x in w.items if x.level == 'danger']
        assert len(dangers) == 1
        assert '6.3 g/L' in dangers[0].message

    def test_density_warning_included(self):
        req = _ccr_req(setpoint=1.3, depth_m=40, bottom_time_min=5)
        w = PlanWarnings(req, 'ccr')
        w.add_diluent(diluent_ppo2=1.3, density_gl=5.5)
        density_warnings = [x for x in w.items if '5.2 g/L' in x.message]
        assert len(density_warnings) == 1
        assert density_warnings[0].level == 'warning'

    def test_no_warnings_for_safe_diluent(self):
        req = _ccr_req(setpoint=1.3, depth_m=40, bottom_time_min=5)
        w = PlanWarnings(req, 'ccr')
        w.add_diluent(diluent_ppo2=1.3, density_gl=3.0)
        assert w.items == []

    def test_floor_and_density_warning_both_present(self):
        req = _ccr_req(setpoint=1.3, depth_m=40, bottom_time_min=5)
        w = PlanWarnings(req, 'ccr')
        w.add_diluent(diluent_ppo2=1.4, density_gl=5.5)
        assert len(w.items) == 2
        levels = {x.level for x in w.items}
        assert levels == {'warning'}


# ── PlanWarnings.add_supply ────────────────────────────────────────────────────

class TestAddSupply:

    def test_infeasible_oc_produces_danger(self):
        req = _oc_req()
        w = PlanWarnings(req, 'oc')
        w.add_supply(infeasible=True, shortened=False, bt_actual=5, sorted_volumes=_unlimited_volumes())
        assert len(w.items) == 1
        assert w.items[0].level == 'danger'
        assert w.items[0].message.startswith('Gas')

    def test_infeasible_ccr_produces_danger_with_bailout_prefix(self):
        req = _ccr_req()
        w = PlanWarnings(req, 'ccr')
        w.add_supply(infeasible=True, shortened=False, bt_actual=20, sorted_volumes=_unlimited_volumes())
        assert len(w.items) == 1
        assert w.items[0].level == 'danger'
        assert w.items[0].message.startswith('Bailout gas')

    def test_shortened_oc_produces_supply_warning(self):
        req = _oc_req(bottom_time_min=5)
        w = PlanWarnings(req, 'oc')
        w.add_supply(infeasible=False, shortened=True, bt_actual=3, sorted_volumes=_unlimited_volumes())
        assert len(w.items) == 1
        assert w.items[0].level == 'warning'
        assert 'insufficient gas supply' in w.items[0].message

    def test_shortened_ccr_produces_bailout_supply_warning(self):
        req = _ccr_req()
        w = PlanWarnings(req, 'ccr')
        w.add_supply(infeasible=False, shortened=True, bt_actual=15, sorted_volumes=_unlimited_volumes())
        assert len(w.items) == 1
        assert w.items[0].level == 'warning'
        assert 'insufficient bailout gas supply' in w.items[0].message

    def test_shortened_message_contains_requested_and_actual_time(self):
        req = _ccr_req(bottom_time_min=20)
        w = PlanWarnings(req, 'ccr')
        w.add_supply(infeasible=False, shortened=True, bt_actual=15, sorted_volumes=_unlimited_volumes())
        msg = w.items[0].message
        assert '20' in msg
        assert '15' in msg

    def test_no_warning_when_neither_infeasible_nor_shortened(self):
        req = _oc_req()
        w = PlanWarnings(req, 'oc')
        w.add_supply(infeasible=False, shortened=False, bt_actual=5, sorted_volumes=_unlimited_volumes())
        assert w.items == []

    def test_infeasible_takes_precedence_over_shortened(self):
        req = _oc_req()
        w = PlanWarnings(req, 'oc')
        w.add_supply(infeasible=True, shortened=True, bt_actual=5, sorted_volumes=_unlimited_volumes())
        assert len(w.items) == 1
        assert w.items[0].level == 'danger'


# ── PlanWarnings.add_oc_gases ──────────────────────────────────────────────────

class TestAddOcGases:

    def test_no_warnings_when_no_bailout_gases(self):
        req = _ccr_req()
        w = PlanWarnings(req, 'ccr')
        w.add_oc_gases()
        assert w.items == []

    def test_oc_mode_single_gas_labeled_back_gas(self):
        # EAN50 at depth 40 m: ppO₂ = 0.5 × 5 = 2.5 bar → danger warning with "Back gas"
        req = _oc_req(
            depth_m=40, bottom_time_min=5,
            bailout_gases=[BailoutGasInput(o2=50, he=0, mod_m=21)],
        )
        w = PlanWarnings(req, 'oc')
        w.add_oc_gases()
        assert len(w.items) > 0
        assert any('Back gas' in x.message for x in w.items)

    def test_ccr_mode_single_gas_labeled_bailout_gas(self):
        req = _ccr_req(
            bailout_gases=[BailoutGasInput(o2=50, he=0, mod_m=21)],
        )
        w = PlanWarnings(req, 'ccr')
        w.add_oc_gases()
        assert len(w.items) > 0
        assert any('Bailout gas' in x.message for x in w.items)

    def test_oc_mode_two_gases_uses_back_gas_and_deco_gas_labels(self):
        # Air at 60 m (i=0, back gas) and EAN50 at 21 m (i=1, deco gas)
        req = _oc_req(
            depth_m=60, bottom_time_min=10,
            bailout_gases=[
                BailoutGasInput(o2=21, he=0, mod_m=60),
                BailoutGasInput(o2=50, he=0, mod_m=21),
            ],
        )
        w = PlanWarnings(req, 'oc')
        w.add_oc_gases()
        messages = [x.message for x in w.items]
        assert any('Back gas' in m for m in messages)
        assert any('Deco gas' in m for m in messages)

    def test_ccr_mode_two_gases_both_labeled_bailout_gas(self):
        req = _ccr_req(
            depth_m=60, bottom_time_min=10,
            bailout_gases=[
                BailoutGasInput(o2=21, he=0, mod_m=60),
                BailoutGasInput(o2=50, he=0, mod_m=21),
            ],
        )
        w = PlanWarnings(req, 'ccr')
        w.add_oc_gases()
        assert len(w.items) > 0
        assert all('Bailout gas' in x.message for x in w.items)


# ── PlanWarnings.add_cns ───────────────────────────────────────────────────────

class TestAddCns:

    def test_warning_at_threshold(self):
        req = _ccr_req()
        w = PlanWarnings(req, 'ccr')
        w.add_cns(req.cns_warn_pct)  # exactly at threshold
        assert len(w.items) == 1
        assert w.items[0].level == 'warning'

    def test_warning_above_threshold(self):
        req = _ccr_req()
        w = PlanWarnings(req, 'ccr')
        w.add_cns(req.cns_warn_pct + 10)
        assert len(w.items) == 1

    def test_no_warning_below_threshold(self):
        req = _ccr_req()
        w = PlanWarnings(req, 'ccr')
        w.add_cns(req.cns_warn_pct - 1)
        assert w.items == []

    def test_cns_value_in_message(self):
        req = _ccr_req()
        w = PlanWarnings(req, 'ccr')
        w.add_cns(95.0)
        assert '95.0' in w.items[0].message

    def test_threshold_value_in_message(self):
        req = _ccr_req(cns_warn_pct=75.0)
        w = PlanWarnings(req, 'ccr')
        w.add_cns(80.0)
        assert '75' in w.items[0].message


# ── PlanWarnings.add_bailout_error ────────────────────────────────────────────

class TestAddBailoutError:

    def test_produces_warning_level(self):
        req = _ccr_req()
        w = PlanWarnings(req, 'ccr')
        w.add_bailout_error('some calculation error')
        assert len(w.items) == 1
        assert w.items[0].level == 'warning'

    def test_message_contains_prefix_and_error(self):
        req = _ccr_req()
        w = PlanWarnings(req, 'ccr')
        w.add_bailout_error('division by zero')
        assert w.items[0].message == 'Bailout plan could not be computed: division by zero'

    def test_empty_error_string(self):
        req = _ccr_req()
        w = PlanWarnings(req, 'ccr')
        w.add_bailout_error('')
        assert 'Bailout plan could not be computed:' in w.items[0].message


# ── PlanWarnings.items (accumulation and copy semantics) ──────────────────────

class TestPlanWarningsItems:

    def test_empty_initially(self):
        assert PlanWarnings(_ccr_req(), 'ccr').items == []

    def test_items_accumulate_in_call_order(self):
        req = _ccr_req(depth_m=40, bottom_time_min=5)
        w = PlanWarnings(req, 'ccr')
        w.add_cns(95.0)
        w.add_bailout_error('boom')
        items = w.items
        assert len(items) == 2
        assert 'CNS' in items[0].message
        assert 'Bailout plan could not be computed' in items[1].message

    def test_items_returns_copy(self):
        req = _ccr_req()
        w = PlanWarnings(req, 'ccr')
        w.add_cns(95.0)
        snapshot = w.items
        snapshot.append(Warning(level='danger', message='injected'))
        assert len(w.items) == 1

    def test_multiple_add_calls_accumulate(self):
        req = _ccr_req(depth_m=40, bottom_time_min=5)
        w = PlanWarnings(req, 'ccr')
        w.add_diluent(diluent_ppo2=1.4, density_gl=3.0)   # 1 floor warning
        w.add_cns(95.0)                                     # 1 cns warning
        w.add_bailout_error('error')                        # 1 bailout warning
        assert len(w.items) == 3
