import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import {
  Chart as ChartJS,
  CategoryScale, LinearScale, PointElement, LineElement,
  Title, Tooltip, Legend, Filler,
  type ChartData, type ChartOptions,
} from 'chart.js'
import { Line } from 'react-chartjs-2'
import Header from '../components/Header'
import DiveComputerDisplay from '../components/DiveComputerDisplay'
import { gasDensityAtDepth } from '../utils'
import type { ProfilePoint, SimulatorInput } from '../types'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, Filler)

// ── ZHL-16C coefficients: [a_N2, b_N2, a_He, b_He] per compartment ──────────
const ZHL16C_AB: [number, number, number, number][] = [
  [1.1696, 0.5578, 1.6189, 0.4770],
  [1.0000, 0.6514, 1.3830, 0.5747],
  [0.8618, 0.7222, 1.1919, 0.6527],
  [0.7562, 0.7825, 1.0458, 0.7223],
  [0.6200, 0.8126, 0.9220, 0.7582],
  [0.5043, 0.8434, 0.8205, 0.7957],
  [0.4410, 0.8693, 0.7305, 0.8279],
  [0.4000, 0.8910, 0.6502, 0.8553],
  [0.4187, 0.9092, 0.5950, 0.8757],
  [0.3798, 0.9222, 0.5545, 0.8903],
  [0.3497, 0.9319, 0.5333, 0.8997],
  [0.3223, 0.9403, 0.5189, 0.9073],
  [0.2971, 0.9477, 0.5181, 0.9122],
  [0.2737, 0.9544, 0.5176, 0.9171],
  [0.2523, 0.9602, 0.5172, 0.9217],
  [0.2327, 0.9653, 0.5119, 0.9267],
]
const SURFACE_BAR = 1.013

function computeGF99(inert: [number, number][], depthM: number): number {
  const pAmb = depthM / 10 + SURFACE_BAR
  let worst = -Infinity
  for (let i = 0; i < inert.length; i++) {
    const [pN2, pHe] = inert[i]
    const p = pN2 + pHe
    if (p <= 0) continue
    const [aN2, bN2, aHe, bHe] = ZHL16C_AB[i]
    const a = (aN2 * pN2 + aHe * pHe) / p
    const b = (bN2 * pN2 + bHe * pHe) / p
    const m = pAmb / b + a
    const denominator = m - pAmb
    if (Math.abs(denominator) < 1e-9) continue
    const gf = (p - pAmb) / denominator * 100
    if (gf > worst) worst = gf
  }
  return worst === -Infinity ? 0 : worst
}

// ── CNS / OTU rate functions (NOAA table, ported from DivePlanner/__init__.py) ─

const CNS_TABLE: [number, number][] = [
  [0.50, 0.0],
  [0.60, 100 / 720],
  [0.70, 100 / 570],
  [0.80, 100 / 450],
  [0.90, 100 / 360],
  [1.00, 100 / 300],
  [1.10, 100 / 270],
  [1.20, 100 / 240],
  [1.30, 100 / 210],
  [1.40, 100 / 180],
  [1.50, 100 / 150],
  [1.60, 100 / 120],
]

function cnsRate(ppO2: number): number {
  if (ppO2 <= 0.5) return 0
  if (ppO2 >= 1.6) return 100 / 120
  for (let i = 0; i < CNS_TABLE.length - 1; i++) {
    const [p0, r0] = CNS_TABLE[i]
    const [p1, r1] = CNS_TABLE[i + 1]
    if (p0 <= ppO2 && ppO2 <= p1) return r0 + (ppO2 - p0) / (p1 - p0) * (r1 - r0)
  }
  return 0
}

function otuRate(ppO2: number): number {
  if (ppO2 <= 0.5) return 0
  return Math.pow((ppO2 - 0.5) / 0.5, 5 / 6)
}

// ── Dive-physics helpers ───────────────────────────────────────────────────────

function getPpO2(depth: number, input: SimulatorInput): number {
  const ambient = depth / 10 + 1
  if (input.mode === 'ccr') return Math.min(input.setpoint ?? 1.3, ambient)
  const sorted = [...input.bailout_gases].sort((a, b) => a.mod_m - b.mod_m)
  const gas = sorted.find(g => depth <= g.mod_m) ?? sorted[sorted.length - 1]
  return gas ? (gas.o2 / 100) * ambient : (21 / 100) * ambient
}

