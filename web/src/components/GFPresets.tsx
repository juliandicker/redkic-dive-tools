const GF_PRESETS: [number, number, string][] = [
  [30, 70, 'Shearwater · 30/70'],
  [60, 80, 'BSAC Trimix · 60/80'],
  [85, 95, 'BSAC Air/Nitrox · 85/95'],
]

export default function GFPresets({
  onSelect, extraButtons,
}: {
  onSelect: (low: number, high: number) => void
  extraButtons?: React.ReactNode
}) {
  return (
    <div className="d-flex align-items-center flex-wrap gap-1 mb-3">
      {GF_PRESETS.map(([l, h, label]) => (
        <button key={label} className="btn btn-sm btn-outline-secondary"
          style={{ fontSize: '0.68rem', padding: '0.1rem 0.35rem' }}
          onClick={() => onSelect(l, h)}>
          {label}
        </button>
      ))}
      {extraButtons}
    </div>
  )
}
