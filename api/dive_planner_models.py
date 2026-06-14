from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class BailoutGasInput(BaseModel):
    o2: float = Field(ge=1, le=100, description="O₂ (%)")
    he: float = Field(default=0.0, ge=0, le=100, description="He (%)")
    mod_m: float = Field(gt=0, description="Maximum Operating Depth (m)")
    ppo2_limit: float = Field(default=1.4, ge=1.0, le=1.6, description="ppO₂ working limit used to set MOD (bar)")
    cyl_l: Optional[float] = Field(default=None, gt=0, description="Cylinder water volume (L)")
    cyl_bar: Optional[float] = Field(default=None, gt=0, description="Fill pressure (bar)")


class DivePlannerRequest(BaseModel):
    """CCR/OC decompression planning parameters (Bühlmann ZHL-16C with gradient factors)."""
    mode: Literal["ccr", "oc"] = Field(default="ccr", description="Dive mode: 'ccr' or 'oc'")
    diluent_o2: Optional[float] = Field(default=None, ge=1, le=100, description="Diluent O₂ (%; CCR only)")
    diluent_he: Optional[float] = Field(default=None, ge=0, le=100, description="Diluent He (%; CCR only)")
    setpoint: Optional[float] = Field(default=None, gt=0, le=2.0, description="CCR setpoint (bar ppO₂; CCR only)")
    depth_m: float = Field(gt=0, description="Bottom depth (m)")
    bottom_time_min: float = Field(gt=0, description="Bottom time (min)")
    gf_low: float = Field(default=60.0, ge=1.0, le=100.0, description="GF Low (%)")
    gf_high: float = Field(default=80.0, ge=1.0, le=100.0, description="GF High (%)")
    desc_rate_mpm: float = Field(default=20.0, ge=1.0, le=50.0, description="Descent rate (m/min)")
    asc_rate_deep_mpm: float = Field(default=9.0, ge=1.0, le=30.0, description="Ascent rate above 6 m (m/min)")
    asc_rate_shallow_mpm: float = Field(default=3.0, ge=1.0, le=30.0, description="Ascent rate ≤6 m (m/min)")
    last_stop_m: Literal[3, 4, 5, 6, 9] = Field(default=3, description="Shallowest deco stop depth (m)")
    cns_warn_pct: float = Field(default=80.0, ge=50.0, le=100.0, description="CNS O₂ toxicity warning threshold (%)")
    bailout_gf_low: Optional[float] = Field(default=None, ge=1.0, le=100.0, description="Bailout GF Low (%; CCR only, defaults to gf_low)")
    bailout_gf_high: Optional[float] = Field(default=None, ge=1.0, le=100.0, description="Bailout GF High (%; CCR only, defaults to gf_high)")
    bailout_gases: List[BailoutGasInput] = Field(default=[], description="OC bailout/deco gases")
    sac_bottom_lpm: float = Field(default=25.0, ge=2.0, le=200.0, description="Bottom SAC / RMV (L/min)")
    sac_deco_lpm: float = Field(default=15.0, ge=2.0, le=200.0, description="Deco SAC / RMV (L/min)")
    reserve_bar: float = Field(default=50.0, ge=0.0, le=300.0, description="Cylinder reserve (bar)")

    @model_validator(mode='after')
    def check_diluent(self):
        if self.mode == 'ccr':
            if self.diluent_o2 is None or self.diluent_he is None or self.setpoint is None:
                raise ValueError("diluent_o2, diluent_he, and setpoint are required for CCR mode.")
            if not (0 < self.diluent_o2 + self.diluent_he <= 100):
                raise ValueError("Invalid diluent composition.")
        return self

    @model_validator(mode='after')
    def check_oc_gases(self):
        if self.mode == 'oc' and not self.bailout_gases:
            raise ValueError("At least one deco gas is required for OC mode.")
        return self

    @model_validator(mode='after')
    def check_gf_ordering(self):
        if self.gf_low > self.gf_high:
            raise ValueError("GF Low must be ≤ GF High.")
        return self

    @model_validator(mode='after')
    def check_bottom_time(self):
        if self.bottom_time_min <= self.depth_m / self.desc_rate_mpm:
            raise ValueError("Bottom time must exceed descent time.")
        return self

    @model_validator(mode='after')
    def check_bailout_gf(self):
        bg_low  = self.bailout_gf_low  if self.bailout_gf_low  is not None else self.gf_low
        bg_high = self.bailout_gf_high if self.bailout_gf_high is not None else self.gf_high
        if bg_low > bg_high:
            raise ValueError("Bailout GF Low must be ≤ Bailout GF High.")
        return self


