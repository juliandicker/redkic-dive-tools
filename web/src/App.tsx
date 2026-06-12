import { BrowserRouter, Routes, Route } from 'react-router-dom'
import GasBlender from './pages/GasBlender'
import DivePlanner from './pages/DivePlanner'
import About from './pages/About'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<GasBlender />} />
        <Route path="/planner" element={<DivePlanner />} />
        <Route path="/about" element={<About />} />
      </Routes>
    </BrowserRouter>
  )
}
