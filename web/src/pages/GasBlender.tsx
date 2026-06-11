import { useState, useEffect, useCallback, useRef } from 'react'
import Accordion from 'react-bootstrap/Accordion'
import Header from '../components/Header'
import GasBar from '../components/GasBar'
import { trimixBlend } from '../api'
import type { TrimixBlendResponse } from '../types'

const BM_DEPTHS = [6,10,15,20,25,30,35,40,45,50,55,60,65,70,75,80,85,90,95,100,105,110,115,120]

interface GasInputs {
  startBar: number; startO2: number; startHe: number
  finishBar: number; finishO2: number; finishHe: number
  heliumBar: number; heliumO2: number; heliumHe: number
}

export default function GasBlender() {
  const [inputs, setInputs] = useState<GasInputs>({
    startBar: 50, startO2: 21, startHe: 0,
    finishBar: 232, finishO2: 21, finishHe: 35,
    heliumBar: 250, heliumO2: 0, heliumHe: 100,
  })
  const [bmDepthIdx, setBmDepthIdx] = useState(5)
  const [bmPpO2, setBmPpO2] = useState(1.4)
  const [bmDensityUpper, setBmDensityUpper] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<TrimixBlendResponse | null>(null)
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null)

  const calculate = useCallback(async () => {
    setError('')
    setLoading(true)
    try {
      const data = await trimixBlend({
        start_bar: inputs.startBar, start_o2: inputs.startO2, start_he: inputs.startHe,
        finish_bar: inputs.finishBar, finish_o2: inputs.finishO2, finish_he: inputs.finishHe,
        helium_bar: inputs.heliumBar, helium_o2: inputs.heliumO2, helium_he: inputs.heliumHe,
      })
      setResult(data)
    } catch (e) {
      setError((e as Error).message)
      setResult(null)
    } finally {
      setLoading(false)
    }
  }, [inputs])

  useEffect(() => {
    if (debounce.current) clearTimeout(debounce.current)
    debounce.current = setTimeout(calculate, 50)
    return () => { if (debounce.current) clearTimeout(debounce.current) }
  }, [calculate])

  function setField(field: keyof GasInputs, val: string) {
    setInputs(prev => ({ ...prev, [field]: parseInt(val, 10) || 0 }))
  }

  const bmDepth = BM_DEPTHS[bmDepthIdx]
  const bmPAbs  = bmDepth / 10 + 1
  const bmFO2   = Math.min(bmPpO2 / bmPAbs, 1.0)
  const densLim = bmDensityUpper ? 6.3 : 5.2
  const targetMM = densLim * 22.4 / bmPAbs
  let bmFHe = (28 + 4 * bmFO2 - targetMM) / 24
  bmFHe = Math.max(0, Math.min(bmFHe, 1 - bmFO2))
  const bmO2 = Math.round(bmFO2 * 100)
  const bmHe = Math.round(bmFHe * 100)
  const bmN2 = 100 - bmO2 - bmHe
  const bmMm = (bmO2 * 32 + bmN2 * 28 + bmHe * 4) / 100
  const bmDensity = Math.round(bmMm / 22.4 * bmPAbs * 100) / 100
  const bmEnd = Math.round(((bmPAbs * (1 - bmHe / 100)) - 1) * 10 * 10) / 10
  const bmLabel = bmHe > 0 ? `${bmO2}/${bmHe}` : `${bmO2}%`

  function applyBestMix() {
    setInputs(prev => ({ ...prev, finishBar: 232, finishO2: bmO2, finishHe: bmHe }))
  }
  function applyPreset(o2: number, he: number) {
    setInputs(prev => ({ ...prev, finishBar: 232, finishO2: o2, finishHe: he }))
  }

  function GasCard({
    label, barField, o2Field, heField, bar, o2, he
  }: {
    label: string; barField: keyof GasInputs; o2Field: keyof GasInputs; heField: keyof GasInputs
    bar: number; o2: number; he: number
  }) {
    return (
      <div className="card">
        <div className="card-body">
          <div className="card-section-title">{label}</div>
          <div className="d-flex flex-column gap-2">
            <div className="input-group input-group-sm">
              <span className="input-group-text">Bar</span>
              <input type="number" className="form-control" value={bar}
                onChange={e => setField(barField, e.target.value)} />
            </div>
            <div className="input-group input-group-sm">
              <span className="input-group-text">O₂ %</span>
              <input type="number" className="form-control" min={0} max={100} value={o2}
                onChange={e => setField(o2Field, e.target.value)} />
            </div>
            <div className="input-group input-group-sm">
              <span className="input-group-text">He %</span>
              <input type="number" className="form-control" min={0} max={100} value={he}
                onChange={e => setField(heField, e.target.value)} />
            </div>
          </div>
          <GasBar o2={o2} he={he} showLegend />
        </div>
      </div>
    )
  }

  return (
    <div>
      <Header
        title="Gas Blender"
        tagline="Trimix fill-sequence calculator for technical diving"
      />

      <div className="container pb-5">
        <div className="row g-3 mb-3">
          <div className="col-4">
            <GasCard label="Start Gas" barField="startBar" o2Field="startO2" heField="startHe"
              bar={inputs.startBar} o2={inputs.startO2} he={inputs.startHe} />
          </div>
          <div className="col-4">
            <GasCard label="Target Gas" barField="finishBar" o2Field="finishO2" heField="finishHe"
              bar={inputs.finishBar} o2={inputs.finishO2} he={inputs.finishHe} />
          </div>
          <div className="col-4">
            <GasCard label="Helium Bank" barField="heliumBar" o2Field="heliumO2" heField="heliumHe"
              bar={inputs.heliumBar} o2={inputs.heliumO2} he={inputs.heliumHe} />
          </div>
        </div>

        <Accordion className="target-accordion mb-3" alwaysOpen={false}>
          <Accordion.Item eventKey="presets">
            <Accordion.Header>Quick Presets</Accordion.Header>
            <Accordion.Body>
              <div className="preset-grid">
                {[
                  [21,0],[21,35],[18,45],[15,55],[12,60],[10,70],[21,30],[18,35]
                ].map(([o2,he]) => (
                  <button key={`${o2}/${he}`} className="preset-btn" onClick={() => applyPreset(o2, he)}>
                    {he > 0 ? `${o2}/${he}` : `${o2}%`}
                  </button>
                ))}
              </div>
            </Accordion.Body>
          </Accordion.Item>
          <Accordion.Item eventKey="bestmix">
            <Accordion.Header>Best Mix Calculator</Accordion.Header>
            <Accordion.Body>
              <div className="best-mix-panel">
                <div className="row g-2 align-items-center mb-2">
                  <div className="col">
                    <label className="field-label">Depth — <b>{bmDepth}</b> m</label>
                    <input type="range" className="form-range" min={0} max={BM_DEPTHS.length - 1}
                      value={bmDepthIdx} onChange={e => setBmDepthIdx(parseInt(e.target.value))} />
                  </div>
                  <div className="col">
                    <label className="field-label">ppO₂ — <b>{bmPpO2.toFixed(1)}</b> bar</label>
                    <input type="range" className="form-range" min={0.7} max={1.6} step={0.1}
                      value={bmPpO2} onChange={e => setBmPpO2(parseFloat(e.target.value))} />
                  </div>
                </div>
                <div className="form-check form-switch mb-3">
                  <input className="form-check-input" type="checkbox" id="bm_density_upper"
                    checked={bmDensityUpper} onChange={e => setBmDensityUpper(e.target.checked)} />
                  <label className="form-check-label small text-muted" htmlFor="bm_density_upper">
                    Upper density limit (6.3 g/L)
                  </label>
                </div>
                <div className="d-flex justify-content-between align-items-center">
                  <div>
                    <div className="bm-mix">{bmLabel}</div>
                    <div className="bm-stats text-muted">
                      Density {bmDensity} g/L &middot; END {bmEnd} m
                    </div>
                  </div>
                  <button className="btn btn-apply btn-sm px-3" onClick={applyBestMix}>
                    Apply
                  </button>
                </div>
              </div>
            </Accordion.Body>
          </Accordion.Item>
        </Accordion>

        {loading && (
          <div className="loading-spinner text-center py-3">
            <div className="spinner-border" />
            <div className="text-muted mt-1">Calculating…</div>
          </div>
        )}
        {error && <div className="alert alert-danger rounded-3">{error}</div>}
        {result && <Results data={result} />}
      </div>

      <footer className="app-footer">
        <div className="container text-center">
          <strong>Not for operational use.</strong> This tool is for educational and planning
          purposes only. Always verify gas mixes with a calibrated analyser before diving.
        </div>
      </footer>
    </div>
  )
}

