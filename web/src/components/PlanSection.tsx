import { useRef, useState, useCallback } from 'react'
import { Modal } from 'react-bootstrap'
import {
  Chart as ChartJS,
  CategoryScale, LinearScale, PointElement, LineElement, BarElement,
  Title, Tooltip, Legend, Filler,
  type ChartData, type ChartOptions,
} from 'chart.js'
import zoom from 'chartjs-plugin-zoom'
import { Line, Bar } from 'react-chartjs-2'
import type { DecoStop, ProfilePoint, GasSwitch, GasSupplyEntry, Warning } from '../types'
import { surfaceDensity, gasName } from '../utils'

const N2_HALF_TIMES = [5, 8, 12.5, 18.5, 27, 38.3, 54.3, 77, 109, 146, 187, 239, 305, 390, 498, 635]
const ZHL16C_AB: [number, number][] = [
  [1.1696, 0.5578], [1.0000, 0.6514], [0.8618, 0.7222], [0.7562, 0.7825],
  [0.6200, 0.8126], [0.5043, 0.8434], [0.4410, 0.8693], [0.4000, 0.8910],
  [0.4187, 0.9092], [0.3798, 0.9222], [0.3497, 0.9319], [0.3223, 0.9403],
  [0.2971, 0.9477], [0.2737, 0.9544], [0.2523, 0.9602], [0.2327, 0.9653],
]
const SURFACE_BAR = 1.013

ChartJS.register(
  CategoryScale, LinearScale, PointElement, LineElement, BarElement,
  Title, Tooltip, Legend, Filler, zoom,
)

function ceilToTick(val: number): number {
  const step = val <= 30 ? 5 : val <= 90 ? 10 : val <= 180 ? 15 : 30
  return Math.ceil(val / step) * step
}

interface PlanSectionProps {
  title: string
  decoStops: DecoStop[]
  totalTimeMin: number
  ttsMin: number
  cnsPct: number
  otu: number
  profilePoints: ProfilePoint[]
  tissueSaturations: number[]
  gasSwitches: GasSwitch[]
  gasSupply: GasSupplyEntry[] | null
  warnings: Warning[]
  gfHigh: number
  diluent?: { o2: number; he: number; setpoint: number }
  depthM?: number
  btMin?: number
  descRate?: number
  isBailout?: boolean
  bailoutInitialGas?: { o2: number; he: number } | null
  xAxisMax?: number
}

