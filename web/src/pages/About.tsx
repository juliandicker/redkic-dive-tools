import { Link } from 'react-router-dom'
import Header from '../components/Header'

export default function About() {
  return (
    <>
      <Header
        title="About & How to Use"
        tagline="What makes these tools different and how to get the most from them"
      />

      <main className="container py-4">
        <div className="row justify-content-center">
          <div className="col-lg-8 col-md-10">

            {/* ── Why it's different ─────────────────────────────────── */}
            <div className="card mb-4">
              <div className="card-body">
                <h2 className="result-heading mb-3">What makes this different</h2>
                <p className="mb-4" style={{ color: 'var(--muted)', fontSize: '0.88rem' }}>
                  These tools were built to scratch a specific itch: features that kept coming up in
                  practice but weren't easy to find in one place.
                </p>

                <div className="d-flex gap-3 mb-4">
                  <div style={{ color: 'var(--aqua)', fontSize: '1.5rem', lineHeight: 1, flexShrink: 0, paddingTop: '0.15rem' }}>
                    <i className="bi bi-flask" />
                  </div>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: '0.95rem', color: 'var(--navy)', marginBottom: '0.3rem' }}>
                      Gas blending from non-pure helium
                    </div>
                    <p style={{ fontSize: '0.85rem', marginBottom: 0 }}>
                      Almost every gas blending calculator assumes your helium source is 100% He. In
                      practice that's often not the case. You might be topping from a cylinder that
                      isn't certified pure, or working with a mix someone else left behind. Enter the
                      actual composition of your helium source and the fill-sequence pressures are
                      calculated correctly. A small thing, but one that matters when the numbers need to
                      be right.
                    </p>
                  </div>
                </div>

                <div className="d-flex gap-3 mb-4">
                  <div style={{ color: 'var(--aqua)', fontSize: '1.5rem', lineHeight: 1, flexShrink: 0, paddingTop: '0.15rem' }}>
                    <i className="bi bi-speedometer2" />
                  </div>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: '0.95rem', color: 'var(--navy)', marginBottom: '0.3rem' }}>
                      Gas density front and centre
                    </div>
                    <p style={{ fontSize: '0.85rem', marginBottom: 0 }}>
                      Density is probably the most underappreciated safety factor in technical diving.
                      Here it's baked into every calculation: warnings when a gas approaches the 5.2&nbsp;g/L
                      recommended limit, a hard warning at 6.3&nbsp;g/L, and in the Dive Planner the
                      algorithm actively delays switching to a richer deco gas if doing so would push
                      density above the limit at that depth.
                    </p>
                  </div>
                </div>

                <div className="d-flex gap-3">
                  <div style={{ color: 'var(--aqua)', fontSize: '1.5rem', lineHeight: 1, flexShrink: 0, paddingTop: '0.15rem' }}>
                    <i className="bi bi-bar-chart-fill" />
                  </div>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: '0.95rem', color: 'var(--navy)', marginBottom: '0.3rem' }}>
                      Tissue loading and M-value visualisation
                    </div>
                    <p style={{ fontSize: '0.85rem', marginBottom: 0 }}>
                      The tissue saturation chart shows all 16 Bühlmann compartments as individual bars,
                      from fastest half-time on the left to slowest on the right. Each bar shows how
                      saturated that compartment is relative to its M-value, with the GF-adjusted limit
                      marked as a line. The bar touching that limit is the controlling compartment: the one
                      dictating when you can ascend. At deep stops it tends to be the fast helium
                      compartments; as you ascend, control passes to the slower nitrogen compartments.
                      Being able to see this shift in real time, and click any point on the profile to
                      inspect the tissue state at that moment, turns the algorithm from a black box into
                      something you can reason about and explain.
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* ── Gas Blender ────────────────────────────────────────── */}
            <div className="card mb-4">
              <div className="card-body">
                <div className="d-flex align-items-center justify-content-between mb-3">
                  <h2 className="result-heading mb-0">Gas Blender</h2>
                  <Link to="/" className="btn btn-sm" style={{ background: 'var(--ocean)', color: '#fff' }}>
                    Open <i className="bi bi-arrow-right" />
                  </Link>
                </div>
                <p style={{ fontSize: '0.85rem' }}>
                  The Gas Blender calculates a partial-pressure fill sequence for trimix and nitrox blends.
                  Fill in three things:
                </p>
                <ul style={{ fontSize: '0.85rem', paddingLeft: '1.25rem' }}>
                  <li className="mb-2">
                    <strong>Starting gas:</strong> whatever is already in the cylinder. Leave it at
                    0&nbsp;bar / 21% O₂ / 0% He for an empty cylinder, or enter the current contents
                    if you're topping up an existing mix.
                  </li>
                  <li className="mb-2">
                    <strong>Target gas:</strong> your desired final mix (e.g. Tx21/35) and target fill
                    pressure.
                  </li>
                  <li>
                    <strong>Helium source:</strong> the actual composition of your He supply. If your
                    cascade or cylinder contains anything other than pure helium, enter what it really is.
                  </li>
                </ul>
                <p style={{ fontSize: '0.85rem' }}>
                  The result is a three-step partial-pressure sequence: bleed to the base pressure → add
                  helium → add oxygen → top up with air. Follow the steps in order on the whip.
                </p>
                <p style={{ fontSize: '0.85rem', marginBottom: 0 }}>
                  The <strong>analysis panel</strong> shows MOD at ppO₂ 1.2, 1.4, and 1.6; gas density
                  at depth with the 5.2&nbsp;g/L limit highlighted; and equivalent narcotic depth. The{' '}
                  <strong>best-mix calculator</strong> works in reverse: give it a target depth and ppO₂
                  limit and it suggests the optimum oxygen and helium percentages.
                </p>
              </div>
            </div>

            {/* ── Dive Planner ───────────────────────────────────────── */}
            <div className="card mb-4">
              <div className="card-body">
                <div className="d-flex align-items-center justify-content-between mb-3">
                  <h2 className="result-heading mb-0">Dive Planner</h2>
                  <Link to="/planner" className="btn btn-sm" style={{ background: 'var(--ocean)', color: '#fff' }}>
                    Open <i className="bi bi-arrow-right" />
                  </Link>
                </div>

                <div className="card-section-title mt-1">Mode</div>
                <p style={{ fontSize: '0.85rem' }}>
                  The planner supports <strong>CCR</strong> and <strong>OC</strong> modes, selected in the
                  Dive Parameters panel.
                </p>
                <ul style={{ fontSize: '0.85rem', paddingLeft: '1.25rem', marginBottom: '1.25rem' }}>
                  <li className="mb-2">
                    <strong>CCR:</strong> set a diluent gas and a constant setpoint. The algorithm models
                    CCR gas loading throughout the bottom phase. Bailout gases (open circuit) are planned
                    as a separate emergency ascent starting from the same tissue state at the end of bottom
                    time.
                  </li>
                  <li>
                    <strong>OC:</strong> set your back gas and any deco or stage cylinders. On the ascent
                    the algorithm selects the richest gas within its MOD, subject to density limits.
                  </li>
                </ul>

                <div className="card-section-title">Gradient factors</div>
                <p style={{ fontSize: '0.85rem', marginBottom: '1.25rem' }}>
                  GF Low controls how conservatively the first stop is placed: lower values push it
                  deeper. GF High sets the allowed saturation at the last stop before surfacing. CCR mode
                  has separate gradient factors for the bailout ascent, because a bailout from depth is a
                  different risk profile to a planned OC dive.
                </p>

                <div className="card-section-title">Profile chart</div>
                <p style={{ fontSize: '0.85rem', marginBottom: '1.25rem' }}>
                  The solid line is your depth profile. The dashed line is the Bühlmann ceiling: the
                  shallowest depth at which the tissues are within their M-value limits at the current
                  gradient factor. When the ceiling rises to meet your depth, a deco stop is required.
                  Gas switches are marked on the chart and listed in the decompression schedule table.
                  Hovering over the chart shows depth, ceiling, and the active gas at that moment.
                </p>

                <div className="card-section-title">Tissue saturation chart</div>
                <p style={{ fontSize: '0.85rem', marginBottom: '1.25rem' }}>
                  See the tissue saturation section above. This chart is the educational core of the
                  planner. Clicking any point on the profile chart snaps the tissue display to that
                  moment so you can inspect exactly which compartment is at the limit and why.
                </p>

                <div className="card-section-title">Gas supply</div>
                <p style={{ fontSize: '0.85rem', marginBottom: '1.25rem' }}>
                  Enter cylinder sizes and fill pressures against each gas. The planner estimates
                  consumption using your SAC rates (configurable in Settings) and shows what percentage of
                  each cylinder the plan uses. A warning appears if any gas runs short before the plan
                  completes.
                </p>

                <div className="card-section-title">CNS and OTU</div>
                <p style={{ fontSize: '0.85rem', marginBottom: 0 }}>
                  CNS% and OTU are tracked cumulatively across the whole dive. CNS tracks short-term
                  central nervous system oxygen toxicity; a warning fires at the threshold set in Settings
                  (default 75%). OTU tracks cumulative pulmonary exposure, useful when planning repetitive
                  dives over a day or a trip.
                </p>
              </div>
            </div>

            {/* ── Disclaimer ─────────────────────────────────────────── */}
            <div className="card mb-4" style={{ borderTopColor: '#c0392b' }}>
              <div className="card-body">
                <div className="d-flex gap-3">
                  <div style={{ color: '#c0392b', fontSize: '1.5rem', lineHeight: 1, flexShrink: 0, paddingTop: '0.1rem' }}>
                    <i className="bi bi-shield-exclamation" />
                  </div>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: '0.95rem', color: 'var(--navy)', marginBottom: '0.5rem' }}>
                      For educational purposes
                    </div>
                    <p style={{ fontSize: '0.85rem', marginBottom: '0.75rem' }}>
                      These tools are implemented carefully and the results are cross-validated, but they
                      are not certified decompression planning software. Before using any plan in the
                      water, validate it with your approved dive planning software or dive computer.
                    </p>
                    <p style={{ fontSize: '0.85rem', marginBottom: 0 }}>
                      If you find a bug, a result that doesn't look right, or have a suggestion, please{' '}
                      <a
                        href="https://github.com/juliandicker/GasBlender/issues"
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ color: 'var(--aqua)' }}
                      >
                        open an issue on GitHub
                      </a>
                      . Feedback from experienced divers and instructors is genuinely useful.
                    </p>
                  </div>
                </div>
              </div>
            </div>

          </div>
        </div>
      </main>

      <footer className="app-footer">
        <div className="container text-center">
          <strong>Redkic Diving Tools</strong> · Bühlmann ZHL-16C · Gas density analysis · Partial-pressure blending
        </div>
      </footer>
    </>
  )
}
