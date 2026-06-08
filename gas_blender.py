import json
import math

_MOLAR_VOLUME = 22.4  # L/mol at STP (0°C, 1 atm) — consistent with BSAC gas density tables


def mod_m(o2_pct, ppo2=1.4):
    """Maximum Operating Depth in metres for a given O2% and ppO2 limit."""
    return round((ppo2 / (o2_pct / 100) - 1) * 10, 1)


def gas_density(o2_pct, he_pct, depth_m):
    """Gas density in g/L at a given depth in metres (BSAC method)."""
    n2_pct = 100 - o2_pct - he_pct
    molar_mass = (o2_pct * 32 + n2_pct * 28 + he_pct * 4) / 100
    return round(molar_mass / _MOLAR_VOLUME * (depth_m / 10 + 1), 2)


def density_depth(o2_pct, he_pct, density_limit):
    """Depth (m) at which the gas mix reaches a given density limit (BSAC method)."""
    n2_pct = 100 - o2_pct - he_pct
    molar_mass = (o2_pct * 32 + n2_pct * 28 + he_pct * 4) / 100
    return round((density_limit * _MOLAR_VOLUME / molar_mass - 1) * 10, 1)


def end_m(o2_pct, he_pct, depth_m):
    """Equivalent Narcotic Depth in metres at a given depth (O2 + N2 narcotic, BSAC method)."""
    return round(((depth_m / 10 + 1) * (100 - he_pct) / 100 - 1) * 10, 1)


def end_depth(o2_pct, he_pct, end_limit):
    """Depth (m) at which the gas mix reaches a given END limit (O2 + N2 narcotic, BSAC method)."""
    return round(((end_limit / 10 + 1) / ((100 - he_pct) / 100) - 1) * 10, 1)


def best_mix(depth_m, ppo2=1.4, density_limit=5.2):
    """Best O2% and He% for a given depth, ppO2 limit, and density limit (BSAC method).

    O2 is set to the fraction that exactly reaches ppo2 at depth.
    He is the minimum fraction needed to keep density at or below density_limit.
    Returns (o2_pct, he_pct) as rounded integers.
    """
    p_abs = depth_m / 10 + 1
    fo2 = min(ppo2 / p_abs, 1.0)
    target_mm = density_limit * _MOLAR_VOLUME / p_abs
    fhe = (28 + 4 * fo2 - target_mm) / 24
    fhe = max(0.0, min(fhe, 1.0 - fo2))
    return round(fo2 * 100), round(fhe * 100)


class Gas:
    def __init__(self, bar, o2, he):
        self.bar = bar
        self.o2 = o2
        self.he = he
        self.n2 = 100 - o2 - he
        self.bar_he = (self.bar + 1) * self.he / 100
        self.bar_o2 = (self.bar + 1) * self.o2 / 100
        self.bar_n2 = (self.bar + 1) * self.n2 / 100

    def __str__(self):
        return f"{self.bar:.1f} bar {self.short_name()}"

    def short_name(self):
        if self.o2 == 100:
            return "O2"
        elif self.he == 100:
            return "He"
        elif self.o2 == 21 and self.he == 0:
            return "Air"
        elif self.o2 > 21 and self.he == 0:
            return f"N{self.o2:.1f}%"
        else:
            return f"{self.o2:.1f}/{self.he:.1f}"


class BlendStep:
    def __init__(self, name, start_gas, result_gas):
        self.name = name
        self.start_gas = start_gas
        self.result_gas = result_gas

    def __str__(self):
        diff = self.result_gas.bar - self.start_gas.bar
        return f"{self.name}\t{self.start_gas.bar:.1f}\t{self.result_gas.bar:.1f} ({diff:.1f})\t{self.result_gas}"