function interpolateProfile(pts: ProfilePoint[], t: number) {
  const emptyInert = ZHL16C_AB.map(() => [0, 0] as [number, number])
  if (!pts.length) return { depth: 0, ceiling: 0, sats: new Array(16).fill(0) as number[], tts: 0, inert: emptyInert }
  if (t <= pts[0].t) return { depth: pts[0].d, ceiling: pts[0].c, sats: [...pts[0].sats], tts: pts[0].tts ?? 0, inert: pts[0].inert as [number, number][] ?? emptyInert }
  const last = pts[pts.length - 1]
  if (t >= last.t) return { depth: last.d, ceiling: last.c, sats: [...last.sats], tts: 0, inert: last.inert as [number, number][] ?? emptyInert }
  let lo = 0, hi = pts.length - 1
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1
    if (pts[mid].t <= t) lo = mid; else hi = mid
  }
  const p0 = pts[lo], p1 = pts[hi]
  const frac = (t - p0.t) / (p1.t - p0.t)
  const t0 = p0.tts ?? 0, t1 = p1.tts ?? 0
  const in0 = p0.inert as [number, number][] ?? emptyInert
  const in1 = p1.inert as [number, number][] ?? emptyInert
  return {
    depth:   p0.d + frac * (p1.d - p0.d),
    ceiling: Math.max(0, p0.c + frac * (p1.c - p0.c)),
    sats:    p0.sats.map((s, i) => s + frac * ((p1.sats[i] ?? s) - s)),
    tts:     Math.max(0, t0 + frac * (t1 - t0)),
    inert:   in0.map(([n0, h0], i) => [n0 + frac * ((in1[i]?.[0] ?? n0) - n0), h0 + frac * ((in1[i]?.[1] ?? h0) - h0)] as [number, number]),
  }
}

function getCnsOtuAt(
  t: number,
  pts: ProfilePoint[],
  cnsTable: number[],
  otuTable: number[],
): { cns: number; otu: number } {
  if (!pts.length || t <= 0) return { cns: 0, otu: 0 }
  if (t >= pts[pts.length - 1].t) return { cns: cnsTable[cnsTable.length - 1], otu: otuTable[otuTable.length - 1] }
  let lo = 0, hi = pts.length - 1
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1
    if (pts[mid].t <= t) lo = mid; else hi = mid
  }
  const frac = (t - pts[lo].t) / (pts[hi].t - pts[lo].t)
  return {
    cns: cnsTable[lo] + frac * (cnsTable[hi] - cnsTable[lo]),
    otu: otuTable[lo] + frac * (otuTable[hi] - otuTable[lo]),
  }
}

function ceilToTick(val: number): number {
  const step = val <= 30 ? 5 : val <= 90 ? 10 : val <= 180 ? 15 : 30
  return Math.ceil(val / step) * step
}

// ── Types ──────────────────────────────────────────────────────────────────────

interface SimulatorFrame {
  currentTime: number
  depth: number
  ceiling: number
  sats: number[]
  inert: [number, number][]
  ppO2: number
  cns: number
  otu: number
  tts: number
}

// ── Component ──────────────────────────────────────────────────────────────────

