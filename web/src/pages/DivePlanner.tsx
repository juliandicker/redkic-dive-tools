import { useState, useEffect, useMemo } from 'react'
import Offcanvas from 'react-bootstrap/Offcanvas'
import Modal from 'react-bootstrap/Modal'
import Header from '../components/Header'
import GasBar from '../components/GasBar'
import PlanSection from '../components/PlanSection'
import { divePlan } from '../api'
import { load, save } from '../storage'
import { densityLimitDepth, bestMix, bailoutAutoMod, gasName } from '../utils'
import type { GasEntry, BailoutEntry, PlannerSettings, SavedPlan, DivePlannerResponse } from '../types'

// ── Default state ──────────────────────────────────────────────────────────────

const DEFAULT_GASES: Omit<GasEntry, 'id'>[] = [
  { o2: 21, he: 0,  setpoint: 1.3, active: false },
  { o2: 10, he: 70, setpoint: 1.3, active: true },
  { o2: 12, he: 60, setpoint: 1.3, active: false },
  { o2: 15, he: 55, setpoint: 1.3, active: false },
  { o2: 18, he: 45, setpoint: 1.3, active: false },
]
const DEFAULT_BAILOUT: Omit<BailoutEntry, 'id'>[] = [
  { o2: 100, he: 0,  mod_m: 6,  cyl_l: 11, cyl_bar: 210, active: false },
  { o2: 80,  he: 0,  mod_m: 9,  cyl_l: 11, cyl_bar: 210, active: false },
  { o2: 60,  he: 0,  mod_m: 12, cyl_l: 11, cyl_bar: 210, active: false },
  { o2: 50,  he: 0,  mod_m: 15, cyl_l: 11, cyl_bar: 210, active: false },
  { o2: 21,  he: 0,  mod_m: 54, cyl_l: 11, cyl_bar: 210, active: false },
  { o2: 21,  he: 25, mod_m: 54, cyl_l: 11, cyl_bar: 210, active: false },
  { o2: 20,  he: 55, mod_m: 57, cyl_l: 11, cyl_bar: 210, active: false },
  { o2: 16,  he: 70, mod_m: 75, cyl_l: 11, cyl_bar: 210, active: false },
  { o2: 13,  he: 75, mod_m: 96, cyl_l: 11, cyl_bar: 210, active: false },
]
const DEFAULT_SETTINGS: PlannerSettings = {
  gfLow: 60, gfHigh: 80,
  bailoutGfLow: 50, bailoutGfHigh: 80,
  descRate: 20, ascRateDeep: 9, ascRateShallow: 3,
  lastStopM: 3, cnsWarnPct: 80,
  sacBottom: 25, sacDeco: 15, reserveBar: 50,
}
const EXAMPLE_PLANS: Omit<SavedPlan, 'id' | 'created_at'>[] = [
  { name: 'Shallow Reef',  gas: { o2: 21, he: 0,  setpoint: 1.3 }, depth_m: 20, bottom_time_min: 45, gf_low: 85, gf_high: 95 },
  { name: 'Wreck Dive',    gas: { o2: 21, he: 35, setpoint: 1.3 }, depth_m: 40, bottom_time_min: 25, gf_low: 65, gf_high: 85 },
  { name: 'Deep Trimix',   gas: { o2: 10, he: 70, setpoint: 1.3 }, depth_m: 60, bottom_time_min: 20, gf_low: 50, gf_high: 80 },
]

function makeGasLibrary(): GasEntry[] {
  let id = 1
  return DEFAULT_GASES.map(g => ({ ...g, id: id++ }))
}
function makeBailoutLibrary(): BailoutEntry[] {
  let id = 1
  return DEFAULT_BAILOUT.map(g => ({ ...g, id: id++ }))
}
function makeExamplePlans(): SavedPlan[] {
  let id = 1
  return EXAMPLE_PLANS.map(p => ({ ...p, id: id++, created_at: new Date().toISOString() }))
}

// ── Gas modal state ────────────────────────────────────────────────────────────

interface GasModalState {
  open: boolean
  isBailout: boolean
  editId: number | null
  o2: number; he: number
  setpoint: number
  mod: number; cylL: number; cylBar: number
  bmDepth: number; bmSp: number; bmPpO2: number
  dlUpper: boolean
  bestMixNote: string
}
const INIT_MODAL: GasModalState = {
  open: false, isBailout: false, editId: null,
  o2: 21, he: 0, setpoint: 1.3, mod: 6, cylL: 7, cylBar: 200,
  bmDepth: 30, bmSp: 1.3, bmPpO2: 1.4, dlUpper: false, bestMixNote: '',
}

// ── Save plan modal ────────────────────────────────────────────────────────────

interface SavePlanModal { open: boolean; name: string; pending: Omit<SavedPlan, 'id' | 'created_at' | 'name'> | null }

// ── Component ──────────────────────────────────────────────────────────────────

