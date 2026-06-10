from .buhlmann import WATER_VAPOUR_BAR


class OpenCircuitGas:
    """Open-circuit gas (trimix, nitrox, oxygen, air).

    Exposes the same pp_n2 / pp_he interface as CCRGas so it can be passed
    directly to BuhlmannModel.load_segment without any special casing.
    """

    def __init__(self, o2_pct: float, he_pct: float, mod_m: float):
        self.fo2 = o2_pct / 100.0
        self.fhe = he_pct / 100.0
        self.fn2 = 1.0 - self.fo2 - self.fhe
        self.mod_m = mod_m

    @property
    def label(self):
        if self.fhe == 0.0:
            return f"{round(self.fo2 * 100)}/{round(self.fn2 * 100)}"
        return f"{round(self.fo2 * 100)}/{round(self.fhe * 100)}"

    def pp_o2(self, p_abs_bar: float) -> float:
        return max(0.0, p_abs_bar - WATER_VAPOUR_BAR) * self.fo2

    def pp_n2(self, p_abs_bar: float) -> float:
        return max(0.0, p_abs_bar - WATER_VAPOUR_BAR) * self.fn2

    def pp_he(self, p_abs_bar: float) -> float:
        return max(0.0, p_abs_bar - WATER_VAPOUR_BAR) * self.fhe


class CCRGas:
    """CCR diluent with a fixed O2 setpoint.

    On CCR, ppO2 is held at the setpoint; the remaining ambient pressure
    (minus water vapour) is inert gas split by the diluent N2/He ratio.
    """

    def __init__(self, diluent_o2_pct, diluent_he_pct, setpoint_bar):
        self.fo2 = diluent_o2_pct / 100.0
        self.fhe = diluent_he_pct / 100.0
        self.fn2 = 1.0 - self.fo2 - self.fhe
        self.setpoint = setpoint_bar
        self._inert_total = self.fn2 + self.fhe

    def _pp_inert(self, p_abs_bar):
        return max(0.0, p_abs_bar - self.setpoint - WATER_VAPOUR_BAR)

    def pp_n2(self, p_abs_bar):
        if self._inert_total <= 0:
            return 0.0
        return self._pp_inert(p_abs_bar) * self.fn2 / self._inert_total

    def pp_he(self, p_abs_bar):
        if self._inert_total <= 0:
            return 0.0
        return self._pp_inert(p_abs_bar) * self.fhe / self._inert_total
