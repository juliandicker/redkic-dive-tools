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
  stopDepth: number
  stopTime: number
  gf99: number
  gasDensity: number
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
  stopDepth, stopTime, gf99, gasDensity,
}: Props) {
  const inDeco = ceiling > 0
  const modeLabel = mode === 'ccr' ? `CCR ${(setpoint ?? 1.3).toFixed(1)}` : 'OC'
  const gas = gasLabel ?? (mode === 'ccr' ? `${(setpoint ?? 1.3).toFixed(1)}` : '?')
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

      {/* ── Row 1: DEPTH · TIME · STOP · STIME · TTS ────── */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1.3fr 0.8fr 0.9fr 0.75fr',
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
            {Math.floor(elapsed)}
          </div>
        </div>
        <div>
          <Label>STOP</Label>
          <div style={{ fontSize: '1.25rem', fontWeight: 700, lineHeight: 1, color: inDeco ? 'rgba(220,53,69,1)' : DIM }}>
            {inDeco ? `${stopDepth} m` : '---'}
          </div>
        </div>
        <div>
          <Label>S.TIME</Label>
          <div style={{ fontSize: '1.25rem', fontWeight: 700, lineHeight: 1, color: inDeco ? 'rgba(220,53,69,1)' : DIM }}>
            {inDeco ? stopTime : '---'}
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
          <div style={{ fontSize: '2.3rem', fontWeight: 700, color: WHITE, lineHeight: 1 }}>
            {ppO2.toFixed(2)}
          </div>
        </div>

        {/* Right: CEIL + GF99 + DENS */}
        <div style={{ textAlign: 'right', display: 'flex', flexDirection: 'column', gap: '0.15rem' }}>
          <div>
            <Label>CEIL</Label>
            <div style={{ fontSize: '0.9rem', fontWeight: 700, color: inDeco ? 'rgba(220,53,69,1)' : DIM }}>
              {inDeco ? `${ceiling.toFixed(0)} m` : '0'}
            </div>
          </div>
          <div>
            <Label>GF99</Label>
            <div style={{ fontSize: '0.9rem', fontWeight: 700, color: WHITE }}>
              {Math.round(gf99)}%
            </div>
          </div>
          <div>
            <Label>G/L</Label>
            <div style={{
              fontSize: '0.9rem', fontWeight: 700,
              color: gasDensity >= 6.2 ? 'rgba(220,53,69,1)' : gasDensity >= 5.2 ? 'rgba(255,140,0,1)' : WHITE,
            }}>
              {gasDensity.toFixed(2)}
            </div>
          </div>
        </div>
      </div>

      {/* ── Mode · Gas · NDL · TTS ───────────────────────── */}
      <div style={{ padding: '0.3rem 0.65rem 0.4rem', borderBottom: `1px solid ${DIVIDER}`, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
        <div>
          <Label>MODE</Label>
          <div style={{ fontSize: '1.0rem', fontWeight: 700, letterSpacing: '0.04em', color: BLUE }}>
            {modeLabel}
          </div>
        </div>
        <div>
          <Label>GAS</Label>
          <div style={{ fontSize: '1.0rem', fontWeight: 700, letterSpacing: '0.04em', color: WHITE }}>
            {gas}
          </div>
        </div>
        <div>
          <Label>NDL</Label>
          <div style={{ fontSize: '1.0rem', fontWeight: 700, color: inDeco ? DIM : (ndl < 5 ? '#ffd700' : WHITE) }}>
            {inDeco ? '0' : Math.round(ndl)}
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <Label>TTS</Label>
          <div style={{ fontSize: '1.0rem', fontWeight: 700, color: WHITE }}>
            {Math.round(tts)}
          </div>
        </div>
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
