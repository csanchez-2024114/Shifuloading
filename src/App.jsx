import { Navigate, Route, Routes } from 'react-router-dom'
import HomePage from './pages/HomePage'
import BriefPage from './pages/BriefPage'
import LoginPage from './pages/LoginPage'
import PanelPage from './pages/PanelPage'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/bienvenida" element={<BriefPage />} />
      <Route path="/panel" element={<PanelPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