export default function DivePlanner() {
  const [gasLib,   setGasLib]   = useState<GasEntry[]>(() =>
    load<{ gases: GasEntry[]; nextId: number } | null>('planner_gases', null)?.gases ?? makeGasLibrary()
  )
  const [gasNextId, setGasNextId] = useState(() =>
    load<{ gases: GasEntry[]; nextId: number } | null>('planner_gases', null)?.nextId ?? DEFAULT_GASES.length + 1
  )
  const [bailoutLib, setBailoutLib] = useState<BailoutEntry[]>(() =>
    load<{ gases: BailoutEntry[]; nextId: number } | null>('planner_bailout_gases', null)?.gases ?? makeBailoutLibrary()
  )
  const [bailoutNextId, setBailoutNextId] = useState(() =>
    load<{ gases: BailoutEntry[]; nextId: number } | null>('planner_bailout_gases', null)?.nextId ?? DEFAULT_BAILOUT.length + 1
  )
  const [settings, setSettings] = useState<PlannerSettings>(() =>
    load<PlannerSettings>('planner_settings', DEFAULT_SETTINGS)
  )
  const [savedPlans, setSavedPlans] = useState<SavedPlan[]>(() =>
    load<{ plans: SavedPlan[]; nextId: number } | null>('planner_saved_plans', null)?.plans ?? makeExamplePlans()
  )
  const [planNextId, setPlanNextId] = useState(() =>
    load<{ plans: SavedPlan[]; nextId: number } | null>('planner_saved_plans', null)?.nextId ?? EXAMPLE_PLANS.length + 1
  )

  const [depth, setDepth]   = useState(40)
  const [bt,    setBt]      = useState(25)
  const [loading, setLoading]   = useState(false)
  const [error,   setError]     = useState('')
  const [result,  setResult]    = useState<DivePlannerResponse | null>(null)

  const [settingsOpen,   setSettingsOpen]   = useState(false)
  const [savedPlansOpen, setSavedPlansOpen] = useState(false)

  const [gasModal, setGasModal] = useState<GasModalState>(INIT_MODAL)
  const [savePlanModal, setSavePlanModal] = useState<SavePlanModal>({ open: false, name: '', pending: null })

  // Persist gas library
  useEffect(() => {
    save('planner_gases', { gases: gasLib, nextId: gasNextId })
  }, [gasLib, gasNextId])

  // Persist bailout library
  useEffect(() => {
    save('planner_bailout_gases', { gases: bailoutLib, nextId: bailoutNextId })
  }, [bailoutLib, bailoutNextId])

  // Persist settings
  useEffect(() => {
    save('planner_settings', settings)
  }, [settings])

  // Persist saved plans
  useEffect(() => {
    save('planner_saved_plans', { plans: savedPlans, nextId: planNextId })
  }, [savedPlans, planNextId])

  const activeGas = useMemo(() => gasLib.find(g => g.active) ?? null, [gasLib])
  const activeBailout = useMemo(() => bailoutLib.filter(g => g.active), [bailoutLib])

  // Gas used at bailout depth — lowest-MOD active bailout gas whose MOD covers the depth
  const bailoutInitialGas = useMemo(() => {
    if (activeBailout.length === 0) return null
    const sorted = [...activeBailout].sort((a, b) => a.mod_m - b.mod_m)
    return (sorted.find(g => depth <= g.mod_m) ?? sorted[sorted.length - 1])
  }, [activeBailout, depth])

  // Shared X axis max so CCR and bailout charts align
  const btActual = result?.bottom_time_actual ?? bt
  const sharedXMax = useMemo(() => {
    if (!result?.bailout?.profile_points?.length || !result.profile_points?.length) return undefined
    const ccrXMax = result.profile_points[result.profile_points.length - 1].t
    const ocXMax  = result.bailout.profile_points[result.bailout.profile_points.length - 1].t + btActual
    return Math.max(ccrXMax, ocXMax)
  }, [result, btActual])

  // Bailout chart: CCR descent+bottom pts prepended, OC pts offset by btActual
  const bailoutProfilePoints = useMemo(() => {
    if (!result?.bailout) return []
    const ccrPts = result.profile_points.filter(p => p.t <= btActual + 0.05)
    const ocPts  = result.bailout.profile_points.map(p => ({ ...p, t: p.t + btActual }))
    return [...ccrPts, ...ocPts]
  }, [result, btActual])

  async function calculate() {
    if (!activeGas) return
    setError('')
    setLoading(true)
    try {
      const data = await divePlan({
        diluent_o2:           activeGas.o2,
        diluent_he:           activeGas.he,
        setpoint:             activeGas.setpoint,
        depth_m:              depth,
        bottom_time_min:      bt,
        gf_low:               settings.gfLow,
        gf_high:              settings.gfHigh,
        desc_rate_mpm:        settings.descRate,
        asc_rate_deep_mpm:    settings.ascRateDeep,
        asc_rate_shallow_mpm: settings.ascRateShallow,
        last_stop_m:          settings.lastStopM,
        cns_warn_pct:         settings.cnsWarnPct,
        bailout_gases:        activeBailout.map(g => ({
          o2: g.o2, he: g.he, mod_m: g.mod_m,
          cyl_l: g.cyl_l || null, cyl_bar: g.cyl_bar || null,
        })),
        bailout_gf_low:       settings.bailoutGfLow,
        bailout_gf_high:      settings.bailoutGfHigh,
        sac_bottom_lpm:       settings.sacBottom,
        sac_deco_lpm:         settings.sacDeco,
        reserve_bar:          settings.reserveBar,
      })
      setResult(data)
    } catch (e) {
      setError((e as Error).message)
      setResult(null)
    } finally {
      setLoading(false)
    }
  }

  // ── Gas library actions ──────────────────────────────────────────────────────

  function selectGas(id: number) {
    setGasLib(prev => prev.map(g => ({ ...g, active: g.id === id })))
  }

  function toggleBailout(id: number) {
    setBailoutLib(prev => prev.map(g => g.id === id ? { ...g, active: !g.active } : g))
  }

  function deleteGas(id: number) {
    setGasLib(prev => {
      if (prev.length <= 1) return prev
      const gas = prev.find(g => g.id === id)
      if (!gas || !window.confirm(`Remove ${gasName(gas.o2, gas.he)}?`)) return prev
      const next = prev.filter(g => g.id !== id)
      if (gas.active && next.length > 0) next[0] = { ...next[0], active: true }
      return next
    })
  }

  function deleteBailout(id: number) {
    setBailoutLib(prev => {
      const gas = prev.find(g => g.id === id)
      if (!gas || !window.confirm(`Remove ${gasName(gas.o2, gas.he)}?`)) return prev
      return prev.filter(g => g.id !== id)
    })
  }

  function openGasModal(isBailout: boolean, editId?: number) {
    const lib = isBailout ? bailoutLib : gasLib
    const gas = editId != null ? lib.find(g => g.id === editId) : null
    const bmDepth = Math.min(150, Math.max(5, Math.ceil(depth / 5) * 5))
    if (isBailout) {
      const bg = gas as BailoutEntry | null
      setGasModal({
        ...INIT_MODAL, open: true, isBailout: true, editId: editId ?? null,
        o2: bg?.o2 ?? 21, he: bg?.he ?? 0,
        mod: bg?.mod_m ?? bailoutAutoMod(21),
        cylL: bg?.cyl_l ?? 7, cylBar: bg?.cyl_bar ?? 200,
        bmDepth, bmSp: 1.3, bmPpO2: 1.4, dlUpper: false, bestMixNote: '',
        setpoint: 1.3,
      })
    } else {
      const dg = gas as GasEntry | null
      setGasModal({
        ...INIT_MODAL, open: true, isBailout: false, editId: editId ?? null,
        o2: dg?.o2 ?? 21, he: dg?.he ?? 0,
        setpoint: dg?.setpoint ?? 1.4,
        bmDepth, bmSp: dg?.setpoint ?? 1.3, dlUpper: false, bestMixNote: '',
        mod: 6, cylL: 7, cylBar: 200, bmPpO2: 1.4,
      })
    }
  }

  function applyModalBestMix() {
    const { bmDepth, bmSp, dlUpper, isBailout, bmPpO2 } = gasModal
    if (isBailout) {
      const amb = bmDepth / 10 + 1
      // O2: maximum fraction that keeps ppO₂ ≤ slider value at target depth
      const o2 = Math.floor(Math.min(1, bmPpO2 / amb) * 100)
      const fO2 = o2 / 100
      const densLim = dlUpper ? 6.3 : 5.2
      // He: solve density equation for fHe given fO2 (fN2 = 1 − fO2 − fHe)
      // ρ_surf·amb ≤ densLim  →  fHe = (1.25 + fO2·0.1786 − densLim/amb) / 1.0714
      const rawFHe = (1.25 + fO2 * 0.1786 - densLim / amb) / 1.0714
      const he = Math.max(0, Math.ceil(Math.max(0, rawFHe) * 20) * 5)
      // MOD = shallower of: ppO₂ MOD (using slider ppO₂) and density MOD
      const ppO2Mod = fO2 > 0 ? Math.round((bmPpO2 / fO2 - 1) * 10) : 150
      const mod = Math.min(ppO2Mod, densityLimitDepth(o2, he, densLim))
      const limitLabel = dlUpper ? '6.3 g/L (upper)' : '5.2 g/L (recommended)'
      setGasModal(prev => ({
        ...prev, o2, he, mod,
        bestMixNote: `${bmDepth} m · ppO₂ ${bmPpO2.toFixed(1)} · density ≤ ${limitLabel}`,
      }))
    } else {
      const densLim = dlUpper ? 6.3 : 5.2
      const mix = bestMix(bmDepth, bmSp, densLim)
      const limitLabel = dlUpper ? '6.3 g/L (upper)' : '5.2 g/L (recommended)'
      setGasModal(prev => ({
        ...prev, o2: mix.o2, he: mix.he,
        bestMixNote: `${bmDepth} m · SP ${bmSp} · O₂ ≤ SP/amb · density ≤ ${limitLabel}`,
      }))
    }
  }

  function saveGas() {
    const { o2, he, setpoint, mod, cylL, cylBar, isBailout, editId } = gasModal
    if (o2 + he > 100) return
    if (isBailout) {
      if (editId != null) {
        setBailoutLib(prev => prev.map(g =>
          g.id === editId ? { ...g, o2, he, mod_m: mod, cyl_l: cylL, cyl_bar: cylBar } : g
        ))
      } else {
        const id = bailoutNextId
        setBailoutLib(prev => [...prev, { id, o2, he, mod_m: mod, cyl_l: cylL, cyl_bar: cylBar, active: true }])
        setBailoutNextId(id + 1)
      }
    } else {
      if (editId != null) {
        setGasLib(prev => prev.map(g => g.id === editId ? { ...g, o2, he, setpoint } : g))
      } else {
        const id = gasNextId
        setGasLib(prev => [...prev, { id, o2, he, setpoint, active: false }])
        setGasNextId(id + 1)
      }
    }
    setGasModal(prev => ({ ...prev, open: false }))
  }

  // ── Saved plans ──────────────────────────────────────────────────────────────

  function openSavePlan() {
    if (!activeGas) { alert('Select a diluent gas first.'); return }
    const name = `${gasName(activeGas.o2, activeGas.he)} · ${depth}m / ${bt}min`
    setSavePlanModal({
      open: true, name,
      pending: {
        gas: { o2: activeGas.o2, he: activeGas.he, setpoint: activeGas.setpoint },
        depth_m: depth, bottom_time_min: bt,
        gf_low: settings.gfLow, gf_high: settings.gfHigh,
      },
    })
  }

  function confirmSavePlan() {
    if (!savePlanModal.pending) return
    const newPlan: SavedPlan = {
      ...savePlanModal.pending,
      id: planNextId,
      name: savePlanModal.name.trim() || 'Unnamed plan',
      created_at: new Date().toISOString(),
    }
    setSavedPlans(prev => [...prev, newPlan])
    setPlanNextId(planNextId + 1)
    setSavePlanModal({ open: false, name: '', pending: null })
    setSavedPlansOpen(true)
  }

  function loadPlan(id: number) {
    const plan = savedPlans.find(p => p.id === id)
    if (!plan) return
    setDepth(plan.depth_m)
    setBt(plan.bottom_time_min)
    setSettings(prev => ({ ...prev, gfLow: plan.gf_low, gfHigh: plan.gf_high }))
    const g = plan.gas
    const match = gasLib.find(x => x.o2 === g.o2 && x.he === g.he && x.setpoint === g.setpoint)
    if (match) {
      selectGas(match.id)
    } else {
      const id = gasNextId
      setGasLib(prev => [...prev.map(x => ({ ...x, active: false })), { id, ...g, active: true }])
      setGasNextId(id + 1)
    }
    setSavedPlansOpen(false)
  }

  function deletePlan(id: number) {
    const plan = savedPlans.find(p => p.id === id)
    if (!plan || !window.confirm(`Remove "${plan.name}"?`)) return
    setSavedPlans(prev => prev.filter(p => p.id !== id))
  }

  // ── Modal preview values ─────────────────────────────────────────────────────

  const { o2: mO2, he: mHe } = gasModal
  const mLimRec   = densityLimitDepth(mO2, mHe, 5.2)
  const mLimUpper = densityLimitDepth(mO2, mHe, 6.3)
  const mAutoMod  = mO2 > 0
    ? Math.max(3, Math.floor((gasModal.bmPpO2 / (mO2 / 100) - 1) * 10 / 3) * 3)
    : 150

  // ── Sorted libraries ─────────────────────────────────────────────────────────

  const sortedGasLib     = [...gasLib].sort((a, b) => b.o2 - a.o2 || a.he - b.he)
  const sortedBailoutLib = [...bailoutLib].sort((a, b) => b.o2 - a.o2 || a.he - b.he)

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <div>
      <Header
        title="Dive Planner"
        tagline="Bühlmann ZHL-16C decompression planner — CCR trimix"
        extraButtons={
          <>
            <button className="btn-cog" onClick={() => setSavedPlansOpen(true)} title="Saved plans">
              <i className="bi bi-bookmark" />
            </button>
            <button className="btn-cog" onClick={() => setSettingsOpen(true)} title="Personal settings">
              <i className="bi bi-gear-fill" />
            </button>
          </>
        }
      />

      <div className="container pb-5">
        {/* Top row: 3 equal columns */}
        <div className="row g-3 mb-4">
          {/* Diluent gas library */}
          <div className="col-md-4">
            <div className="card h-100">
              <div className="card-body">
                <div className="d-flex align-items-center justify-content-between mb-2">
                  <div className="card-section-title mb-0">Diluent Gases</div>
                  <button className="btn-add-gas" onClick={() => openGasModal(false)} title="Add gas">
                    <i className="bi bi-plus" />
                  </button>
                </div>
                <div className="gas-library">
                  {sortedGasLib.map(gas => (
                    <GasCard
                      key={gas.id} gas={gas} isBailout={false}
                      reserveBar={settings.reserveBar}
                      onSelect={() => selectGas(gas.id)}
                      onEdit={() => openGasModal(false, gas.id)}
                      onDelete={() => deleteGas(gas.id)}
                    />
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Bailout library */}
          <div className="col-md-4">
            <div className="card h-100">
              <div className="card-body">
                <div className="d-flex align-items-center justify-content-between mb-2">
                  <div className="card-section-title mb-0">Bailout Gases</div>
                  <button className="btn-add-gas" onClick={() => openGasModal(true)} title="Add bailout gas">
                    <i className="bi bi-plus" />
                  </button>
                </div>
                <div className="gas-library">
                  {sortedBailoutLib.map(gas => (
                    <GasCard
                      key={gas.id} gas={gas} isBailout
                      reserveBar={settings.reserveBar}
                      onSelect={() => toggleBailout(gas.id)}
                      onEdit={() => openGasModal(true, gas.id)}
                      onDelete={() => deleteBailout(gas.id)}
                    />
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Dive inputs + Calculate button */}
          <div className="col-md-4">
            <div className="card h-100">
              <div className="card-body">
                <div className="card-section-title">Dive Parameters</div>
                <div className="d-flex flex-column gap-2">
                  <div className="input-group input-group-sm">
                    <span className="input-group-text">Depth</span>
                    <input type="number" className="form-control" min={5} max={300} value={depth}
                      onChange={e => setDepth(parseInt(e.target.value) || 0)} />
                    <span className="input-group-text">m</span>
                  </div>
                  <div className="input-group input-group-sm">
                    <span className="input-group-text">Bottom time</span>
                    <input type="number" className="form-control" min={1} max={999} value={bt}
                      onChange={e => setBt(parseInt(e.target.value) || 0)} />
                    <span className="input-group-text">min</span>
                  </div>
                  {result && result.bottom_time_actual < bt && (
                    <div className="small text-warning-emphasis" style={{ fontSize: '0.78rem', marginTop: '-0.1rem' }}>
                      <i className="bi bi-scissors me-1" />Shortened to {result.bottom_time_actual} min — insufficient bailout gas
                    </div>
                  )}
                  <button className="btn btn-apply w-100 mt-1" onClick={calculate} disabled={!activeGas || loading}>
                    Calculate Decompression
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Results — full width below */}
        {!activeGas && (
          <div className="alert alert-info rounded-3">Select a diluent gas to plan a dive.</div>
        )}
        {loading && (
          <div className="loading-spinner text-center py-3">
            <div className="spinner-border" />
            <div className="text-muted mt-1">Planning decompression…</div>
          </div>
        )}
        {error && <div className="alert alert-danger rounded-3">{error}</div>}

        {result && activeGas && (
          <>
            <PlanSection
              title="Decompression Schedule"
              decoStops={result.stops}
              totalTimeMin={result.total_time_min}
              ttsMin={result.tts_min}
              cnsPct={result.cns_pct}
              otu={result.otu}
              profilePoints={result.profile_points}
              tissueSaturations={result.tissue_saturations}
              gasSwitches={[]}
              gasSupply={null}
              warnings={result.warnings}
              gfHigh={settings.gfHigh}
              diluent={activeGas}
              depthM={depth}
              btMin={btActual}
              descRate={settings.descRate}
              xAxisMax={sharedXMax}
            />

            {result.bailout && (
              <div className="mt-4">
                <PlanSection
                  title="Bailout Schedule"
                  decoStops={result.bailout.stops}
                  totalTimeMin={result.bailout.total_time_min}
                  ttsMin={result.bailout.tts_min}
                  cnsPct={result.bailout.cns_pct}
                  otu={result.bailout.otu}
                  profilePoints={bailoutProfilePoints}
                  tissueSaturations={result.bailout.tissue_saturations}
                  gasSwitches={result.bailout.gas_switches}
                  gasSupply={result.bailout.gas_supply}
                  warnings={[]}
                  gfHigh={settings.bailoutGfHigh}
                  diluent={activeGas}
                  depthM={depth}
                  btMin={btActual}
                  descRate={settings.descRate}
                  isBailout
                  bailoutInitialGas={bailoutInitialGas}
                  xAxisMax={sharedXMax}
                />
              </div>
            )}
          </>
        )}
      </div>

      <footer className="app-footer">
        <div className="container text-center">
          <strong>Not for operational use.</strong> This is an educational planning tool only.
          Decompression diving requires proper training, experience, and in-water verification.
        </div>
      </footer>

      {/* Settings offcanvas */}
      <Offcanvas show={settingsOpen} onHide={() => setSettingsOpen(false)} placement="end">
        <Offcanvas.Header closeButton>
          <Offcanvas.Title>Personal Settings</Offcanvas.Title>
        </Offcanvas.Header>
        <Offcanvas.Body>
          <p className="text-muted mb-3" style={{ fontSize: '0.82rem' }}>
            Settings are saved automatically.
          </p>
          <SettingsBody settings={settings} setSettings={setSettings} />
        </Offcanvas.Body>
      </Offcanvas>

      {/* Saved plans offcanvas */}
      <Offcanvas show={savedPlansOpen} onHide={() => setSavedPlansOpen(false)} placement="end">
        <Offcanvas.Header closeButton>
          <Offcanvas.Title>Saved Plans</Offcanvas.Title>
        </Offcanvas.Header>
        <Offcanvas.Body>
          <button className="btn btn-sm btn-apply w-100 mb-3" onClick={openSavePlan}>
            <i className="bi bi-bookmark-plus me-1" />Save current plan
          </button>
          {savedPlans.length === 0
            ? <p className="text-muted" style={{ fontSize: '0.82rem' }}>No saved plans yet.</p>
            : [...savedPlans].reverse().map(plan => (
              <div key={plan.id} className="plan-card">
                <div className="plan-card-name">{plan.name}</div>
                <div className="plan-card-meta">
                  {gasName(plan.gas.o2, plan.gas.he)} · SP {plan.gas.setpoint} · {plan.depth_m} m
                  · {plan.bottom_time_min} min · GF {plan.gf_low}/{plan.gf_high}
                </div>
                <div className="plan-card-actions">
                  <button className="btn btn-sm btn-apply flex-grow-1" onClick={() => loadPlan(plan.id)}>Load</button>
                  <button className="btn btn-sm btn-outline-secondary" onClick={() => deletePlan(plan.id)}>
                    <i className="bi bi-trash" />
                  </button>
                </div>
              </div>
            ))
          }
        </Offcanvas.Body>
      </Offcanvas>

      {/* Gas modal */}
      <Modal show={gasModal.open} onHide={() => setGasModal(prev => ({ ...prev, open: false }))} size="sm">
        <Modal.Header closeButton className="py-2">
          <Modal.Title style={{ fontSize: '0.9rem', fontWeight: 700 }}>
            {gasModal.editId != null ? 'Edit' : 'Add'} {gasModal.isBailout ? 'Bailout' : 'Diluent'} Gas
          </Modal.Title>
        </Modal.Header>
        <Modal.Body className="py-3">
          <div className="mb-2">
            <div className="input-group input-group-sm">
              <span className="input-group-text">O₂ %</span>
              <input type="number" className="form-control" min={0} max={100} value={gasModal.o2}
                onChange={e => setGasModal(prev => ({ ...prev, o2: parseInt(e.target.value) || 0 }))} />
            </div>
          </div>
          <div className="mb-2">
            <div className="input-group input-group-sm">
              <span className="input-group-text">He %</span>
              <input type="number" className="form-control" min={0} max={100} value={gasModal.he}
                onChange={e => setGasModal(prev => ({ ...prev, he: parseInt(e.target.value) || 0 }))} />
            </div>
          </div>

          <GasBar o2={mO2} he={mHe} />
          <div className="d-flex justify-content-between align-items-baseline mt-1 mb-3" style={{ fontSize: '0.75rem' }}>
            <span style={{ fontWeight: 800, color: 'var(--ocean)', fontSize: '1rem' }}>{gasName(mO2, mHe)}</span>
            <span className="text-muted">rec ~{mLimRec} m · upper ~{mLimUpper} m</span>
          </div>

          <div className="mb-2">
            <label className="field-label">Depth — <b>{gasModal.bmDepth}</b> m</label>
            <input type="range" className="form-range" min={5} max={150} step={5} value={gasModal.bmDepth}
              onChange={e => setGasModal(prev => ({ ...prev, bmDepth: parseInt(e.target.value) }))} />
          </div>

          {!gasModal.isBailout ? (
            <>
              <div className="mb-2">
                <label className="field-label">Setpoint — <b>{gasModal.bmSp.toFixed(1)}</b> bar</label>
                <input type="range" className="form-range" min={0.7} max={1.6} step={0.1} value={gasModal.bmSp}
                  onChange={e => setGasModal(prev => ({ ...prev, bmSp: parseFloat(e.target.value) }))} />
              </div>
              <div className="form-check form-switch mb-3">
                <input className="form-check-input" type="checkbox" id="dl_upper"
                  checked={gasModal.dlUpper} onChange={e => setGasModal(prev => ({ ...prev, dlUpper: e.target.checked }))} />
                <label className="form-check-label small text-muted" htmlFor="dl_upper">Upper density limit (6.3 g/L)</label>
              </div>
              <button className="btn btn-sm w-100 mb-1" style={{ background: '#eef2f8', color: 'var(--ocean)', fontSize: '0.75rem', fontWeight: 600, border: '1px solid var(--border)' }}
                onClick={applyModalBestMix}>
                <i className="bi bi-stars me-1" />Best Mix
              </button>
              {gasModal.bestMixNote && <div className="text-muted mt-1" style={{ fontSize: '0.65rem', textAlign: 'center' }}>{gasModal.bestMixNote}</div>}
            </>
          ) : (
            <>
              <div className="mb-2">
                <label className="field-label">ppO₂ — <b>{gasModal.bmPpO2.toFixed(1)}</b> bar</label>
                <input type="range" className="form-range" min={1.2} max={1.6} step={0.1} value={gasModal.bmPpO2}
                  onChange={e => setGasModal(prev => ({ ...prev, bmPpO2: parseFloat(e.target.value) }))} />
              </div>
              <div className="form-check form-switch mb-3">
                <input className="form-check-input" type="checkbox" id="dl_upper_bailout"
                  checked={gasModal.dlUpper} onChange={e => setGasModal(prev => ({ ...prev, dlUpper: e.target.checked }))} />
                <label className="form-check-label small text-muted" htmlFor="dl_upper_bailout">Upper density limit (6.3 g/L)</label>
              </div>
              <button className="btn btn-sm w-100 mb-1" style={{ background: '#eef2f8', color: 'var(--ocean)', fontSize: '0.75rem', fontWeight: 600, border: '1px solid var(--border)' }}
                onClick={applyModalBestMix}>
                <i className="bi bi-stars me-1" />Best Mix
              </button>
              {gasModal.bestMixNote && <div className="text-muted mb-2" style={{ fontSize: '0.65rem', textAlign: 'center' }}>{gasModal.bestMixNote}</div>}
              <hr className="my-2" />
              <div className="mb-2">
                <label className="field-label">
                  MOD <span className="text-muted" style={{ fontWeight: 400, fontSize: '0.65rem' }}>
                    (auto at {gasModal.bmPpO2.toFixed(1)} bar ppO₂: {mAutoMod} m)
                  </span>
                </label>
                <div className="input-group input-group-sm">
                  <input type="number" className="form-control" min={3} max={200} step={3} value={gasModal.mod}
                    onChange={e => setGasModal(prev => ({ ...prev, mod: parseInt(e.target.value) || 6 }))} />
                  <span className="input-group-text">m</span>
                </div>
              </div>
              <div className="d-flex gap-2">
                <div className="input-group input-group-sm flex-grow-1">
                  <span className="input-group-text">Cyl L</span>
                  <input type="number" className="form-control" min={1} value={gasModal.cylL}
                    onChange={e => setGasModal(prev => ({ ...prev, cylL: parseFloat(e.target.value) || 7 }))} />
                </div>
                <div className="input-group input-group-sm flex-grow-1">
                  <span className="input-group-text">Bar</span>
                  <input type="number" className="form-control" min={1} value={gasModal.cylBar}
                    onChange={e => setGasModal(prev => ({ ...prev, cylBar: parseFloat(e.target.value) || 200 }))} />
                </div>
              </div>
            </>
          )}
        </Modal.Body>
        <Modal.Footer className="py-2">
          <button className="btn btn-sm btn-apply px-3" onClick={saveGas}>Save</button>
        </Modal.Footer>
      </Modal>

      {/* Save plan modal */}
      <Modal show={savePlanModal.open} onHide={() => setSavePlanModal(prev => ({ ...prev, open: false }))} size="sm">
        <Modal.Header closeButton className="py-2">
          <Modal.Title style={{ fontSize: '0.9rem', fontWeight: 700 }}>Save Plan</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <div className="input-group input-group-sm">
            <span className="input-group-text">Name</span>
            <input type="text" className="form-control"
              value={savePlanModal.name}
              onChange={e => setSavePlanModal(prev => ({ ...prev, name: e.target.value }))}
              onKeyDown={e => { if (e.key === 'Enter') confirmSavePlan() }}
              autoFocus
            />
          </div>
        </Modal.Body>
        <Modal.Footer className="py-2">
          <button className="btn btn-sm btn-apply px-3" onClick={confirmSavePlan}>Save</button>
        </Modal.Footer>
      </Modal>
    </div>
  )
}

// ── Sub-components ─────────────────────────────────────────────────────────────

interface GasCardProps {
  gas: GasEntry | BailoutEntry
  isBailout: boolean
  reserveBar: number
  onSelect: () => void
  onEdit: () => void
  onDelete: () => void
}

function GasCard({ gas, isBailout, reserveBar, onSelect, onEdit, onDelete }: GasCardProps) {
  const { o2, he } = gas
  const limRec   = densityLimitDepth(o2, he, 5.2)
  const limUpper = densityLimitDepth(o2, he, 6.3)
  let infoLine: React.ReactNode
  if (isBailout) {
    const bg = gas as BailoutEntry
    const modLine = bg.mod_m <= limRec
      ? `MOD ${bg.mod_m} m`
      : `${limRec} m – ${limUpper} m`
    if (bg.cyl_l && bg.cyl_bar) {
      const usable = Math.round(bg.cyl_l * Math.max(0, bg.cyl_bar - reserveBar))
      infoLine = <>{modLine}<br />{bg.cyl_l} L / {bg.cyl_bar} bar · {usable} L</>
    } else {
      infoLine = modLine
    }
  } else {
    const dg = gas as GasEntry
    infoLine = `${limRec} m – ${limUpper} m · SP ${dg.setpoint}`
  }

  return (
    <div
      className={`gas-card${gas.active ? ' gas-card-active' : ''}`}
      onClick={onSelect}
    >
      <div className="gas-card-top">
        <span className="gas-card-name">{gasName(o2, he)}</span>
        <span className="gas-card-info" style={isBailout ? { whiteSpace: 'normal' } : {}}>
          {infoLine}
        </span>
        <span>
          <i
            className={`bi bi-${gas.active ? 'check-circle-fill' : 'circle'} btn-gas-action`}
            style={gas.active ? { color: 'var(--aqua)' } : {}}
          />
          <button
            className="btn-gas-action"
            onClick={e => { e.stopPropagation(); onEdit() }}
            title="Edit"
          >
            <i className="bi bi-pencil" />
          </button>
          <button
            className="btn-gas-action"
            onClick={e => { e.stopPropagation(); onDelete() }}
            title="Delete"
          >
            <i className="bi bi-trash" />
          </button>
        </span>
      </div>
      <GasBar o2={o2} he={he} style={{ marginTop: '0.1rem' }} />
    </div>
  )
}

interface SettingsBodyProps {
  settings: PlannerSettings
  setSettings: React.Dispatch<React.SetStateAction<PlannerSettings>>
}

function SettingsBody({ settings, setSettings }: SettingsBodyProps) {
  function set<K extends keyof PlannerSettings>(key: K, val: number) {
    setSettings(prev => ({ ...prev, [key]: val }))
  }
  function num(s: string, fallback: number) { return parseFloat(s) || fallback }

  return (
    <>
      <div className="card-section-title mb-2">Gradient Factors (CCR)</div>
      <div className="gf-row mb-2">
        <div className="input-group input-group-sm">
          <span className="input-group-text">GF Low</span>
          <input type="number" className="form-control" min={1} max={100} value={settings.gfLow}
            onChange={e => set('gfLow', num(e.target.value, 60))} />
          <span className="input-group-text">%</span>
        </div>
        <div className="input-group input-group-sm">
          <span className="input-group-text">GF High</span>
          <input type="number" className="form-control" min={1} max={100} value={settings.gfHigh}
            onChange={e => set('gfHigh', num(e.target.value, 80))} />
          <span className="input-group-text">%</span>
        </div>
      </div>
      <div className="d-flex align-items-center flex-wrap gap-1 mb-3">
        {[[30,70,'Shearwater · 30/70'],[60,80,'BSAC Trimix · 60/80'],[85,95,'BSAC Air/Nitrox · 85/95']].map(([l,h,label]) => (
          <button key={String(label)} className="btn btn-sm btn-outline-secondary"
            style={{ fontSize: '0.68rem', padding: '0.1rem 0.35rem' }}
            onClick={() => setSettings(prev => ({ ...prev, gfLow: Number(l), gfHigh: Number(h) }))}>
            {label}
          </button>
        ))}
      </div>

      <div className="card-section-title mb-2">Bailout Gradient Factors</div>
      <div className="gf-row mb-2">
        <div className="input-group input-group-sm">
          <span className="input-group-text">GF Low</span>
          <input type="number" className="form-control" min={1} max={100} value={settings.bailoutGfLow}
            onChange={e => set('bailoutGfLow', num(e.target.value, 50))} />
          <span className="input-group-text">%</span>
        </div>
        <div className="input-group input-group-sm">
          <span className="input-group-text">GF High</span>
          <input type="number" className="form-control" min={1} max={100} value={settings.bailoutGfHigh}
            onChange={e => set('bailoutGfHigh', num(e.target.value, 80))} />
          <span className="input-group-text">%</span>
        </div>
      </div>
      <div className="d-flex align-items-center flex-wrap gap-1 mb-3">
        {[[30,70,'Shearwater · 30/70'],[60,80,'BSAC Trimix · 60/80'],[85,95,'BSAC Air/Nitrox · 85/95']].map(([l,h,label]) => (
          <button key={String(label)} className="btn btn-sm btn-outline-secondary"
            style={{ fontSize: '0.68rem', padding: '0.1rem 0.35rem' }}
            onClick={() => setSettings(prev => ({ ...prev, bailoutGfLow: Number(l), bailoutGfHigh: Number(h) }))}>
            {label}
          </button>
        ))}
        <button className="btn btn-sm btn-outline-secondary"
          style={{ fontSize: '0.68rem', padding: '0.1rem 0.35rem' }}
          onClick={() => setSettings(prev => ({ ...prev, bailoutGfLow: prev.gfLow, bailoutGfHigh: prev.gfHigh }))}>
          Same as CCR
        </button>
      </div>

      <div className="card-section-title mb-2">Ascent / Descent Rates</div>
      <div className="mb-2">
        <div className="input-group input-group-sm">
          <span className="input-group-text">Descent</span>
          <input type="number" className="form-control" min={5} max={30} value={settings.descRate}
            onChange={e => set('descRate', num(e.target.value, 20))} />
          <span className="input-group-text">m/min</span>
        </div>
      </div>
      <div className="mb-2">
        <div className="input-group input-group-sm">
          <span className="input-group-text">Ascent (&gt;6 m)</span>
          <input type="number" className="form-control" min={1} max={20} value={settings.ascRateDeep}
            onChange={e => set('ascRateDeep', num(e.target.value, 9))} />
          <span className="input-group-text">m/min</span>
        </div>
      </div>
      <div className="mb-3">
        <div className="input-group input-group-sm">
          <span className="input-group-text">Ascent (≤6 m)</span>
          <input type="number" className="form-control" min={1} max={10} value={settings.ascRateShallow}
            onChange={e => set('ascRateShallow', num(e.target.value, 3))} />
          <span className="input-group-text">m/min</span>
        </div>
      </div>

      <div className="card-section-title mb-2">Last Stop Depth</div>
      <div className="mb-3">
        <div className="input-group input-group-sm">
          <span className="input-group-text">Last stop</span>
          <select className="form-select form-select-sm" value={settings.lastStopM}
            onChange={e => set('lastStopM', parseInt(e.target.value))}>
            {[3,4,5,6,9].map(v => <option key={v} value={v}>{v} m</option>)}
          </select>
        </div>
      </div>

      <div className="card-section-title mb-2">Oxygen Toxicity</div>
      <div className="mb-3">
        <div className="input-group input-group-sm">
          <span className="input-group-text">CNS warn</span>
          <input type="number" className="form-control" min={50} max={100} value={settings.cnsWarnPct}
            onChange={e => set('cnsWarnPct', num(e.target.value, 80))} />
          <span className="input-group-text">%</span>
        </div>
      </div>

      <div className="card-section-title mb-2">Breathing Rates (SAC/RMV)</div>
      <div className="mb-2">
        <div className="input-group input-group-sm">
          <span className="input-group-text">Bottom</span>
          <input type="number" className="form-control" min={2} max={200} value={settings.sacBottom}
            onChange={e => set('sacBottom', num(e.target.value, 25))} />
          <span className="input-group-text">L/min</span>
        </div>
      </div>
      <div className="mb-3">
        <div className="input-group input-group-sm">
          <span className="input-group-text">Deco</span>
          <input type="number" className="form-control" min={2} max={200} value={settings.sacDeco}
            onChange={e => set('sacDeco', num(e.target.value, 15))} />
          <span className="input-group-text">L/min</span>
        </div>
      </div>

      <div className="card-section-title mb-2">Tank Reserve</div>
      <div className="mb-3">
        <div className="input-group input-group-sm">
          <span className="input-group-text">Reserve</span>
          <input type="number" className="form-control" min={0} max={200} value={settings.reserveBar}
            onChange={e => set('reserveBar', num(e.target.value, 50))} />
          <span className="input-group-text">bar</span>
        </div>
      </div>

      <div className="mt-4 pt-3 border-top">
        <button className="btn btn-sm btn-outline-danger w-100"
          onClick={() => setSettings(DEFAULT_SETTINGS)}>
          Reset to defaults
        </button>
      </div>
    </>
  )
}
