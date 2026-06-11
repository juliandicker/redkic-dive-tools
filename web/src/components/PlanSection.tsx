import { useRef, useState, useCallback } from 'react'
import {
  Chart as ChartJS,
  CategoryScale, LinearScale, PointElement, LineElement, BarElement,
  Title, Tooltip, Legend, Filler,
  type ChartData, type ChartOptions,
} from 'chart.js'
import { Line, Bar } from 'react-chartjs-2'
import type { DecoStop, ProfilePoint, GasSwitch, GasSupplyEntry, Warning } from '../types'
import { surfaceDensity, gasName } from '../utils'

ChartJS.register(
  CategoryScale, LinearScale, PointElement, LineElement, BarElement,
  Title, Tooltip, Legend, Filler,
)

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
}

export default function PlanSection({
  title, decoStops, totalTimeMin, ttsMin, cnsPct, otu,
  profilePoints, tissueSaturations, gasSwitches,
  gasSupply, warnings, gfHigh, diluent, depthM, btMin, descRate, isBailout,
}: PlanSectionProps) {
  const [hoveredSats, setHoveredSats] = useState<number[] | null>(null)
  const profileRef = useRef<ChartJS<'line'>>(null)
  const chartWrapRef = useRef<HTMLDivElement>(null)
  const [isFullscreen, setIsFullscreen] = useState(false)

  const displaySats = (hoveredSats ?? tissueSaturations).map(s => Math.round(s * 100))
  const gfHighPct = gfHigh

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

  const xMax = profilePoints.length ? profilePoints[profilePoints.length - 1].t : totalTimeMin

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
        min: 0, max: xMax,
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
      title: { display: false },
      tooltip: { enabled: false },
    },
    animation: false,
  }

  const tissueTitle = hoveredSats ? 'Tissue loading at hover' : 'Tissue loading — surface'

  const tissueData: ChartData<'bar'> = {
    labels: Array.from({ length: 16 }, (_, i) => `C${i + 1}`),
    datasets: [{
      label: 'Saturation %',
      data: displaySats,
      backgroundColor: displaySats.map(s =>
        s > 100 ? 'rgba(220,53,69,0.75)' :
        s > gfHighPct ? 'rgba(255,140,0,0.75)' :
        'rgba(32,150,130,0.75)'
      ),
      borderWidth: 0,
    }],
  }

  const tissueOptions: ChartOptions<'bar'> = {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      x: { ticks: { font: { size: 9 } } },
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

  const gas    = diluent
  const depth  = depthM ?? 0
  const bt     = btMin  ?? 0
  const dRate  = descRate ?? 20
  const descTime = Math.round(depth / dRate)
  const flatBt   = Math.round(bt - descTime)
  const sp       = gas?.setpoint ?? 1.3
  const gO2      = gas?.o2 ?? 21
  const gHe      = gas?.he ?? 0

  const cnsColor = cnsPct > 80 ? '#dc3545' : cnsPct > 40 ? '#e07000' : 'var(--ocean)'
  const otuColor = otu > 250    ? '#dc3545' : otu > 150   ? '#e07000' : 'var(--navy)'

  return (
    <div>
      {warnings.map((w, i) => (
        <div key={i} className={`alert alert-${w.level === 'error' ? 'danger' : 'warning'} rounded-3 density-warning mb-3`}>
          {w.message}
        </div>
      ))}

      <div className="row g-3 align-items-start">
        {/* Left col: heading + schedule table + metrics */}
        <div className="col-12 col-lg-5">
          <div className="mb-1"><span className="result-heading">{title}</span></div>

          {/* Schedule table */}
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
                    {!isBailout && (
                      <tr>
                        <td className="ps-2"><i className="bi bi-arrow-down-circle" style={{ color: '#0077b6' }} /></td>
                        <td>0→{depth}m</td>
                        <td>{descTime}</td>
                        <td>{descTime}</td>
                        <td>{sp.toFixed(2)}</td>
                        <td>{(surfaceDensity(gO2, gHe) * (depth / 10 + 1)).toFixed(2)}</td>
                        <td style={{ fontSize: '0.78rem' }}>{gasName(gO2, gHe)}</td>
                      </tr>
                    )}
                    {!isBailout && (
                      <tr>
                        <td className="ps-2"><i className="bi bi-circle-fill" style={{ color: '#03045e', fontSize: '0.55em', verticalAlign: 'middle' }} /></td>
                        <td>{depth} m</td>
                        <td>{flatBt}</td>
                        <td>{Math.round(bt)}</td>
                        <td>{sp.toFixed(2)}</td>
                        <td>{(surfaceDensity(gO2, gHe) * (depth / 10 + 1)).toFixed(2)}</td>
                        <td style={{ fontSize: '0.78rem' }}>{gasName(gO2, gHe)}</td>
                      </tr>
                    )}
                    {gasSwitches.map((sw, i) => (
                      <tr key={`sw${i}`} style={{ background: '#f0f8ff' }}>
                        <td className="ps-2"><i className="bi bi-arrow-repeat" style={{ color: 'var(--aqua)' }} /></td>
                        <td>{sw.depth_m} m</td>
                        <td>—</td><td>—</td><td>—</td><td>—</td>
                        <td style={{ fontSize: '0.78rem', color: 'var(--ocean)', fontWeight: 700 }}>→ {sw.label}</td>
                      </tr>
                    ))}
                    {decoStops.map((stop, i) => {
                      const isLast = i === decoStops.length - 1
                      const gasAtStop = resolveGasAtStop(stop.depth_m, gasSwitches, gas)
                      const dens = (surfaceDensity(gasAtStop.o2, gasAtStop.he) * (stop.depth_m / 10 + 1)).toFixed(2)
                      const densNum = parseFloat(dens)
                      const densColor = densNum > 6.3 ? '#dc3545' : densNum > 5.2 ? '#e07000' : ''
                      const ppO2 = isBailout
                        ? ((gasAtStop.o2 / 100) * (stop.depth_m / 10 + 1)).toFixed(2)
                        : sp.toFixed(2)
                      return (
                        <tr key={i}>
                          <td className="ps-2">
                            <i
                              className={`bi bi-arrow-up-circle`}
                              style={{ color: isLast ? '#198754' : '#e07000' }}
                            />
                          </td>
                          <td>{stop.depth_m} m</td>
                          <td>{stop.time_min}</td>
                          <td>{stop.runtime_min}</td>
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
                  { label: 'Runtime', val: `${totalTimeMin} min`, color: 'var(--ocean)' },
                  { label: 'TTS',     val: `${ttsMin} min`,       color: 'var(--ocean)' },
                  { label: 'CNS',     val: `${cnsPct}%`,           color: cnsColor },
                  { label: 'OTU',     val: `${otu}`,               color: otuColor },
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
                          <span style={{ color: 'var(--muted)', fontStyle: 'italic' }}>
                            {Math.round(gs.consumed_L)} L (no cylinder data)
                          </span>
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
            <div style={{ height: 200, position: 'relative', marginTop: 8 }}>
              <Bar data={tissueData} options={tissueOptions} />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function resolveGasAtStop(
  depthM: number,
  switches: GasSwitch[],
  diluent?: { o2: number; he: number; setpoint: number },
): { o2: number; he: number; name: string } {
  const relevant = switches.filter(s => s.depth_m >= depthM)
  if (relevant.length > 0) {
    const sw = relevant[relevant.length - 1]
    const parts = sw.label.replace('Tx', '').replace('Nx', '').split('/')
    const o2 = parseInt(parts[0]) || 21
    const he = parseInt(parts[1]) || 0
    return { o2, he, name: sw.label }
  }
  const o2 = diluent?.o2 ?? 21
  const he = diluent?.he ?? 0
  return { o2, he, name: gasName(o2, he) }
}
