interface GasBarProps {
  o2: number
  he: number
  showLegend?: boolean
  style?: React.CSSProperties
}

export default function GasBar({ o2, he, showLegend, style }: GasBarProps) {
  const n2 = Math.max(0, 100 - o2 - he)
  return (
    <>
      <div className="gas-bar" style={style}>
        <div className="gas-bar-o2" style={{ width: `${o2}%` }} />
        <div className="gas-bar-he" style={{ width: `${he}%` }} />
        <div className="gas-bar-n2" style={{ width: `${n2}%` }} />
      </div>
      {showLegend && (
        <div className="gas-legend">
          <span><span className="gas-dot" style={{ background: 'var(--o2-color)' }} />O₂ {o2}%</span>
          <span><span className="gas-dot" style={{ background: 'var(--he-color)' }} />He {he}%</span>
          <span><span className="gas-dot" style={{ background: 'var(--n2-color)' }} />N₂ {n2}%</span>
        </div>
      )}
    </>
  )
}
