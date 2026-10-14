/* Dibuja un CRM completo a partir de una plantilla (estructura + vistas) y unos datos. Usa el mismo marco visual que
 * CrmPage (.mc, .mc-top, .mc-menu, .mc-main y los temas de crm-extra.css) para que lo que se prueba sea lo que se integra.
 * Si la plantilla no pasa `validarPlantilla`, muestra los errores en vez de dibujarla mal. */
import { useState } from 'react'
import Logo from '@base/components/Logo'
import { LuLayoutDashboard, LuUsers, LuCalendarDays, LuPackage, LuCreditCard, LuFolderKanban, LuTable, LuActivity, LuIdCard, LuZap, LuFileText, LuTruck, LuCalendarClock } from 'react-icons/lu'
import { COMPONENTES } from './vistas'
import { validarPlantilla, camposDe } from './validar'
import { registrosDe } from './datosEjemplo'
import '@base/crm.css'
import '@base/crm-extra.css'
import './plantillas.css'

const ICONOS = { usuarios: LuUsers, calendario: LuCalendarDays, caja: LuPackage, tarjeta: LuCreditCard, tablero: LuFolderKanban, tabla: LuTable,
  actividad: LuActivity, equipo: LuIdCard, rayo: LuZap, documento: LuFileText, camion: LuTruck, reloj: LuCalendarClock }
const GRUPOS = ['Estructura', 'Medición y equipo', 'Automatizaciones']
const TITULO_VISTA = { kpis: 'Resumen', tablero: 'Por etapa', agenda: 'Próximos días', vencimientos: 'Por vencer', grafica: 'Gráfica', tabla: 'Lista' }

export default function PlantillaCRM({ plantilla, datos, tema = 'oscuro', negocio = 'Mi negocio' }) {
  const [vista, setVista] = useState('inicio')
  const errores = validarPlantilla(plantilla)
  const porId = Object.fromEntries(plantilla.secciones.map((s) => [s.id, s]))
  const actual = porId[vista]
  const dibujar = (s, nombreVista, opciones) => {
    const V = COMPONENTES[nombreVista]
    return V ? <V seccion={s} campos={camposDe(s, porId)} registros={registrosDe(s, datos)} opciones={opciones || {}} datos={datos} /> : null
  }
  return (
    <div className="mc pl" data-tema={tema}>
      <header className="mc-top">
        <Logo height={24} />
        <span className="mc-negocio">{negocio}</span>
        <span className="pl-plantilla" title={plantilla.para}>Plantilla: {plantilla.nombre}</span>
      </header>
      <div className="mc-cuerpo">
        <nav className="mc-menu" aria-label="Secciones">
          <div className="mc-grupo">
            <ul><li><button type="button" className={vista === 'inicio' ? 'on' : ''} aria-current={vista === 'inicio' ? 'page' : undefined} onClick={() => setVista('inicio')}><LuLayoutDashboard aria-hidden="true" />Inicio</button></li></ul>
          </div>
          {GRUPOS.map((g, gi) => {
            const items = plantilla.secciones.filter((s) => s.grupo === gi)
            if (!items.length) return null
            return (
              <div key={g} className="mc-grupo">
                <h2>{g}</h2>
                <ul>
                  {items.map((s) => {
                    const I = ICONOS[s.icono] || LuTable
                    return <li key={s.id}><button type="button" className={vista === s.id ? 'on' : ''} aria-current={vista === s.id ? 'page' : undefined} onClick={() => setVista(s.id)}><I aria-hidden="true" />{s.titulo}</button></li>
                  })}
                </ul>
              </div>
            )
          })}
        </nav>
        <main className="mc-main">
          {errores.length > 0 && (
            <div className="pl-errores" role="alert"><b>Esta plantilla no es válida ({errores.length})</b><ul>{errores.map((e) => <li key={e}>{e}</li>)}</ul></div>
          )}
          {errores.length === 0 && vista === 'inicio' && (
            <>
              <div className="mc-cab"><div><h1>Inicio</h1><p>{plantilla.para}</p></div></div>
              <div className="pl-inicio">
                {plantilla.inicio.map((w, i) => (
                  <section key={i} className={`pl-bloque pl-bloque-${w.vista}`}>
                    <h2>{TITULO_VISTA[w.vista] || w.vista} · {porId[w.seccion].titulo}</h2>
                    {dibujar(porId[w.seccion], w.vista, w.opciones)}
                  </section>
                ))}
              </div>
            </>
          )}
          {errores.length === 0 && actual && (
            <>
              <div className="mc-cab">
                <div><h1>{actual.titulo}</h1>{(actual.campos || actual.fuente) && <p>{registrosDe(actual, datos).length ? `${registrosDe(actual, datos).length.toLocaleString('es')} registros.` : 'Todavía no hay registros.'}</p>}</div>
                {actual.campos && <button type="button" className="btn-pildora">Agregar</button>}
              </div>
              <div className="pl-seccion">{dibujar(actual, actual.vista, actual.opciones)}</div>
            </>
          )}
        </main>
      </div>
    </div>
  )
}
