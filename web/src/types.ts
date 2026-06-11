// ── Gas Blender API ────────────────────────────────────────────────────────────

export interface GasComposition { o2: number; he: number; n2: number; bar: number }
export interface BlendStep {
  name: string
  start_gas: GasComposition
  add_bar: number
  result_gas: GasComposition
}
export interface TrimixBlendAnalysis {
  mod_1_2: number; mod_1_4: number; mod_1_6: number
  density_max_depth: number; density_limit_depth: number
  end_30_depth: number; end_40_depth: number
}
export interface TrimixBlendResponse {
  steps: BlendStep[]
  analysis: TrimixBlendAnalysis
}

// ── Dive Planner API ───────────────────────────────────────────────────────────

export interface Warning { level: string; message: string }
export interface DecoStop { depth_m: number; time_min: number; runtime_min: number }
export interface ProfilePoint { t: number; d: number; c: number; sats: number[]; inert?: [number, number][] }
export interface DensityAnalysis {
  density_gl: number
  exceeded_recommended: boolean
  exceeded_limit: boolean
}
export interface GasSwitch { depth_m: number; label: string }
export interface GasSupplyEntry {
  o2: number; he: number; mod_m: number
  consumed_L: number; available_L: number | null; pct: number | null
}
export interface BailoutPlan {
  stops: DecoStop[]
  total_time_min: number; tts_min: number; cns_pct: number; otu: number
  gas_switches: GasSwitch[]
  profile_points: ProfilePoint[]
  tissue_saturations: number[]
  gas_supply: GasSupplyEntry[] | null
}
export interface DivePlannerResponse {
  stops: DecoStop[]
  total_time_min: number; tts_min: number; cns_pct: number; otu: number
  bottom_time_actual: number
  profile_points: ProfilePoint[]
  tissue_saturations: number[]
  density_analysis: DensityAnalysis
  bailout: BailoutPlan | null
  warnings: Warning[]
}

// ── App state ──────────────────────────────────────────────────────────────────

export interface GasEntry {
  id: number; o2: number; he: number; setpoint: number; active: boolean
}
export interface BailoutEntry {
  id: number; o2: number; he: number; mod_m: number
  cyl_l: number; cyl_bar: number; active: boolean
  ppo2_limit?: number
}
export interface PlannerSettings {
  gfLow: number; gfHigh: number
  bailoutGfLow: number; bailoutGfHigh: number
  descRate: number; ascRateDeep: number; ascRateShallow: number
  lastStopM: number; cnsWarnPct: number
  sacBottom: number; sacDeco: number; reserveBar: number
}
export interface SavedPlan {
  id: number; name: string; created_at: string
  gas: { o2: number; he: number; setpoint: number }
  depth_m: number; bottom_time_min: number
}