export default function DiveSimulator() {
  const location = useLocation()
  const navigate = useNavigate()
  const simInput = location.state as SimulatorInput | null
  const pts = simInput?.profile_points ?? []
  const totalTime = pts.length ? pts[pts.length - 1].t : 1
  const maxDepth = pts.length ? Math.max(...pts.map(p => p.d)) + 5 : 50

  const ndlExpiry = useMemo(() => {
    for (const p of pts) { if (p.c > 0) return p.t }
    return totalTime
  }, [pts, totalTime])

  const { cnsTable, otuTable } = useMemo(() => {
    if (!simInput) return { cnsTable: [0], otuTable: [0] }
    const cns = [0], otu = [0]
    for (let i = 0; i < pts.length - 1; i++) {
      const dt = pts[i + 1].t - pts[i].t
      const avgDepth = (pts[i].d + pts[i + 1].d) / 2
      const ppO2 = getPpO2(avgDepth, simInput)
      cns.push(cns[i] + cnsRate(ppO2) * dt)
      otu.push(otu[i] + otuRate(ppO2) * dt)
    }
    return { cnsTable: cns, otuTable: otu }
  }, [pts, simInput])

  const [frame, setFrame] = useState<SimulatorFrame>({
    currentTime: 0, depth: 0, ceiling: 0,
    sats: new Array(16).fill(0), inert: ZHL16C_AB.map(() => [0, 0]),
    ppO2: 0, cns: 0, otu: 0, tts: 0,
  })
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(60)

  const speedRef = useRef(speed)
  const chartRef = useRef<ChartJS<'line'>>(null)

  useEffect(() => { speedRef.current = speed }, [speed])

  // Redirect if navigated directly without data
  useEffect(() => {
    if (!simInput) navigate('/planner', { replace: true })
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Initialise display at t=0 once profile is available
  useEffect(() => {
    if (!simInput || !pts.length) return
    const state = interpolateProfile(pts, 0)
    setFrame({
      currentTime: 0, ...state,
      ppO2: getPpO2(state.depth, simInput),
      cns: 0, otu: 0,
    })
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Playback engine — advances currentTime 100ms per tick
  useEffect(() => {
    if (!playing || !simInput) return
    const id = setInterval(() => {
      setFrame(prev => {
        if (prev.currentTime >= totalTime) { setPlaying(false); return prev }
        const dt = speedRef.current / 60 * 0.1   // minutes of dive per 100ms tick
        const nextTime = Math.min(prev.currentTime + dt, totalTime)
        const state = interpolateProfile(pts, nextTime)
        const ppO2 = getPpO2(state.depth, simInput)
        const { cns, otu } = getCnsOtuAt(nextTime, pts, cnsTable, otuTable)
        if (nextTime >= totalTime) setPlaying(false)
        return { currentTime: nextTime, ...state, ppO2, cns, otu }
      })
    }, 100)
    return () => clearInterval(id)
  }, [playing, pts, simInput, totalTime, cnsTable, otuTable])

  // Update chart cursor imperatively (avoids re-rendering the whole chart on every tick)
  useEffect(() => {
    const chart = chartRef.current
    if (!chart?.data.datasets[2]) return
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(chart.data.datasets[2] as any).data = [
      { x: frame.currentTime, y: 0 },
      { x: frame.currentTime, y: maxDepth },
    ]
    chart.update('none')
  }, [frame.currentTime, maxDepth])

  function scrubTo(t: number) {
    if (!simInput) return
    setPlaying(false)
    const state = interpolateProfile(pts, t)
    const ppO2 = getPpO2(state.depth, simInput)
    const { cns, otu } = getCnsOtuAt(t, pts, cnsTable, otuTable)
    setFrame({ currentTime: t, ...state, ppO2, cns, otu })
  }

  // Static chart data — computed once from profile (cursor updated imperatively above)
  const chartData: ChartData<'line'> = useMemo(() => ({
    datasets: [
      {
        label: 'Depth (m)',
        data: pts.map(p => ({ x: p.t, y: p.d })),
        borderColor: '#1a4a72',
        backgroundColor: 'rgba(26,74,114,0.12)',
        fill: true, tension: 0, pointRadius: 0, borderWidth: 2, yAxisID: 'y',
      },
      {
        label: 'Ceiling (m)',
        data: pts.map(p => ({ x: p.t, y: p.c })),
        borderColor: 'rgba(220,100,0,0.8)',
        fill: false, tension: 0, pointRadius: 0, borderWidth: 1.5,
        borderDash: [4, 3], yAxisID: 'y',
      },
      {
        label: 'Now',
        data: [{ x: 0, y: 0 }, { x: 0, y: maxDepth }],
        borderColor: 'rgba(220,50,50,0.85)',
        fill: false, tension: 0, pointRadius: 0, borderWidth: 2, yAxisID: 'y',
      },
    ],
  }), [pts, maxDepth])

  const chartOptions: ChartOptions<'line'> = useMemo(() => ({
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    scales: {
      x: {
        type: 'linear', min: 0, max: ceilToTick(totalTime),
        title: { display: true, text: 'Time (min)', font: { size: 10 } },
        ticks: { font: { size: 10 } },
      },
      y: {
        reverse: true,
        title: { display: true, text: 'Depth (m)', font: { size: 10 } },
        ticks: { font: { size: 10 } },
      },
    },
    plugins: {
      legend: { display: true, labels: { font: { size: 10 }, boxWidth: 14, padding: 8 } },
      tooltip: { enabled: false },
    },
  }), [totalTime])

  if (!simInput) return null

  const inDeco = frame.ceiling > 0
  const ndl = Math.max(0, ndlExpiry - frame.currentTime)

  // TTS: simple ascent time when no deco obligation; remaining plan time when in deco
  const displayTts = (() => {
    if (!inDeco) {
      const d = frame.depth
      if (d <= 0) return 0
      const shallow = Math.min(d, 6)
      const deep = Math.max(0, d - 6)
      return deep / simInput.asc_rate_deep_mpm + shallow / simInput.asc_rate_shallow_mpm
    }
    return frame.tts
  })()

  // STOP depth: raw ceiling rounded up to next 3 m grid
  const stopDepth = inDeco ? Math.ceil(frame.ceiling / 3) * 3 : 0

  // STOP time: remaining time at the current/next stop
  const nextStop = simInput.stops.find(s => s.runtime_min > frame.currentTime) ?? null
  const stopTime = (() => {
    if (!inDeco || !nextStop) return 0
    const stopStart = nextStop.runtime_min - nextStop.time_min
    if (frame.currentTime >= stopStart) {
      return Math.ceil(Math.max(0, nextStop.runtime_min - frame.currentTime))
    }
    return Math.ceil(nextStop.time_min)
  })()

  const currentGas = (() => {
    if (simInput.mode === 'ccr') return { o2: simInput.diluent_o2 ?? 21, he: simInput.diluent_he ?? 0 }
    const sorted = [...simInput.bailout_gases].sort((a, b) => a.mod_m - b.mod_m)
    return sorted.find(g => frame.depth <= g.mod_m) ?? sorted[sorted.length - 1] ?? { o2: 21, he: 0 }
  })()

  const gasLabel = simInput.mode === 'ccr'
    ? `${simInput.diluent_o2 ?? 21}/${simInput.diluent_he ?? 0}`
    : `${currentGas.o2}/${currentGas.he}`

  // Gas density: CCR uses setpoint-adjusted loop gas fractions
  const gasDensity = (() => {
    if (simInput.mode === 'ccr' && simInput.setpoint != null) {
      const pAmb = frame.depth / 10 + 1
      const fO2loop = Math.min((simInput.setpoint ?? 1.3) / pAmb, (simInput.diluent_o2 ?? 21) / 100)
      const fHedil = (simInput.diluent_he ?? 0) / 100
      const fO2dil = (simInput.diluent_o2 ?? 21) / 100
      const fHeloop = fO2dil < 1 ? fHedil * (1 - fO2loop) / (1 - fO2dil) : 0
      return gasDensityAtDepth(fO2loop * 100, fHeloop * 100, frame.depth)
    }
    return gasDensityAtDepth(currentGas.o2, currentGas.he, frame.depth)
  })()

  const gf99 = computeGF99(frame.inert, frame.depth)

  function fmtTime(t: number): string {
    const s = Math.floor(t * 60)
    const h = Math.floor(s / 3600)
    const m = Math.floor((s % 3600) / 60)
    const ss = s % 60
    if (h > 0) return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(ss).padStart(2, '0')}`
    return `${String(m).padStart(2, '0')}:${String(ss).padStart(2, '0')}`
  }

  const depthLabel = `${simInput.depth_m} m · ${simInput.bottom_time_min} min · ${simInput.mode.toUpperCase()}`

  return (
    <div>
      <Header
        title="Dive Simulator"
        tagline={depthLabel}
        extraButtons={
          <button className="btn-cog" onClick={() => navigate('/planner')} title="Back to Planner">
            <i className="bi bi-arrow-left" />
          </button>
        }
      />

      <div className="container pb-5">
        <div className="row g-3 align-items-start mt-1">
          {/* Profile chart + controls */}
          <div className="col-lg-7">
            <div className="card">
              <div className="card-body">
                <div
                  style={{ height: 300, position: 'relative', cursor: 'crosshair' }}
                  onClick={e => {
                    const chart = chartRef.current
                    if (!chart) return
                    const rect = chart.canvas.getBoundingClientRect()
                    const t = chart.scales.x.getValueForPixel(e.clientX - rect.left) ?? 0
                    scrubTo(Math.max(0, Math.min(totalTime, t)))
                  }}
                  onTouchStart={e => {
                    const chart = chartRef.current
                    if (!chart) return
                    const touch = e.touches[0]
                    if (!touch) return
                    const rect = chart.canvas.getBoundingClientRect()
                    const t = chart.scales.x.getValueForPixel(touch.clientX - rect.left) ?? 0
                    scrubTo(Math.max(0, Math.min(totalTime, t)))
                  }}
                  onTouchMove={e => {
                    e.preventDefault()
                    const chart = chartRef.current
                    if (!chart) return
                    const touch = e.touches[0]
                    if (!touch) return
                    const rect = chart.canvas.getBoundingClientRect()
                    const t = chart.scales.x.getValueForPixel(touch.clientX - rect.left) ?? 0
                    scrubTo(Math.max(0, Math.min(totalTime, t)))
                  }}
                >
                  <Line ref={chartRef} data={chartData} options={chartOptions} />
                </div>

                {/* Controls inside chart card */}
                <div className="d-flex align-items-center flex-wrap gap-2 mt-3">
                  <button
                    className="btn btn-apply btn-sm"
                    style={{ minWidth: '5.5rem' }}
                    onClick={() => {
                      if (frame.currentTime >= totalTime) scrubTo(0)
                      setPlaying(p => !p)
                    }}
                  >
                    <i className={`bi bi-${playing ? 'pause-fill' : 'play-fill'} me-1`} />
                    {playing ? 'Pause' : 'Play'}
                  </button>

                  <button
                    className="btn btn-outline-secondary btn-sm"
                    onClick={() => scrubTo(0)}
                    title="Reset"
                  >
                    <i className="bi bi-skip-backward-fill" />
                  </button>

                  <div className="btn-group btn-group-sm">
                    {([60, 120, 300, 600] as const).map(s => (
                      <button
                        key={s}
                        className={`btn ${speed === s ? 'btn-apply' : 'btn-outline-secondary'}`}
                        onClick={() => setSpeed(s)}
                      >
                        {s}×
                      </button>
                    ))}
                  </div>

                  <span style={{ fontFamily: 'monospace', fontSize: '0.82rem', color: '#555', whiteSpace: 'nowrap', marginLeft: 'auto' }}>
                    {fmtTime(frame.currentTime)} / {fmtTime(totalTime)}
                  </span>
                </div>

                <input
                  type="range"
                  className="form-range mt-2"
                  min={0}
                  max={totalTime}
                  step={totalTime / 1000}
                  value={frame.currentTime}
                  onChange={e => scrubTo(parseFloat(e.target.value))}
                />
              </div>
            </div>
          </div>

          {/* Dive computer display */}
          <div className="col-lg-5">
            <DiveComputerDisplay
              depth={frame.depth}
              elapsed={frame.currentTime}
              ceiling={frame.ceiling}
              ppO2={frame.ppO2}
              cns={frame.cns}
              otu={frame.otu}
              tts={displayTts}
              ndl={ndl}
              sats={frame.sats}
              mode={simInput.mode}
              setpoint={simInput.setpoint}
              gasLabel={gasLabel}
              stopDepth={stopDepth}
              stopTime={stopTime}
              gf99={gf99}
              gasDensity={gasDensity}
            />
          </div>
        </div>
      </div>

      <footer className="app-footer">
        <div className="container text-center">
          <strong>Not for operational use.</strong> Educational teaching aid only.
        </div>
      </footer>
    </div>
  )
}
