from typing import List, Optional

from gas_blender import density_depth, gas_density
from planner.gas import OpenCircuitGas
from api.dive_planner_models import DivePlannerRequest, Warning


def _infeasibility_msg(sorted_volumes, reserve_bar, depth_m, prefix='Gas') -> str:
    empty_gases = [
        g.label for g, v in sorted_volumes
        if v['cyl_l'] and v['cyl_bar']
        and v['cyl_l'] * max(0.0, v['cyl_bar'] - reserve_bar) == 0
    ]
    if empty_gases:
        have = 'has' if len(empty_gases) == 1 else 'have'
        return (
            f"{prefix} supply error: {', '.join(empty_gases)} {have} no usable gas after "
            f"deducting the {reserve_bar:.0f} bar reserve. "
            f"Increase cylinder pressure or reduce the tank reserve setting."
        )
    return (
        f"{prefix} supply is insufficient even for the minimum possible dive time "
        f"at {depth_m:.0f} m. Increase cylinder sizes, pressure, or reduce the "
        f"{reserve_bar:.0f} bar reserve."
    )


def _density_warnings(description: str, depth_m: float, d: float) -> List[Warning]:
    if d > 6.3:
        return [Warning(
            level='danger',
            message=(
                f'{description} at {depth_m:.0f} m: '
                f'gas density {d:.2f} g/L exceeds the upper limit (6.3 g/L). '
                f'This gas cannot be safely breathed at this depth — '
                f'consider a less dense alternative or reducing planned depth.'
            ),
        )]
    if d > 5.2:
        return [Warning(
            level='warning',
            message=(
                f'{description} at {depth_m:.0f} m: '
                f'gas density {d:.2f} g/L exceeds the recommended limit (5.2 g/L). '
                f'Increased work of breathing and CO₂ retention risk.'
            ),
        )]
    return []


def _gas_warnings(
    gases, bottom_depth_m,
    first_gas_type='Back gas', other_gas_type='Deco gas',
    skip_first_density=True,
) -> List[Warning]:
    warnings: List[Warning] = []
    for i, bg in enumerate(sorted(gases, key=lambda g: g.mod_m, reverse=True)):
        use_depth = bottom_depth_m if i == 0 else min(bg.mod_m, density_depth(bg.o2, bg.he, 5.2))
        fo2 = bg.o2 / 100.0
        d = gas_density(bg.o2, bg.he, use_depth)
        label = OpenCircuitGas(bg.o2, bg.he, bg.mod_m).label
        ppo2 = fo2 * (use_depth / 10.0 + 1.0)
        ppo2_r = round(ppo2, 2)
        gas_type = first_gas_type if i == 0 else other_gas_type
        if ppo2_r > 1.6:
            warnings.append(Warning(
                level='danger',
                message=(
                    f'{gas_type} {label} at {use_depth:.0f} m: '
                    f'ppO₂ {ppo2:.2f} bar exceeds the absolute maximum (1.6 bar). '
                    f'This gas cannot be safely breathed at this depth.'
                ),
            ))
        elif ppo2_r > bg.ppo2_limit:
            warnings.append(Warning(
                level='warning',
                message=(
                    f'{gas_type} {label} at {use_depth:.0f} m: '
                    f'ppO₂ {ppo2:.2f} bar exceeds the working limit ({bg.ppo2_limit:.1f} bar). '
                    f'Consider a lower O₂ fraction or shallower planned depth.'
                ),
            ))
        if skip_first_density and i == 0:
            continue
        warnings.extend(_density_warnings(f'{gas_type} {label}', use_depth, d))
    return warnings


class PlanWarnings:
    def __init__(self, req: DivePlannerRequest, mode: str):
        self._req = req
        self._mode = mode
        self._items: List[Warning] = []

    def add_diluent(self, diluent_ppo2: float, density_gl: float) -> None:
        req = self._req
        diluent_label = OpenCircuitGas(req.diluent_o2, req.diluent_he, req.depth_m).label

        floor_fires = diluent_ppo2 > req.setpoint + 0.05 and diluent_ppo2 <= 1.6
        if floor_fires:
            self._items.append(Warning(
                level='warning',
                message=(
                    f'Diluent ppO₂ at {req.depth_m:.0f} m is {diluent_ppo2:.2f} bar — '
                    f'exceeds setpoint ({req.setpoint:.2f} bar). '
                    f'The CCR cannot reduce ppO₂ below the diluent floor; '
                    f'actual ppO₂ at depth will be {diluent_ppo2:.2f} bar.'
                ),
            ))
        if diluent_ppo2 > 1.6:
            self._items.append(Warning(
                level='danger',
                message=(
                    f'Diluent {diluent_label} at {req.depth_m:.0f} m: '
                    f'ppO₂ {diluent_ppo2:.2f} bar exceeds the absolute maximum (1.6 bar). '
                    f'Unsafe to flush the loop or bail out on this diluent at this depth — '
                    f'CNS O₂ toxicity risk.'
                ),
            ))
        elif not floor_fires and diluent_ppo2 > 1.4:
            self._items.append(Warning(
                level='warning',
                message=(
                    f'Diluent {diluent_label} at {req.depth_m:.0f} m: '
                    f'ppO₂ {diluent_ppo2:.2f} bar exceeds the 1.4 bar working limit. '
                    f'Safe in normal CCR operation but approach diluent flushes and OC bailout with caution.'
                ),
            ))
        self._items.extend(_density_warnings(f'Diluent {diluent_label}', req.depth_m, density_gl))

    def add_supply(self, infeasible: bool, shortened: bool, bt_actual: float, sorted_volumes) -> None:
        req = self._req
        if infeasible:
            prefix = 'Bailout gas' if self._mode == 'ccr' else 'Gas'
            msg = _infeasibility_msg(sorted_volumes, req.reserve_bar, req.depth_m, prefix=prefix)
            self._items.append(Warning(level='danger', message=msg))
        elif shortened:
            supply_phrase = 'insufficient bailout gas supply' if self._mode == 'ccr' else 'insufficient gas supply'
            self._items.append(Warning(
                level='warning',
                message=(
                    f'Bottom time shortened from {req.bottom_time_min:.0f} min to {bt_actual:.0f} min '
                    f'— {supply_phrase} for the requested dive time.'
                ),
            ))

    def add_oc_gases(self) -> None:
        if not self._req.bailout_gases:
            return
        first_gas_type = 'Bailout gas' if self._mode == 'ccr' else 'Back gas'
        other_gas_type = 'Bailout gas' if self._mode == 'ccr' else 'Deco gas'
        self._items.extend(_gas_warnings(
            self._req.bailout_gases, self._req.depth_m,
            first_gas_type=first_gas_type,
            other_gas_type=other_gas_type,
            skip_first_density=False,
        ))

    def add_cns(self, cns_pct: float) -> None:
        if cns_pct >= self._req.cns_warn_pct:
            self._items.append(Warning(
                level='warning',
                message=(
                    f'CNS O₂ toxicity is {cns_pct:.1f}% — '
                    f'exceeds the warning threshold of {self._req.cns_warn_pct:.0f}%.'
                ),
            ))

    def add_bailout_error(self, error: str) -> None:
        self._items.append(Warning(
            level='warning',
            message=f'Bailout plan could not be computed: {error}',
        ))

    @property
    def items(self) -> List[Warning]:
        return list(self._items)
