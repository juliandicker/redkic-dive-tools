import json

_MOLAR_VOLUME = 22.4  # L/mol at STP (0°C, 1 atm) — consistent with BSAC gas density tables


def mod_m(o2_pct, ppo2=1.4):
    """Maximum Operating Depth in metres for a given O2% and ppO2 limit."""
    return round((ppo2 / (o2_pct / 100) - 1) * 10, 1)


def gas_density(o2_pct, he_pct, depth_m):
    """Gas density in g/L at a given depth in metres (BSAC method)."""
    n2_pct = 100 - o2_pct - he_pct
    molar_mass = (o2_pct * 32 + n2_pct * 28 + he_pct * 4) / 100
    return round(molar_mass / _MOLAR_VOLUME * (depth_m / 10 + 1), 2)


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
        bar_p = (self.finish_gas.bar_he - start_gas.bar_he) * (100 / he_gas.he)
        if bar_p < 0:
            raise ValueError(
                "Blend not achievable: the target contains less helium than the start gas. "
                "Bleed the cylinder and start again."
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
            self.add_step("O2", start_gas, Gas(round(target_o2, 1), 100, 0))

    def step_air(self):
        current = self.steps[-1].result_gas if self.steps else self.start_gas
        target_air = current.bar + ((self.finish_gas.bar_n2 - current.bar_n2) / 0.79)
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
