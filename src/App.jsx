import { useEffect } from 'react'
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { SESION_VENCIDA } from './api/http'
import HomePage from './pages/HomePage'
import BriefPage from './pages/BriefPage'
import LoginPage from './pages/LoginPage'
import RegistroPage from './pages/RegistroPage'
import CrmPage from './pages/CrmPage'
import PanelPage from './pages/PanelPage'
import InfoIntegraciones from './pages/InfoIntegraciones'
import InfoDesarrolladores from './pages/InfoDesarrolladores'

export default function App() {
  const nav = useNavigate()
  // Si la sesión ya no se puede renovar, en cualquier pantalla se vuelve a pedir que inicie sesión.
  useEffect(() => {
    const f = () => nav('/login', { replace: true })
    window.addEventListener(SESION_VENCIDA, f)
    return () => window.removeEventListener(SESION_VENCIDA, f)
  }, [nav])
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/registro" element={<RegistroPage />} />
      <Route path="/bienvenida" element={<BriefPage />} />
      <Route path="/mi-crm" element={<CrmPage />} />
      <Route path="/panel" element={<PanelPage />} />
      <Route path="/integraciones" element={<InfoIntegraciones />} />
      <Route path="/desarrolladores" element={<InfoDesarrolladores />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