export default function PlanSection({
  title, decoStops, totalTimeMin, ttsMin, cnsPct, otu,
  profilePoints, tissueSaturations, gasSwitches,
  gasSupply, warnings, gfHigh, diluent, depthM, btMin, descRate,
  isBailout, bailoutInitialGas, xAxisMax,
}: PlanSectionProps) {
  const [hoveredSats, setHoveredSats] = useState<number[] | null>(null)
  const profileRef = useRef<ChartJS<'line'>>(null)
  const chartWrapRef = useRef<HTMLDivElement>(null)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [mvalueOpen, setMvalueOpen] = useState(false)
  const [activeView, setActiveView] = useState<'time' | 'mvalue'>('time')
  const [modalFullscreen, setModalFullscreen] = useState(false)

  const displaySats = (hoveredSats ?? tissueSaturations).map(s => Math.round(s * 100))
  const gfHighPct = gfHigh
  const controlIdx = displaySats.indexOf(Math.max(...displaySats))
  const controlHt  = N2_HALF_TIMES[controlIdx]

  const handleProfileHover = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const chart = profileRef.current
    if (!chart || !profilePoints.length) return
    const rect = e.currentTarget.getBoundingClientRect()
    const x = e.clientX - rect.left
    const xVal = chart.scales.x.getValueForPixel(x) ?? 0
    const nearest = profilePoints.reduce((prev, curr) =>
      Math.abs(curr.t - xVal) < Math.abs(prev.t - xVal) ? curr : prev
    )
    if (nearest?.sats) setHoveredSats(nearest.sats)
  }, [profilePoints])

  const resetHover = useCallback(() => setHoveredSats(null), [])

  const toggleFullscreen = () => {
    if (!chartWrapRef.current) return
    if (!document.fullscreenElement) {
      chartWrapRef.current.requestFullscreen()
      setIsFullscreen(true)
    } else {
      document.exitFullscreen()
      setIsFullscreen(false)
    }
  }

  const autoXMax = profilePoints.length ? profilePoints[profilePoints.length - 1].t : totalTimeMin
  const chartXMax = ceilToTick(xAxisMax ?? autoXMax)

  const profileData: ChartData<'line'> = {
    datasets: [
      {
        label: 'Depth (m)',
        data: profilePoints.map(p => ({ x: p.t, y: p.d })),
        borderColor: '#1a4a72',
        backgroundColor: 'rgba(26,74,114,0.12)',
        fill: true,
        tension: 0,
        pointRadius: 0,
        borderWidth: 2,
        yAxisID: 'y',
      },
      {
        label: 'Ceiling (m)',
        data: profilePoints.map(p => ({ x: p.t, y: p.c })),
        borderColor: 'rgba(220,100,0,0.8)',
        backgroundColor: 'transparent',
        fill: false,
        tension: 0,
        pointRadius: 0,
        borderWidth: 1.5,
        borderDash: [4, 3],
        yAxisID: 'y',
      },
    ],
  }

  const profileOptions: ChartOptions<'line'> = {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      x: {
        type: 'linear',
        title: { display: true, text: 'Time (min)', font: { size: 10 } },
        min: 0, max: chartXMax,
        ticks: { font: { size: 10 } },
      },
      y: {
        reverse: true,
        title: { display: true, text: 'Depth (m)', font: { size: 10 } },
        ticks: { font: { size: 10 } },
      },
    },
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: { display: true, labels: { font: { size: 10 }, boxWidth: 14, padding: 8 } },
      title: { display: false },
      tooltip: {
        callbacks: {
          title: (items) => `${Math.round(items[0].parsed.x ?? 0)} min`,
          label: (item) => `${item.dataset.label}: ${(item.parsed.y ?? 0).toFixed(1)} m`,
          afterBody: (items) => {
            if (!isBailout) return []
            const depth = items[0]?.parsed.y ?? 0
            const gas = resolveGasAtStop(depth, gasSwitches, bailoutInitialGas ?? diluent)
            return [`Gas: ${gas.name}`]
          },
        },
      },
    },
    animation: false,
  }

  const tissueTitle = hoveredSats
    ? `Tissue loading at hover — C${controlIdx + 1} (${controlHt} min) controlling`
    : `Tissue loading — surface · C${controlIdx + 1} (${controlHt} min) controlling`

  const tissueData: ChartData<'bar'> = {
    labels: Array.from({ length: 16 }, (_, i) => `C${i + 1}`),
    datasets: [{
      label: 'Saturation %',
      data: displaySats,
      backgroundColor: displaySats.map(s =>
        s > 100       ? 'rgba(220,53,69,0.75)'  :
        s > gfHighPct ? 'rgba(255,140,0,0.75)'  :
                        'rgba(32,150,130,0.75)'
      ),
      borderWidth: 0,
    }],
  }

  const tissueOptions: ChartOptions<'bar'> = {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      x: { ticks: {
        font:  (ctx) => ({ size: 9, weight: ctx.index === controlIdx ? 700 : 400 }),
        color: (ctx) => ctx.index === controlIdx ? '#0077b6' : '#666',
      }},
      y: {
        min: 0, max: 110,
        ticks: { font: { size: 9 } },
      },
    },
    plugins: {
      legend: { display: false },
      title: {
        display: true,
        text: tissueTitle,
        font: { size: 10 },
        color: '#555',
        padding: { bottom: 2 },
      },
      tooltip: { enabled: false },
    },
    animation: false,
  }

  const gas       = diluent
  const depth     = depthM ?? 0
  const bt        = btMin  ?? 0
  const dRate     = descRate ?? 20
  const descTime  = Math.round(depth / dRate)
  const flatBt    = Math.round(bt - descTime)
  const sp        = gas?.setpoint ?? 1.3
  const gO2       = gas?.o2 ?? 21
  const gHe       = gas?.he ?? 0

  // For bailout stops: runtime reported by API is from OC bailout point, offset by bt for absolute runtime
  const rtOffset = isBailout ? bt : 0

  const cnsColor = cnsPct > 80 ? '#dc3545' : cnsPct > 40 ? '#e07000' : 'var(--ocean)'
  const otuColor = otu > 250    ? '#dc3545' : otu > 150   ? '#e07000' : 'var(--navy)'

  return (
    <div>
      {warnings.map((w, i) => (
        <div key={i} className={`alert alert-${w.level === 'warning' ? 'warning' : 'danger'} rounded-3 density-warning mb-3`}>
          {w.message}
        </div>
      ))}

      <div className="row g-3 align-items-start">
        {/* Left col: heading + schedule table + metrics */}
        <div className="col-12 col-lg-5">
          <div className="mb-1"><span className="result-heading">{title}</span></div>

          <div className="card mb-0">
            <div className="card-body p-0">
              <div className="table-responsive">
                <table className="table table-sm mb-0 deco-table">
                  <thead>
                    <tr>
                      <th className="ps-2" style={{ width: '2rem' }} />
                      <th>Depth</th><th>T</th><th>RT</th>
                      <th>ppO₂</th><th>g/L</th><th>Gas</th>
                    </tr>
                  </thead>
                  <tbody>
                    {/* CCR descent — shown for both CCR plan and bailout */}
                    <tr style={isBailout ? { background: 'rgba(0,119,182,0.04)' } : {}}>
                      <td className="ps-2"><i className="bi bi-arrow-down-circle" style={{ color: '#0077b6' }} /></td>
                      <td>0→{depth}m</td>
                      <td>{descTime}</td>
                      <td>{descTime}</td>
                      <td>{sp.toFixed(2)}</td>
                      <td>{(surfaceDensity(gO2, gHe) * (depth / 10 + 1)).toFixed(2)}</td>
                      <td style={{ fontSize: '0.78rem' }}>{gasName(gO2, gHe)}</td>
                    </tr>
                    {/* CCR bottom */}
                    <tr style={isBailout ? { background: 'rgba(0,119,182,0.04)' } : {}}>
                      <td className="ps-2"><i className="bi bi-circle-fill" style={{ color: '#03045e', fontSize: '0.55em', verticalAlign: 'middle' }} /></td>
                      <td>{depth} m</td>
                      <td>{flatBt}</td>
                      <td>{Math.round(bt)}</td>
                      <td>{sp.toFixed(2)}</td>
                      <td>{(surfaceDensity(gO2, gHe) * (depth / 10 + 1)).toFixed(2)}</td>
                      <td style={{ fontSize: '0.78rem' }}>{gasName(gO2, gHe)}</td>
                    </tr>
                    {/* OC bailout switch row — thick top border marks the CCR→OC transition */}
                    {isBailout && (() => {
                      const bigO2   = bailoutInitialGas?.o2 ?? gO2
                      const bigHe   = bailoutInitialGas?.he ?? gHe
                      const bigPpO2 = ((bigO2 / 100) * (depth / 10 + 1)).toFixed(2)
                      const bigDens = (surfaceDensity(bigO2, bigHe) * (depth / 10 + 1)).toFixed(2)
                      const bigDensNum = parseFloat(bigDens)
                      const bigDensColor = bigDensNum > 6.3 ? '#dc3545' : bigDensNum > 5.2 ? '#e07000' : ''
                      return (
                        <tr style={{ borderTop: '2px solid #495057' }}>
                          <td className="ps-2"><i className="bi bi-lightning-charge-fill" style={{ color: '#dc3545' }} /></td>
                          <td>{depth} m</td>
                          <td>—</td>
                          <td>{Math.round(bt)}</td>
                          <td>{bigPpO2}</td>
                          <td style={bigDensColor ? { color: bigDensColor } : {}}>{bigDens}</td>
                          <td style={{ fontSize: '0.78rem' }}>{gasName(bigO2, bigHe)}</td>
                        </tr>
                      )
                    })()}
                    {/* No-stop ascent gas switches (between OC switch and first deco stop) */}
                    {isBailout && (() => {
                      const firstStopDepth = decoStops[0]?.depth_m ?? 0
                      const noStopSwitches = [...gasSwitches]
                        .filter(sw => sw.depth_m > firstStopDepth)
                        .sort((a, b) => b.depth_m - a.depth_m)
                      return noStopSwitches.map((sw, i) => {
                        const gasAtSwitch = resolveGasAtStop(sw.depth_m, gasSwitches, bailoutInitialGas ?? gas)
                        const dens = (surfaceDensity(gasAtSwitch.o2, gasAtSwitch.he) * (sw.depth_m / 10 + 1)).toFixed(2)
                        const densNum = parseFloat(dens)
                        const densColor = densNum > 6.3 ? '#dc3545' : densNum > 5.2 ? '#e07000' : ''
                        const ppo2 = ((gasAtSwitch.o2 / 100) * (sw.depth_m / 10 + 1)).toFixed(2)
                        return (
                          <tr key={`ns-${i}`} style={{ borderTop: '2px solid #495057' }}>
                            <td className="ps-2"><i className="bi bi-repeat" style={{ color: '#6c757d', fontSize: '0.8em' }} /></td>
                            <td>{sw.depth_m} m</td>
                            <td>—</td>
                            <td>—</td>
                            <td>{ppo2}</td>
                            <td style={densColor ? { color: densColor } : {}}>{dens}</td>
                            <td style={{ fontSize: '0.78rem' }}>{sw.label}</td>
                          </tr>
                        )
                      })
                    })()}
                    {/* Deco stops — thick top border marks a deco gas switch above */}
                    {decoStops.map((stop, i) => {
                      const isLast = i === decoStops.length - 1
                      const firstStopDepth = decoStops[0]?.depth_m ?? 0
                      const prevDepth = i === 0 ? Infinity : decoStops[i - 1].depth_m
                      const switchAbove = gasSwitches.some(
                        sw => sw.depth_m >= stop.depth_m && sw.depth_m < prevDepth
                          && sw.depth_m <= firstStopDepth
                      )
                      const gasAtStop = resolveGasAtStop(stop.depth_m, gasSwitches, bailoutInitialGas ?? gas)
                      const dens = (surfaceDensity(gasAtStop.o2, gasAtStop.he) * (stop.depth_m / 10 + 1)).toFixed(2)
                      const densNum = parseFloat(dens)
                      const densColor = densNum > 6.3 ? '#dc3545' : densNum > 5.2 ? '#e07000' : ''
                      const ppO2 = isBailout
                        ? ((gasAtStop.o2 / 100) * (stop.depth_m / 10 + 1)).toFixed(2)
                        : sp.toFixed(2)
                      return (
                        <tr key={i} style={switchAbove ? { borderTop: '2px solid #495057' } : {}}>
                          <td className="ps-2">
                            <i className="bi bi-arrow-up-circle"
                              style={{ color: isLast ? '#198754' : '#e07000' }} />
                          </td>
                          <td>{stop.depth_m} m</td>
                          <td>{stop.time_min}</td>
                          <td>{Math.round(rtOffset + stop.runtime_min)}</td>
                          <td>{ppO2}</td>
                          <td style={densColor ? { color: densColor } : {}}>{dens}</td>
                          <td style={{ fontSize: '0.78rem' }}>{gasAtStop.name}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          {/* Metrics + gas supply */}
          <div className="card mt-3">
            <div className="card-body py-2 px-3">
              <div className="d-flex justify-content-around text-center">
                {[
                  { label: 'Runtime', val: `${Math.round(rtOffset + totalTimeMin)} min`, color: 'var(--ocean)' },
                  { label: isBailout ? 'TTS (OC)' : 'TTS', val: `${ttsMin} min`, color: 'var(--ocean)' },
                  { label: 'CNS',     val: `${cnsPct}%`,                               color: cnsColor },
                  { label: 'OTU',     val: `${otu}`,                                   color: otuColor },
                ].map(({ label, val, color }) => (
                  <div key={label}>
                    <div className="field-label mb-1">{label}</div>
                    <div style={{ fontSize: '1.05rem', fontWeight: 800, color }}>{val}</div>
                  </div>
                ))}
              </div>

              {gasSupply && gasSupply.length > 0 && (
                <>
                  <hr className="my-2" />
                  <div className="field-label mb-1">Gas Supply</div>
                  {gasSupply.map((gs, i) => {
                    const pctColor = gs.available_L != null
                      ? (gs.pct! > 90 ? '#dc3545' : gs.pct! > 70 ? '#e07000' : '')
                      : ''
                    const barW = gs.pct != null ? Math.min(100, gs.pct) : 0
                    return (
                      <div key={i} className="d-flex align-items-center gap-2 mb-1" style={{ fontSize: '0.8rem' }}>
                        <span style={{ fontWeight: 700, minWidth: '4.5rem' }}>{gasName(gs.o2, gs.he)}</span>
                        {gs.available_L != null ? (
                          <>
                            <div style={{ flex: 1, background: '#e9ecef', borderRadius: 4, height: 8, overflow: 'hidden' }}>
                              <div style={{ width: `${barW}%`, height: '100%', background: pctColor || 'var(--aqua)', borderRadius: 4 }} />
                            </div>
                            <span style={{ minWidth: '5.5rem', textAlign: 'right', color: pctColor || 'var(--navy)', fontWeight: 600 }}>
                              {Math.round(gs.consumed_L)} / {Math.round(gs.available_L)} L
                            </span>
                            <span style={{ minWidth: '2.5rem', textAlign: 'right', color: pctColor || 'var(--muted)', fontWeight: 700 }}>
                              {Math.round(gs.pct!)}%
                            </span>
                          </>
                        ) : (
                          <span style={{ color: 'var(--muted)' }}>{Math.round(gs.consumed_L)} L used</span>
                        )}
                      </div>
                    )
                  })}
                </>
              )}
            </div>
          </div>
        </div>

        {/* Right col: charts */}
        <div className="col-12 col-lg-7">
          <div className="chart-wrap" ref={chartWrapRef}>
            <div className="chart-header">
              <span className="result-heading" style={{ marginBottom: 0, borderBottom: 'none' }}>{title}</span>
              {profilePoints.some(p => p.inert?.length) && (
                <button className="chart-fs-btn" onClick={() => setMvalueOpen(true)} title="Compartment loading">
                  <i className="bi bi-graph-up" />
                </button>
              )}
              <button className="chart-fs-btn" onClick={toggleFullscreen} title="Full screen">
                <i className={`bi bi-fullscreen${isFullscreen ? '-exit' : ''}`} />
              </button>
            </div>
            <div
              className="profile-canvas"
              style={{ height: 260, position: 'relative' }}
              onMouseMove={handleProfileHover}
              onMouseLeave={resetHover}
            >
              <Line ref={profileRef} data={profileData} options={profileOptions} />
            </div>
            <div className="no-print" style={{ height: 200, position: 'relative', marginTop: 8 }}>
              <Bar data={tissueData} options={tissueOptions} />
            </div>
          </div>
        </div>
      </div>

      <Modal show={mvalueOpen} onHide={() => setMvalueOpen(false)}
        size={modalFullscreen ? undefined : 'xl'} fullscreen={modalFullscreen || undefined}>
        <Modal.Header closeButton>
          <Modal.Title style={{ fontSize: '0.95rem' }}>Tissue loading</Modal.Title>
          <button
            className="btn btn-sm btn-outline-secondary ms-auto me-2"
            onClick={() => setModalFullscreen(f => !f)}
            title={modalFullscreen ? 'Exit fullscreen' : 'Fullscreen'}>
            <i className={`bi bi-${modalFullscreen ? 'fullscreen-exit' : 'fullscreen'}`} />
          </button>
        </Modal.Header>
        <Modal.Body>
          <div className="btn-group btn-group-sm mb-3" role="group">
            <button type="button"
              className={`btn ${activeView === 'time' ? 'btn-primary' : 'btn-outline-secondary'}`}
              onClick={() => setActiveView('time')}>
              Loading over time
            </button>
            <button type="button"
              className={`btn ${activeView === 'mvalue' ? 'btn-primary' : 'btn-outline-secondary'}`}
              onClick={() => setActiveView('mvalue')}>
              M-value diagram
            </button>
          </div>
          {activeView === 'time'
            ? <MvalueDiagram profilePoints={profilePoints} isFullscreen={modalFullscreen} />
            : <MvaluePressureDiagram profilePoints={profilePoints} gfHigh={gfHigh} maxDepthM={depthM ?? 0} isFullscreen={modalFullscreen} />
          }
        </Modal.Body>
      </Modal>
    </div>
  )
}

function resolveGasAtStop(
  depthM: number,
  switches: GasSwitch[],
  baseGas?: { o2: number; he: number; setpoint?: number } | null,
): { o2: number; he: number; name: string } {
  const relevant = switches.filter(s => s.depth_m >= depthM)
  if (relevant.length > 0) {
    const sw = relevant[relevant.length - 1]
    const parts = sw.label.replace('Tx', '').replace('Nx', '').replace('N', '').split('/')
    const o2 = parseInt(parts[0]) || 21
    const he = parseInt(parts[1]) || 0
    return { o2, he, name: sw.label }
  }
  const o2 = baseGas?.o2 ?? 21
  const he = baseGas?.he ?? 0
  return { o2, he, name: gasName(o2, he) }
}

function MvalueDiagram({ profilePoints, isFullscreen }: {
  profilePoints: ProfilePoint[]
  isFullscreen?: boolean
}) {
  const chartRef = useRef<ChartJS<'line'>>(null)
  const pts = profilePoints.filter(p => p.inert && p.inert.length === 16)

  if (pts.length === 0) {
    return (
      <div className="text-muted text-center py-4" style={{ fontSize: '0.85rem' }}>
        No tissue data — recalculate the plan to load this diagram.
      </div>
    )
  }

  const compColor = (i: number) => `hsl(${Math.round(i / 15 * 220)}, 65%, 42%)`

  // Default: show every other compartment to reduce initial clutter; user clicks legend to toggle
  const tissueDatasets = Array.from({ length: 16 }, (_, i) => ({
    label: `C${i + 1} (${N2_HALF_TIMES[i]} min)`,
    hidden: false,
    data: pts.map(p => ({ x: p.t, y: +(p.inert![i][0] + p.inert![i][1]).toFixed(4) })),
    showLine: true, pointRadius: 0, fill: false, tension: 0.15,
    borderColor: compColor(i),
    borderWidth: 1.5,
  }))

  const maxLoad = Math.max(...pts.flatMap(p => p.inert!.map(([n, h]) => n + h)))
  const chartData = { datasets: tissueDatasets } as unknown as ChartData<'line'>

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    interaction: { mode: 'nearest', intersect: false, axis: 'x' },
    scales: {
      x: {
        type: 'linear', min: 0,
        title: { display: true, text: 'Time (min)', font: { size: 10 } },
        ticks: { font: { size: 9 } },
      },
      y: {
        type: 'linear', min: 0,
        suggestedMax: +(maxLoad * 1.12).toFixed(1),
        title: { display: true, text: 'Inert gas pressure (bar)', font: { size: 10 } },
        ticks: { font: { size: 9 } },
      },
    },
    plugins: {
      legend: {
        display: true, position: 'right',
        labels: { font: { size: 9 }, boxWidth: 12, padding: 4 },
        title: { display: true, text: 'click to toggle', color: '#aaa', font: { size: 8, style: 'italic' } },
      },
      tooltip: {
        callbacks: {
          title: (items: { dataIndex: number }[]) => {
            const pt = pts[items[0].dataIndex]
            return pt ? `t = ${pt.t.toFixed(1)} min · ${pt.d.toFixed(0)} m${pt.c > 0 ? ` · ceil ${pt.c.toFixed(0)} m` : ''}` : ''
          },
          label: (item: { datasetIndex: number; dataIndex: number }) => {
            const pt = pts[item.dataIndex]
            if (!pt) return ''
            const [pn2, phe] = pt.inert![item.datasetIndex]
            return `C${item.datasetIndex + 1}: ${(pn2 + phe).toFixed(3)} bar  (N₂ ${pn2.toFixed(3)}  He ${phe.toFixed(3)})`
          },
        },
      },
      zoom: {
        zoom: { wheel: { enabled: true, speed: 0.1 }, pinch: { enabled: true }, mode: 'xy' as const },
        pan: { enabled: true, mode: 'xy' as const },
      },
    },
  } satisfies ChartOptions<'line'>

  const chartHeight = isFullscreen ? 'calc(100vh - 190px)' : 450

  return (
    <div>
      <div style={{ height: chartHeight, position: 'relative' }}>
        <Line ref={chartRef} data={chartData} options={chartOptions} />
      </div>
      <div className="text-end mt-1">
        <button className="btn btn-link btn-sm text-secondary p-0" style={{ fontSize: '0.75rem' }}
          onClick={() => (chartRef.current as any)?.resetZoom()}>Reset zoom</button>
      </div>
    </div>
  )
}

function MvaluePressureDiagram({ profilePoints, gfHigh, maxDepthM, isFullscreen }: {
  profilePoints: ProfilePoint[]
  gfHigh: number
  maxDepthM: number
  isFullscreen?: boolean
}) {
  const chartRef = useRef<ChartJS<'line'>>(null)
  // Hover-to-preview + click-to-lock: track which compartment is locked (null = none)
  // and save visibility state so we can restore it on mouse-leave / unlock.
  const lockedIdx = useRef<number | null>(null)
  const preHoverVis = useRef<boolean[]>([])
  const pts = profilePoints.filter(p => p.inert && p.inert.length === 16)
  if (pts.length === 0) {
    return (
      <div className="text-muted text-center py-4" style={{ fontSize: '0.85rem' }}>
        No tissue data — recalculate the plan to load this diagram.
      </div>
    )
  }

  const gf   = gfHigh / 100
  const maxP = Math.max(maxDepthM / 10 + SURFACE_BAR, SURFACE_BAR + 0.5)

  // Color per compartment — same hue for tissue path, M-value, and GF line so they're obviously linked
  const compHue  = (i: number) => Math.round(i / 15 * 220)
  const compColor = (i: number, alpha = 1) => `hsla(${compHue(i)}, 65%, 42%, ${alpha})`

  const mLine  = (a: number, b: number, x: number) => a + x / b
  const gfLine = (a: number, b: number, x: number) => gf * a + x * (1 + gf * (1 / b - 1))

  // Reference lines: same colour as their compartment, hidden from legend,
  // visibility coupled to the tissue path via legend onClick below.
  const mvalueDatasets = ZHL16C_AB.map(([a, b], i) => ({
    label: '_',
    hidden: false,
    data: [{ x: SURFACE_BAR, y: mLine(a, b, SURFACE_BAR) }, { x: maxP, y: mLine(a, b, maxP) }],
    showLine: true, pointRadius: 0, fill: false, tension: 0,
    borderColor: compColor(i, 0.3), borderWidth: 1, borderDash: [4, 3],
  }))

  const gfDatasets = ZHL16C_AB.map(([a, b], i) => ({
    label: '_',
    hidden: false,
    data: [{ x: SURFACE_BAR, y: gfLine(a, b, SURFACE_BAR) }, { x: maxP, y: gfLine(a, b, maxP) }],
    showLine: true, pointRadius: 0, fill: false, tension: 0,
    borderColor: compColor(i, 0.55), borderWidth: 1, borderDash: [2, 2],
  }))

  const diagDataset = {
    label: 'Ambient P',
    data: [{ x: SURFACE_BAR, y: SURFACE_BAR }, { x: maxP, y: maxP }],
    showLine: true, pointRadius: 0, fill: false, tension: 0,
    borderColor: 'rgba(40,160,80,0.65)', borderWidth: 1.5, borderDash: [6, 4],
  }

  // Tissue paths — dataset order: 0-15 mvalue, 16-31 gf, 32 diag, 33-48 tissue
  const tissueDatasets = Array.from({ length: 16 }, (_, i) => ({
    label: `C${i + 1} (${N2_HALF_TIMES[i]} min)`,
    hidden: false,
    data: pts.map(p => ({ x: p.d / 10 + SURFACE_BAR, y: +(p.inert![i][0] + p.inert![i][1]).toFixed(4) })),
    showLine: true, pointRadius: 0, fill: false, tension: 0,
    borderColor: compColor(i), borderWidth: 1.5,
  }))

  const maxLoad = Math.max(...pts.flatMap(p => p.inert!.map(([n, h]) => n + h)))
  const chartData = {
    datasets: [...mvalueDatasets, ...gfDatasets, diagDataset, ...tissueDatasets],
  } as unknown as ChartData<'line'>

  // Tooltip dedup: the tissue path crosses back over itself during ascent so the
  // same compartment can appear twice as "nearest". Track the last seen label
  // per tooltip render and skip repeats.
  const tooltipSeen = { label: '' }

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    interaction: { mode: 'nearest', intersect: false },
    scales: {
      x: {
        type: 'linear', min: SURFACE_BAR, max: +maxP.toFixed(2),
        title: { display: true, text: 'Ambient pressure (bar)', font: { size: 10 } },
        ticks: { font: { size: 9 } },
      },
      y: {
        type: 'linear', min: 0, suggestedMax: +(maxLoad * 1.2).toFixed(2),
        title: { display: true, text: 'Inert gas pressure (bar)', font: { size: 10 } },
        ticks: { font: { size: 9 } },
      },
    },
    plugins: {
      legend: {
        display: true, position: 'right',
        title: { display: true, text: 'hover · click to lock', color: '#aaa', font: { size: 8, style: 'italic' } },
        labels: {
          font: { size: 9 }, boxWidth: 12, padding: 4,
          filter: (item: { text?: string }) => !(item.text ?? '').startsWith('_'),
        },
        // Hover: temporarily isolate the compartment (unless something is locked)
        onHover: (_e: unknown, legendItem: any, legend: any) => {
          if (lockedIdx.current !== null) return
          const idx: number = legendItem.datasetIndex ?? 0
          const compIdx = idx - 33
          if (compIdx < 0 || compIdx >= 16) return
          const chart = legend.chart
          if (preHoverVis.current.length === 0)
            preHoverVis.current = chart.data.datasets.map((_: any, i: number) => chart.isDatasetVisible(i))
          for (let i = 0; i < 16; i++) {
            const show = i === compIdx
            chart.setDatasetVisibility(i, show)
            chart.setDatasetVisibility(16 + i, show)
            chart.setDatasetVisibility(33 + i, show)
          }
          chart.update('none')
        },
        // Leave: restore state (unless locked)
        onLeave: (_e: unknown, legendItem: any, legend: any) => {
          if (lockedIdx.current !== null) return
          const idx: number = legendItem.datasetIndex ?? 0
          const compIdx = idx - 33
          if (compIdx < 0 || compIdx >= 16) return
          const chart = legend.chart
          if (preHoverVis.current.length > 0) {
            preHoverVis.current.forEach((vis, i) => chart.setDatasetVisibility(i, vis))
            preHoverVis.current = []
          }
          chart.update('none')
        },
        // Click: lock to this compartment (or unlock if already locked here)
        onClick: (_e: unknown, legendItem: any, legend: any) => {
          const chart = legend.chart
          const idx: number = legendItem.datasetIndex ?? 0
          const compIdx = idx - 33
          if (compIdx < 0 || compIdx >= 16) {
            chart.setDatasetVisibility(idx, !chart.isDatasetVisible(idx))
            chart.update('none')
            return
          }
          if (lockedIdx.current === compIdx) {
            // Unlock — restore saved state
            lockedIdx.current = null
            if (preHoverVis.current.length > 0) {
              preHoverVis.current.forEach((vis, i) => chart.setDatasetVisibility(i, vis))
              preHoverVis.current = []
            }
          } else {
            // Lock to this compartment (save state first if not already saved by hover)
            if (preHoverVis.current.length === 0)
              preHoverVis.current = chart.data.datasets.map((_: any, i: number) => chart.isDatasetVisible(i))
            lockedIdx.current = compIdx
            for (let i = 0; i < 16; i++) {
              const show = i === compIdx
              chart.setDatasetVisibility(i, show)
              chart.setDatasetVisibility(16 + i, show)
              chart.setDatasetVisibility(33 + i, show)
            }
          }
          chart.update('none')
        },
      },
      tooltip: {
        filter: (item: any) => (item.dataset.label ?? '').startsWith('C'),
        callbacks: {
          beforeBody: () => { tooltipSeen.label = '' },
          title: (items: any[]) => {
            const pt = pts[items[0].dataIndex]
            return pt ? `t = ${pt.t.toFixed(1)} min · ${pt.d.toFixed(0)} m${pt.c > 0 ? ` · ceil ${pt.c.toFixed(0)} m` : ''}` : ''
          },
          label: (item: any) => {
            const label: string = item.dataset.label ?? ''
            if (label === tooltipSeen.label) return undefined as unknown as string
            tooltipSeen.label = label
            const ci = parseInt(label.slice(1)) - 1
            const pt = pts[item.dataIndex]
            if (!pt || isNaN(ci)) return undefined as unknown as string
            const [pn2, phe] = pt.inert![ci]
            return `C${ci + 1}: ${(pn2 + phe).toFixed(3)} bar  (N₂ ${pn2.toFixed(3)}  He ${phe.toFixed(3)})`
          },
        },
      },
      zoom: {
        zoom: { wheel: { enabled: true, speed: 0.1 }, pinch: { enabled: true }, mode: 'xy' as const },
        pan: { enabled: true, mode: 'xy' as const },
      },
    },
  } satisfies ChartOptions<'line'>

  const chartHeight = isFullscreen ? 'calc(100vh - 200px)' : 450

  return (
    <div>
      <div style={{ height: chartHeight, position: 'relative' }}>
        <Line ref={chartRef} data={chartData} options={chartOptions} />
      </div>
      <div className="d-flex justify-content-between align-items-center mt-1">
        <div style={{ fontSize: '0.7rem', color: '#aaa' }}>
          Each compartment: solid = tissue · long-dashed = M-value · short-dashed = GF-High {gfHigh}%
        </div>
        <button className="btn btn-link btn-sm text-secondary p-0" style={{ fontSize: '0.75rem' }}
          onClick={() => (chartRef.current as any)?.resetZoom()}>Reset zoom</button>
      </div>
    </div>
  )
}