class TrimixBlend:
    def __init__(self, start_gas, finish_gas, he_gas=None):
        self.start_gas = start_gas
        self.finish_gas = finish_gas
        self.he_gas = he_gas if he_gas is not None else Gas(250, 0, 100)
        self.blend()

    def __str__(self):
        msg = "\tStart\tFinish\t\tTest\n"
        for step in self.steps:
            msg += step.__str__() + "\n"
        return msg

    def toJSON(self):
        return json.dumps(self, default=lambda o: o.__dict__, sort_keys=True, indent=4)

    def blend(self):
        self.steps = []
        if self.finish_gas.bar <= self.start_gas.bar:
            raise ValueError(
                f"Target pressure ({self.finish_gas.bar} bar) must be greater than "
                f"start pressure ({self.start_gas.bar} bar)."
            )
        if self.finish_gas.he == 0:
            self.step_o2(self.start_gas)
        else:
            self.step_he(self.he_gas.short_name(), self.start_gas, self.he_gas)
            self.step_o2(self.steps[-1].result_gas)
        self.step_air()

    def step_he(self, name, start_gas, he_gas):
        if he_gas.he == 0:
            raise ValueError(f"Helium bank '{name}' contains 0% helium")
        if start_gas.bar >= he_gas.bar:
            raise ValueError(
                f"He bank exhausted: cylinder pressure ({start_gas.bar:.1f} bar) is already "
                f"at or above the He bank pressure ({he_gas.bar:.1f} bar)."
            )
        bar_p = (self.finish_gas.bar_he - start_gas.bar_he) * (100 / he_gas.he)
        if bar_p < 0:
            bleed_to = max(0, math.floor(self.finish_gas.bar_he / (start_gas.he / 100) - 1))
            raise ValueError(
                f"Blend not achievable: the target contains less helium than the start gas. "
                f"Bleed the cylinder to {bleed_to} bar and start again."
            )
        he_required = start_gas.bar + bar_p > he_gas.bar
        if he_required:
            bar_p = he_gas.bar - start_gas.bar
        target_he = start_gas.bar + bar_p
        self.add_step(name, start_gas, Gas(round(target_he, 1), he_gas.o2, he_gas.he))
        if he_required:
            self.step_he("He", self.steps[-1].result_gas, Gas(250, 0, 100))

    def step_o2(self, start_gas):
        target_o2 = start_gas.bar + self.finish_gas.bar_o2 - start_gas.bar_o2 - ((self.finish_gas.bar_n2 - start_gas.bar_n2) * (0.21 / 0.79))
        if target_o2 > start_gas.bar:
            self.add_step("O₂", start_gas, Gas(round(target_o2, 1), 100, 0))

    def step_air(self):
        current = self.steps[-1].result_gas if self.steps else self.start_gas
        target_air = current.bar + ((self.finish_gas.bar_n2 - current.bar_n2) / 0.79)
        if target_air < current.bar - 0.5:
            fhe_bank = self.he_gas.he / 100
            c = (100 - self.he_gas.o2 - self.he_gas.he) / 100 / fhe_bank if fhe_bank > 0 else 0
            denom = self.start_gas.n2 / 100 - c * self.start_gas.he / 100
            if denom > 0:
                bleed_to = max(0, math.floor(
                    (self.finish_gas.bar_n2 - c * self.finish_gas.bar_he) / denom - 1
                ))
                raise ValueError(
                    f"Blend not achievable: the start gas contains too much N2 to reach "
                    f"the target mix. Bleed the cylinder to {bleed_to} bar and start again."
                )
            raise ValueError(
                "Blend not achievable: the start gas contains too much N2 to reach "
                "the target mix. Bleed the cylinder and start again."
            )
        if target_air > self.finish_gas.bar + 2:
            raise ValueError(
                "Blend not achievable: the start gas contains too much O2 or N2 to reach "
                "the target mix. Bleed the cylinder and start again."
            )
        self.add_step("Air", current, Gas(round(target_air, 1), 21, 0))

    def add_step(self, name, start_gas, topup_gas):
        self.steps.append(BlendStep(name, start_gas, topup_blend(start_gas, topup_gas)))


def topup_blend(start_gas, topup_gas, bar=None):
    bar = topup_gas.bar if bar is None else bar
    o2 = round((((start_gas.o2 / 100) * start_gas.bar) + ((topup_gas.bar - start_gas.bar) * (topup_gas.o2 / 100))) / topup_gas.bar * 100, 1)
    he = round((((start_gas.he / 100) * start_gas.bar) + ((topup_gas.bar - start_gas.bar) * (topup_gas.he / 100))) / topup_gas.bar * 100, 1)
    return Gas(bar, o2, he)
