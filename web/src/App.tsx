import { BrowserRouter, Routes, Route } from 'react-router-dom'
import GasBlender from './pages/GasBlender'
import DivePlanner from './pages/DivePlanner'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<GasBlender />} />
        <Route path="/planner" element={<DivePlanner />} />
      </Routes>
    </BrowserRouter>
  )
}