function Results({ data }: { data: TrimixBlendResponse }) {
  return (
    <>
      <div className="mb-1"><span className="result-heading">Fill Sequence</span></div>
      <div className="d-flex flex-column gap-2 mb-4">
        {data.steps.map((step, i) => {
          const diff = Math.round((step.result_gas.bar - step.start_gas.bar) * 100) / 100
          const sign = diff >= 0 ? '+' : ''
          return (
            <div key={i} className="step-card">
              <div className="step-num">{i + 1}</div>
              <div className="flex-grow-1">
                <div className="step-name">Add {step.name}</div>
                <div className="step-pressure">
                  {step.start_gas.bar} bar
                  <span className="step-arrow">→</span>
                  {step.result_gas.bar} bar
                </div>
              </div>
              <div>
                <div className={`step-finish-delta ${diff >= 0 ? 'delta-pos' : 'delta-neg'}`}>
                  ({sign}{diff})
                </div>
                <div className="step-result-mix text-muted">
                  mix: {step.result_gas.o2}/{step.result_gas.he}
                </div>
              </div>
            </div>
          )
        })}
      </div>

      <div className="mb-1"><span className="result-heading">Gas Analysis</span></div>
      <div className="row g-3 mb-4">
        {[
          {
            title: 'Max Operating Depths',
            rows: [
              ['ppO₂ 1.2 (CCR)', data.analysis.mod_1_2],
              ['ppO₂ 1.4',       data.analysis.mod_1_4],
              ['ppO₂ 1.6',       data.analysis.mod_1_6],
            ],
          },
          {
            title: 'Gas Density Limits',
            rows: [
              ['Recommended (5.2 g/L)', data.analysis.density_max_depth],
              ['Upper limit (6.3 g/L)', data.analysis.density_limit_depth],
            ],
          },
          {
            title: 'Narcotic Depth (END)',
            rows: [
              ['Recommended (END 30 m)', data.analysis.end_30_depth],
              ['Upper limit (END 40 m)', data.analysis.end_40_depth],
            ],
          },
        ].map(card => (
          <div key={card.title} className="col-md-4">
            <div className="card h-100">
              <div className="card-body">
                <div className="card-section-title">{card.title}</div>
                {card.rows.map(([label, depth]) => (
                  <div key={label} className="analysis-row">
                    <span className="analysis-label">{label}</span>
                    <span className="analysis-depth">{depth} m</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        ))}
      </div>
    </>
  )
}
