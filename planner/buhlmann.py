import math
import copy

WATER_VAPOUR_BAR = 0.0627
SURFACE_BAR = 1.013
_FN2_AIR = 0.7902

# ZHL-16C coefficients: (ht_n2, a_n2, b_n2, ht_he, a_he, b_he)
ZHL16C = [
    (  5.0, 1.1696, 0.5578,   1.88, 1.6189, 0.4770),
    (  8.0, 1.0000, 0.6514,   3.02, 1.3830, 0.5747),
    ( 12.5, 0.8618, 0.7222,   4.72, 1.1919, 0.6527),
    ( 18.5, 0.7562, 0.7825,   6.99, 1.0458, 0.7223),
    ( 27.0, 0.6200, 0.8126,  10.21, 0.9220, 0.7582),
    ( 38.3, 0.5043, 0.8434,  14.48, 0.8205, 0.7957),
    ( 54.3, 0.4410, 0.8693,  20.53, 0.7305, 0.8279),
    ( 77.0, 0.4000, 0.8910,  29.11, 0.6502, 0.8553),
    (109.0, 0.4187, 0.9092,  41.20, 0.5950, 0.8757),
    (146.0, 0.3798, 0.9222,  55.19, 0.5545, 0.8903),
    (187.0, 0.3497, 0.9319,  70.69, 0.5333, 0.8997),
    (239.0, 0.3223, 0.9403,  90.34, 0.5189, 0.9073),
    (305.0, 0.2971, 0.9477, 115.29, 0.5181, 0.9122),
    (390.0, 0.2737, 0.9544, 147.42, 0.5176, 0.9171),
    (498.0, 0.2523, 0.9602, 188.24, 0.5172, 0.9217),
    (635.0, 0.2327, 0.9653, 240.03, 0.5119, 0.9267),
]


def schreiner(p_begin, p_gas, duration_min, half_time_min, rate_bar_per_min):
    """Inert gas pressure after a linear-rate segment (Schreiner equation)."""
    k = math.log(2) / half_time_min
    return (p_gas
            + rate_bar_per_min * (duration_min - 1.0 / k)
            - (p_gas - p_begin - rate_bar_per_min / k) * math.exp(-k * duration_min))


class Tissue:
    def __init__(self, ht_n2, a_n2, b_n2, ht_he, a_he, b_he):
        self.ht_n2 = ht_n2
        self.a_n2 = a_n2
        self.b_n2 = b_n2
        self.ht_he = ht_he
        self.a_he = a_he
        self.b_he = b_he
        # Initialise to surface saturation: N2 only, no He
        self.pn2 = _FN2_AIR * (SURFACE_BAR - WATER_VAPOUR_BAR)
        self.phe = 0.0

    def load(self, pp_n2_start, pp_he_start, pp_n2_end, pp_he_end, duration_min):
        """Apply Schreiner equation for N2 and He over one segment."""
        if duration_min <= 0:
            return
        rate_n2 = (pp_n2_end - pp_n2_start) / duration_min
        rate_he = (pp_he_end - pp_he_start) / duration_min
        self.pn2 = schreiner(self.pn2, pp_n2_start, duration_min, self.ht_n2, rate_n2)
        self.phe = schreiner(self.phe, pp_he_start, duration_min, self.ht_he, rate_he)

    def ceiling(self, gf):
        """Tolerated ambient pressure (bar) for this tissue at gradient factor gf (0–1)."""
        p_total = self.pn2 + self.phe
        if p_total <= 0:
            return 0.0
        # Weighted Bühlmann a/b coefficients
        a = (self.a_n2 * self.pn2 + self.a_he * self.phe) / p_total
        b = (self.b_n2 * self.pn2 + self.b_he * self.phe) / p_total
        return (p_total - a * gf) / (gf / b - gf + 1.0)


class BuhlmannModel:
    def __init__(self):
        self.tissues = [Tissue(*c) for c in ZHL16C]

    def load_segment(self, gas, depth_start_m, depth_end_m, duration_min):
        """Load all tissues for one dive segment."""
        p_start = depth_start_m / 10.0 + SURFACE_BAR
        p_end = depth_end_m / 10.0 + SURFACE_BAR
        pp_n2_start = gas.pp_n2(p_start)
        pp_he_start = gas.pp_he(p_start)
        pp_n2_end = gas.pp_n2(p_end)
        pp_he_end = gas.pp_he(p_end)
        for t in self.tissues:
            t.load(pp_n2_start, pp_he_start, pp_n2_end, pp_he_end, duration_min)

    def ceiling_bar(self, gf):
        """Deepest tissue ceiling in bar."""
        return max(t.ceiling(gf) for t in self.tissues)

    def ceiling_m(self, gf):
        """Deepest tissue ceiling in metres (0 if below surface)."""
        return max(0.0, (self.ceiling_bar(gf) - SURFACE_BAR) * 10.0)

    def tissue_saturations(self, gf_high):
        """Saturation ratio for each compartment vs GF-adjusted surface M-value (1.0 = at limit)."""
        result = []
        for t in self.tissues:
            p_total = t.pn2 + t.phe
            if p_total <= 0:
                result.append(0.0)
                continue
            a = (t.a_n2 * t.pn2 + t.a_he * t.phe) / p_total
            b = (t.b_n2 * t.pn2 + t.b_he * t.phe) / p_total
            m_adjusted = SURFACE_BAR + gf_high * (a + SURFACE_BAR / b - SURFACE_BAR)
            result.append(round(p_total / m_adjusted, 3))
        return result

    def copy(self):
        return copy.deepcopy(self)


# NOAA single-dive CNS table: (ppO2, % per minute)
_CNS_TABLE = [
    (0.50, 0.0),
    (0.60, 100 / 720),
    (0.70, 100 / 570),
    (0.80, 100 / 450),
    (0.90, 100 / 360),
    (1.00, 100 / 300),
    (1.10, 100 / 270),
    (1.20, 100 / 240),
    (1.30, 100 / 210),
    (1.40, 100 / 180),
    (1.50, 100 / 150),
    (1.60, 100 / 120),
]


def _cns_rate(ppo2):
    if ppo2 <= 0.5:
        return 0.0
    if ppo2 >= 1.6:
        return 100 / 120
    for i in range(len(_CNS_TABLE) - 1):
        p0, r0 = _CNS_TABLE[i]
        p1, r1 = _CNS_TABLE[i + 1]
        if p0 <= ppo2 <= p1:
            return r0 + (ppo2 - p0) / (p1 - p0) * (r1 - r0)
    return 0.0


def _otu_rate(ppo2):
    if ppo2 <= 0.5:
        return 0.0
    return ((ppo2 - 0.5) / 0.5) ** (5 / 6)


def _oc_cns_otu(profile, sorted_gases):
    """Integrate CNS% and OTU over an OC profile. sorted_gases sorted by mod_m ascending."""
    def select_gas(depth_m):
        for g in sorted_gases:
            if depth_m <= g.mod_m:
                return g
        return sorted_gases[-1]

    cns = 0.0
    otu = 0.0
    pts = profile.profile_points
    for i in range(len(pts) - 1):
        d1, d2 = pts[i]['d'], pts[i + 1]['d']
        t1, t2 = pts[i]['t'], pts[i + 1]['t']
        dt = t2 - t1
        if dt <= 0:
            continue
        avg_depth = (d1 + d2) / 2.0
        p_abs = avg_depth / 10.0 + SURFACE_BAR
        ppo2 = select_gas(avg_depth).fo2 * p_abs
        cns += _cns_rate(ppo2) * dt
        otu += _otu_rate(ppo2) * dt
    return cns, otu
