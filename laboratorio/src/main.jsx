import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import LaboratorioPage from './lab/LaboratorioPage'
import VistaPage from './lab/VistaPage'
import HubPage from './lab/HubPage'
import '@base/styles.css'
import '@base/home.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HubPage />} />
        <Route path="/panel" element={<LaboratorioPage />} />
        <Route path="/vista" element={<VistaPage />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
)
