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
import type { ProfilePoint, SimulatorInput } from '../types'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, Filler)

function interpolateProfile(pts: ProfilePoint[], t: number) {
  const empty = { depth: 0, ceiling: 0, sats: new Array(16).fill(0) as number[], tts: 0, ppO2: 0, cns: 0, otu: 0, gf99: 0, densityGl: 0 }
  if (!pts.length) return empty
  const first = pts[0]
  if (t <= first.t) return { depth: first.d, ceiling: first.c, sats: [...first.sats], tts: first.tts ?? 0, ppO2: first.ppO2 ?? 0, cns: first.cns ?? 0, otu: first.otu ?? 0, gf99: first.gf99 ?? 0, densityGl: first.density_gl ?? 0 }
  const last = pts[pts.length - 1]
  if (t >= last.t) return { depth: last.d, ceiling: last.c, sats: [...last.sats], tts: 0, ppO2: last.ppO2 ?? 0, cns: last.cns ?? 0, otu: last.otu ?? 0, gf99: last.gf99 ?? 0, densityGl: last.density_gl ?? 0 }
  let lo = 0, hi = pts.length - 1
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1
    if (pts[mid].t <= t) lo = mid; else hi = mid
  }
  const p0 = pts[lo], p1 = pts[hi]
  const frac = (t - p0.t) / (p1.t - p0.t)
  const lerp = (a: number, b: number) => a + frac * (b - a)
  return {
    depth:     lerp(p0.d, p1.d),
    ceiling:   Math.max(0, lerp(p0.c, p1.c)),
    sats:      p0.sats.map((s, i) => lerp(s, p1.sats[i] ?? s)),
    tts:       Math.max(0, lerp(p0.tts ?? 0, p1.tts ?? 0)),
    ppO2:      lerp(p0.ppO2 ?? 0, p1.ppO2 ?? 0),
    cns:       lerp(p0.cns ?? 0, p1.cns ?? 0),
    otu:       lerp(p0.otu ?? 0, p1.otu ?? 0),
    gf99:      lerp(p0.gf99 ?? 0, p1.gf99 ?? 0),
    densityGl: lerp(p0.density_gl ?? 0, p1.density_gl ?? 0),
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
  ppO2: number
  cns: number
  otu: number
  gf99: number
  densityGl: number
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
    let lastZeroT = pts[0]?.t ?? 0
    for (const p of pts) {
      if (p.c > 0) return lastZeroT
      lastZeroT = p.t
    }
    return totalTime
  }, [pts, totalTime])

  const [frame, setFrame] = useState<SimulatorFrame>({
    currentTime: 0, depth: 0, ceiling: 0,
    sats: new Array(16).fill(0),
    ppO2: 0, cns: 0, otu: 0, gf99: 0, densityGl: 0, tts: 0,
  })
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(60)

  const speedRef = useRef(speed)
  const chartRef = useRef<ChartJS<'line'>>(null)
  const isDragging = useRef(false)

  useEffect(() => { speedRef.current = speed }, [speed])

  // Redirect if navigated directly without data
  useEffect(() => {
    if (!simInput) navigate('/planner', { replace: true })
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Initialise display at t=0 once profile is available
  useEffect(() => {
    if (!simInput || !pts.length) return
    setFrame({ currentTime: 0, ...interpolateProfile(pts, 0) })
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Playback engine — advances currentTime 100ms per tick
  useEffect(() => {
    if (!playing || !simInput) return
    const id = setInterval(() => {
      setFrame(prev => {
        if (prev.currentTime >= totalTime) { setPlaying(false); return prev }
        const dt = speedRef.current / 60 * 0.1   // minutes of dive per 100ms tick
        const nextTime = Math.min(prev.currentTime + dt, totalTime)
        if (nextTime >= totalTime) setPlaying(false)
        return { currentTime: nextTime, ...interpolateProfile(pts, nextTime) }
      })
    }, 100)
    return () => clearInterval(id)
  }, [playing, pts, simInput, totalTime])

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
    setFrame({ currentTime: t, ...interpolateProfile(pts, t) })
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

  const gasLabel = (() => {
    if (simInput.mode === 'ccr') return `${simInput.diluent_o2 ?? 21}/${simInput.diluent_he ?? 0}`
    const sorted = [...simInput.bailout_gases].sort((a, b) => a.mod_m - b.mod_m)
    const gas = sorted.find(g => frame.depth <= g.mod_m) ?? sorted[sorted.length - 1]
    return gas ? `${gas.o2}/${gas.he}` : '?'
  })()

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
                  onMouseDown={e => {
                    isDragging.current = true
                    const chart = chartRef.current
                    if (!chart) return
                    const t = chart.scales.x.getValueForPixel(e.clientX - chart.canvas.getBoundingClientRect().left) ?? 0
                    scrubTo(Math.max(0, Math.min(totalTime, t)))
                  }}
                  onMouseMove={e => {
                    if (!isDragging.current) return
                    const chart = chartRef.current
                    if (!chart) return
                    const t = chart.scales.x.getValueForPixel(e.clientX - chart.canvas.getBoundingClientRect().left) ?? 0
                    scrubTo(Math.max(0, Math.min(totalTime, t)))
                  }}
                  onMouseUp={() => { isDragging.current = false }}
                  onMouseLeave={() => { isDragging.current = false }}
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
                    onClick={() => { setPlaying(false); scrubTo(0) }}
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
              gf99={frame.gf99}
              gasDensity={frame.densityGl}
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
