import { lazy, Suspense, useEffect } from 'react'
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { SESION_VENCIDA } from './api/http'
import HomePage from './pages/HomePage'
import BriefPage from './pages/BriefPage'
import LoginPage from './pages/LoginPage'
import RegistroPage from './pages/RegistroPage'
import CrmPage from './pages/CrmPage'
import PanelPage from './pages/PanelPage'

// Laboratorio de plantillas: solo en desarrollo (import.meta.env.DEV es false en el build, así que no entra a producción).
const LaboratorioPage = import.meta.env.DEV ? lazy(() => import('./laboratorio/LaboratorioPage')) : null
const VistaLabPage = import.meta.env.DEV ? lazy(() => import('./laboratorio/VistaPage')) : null

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
      {import.meta.env.DEV && <Route path="/laboratorio" element={<Suspense fallback={null}><LaboratorioPage /></Suspense>} />}
      {import.meta.env.DEV && <Route path="/laboratorio/vista" element={<Suspense fallback={null}><VistaLabPage /></Suspense>} />}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