class Warning(BaseModel):
    level: str = Field(description="Severity: 'warning' or 'danger'")
    message: str


class DecoStop(BaseModel):
    depth_m: float
    time_min: float
    runtime_min: float


class DensityAnalysis(BaseModel):
    density_gl: float
    exceeded_recommended: bool
    exceeded_limit: bool


class ProfilePoint(BaseModel):
    t: float = Field(description="Runtime (min)")
    d: float = Field(description="Depth (m)")
    c: float = Field(description="Ceiling (m)")
    sats: List[float] = Field(description="Tissue saturation ratios (16 compartments)")
    inert: List[List[float]] = Field(default_factory=list, description="Inert gas loads [[pn2, phe]] per compartment")
    tts: Optional[float] = Field(default=None, description="Time to surface (min) — forward projection from current tissue state")
    gf99: Optional[float] = Field(default=None, description="Current gradient factor of leading tissue, raw % (Perdix spec)")
    ppO2: Optional[float] = Field(default=None, description="ppO₂ (bar)")
    cns: Optional[float] = Field(default=None, description="Cumulative CNS oxygen toxicity (%)")
    otu: Optional[float] = Field(default=None, description="Cumulative OTU")
    density_gl: Optional[float] = Field(default=None, description="Gas density (g/L)")
    gas_o2: Optional[int] = Field(default=None, description="Gas O₂ % breathed at this point")
    gas_he: Optional[int] = Field(default=None, description="Gas He % breathed at this point")
    ndl: Optional[float] = Field(default=None, description="No-decompression limit (min) — time remaining before deco starts")


class GasSwitch(BaseModel):
    depth_m: float
    label: str


class TravelGas(BaseModel):
    o2: int
    he: int
    switch_depth_m: int


class GasSupplyEntry(BaseModel):
    o2: float
    he: float
    mod_m: float
    consumed_L: float
    available_L: Optional[float] = None
    pct: Optional[float] = None


class BailoutPlan(BaseModel):
    stops: List[DecoStop]
    total_time_min: float
    tts_min: float
    cns_pct: float
    otu: float
    gas_switches: List[GasSwitch]
    profile_points: List[ProfilePoint]
    tissue_saturations: List[float]
    gas_supply: Optional[List[GasSupplyEntry]] = None


class DivePlannerResponse(BaseModel):
    """CCR/OC decompression schedule with toxicity data and optional CCR bailout plan."""
    stops: List[DecoStop]
    total_time_min: float
    warnings: List[Warning]
    density_analysis: DensityAnalysis
    profile_points: List[ProfilePoint]
    tissue_saturations: List[float]
    tts_min: float
    cns_pct: float
    otu: float
    bottom_time_actual: float
    gas_switches: List[GasSwitch] = Field(default=[], description="Gas switches during the dive (OC mode)")
    gas_supply: Optional[List[GasSupplyEntry]] = Field(default=None, description="Gas supply summary (OC mode)")
    travel_gas: Optional[TravelGas] = Field(default=None, description="Descent travel gas (OC only, when back gas is hypoxic at surface)")
    bailout: Optional[BailoutPlan] = None
