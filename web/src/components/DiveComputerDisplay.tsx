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
  gasLabel?: string
}

// ── Constants ──────────────────────────────────────────────────────────────────
const BG        = '#141b2d'
const BLUE      = '#00b3e0'
const WHITE     = '#ffffff'
const DIM       = '#4a6080'
const DIVIDER   = 'rgba(255,255,255,0.08)'
const TISSUE_BG = '#1a2540'

// Matches the dive planner's bar chart colours exactly
function tissueColor(pct: number): string {
  if (pct > 100) return 'rgba(220,53,69,0.9)'
  if (pct > 80)  return 'rgba(255,140,0,0.9)'
  return 'rgba(32,150,130,0.9)'
}

function ppO2Color(v: number): string {
  if (v < 0.18) return '#4dabf7'
  if (v > 1.6)  return 'rgba(220,53,69,1)'
  if (v > 1.4)  return 'rgba(255,140,0,1)'
  return 'rgba(32,150,130,1)'
}

function formatElapsed(minutes: number): string {
  const s = Math.floor(minutes * 60)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const ss = s % 60
  if (h > 0) return `${h}:${String(m).padStart(2,'0')}:${String(ss).padStart(2,'0')}`
  return `${String(m).padStart(2,'0')}:${String(ss).padStart(2,'0')}`
}

function Label({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ fontSize: '0.48rem', color: BLUE, letterSpacing: '0.12em', textTransform: 'uppercase', marginBottom: 1 }}>
      {children}
    </div>
  )
}

// ── Component ──────────────────────────────────────────────────────────────────
const DiveComputerDisplay = React.memo(function DiveComputerDisplay({
  depth, elapsed, ceiling, ppO2, cns, otu, tts, ndl, sats, mode, setpoint, gasLabel,
}: Props) {
  const inDeco = ceiling > 0
  const gas = gasLabel ?? (mode === 'ccr' ? `CCR SP ${(setpoint ?? 1.3).toFixed(1)}` : 'OC')
  const cnsColor = cns > 80 ? 'rgba(220,53,69,1)' : cns > 40 ? 'rgba(255,140,0,1)' : WHITE
  const otuColor = otu > 250 ? 'rgba(220,53,69,1)' : otu > 150 ? 'rgba(255,140,0,1)' : WHITE

  return (
    <div style={{
      background: BG,
      borderRadius: 10,
      fontFamily: "'Arial', 'Helvetica', sans-serif",
      color: WHITE,
      border: '2px solid #1e2d47',
      boxShadow: '0 0 20px rgba(0,179,224,0.08)',
      overflow: 'hidden',
      userSelect: 'none',
    }}>

      {/* ── Row 1: DEPTH · TIME · STOP · TTS ───────────── */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1.3fr 1fr 1fr 0.8fr',
        padding: '0.5rem 0.65rem 0.45rem',
        columnGap: '0.3rem',
        borderBottom: `1px solid ${DIVIDER}`,
      }}>
        <div>
          <Label>DEPTH</Label>
          <div style={{ fontSize: '2.2rem', fontWeight: 700, color: BLUE, lineHeight: 1 }}>
            {depth.toFixed(1)}
          </div>
        </div>
        <div>
          <Label>TIME</Label>
          <div style={{ fontSize: '1.25rem', fontWeight: 700, color: WHITE, lineHeight: 1 }}>
            {formatElapsed(elapsed)}
          </div>
        </div>
        <div>
          <Label>STOP</Label>
          <div style={{ fontSize: '1.25rem', fontWeight: 700, lineHeight: 1, color: inDeco ? 'rgba(220,53,69,1)' : DIM }}>
            {inDeco ? `${ceiling.toFixed(0)} m` : '---'}
          </div>
        </div>
        <div>
          <Label>TTS</Label>
          <div style={{ fontSize: '1.25rem', fontWeight: 700, color: WHITE, lineHeight: 1 }}>
            {Math.round(tts)}
          </div>
        </div>
      </div>

      {/* ── Row 2: CNS/OTU · PPO₂ · CEIL ───────────────── */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1.2fr 1fr',
        padding: '0.4rem 0.65rem',
        columnGap: '0.3rem',
        borderBottom: `1px solid ${DIVIDER}`,
        alignItems: 'center',
      }}>
        {/* Left: CNS + OTU */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
          <div>
            <Label>CNS</Label>
            <div style={{ fontSize: '0.9rem', fontWeight: 700, color: cnsColor }}>{cns.toFixed(1)}%</div>
          </div>
          <div>
            <Label>OTU</Label>
            <div style={{ fontSize: '0.9rem', fontWeight: 700, color: otuColor }}>{Math.round(otu)}</div>
          </div>
        </div>

        {/* Center: PPO₂ */}
        <div style={{ textAlign: 'center' }}>
          <Label>PPO₂</Label>
          <div style={{ fontSize: '2.3rem', fontWeight: 700, color: ppO2Color(ppO2), lineHeight: 1 }}>
            {ppO2.toFixed(2)}
          </div>
        </div>

        {/* Right: CEIL */}
        <div style={{ textAlign: 'right' }}>
          <Label>CEIL</Label>
          <div style={{ fontSize: '0.9rem', fontWeight: 700, color: inDeco ? 'rgba(220,53,69,1)' : DIM }}>
            {inDeco ? `${ceiling.toFixed(0)} m` : '0'}
          </div>
        </div>
      </div>

      {/* ── Row 3: gas · NDL · TTS labels ───────────────── */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1.4fr 1fr 0.8fr',
        padding: '0.1rem 0.65rem 0',
        columnGap: '0.3rem',
      }}>
        <Label>O₂ / HE</Label>
        <Label>NDL</Label>
        <Label>TTS</Label>
      </div>
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1.4fr 1fr 0.8fr',
        padding: '0 0.65rem 0.4rem',
        columnGap: '0.3rem',
        borderBottom: `1px solid ${DIVIDER}`,
        alignItems: 'baseline',
      }}>
        <div style={{ fontSize: '1.05rem', fontWeight: 700, letterSpacing: '0.02em' }}>{gas}</div>
        <div style={{ fontSize: '1.05rem', fontWeight: 700, color: inDeco ? 'rgba(220,53,69,1)' : '#ffd700' }}>
          {inDeco ? `${ceiling.toFixed(0)} m` : Math.round(ndl)}
        </div>
        <div style={{ fontSize: '1.05rem', fontWeight: 700 }}>{Math.round(tts)}</div>
      </div>

      {/* ── Tissue bars (vertical, matching planner) ─────── */}
      <div style={{ padding: '0.35rem 0.5rem 0.45rem' }}>
        <Label>Tissue Loading</Label>
        <div style={{ display: 'flex', gap: 2, alignItems: 'flex-end', height: 56, marginTop: '0.2rem' }}>
          {sats.map((sat, i) => {
            const pct = Math.min(110, Math.round(sat * 100))
            const fillH = Math.max(1, (pct / 110) * 48)
            const col = tissueColor(pct)
            return (
              <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                <div style={{
                  width: '100%', height: 48,
                  background: TISSUE_BG, borderRadius: 2,
                  display: 'flex', flexDirection: 'column', justifyContent: 'flex-end',
                }}>
                  <div style={{ height: fillH, background: col, borderRadius: 2 }} />
                </div>
                <div style={{ fontSize: '0.3rem', color: DIM, marginTop: 2 }}>C{i + 1}</div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
})

export default DiveComputerDisplay
