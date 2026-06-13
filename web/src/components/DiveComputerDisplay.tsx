import React from 'react'

interface Props {
  depth: number
  elapsed: number
  ceiling: number
  ppO2: number
  cns: number
  otu: number
  tts: number
  ndl: number
  sats: number[]
  mode: 'ccr' | 'oc'
  setpoint?: number
}

function formatElapsed(minutes: number): string {
  const totalSecs = Math.floor(minutes * 60)
  const h = Math.floor(totalSecs / 3600)
  const m = Math.floor((totalSecs % 3600) / 60)
  const s = totalSecs % 60
  if (h > 0) return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

function ppO2Color(v: number): string {
  if (v < 0.18) return '#4dabf7'
  if (v > 1.6)  return '#ff4444'
  if (v > 1.4)  return '#ffa500'
  return '#2dce89'
}

function satColor(pct: number): string {
  if (pct > 100) return '#ff4444'
  if (pct > 80)  return '#ffa500'
  return '#2dce89'
}

const DiveComputerDisplay = React.memo(function DiveComputerDisplay({
  depth, elapsed, ceiling, ppO2, cns, otu, tts, ndl, sats, mode, setpoint,
}: Props) {
  const dimmed = '#4a5568'
  const bright = '#e2e8f0'
  const border = '#2d3748'

  return (
    <div style={{
      background: '#0a0d1a',
      borderRadius: 12,
      padding: '1.1rem 1.2rem',
      fontFamily: "'Courier New', Courier, monospace",
      color: bright,
      border: `2px solid ${border}`,
      boxShadow: '0 0 28px rgba(0,150,183,0.12)',
    }}>
      {/* Depth + Time */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '0.9rem' }}>
        <div>
          <div style={{ fontSize: '0.55rem', color: dimmed, letterSpacing: '0.15em', textTransform: 'uppercase', marginBottom: 2 }}>Depth</div>
          <div style={{ fontSize: '2.6rem', fontWeight: 700, color: '#4dabf7', lineHeight: 1 }}>
            {depth.toFixed(1)}<span style={{ fontSize: '1.1rem', color: dimmed, marginLeft: 4 }}>m</span>
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: '0.55rem', color: dimmed, letterSpacing: '0.15em', textTransform: 'uppercase', marginBottom: 2 }}>Time</div>
          <div style={{ fontSize: '1.55rem', fontWeight: 700, color: bright, lineHeight: 1, letterSpacing: '0.04em' }}>
            {formatElapsed(elapsed)}
          </div>
          {mode === 'ccr' && setpoint != null && (
            <div style={{ fontSize: '0.7rem', color: dimmed, marginTop: 3 }}>SP {setpoint.toFixed(1)} bar</div>
          )}
        </div>
      </div>

      <div style={{ borderTop: `1px solid ${border}`, marginBottom: '0.8rem' }} />

      {/* ppO2 · CNS · OTU */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.4rem', marginBottom: '0.8rem' }}>
        <Metric label="ppO₂" value={ppO2.toFixed(2)} unit="bar" color={ppO2Color(ppO2)} />
        <Metric label="CNS" value={cns.toFixed(1)} unit="%" color={cns > 80 ? '#ff4444' : cns > 40 ? '#ffa500' : '#2dce89'} />
        <Metric label="OTU" value={Math.round(otu).toString()} color={otu > 250 ? '#ff4444' : otu > 150 ? '#ffa500' : bright} />
      </div>

      {/* Ceiling · TTS */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.4rem', marginBottom: '0.8rem' }}>
        <div style={{
          background: ceiling > 0 ? 'rgba(220,50,50,0.12)' : 'rgba(45,206,137,0.08)',
          border: `1px solid ${ceiling > 0 ? 'rgba(220,50,50,0.4)' : 'rgba(45,206,137,0.25)'}`,
          borderRadius: 6, padding: '0.35rem 0.55rem',
        }}>
          <div style={{ fontSize: '0.5rem', color: dimmed, textTransform: 'uppercase', letterSpacing: '0.15em', marginBottom: 2 }}>Ceiling</div>
          {ceiling > 0
            ? <div style={{ fontSize: '1rem', fontWeight: 700, color: '#ff6b6b' }}>DECO {ceiling.toFixed(0)} m</div>
            : <div style={{ fontSize: '1rem', fontWeight: 700, color: '#2dce89' }}>NDL {Math.round(ndl)} min</div>
          }
        </div>
        <Metric label="TTS" value={Math.max(0, Math.round(tts)).toString()} unit="min" color={bright} />
      </div>

      <div style={{ borderTop: `1px solid ${border}`, marginBottom: '0.7rem' }} />

      {/* Tissue bars */}
      <div style={{ fontSize: '0.5rem', color: dimmed, textTransform: 'uppercase', letterSpacing: '0.15em', marginBottom: '0.5rem' }}>
        Tissue Loading
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '0.18rem 0.8rem' }}>
        {sats.map((sat, i) => {
          const pct = Math.round(sat * 100)
          const col = satColor(pct)
          return (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
              <div style={{ fontSize: '0.5rem', color: dimmed, width: '1.5rem', textAlign: 'right', flexShrink: 0 }}>
                C{i + 1}
              </div>
              <div style={{ flex: 1, height: 5, background: '#1a2040', borderRadius: 3, overflow: 'hidden' }}>
                <div style={{ width: `${Math.min(100, pct)}%`, height: '100%', background: col, borderRadius: 3 }} />
              </div>
              <div style={{ fontSize: '0.48rem', color: col, width: '1.8rem', textAlign: 'right', flexShrink: 0 }}>
                {pct}%
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
})

function Metric({ label, value, unit, color }: { label: string; value: string; unit?: string; color: string }) {
  return (
    <div style={{ background: '#0d1428', border: '1px solid #2d3748', borderRadius: 6, padding: '0.35rem 0.55rem' }}>
      <div style={{ fontSize: '0.5rem', color: '#4a5568', textTransform: 'uppercase', letterSpacing: '0.15em', marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: '1rem', fontWeight: 700, color }}>
        {value}{unit && <span style={{ fontSize: '0.6rem', marginLeft: 2 }}>{unit}</span>}
      </div>
    </div>
  )
}

export default DiveComputerDisplay
