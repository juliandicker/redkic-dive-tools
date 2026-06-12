import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import Offcanvas from 'react-bootstrap/Offcanvas'

interface HeaderProps {
  title: string
  tagline: string
  extraButtons?: React.ReactNode
}

export default function Header({ title, tagline, extraButtons }: HeaderProps) {
  const [navOpen, setNavOpen] = useState(false)
  const { pathname } = useLocation()

  return (
    <header className="app-header mb-4">
      <div className="container d-flex align-items-center gap-3">
        <img
          src="/redkic_diving_tools_logo.png"
          alt="Redkic Diving Tools"
          style={{ height: 48, width: 'auto', flexShrink: 0 }}
        />
        <div className="flex-grow-1">
          <h1 className="mb-0">{title}</h1>
          <div className="tagline">{tagline}</div>
        </div>
        {extraButtons}
        <button
          className="btn-hamburger"
          onClick={() => setNavOpen(true)}
          aria-label="Navigation"
        >
          <i className="bi bi-list" />
        </button>
      </div>

      <Offcanvas show={navOpen} onHide={() => setNavOpen(false)} placement="end">
        <Offcanvas.Header closeButton style={{ borderBottom: '1px solid var(--border)' }}>
          <Offcanvas.Title style={{ color: 'var(--ocean)', fontWeight: 700 }}>
            GasBlender
          </Offcanvas.Title>
        </Offcanvas.Header>
        <Offcanvas.Body className="px-3 pt-3">
          <Link
            to="/"
            className={`nav-offcanvas-link${pathname === '/' ? ' active' : ''}`}
            onClick={() => setNavOpen(false)}
          >
            <div className="nav-page-title">Gas Blender</div>
            <div className="nav-page-desc">Fill sequence calculator for technical diving</div>
          </Link>
          <Link
            to="/planner"
            className={`nav-offcanvas-link${pathname === '/planner' ? ' active' : ''}`}
            onClick={() => setNavOpen(false)}
          >
            <div className="nav-page-title">Dive Planner</div>
            <div className="nav-page-desc">Bühlmann ZHL-16C decompression planner — CCR trimix</div>
          </Link>
          <hr style={{ margin: '0.5rem 0', borderColor: 'var(--border)' }} />
          <Link
            to="/about"
            className={`nav-offcanvas-link${pathname === '/about' ? ' active' : ''}`}
            onClick={() => setNavOpen(false)}
          >
            <div className="nav-page-title">About &amp; How to Use</div>
            <div className="nav-page-desc">Features, usage guide, and educational context</div>
          </Link>
        </Offcanvas.Body>
      </Offcanvas>
    </header>
  )
}
