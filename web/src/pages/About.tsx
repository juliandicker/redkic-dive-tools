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
                      Most blending calculators assume your helium source is 100% He. Enter the actual
                      composition and the fill-sequence pressures are calculated correctly — useful when
                      topping from a cylinder that isn't certified pure, or one someone else part-filled.
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
                      Density is baked into every calculation: warnings at 5.2&nbsp;g/L and 6.3&nbsp;g/L,
                      and in the Dive Planner the algorithm actively delays switching to a richer deco gas
                      if doing so would push density above the limit at that depth.
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
                      The tissue saturation chart shows all 16 Bühlmann compartments with the GF-adjusted
                      M-value limit marked on each bar. The compartment touching that line is the one
                      controlling your ascent. At deep stops it tends to be the fast helium compartments;
                      as you ascend, control passes to the slower nitrogen compartments. Click any point on
                      the profile to inspect the tissue state at that moment. You won't find this level of
                      visibility in most planning tools.
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
                <p style={{ fontSize: '0.85rem', marginBottom: 0 }}>
                  Partial-pressure fill sequence for trimix and nitrox. Set your starting contents,
                  target mix, and fill pressure. The key input is the helium source: enter its actual
                  composition rather than assuming 100% He. The analysis panel and best-mix calculator
                  are self-explanatory from there.
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
                <p style={{ fontSize: '0.85rem', marginBottom: '1rem' }}>
                  Bühlmann ZHL-16C with configurable gradient factors, CCR and OC modes. In CCR mode,
                  bailout gases are planned as a separate OC ascent starting from the same tissue state
                  at end of bottom time. In OC mode, gas switching on ascent respects density limits.
                </p>
                <p style={{ fontSize: '0.85rem', marginBottom: 0 }}>
                  Hovering the profile chart shows depth, ceiling, and the active gas at that moment.
                  The tissue saturation chart is the educational centrepiece: click any point on the
                  profile to see which compartment is at the GF limit and why the stop is where it is.
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
                    <p style={{ fontSize: '0.85rem', marginBottom: 0 }}>
                      These tools are cross-validated but not certified decompression planning software.
                      Validate any plan with your approved dive planning software or dive computer before
                      getting in the water. Bugs and suggestions welcome via{' '}
                      <a
                        href="https://github.com/juliandicker/GasBlender/issues"
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ color: 'var(--aqua)' }}
                      >
                        GitHub issues
                      </a>.
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
