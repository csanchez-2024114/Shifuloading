/* Puntos de enganche del sistema de diseño (D61) en CrmPage. Todo está detrás de VITE_CRM_DISENO=1: con la bandera
 * apagada, DISENO es la constante `false`, estas funciones devuelven lo mismo que reciben y la pantalla del sistema de diseño
 * (DisenoCrm, con sus estilos) ni siquiera entra al paquete: se carga aparte, solo cuando la bandera está prendida. */
import { Suspense, createElement, lazy } from 'react'
import { LuLayoutDashboard } from 'react-icons/lu'
import { tokensDeMarca } from '@lab/plantillas/marca.js'
import { tieneInicio } from './desdeCrm.js'
import { tomarPiezas } from './seleccion.js'

export const DISENO = import.meta.env.VITE_CRM_DISENO === '1'

/** Inicio, listas, contactos y tareas los dibujan las piezas del laboratorio (lienzo, vistas y ficha). */
export const DisenoCrm = DISENO ? lazy(() => import('./DisenoCrm.jsx')) : null

/** El menú con «Inicio» primero cuando el CRM tiene piezas de inicio (§4: crm.inicio). Sin Automatizaciones: en el sistema de
 * diseño están en pausa (el chat tampoco las ofrece). */
export const conInicio = (menu, crm) => {
  if (!DISENO) return menu
  const sinPausa = menu.filter((m) => m.id !== 'automatizaciones')
  return tieneInicio(crm) ? [{ id: 'inicio', t: 'Inicio', I: LuLayoutDashboard, grupo: 0 }, ...sinPausa] : sinPausa
}

/** ¿Esta vista la dibuja el sistema de diseño? (el resto — Ajustes, Importar, Automatizaciones… — sigue siendo de CrmPage). */
export const esVistaDiseno = (vista, crm) => DISENO && (vista === 'inicio' || vista === 'contactos' || vista === 'desarrollo'
  || (vista.startsWith('l_') && !!crm?.listas?.some((l) => l.id === vista)))

/** Atributos del marco .mc: el estilo decidido del laboratorio (Vivo + Compacto) y los tokens de la marca del negocio. */
export function marcoDiseno(crm, tema) {
  if (!DISENO) return { className: 'mc' }
  const { logo_id: _logo, ...marca } = crm?.marca || {}
  return { className: 'mc pl', 'data-estilo': 'vivo', 'data-densidad': 'compacto', style: { '--acento': '#22d3a6', '--vel': 2.2, ...tokensDeMarca(marca, tema).vars } }
}

/** Lo del sistema de diseño dentro del chat de Shifu (se carga aparte): los cambios con «Deshacer», «Quitar ejemplos» y las
 * piezas elegidas en el lienzo. Props: crm, aplicar (la de CrmPage). */
const ChatDisenoAparte = DISENO ? lazy(() => import('./ChatDiseno.jsx')) : null
export const ChatDiseno = DISENO ? (props) => createElement(Suspense, { fallback: null }, createElement(ChatDisenoAparte, props)) : null

/** Las piezas elegidas para el mensaje que sale: { prefijo, contexto: { seleccion } } o null (sin bandera, siempre null). */
export const tomarSeleccion = DISENO ? tomarPiezas : () => null
