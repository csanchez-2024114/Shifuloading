/* Experiencia completa (la "versión final" para vivir el producto de punta a punta, en una sola vista):
 * bienvenida → cuestionario (las MISMAS preguntas del CRM de Carlos) → crear cuenta → Shifu arma tu CRM (y dice por qué) →
 * primer ingreso con recorrido y datos de ejemplo → el CRM vivo con todo lo nuevo (chat, ficha, pestañas como cuaderno,
 * íconos, selección de piezas, deshacer, acomodo automático…).
 * Reglas que respeta: nunca se muestran plantillas para elegir (D29, D49); si las respuestas no alcanzan, una sola pregunta
 * simple de qué quiere llevar (D7); tema del sistema (D9); los datos de ejemplo se borran sin tocar nada real.
 * Laboratorio: la cuenta es de mentira. Lo que hace la persona se guarda en este navegador y sobrevive a recargar (D57);
 * la contraseña nunca se guarda. */
import { useEffect, useMemo, useState } from 'react'
import { PREGUNTAS } from '@base/brief/preguntas'
import Logo from '@base/components/Logo'
import ShifuAvatar from '@base/components/ShifuAvatar'
import PlantillaCRM from '../plantillas/PlantillaCRM'
import { asignar } from '../plantillas/asignar'
import { plantillaPorId } from '../plantillas/semillas'
import { datosEjemplo, sinEjemplos } from '../plantillas/datosEjemplo'
import { fijarRegion, PAISES } from '../plantillas/regional'
import { cargar, guardar, borrarTodo } from './guardado'
import '@base/brief.css'
import './experiencia.css'

// D29/D49: la pregunta «¿cómo quieres armar tu CRM? → partir de una plantilla» no va: Shifu lo arma siempre.
const LISTA = PREGUNTAS.filter((q) => q.id !== 'armado')
// D7: si con las respuestas no hay una opción clara, se pregunta QUÉ quiere llevar (no se muestran estilos ni plantillas).
const QUE_LLEVAR = [
  { v: 'embudo', e: '🧾', t: 'Mis ventas y cotizaciones' }, { v: 'agenda', e: '📅', t: 'Mis citas y mi agenda' },
  { v: 'pedidos', e: '📦', t: 'Mis pedidos y entregas' }, { v: 'membresias', e: '🔄', t: 'Mis clientes recurrentes y pagos' },
  { v: 'proyectos', e: '🗂️', t: 'Mis proyectos y campañas' }, { v: 'simple', e: '🌱', t: 'Algo simple: clientes y tareas' },
]
const CORREO_OK = /^\S+@\S+\.\S+$/
const valido = (q, r) => !q.requerido || (q.tipo === 'varias' ? (r[q.id] || []).length > 0 : q.tipo === 'ubicacion' ? !!r[q.id]?.pais : String(r[q.id] || '').trim().length > 1)
const temaSistema = () => (window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'oscuro' : 'claro')

function Opcion({ op, n, activa, multiple, onClick }) {
  return (
    <button type="button" role={multiple ? 'checkbox' : 'radio'} aria-checked={activa} className={`op ${activa ? 'op-on' : ''}`} onClick={onClick}>
      <span className="op-e" aria-hidden="true">{op.e}</span><span className="op-t">{op.t}</span>{op.d && <small>{op.d}</small>}
      <i className="op-ok" aria-hidden="true">✓</i>{n <= 9 && <kbd aria-hidden="true">{n}</kbd>}
    </button>
  )
}

export default function ExperienciaPage() {
  const [paso, setPaso] = useState('bienvenida') // bienvenida | cuestionario | cuenta | armando | queLlevar | crm
  const [idx, setIdx] = useState(0)
  const [resp, setResp] = useState({})
  const [cuenta, setCuenta] = useState({ nombre: '', apellido: '', correo: '', clave: '' })
  const [aviso, setAviso] = useState('')
  const [eleccion, setEleccion] = useState(null) // id de la estructura de partida (interno: el usuario nunca lo ve como «plantilla»)
  const [ejemplosBorrados, setEjemplosBorrados] = useState(false)
  const [recorridoVisto, setRecorridoVisto] = useState(false)
  // Guardado (D57): hasta leerlo no se dibuja nada (así no parpadea la bienvenida antes de volver a tu CRM).
  const [guardado, setGuardado] = useState(null)
  const [seguro, setSeguro] = useState(false) // «Empezar de nuevo» pide un segundo toque: ahora sí borra algo
  useEffect(() => {
    cargar().then((g) => {
      const x = g.experiencia
      if (x) { setPaso(x.paso === 'armando' || x.paso === 'cuenta' ? 'cuenta' : x.paso); setIdx(x.idx || 0); setResp(x.resp || {}); setEleccion(x.eleccion || null); setEjemplosBorrados(!!x.ejemplosBorrados); setRecorridoVisto(!!x.recorridoVisto) }
      setGuardado(g)
    })
  }, [])
  useEffect(() => {
    if (guardado) guardar('experiencia', { paso, idx, resp, eleccion, ejemplosBorrados, recorridoVisto }) // sin la cuenta: la contraseña no se guarda
  }, [guardado, paso, idx, resp, eleccion, ejemplosBorrados, recorridoVisto])
  const tema = useMemo(temaSistema, [])
  const pais = PAISES[resp.ubicacion?.pais] ? resp.ubicacion.pais : 'gt'

  // Lo que decide el código con las respuestas (asignar.js): estructura y motivos.
  const asig = useMemo(() => asignar({ rubro: resp.rubro, ciclo: resp.ciclo, objetivos: resp.objetivos || [], queVendes: resp.que_vendes || '' }), [resp])
  const plantilla = eleccion ? plantillaPorId(eleccion) : null
  const datos = useMemo(() => { if (!plantilla) return null; fijarRegion(pais); const d = datosEjemplo(plantilla, 'muchos'); return ejemplosBorrados ? sinEjemplos(d) : d }, [plantilla, pais, ejemplosBorrados])
  useEffect(() => { document.documentElement.style.colorScheme = tema === 'claro' ? 'light' : 'dark' }, [tema])

  // «Shifu está armando tu CRM»: una pausa corta con lo que decidió y por qué; si no hay opción clara, la pregunta de D7.
  useEffect(() => {
    if (paso !== 'armando') return undefined
    const t = setTimeout(() => { if (asig.ambiguo) setPaso('queLlevar'); else { setEleccion(asig.recomendada.id); setPaso('crm') } }, 3600)
    return () => clearTimeout(t)
  }, [paso, asig])

  const reiniciar = async () => {
    if (!seguro) { setSeguro(true); setTimeout(() => setSeguro(false), 4000); return }
    await borrarTodo()
    setSeguro(false); setGuardado({}); setPaso('bienvenida'); setIdx(0); setResp({}); setCuenta({ nombre: '', apellido: '', correo: '', clave: '' }); setEleccion(null); setEjemplosBorrados(false); setRecorridoVisto(false)
  }

  if (!guardado) return <div className="brief exp" aria-busy="true" />

  if (paso === 'crm' && plantilla) {
    return (
      <>
        <PlantillaCRM key={plantilla.id} plantilla={plantilla} datos={datos} nivel={ejemplosBorrados ? 'vacio' : 'muchos'} tema={tema} estilo="vivo-compacto" vel={1.6} pais={pais}
          negocio={resp.nombre || 'Mi negocio'} mostrarPlantilla={false} recorrido={!recorridoVisto} onFinRecorrido={() => setRecorridoVisto(true)} onBorrarEjemplos={() => setEjemplosBorrados(true)}
          inicial={guardado.crm} chatInicial={guardado.chat} onGuardar={guardar} />
        <button type="button" className={`exp-reiniciar${seguro ? ' seguro' : ''}`} onClick={reiniciar} title="Volver a empezar la experiencia desde el registro">{seguro ? '¿Seguro? Se borra tu CRM · toca otra vez' : '↺ Empezar de nuevo'}</button>
      </>
    )
  }

  const q = LISTA[idx]
  const titulo = q && (typeof q.titulo === 'function' ? q.titulo(resp) : q.titulo)
  const poner = (id, v) => setResp((r) => ({ ...r, [id]: v }))
  const siguiente = () => { if (idx < LISTA.length - 1) setIdx(idx + 1); else setPaso('cuenta') }
  const elegirUna = (v) => { poner(q.id, v); setTimeout(() => setIdx((i) => (i === idx ? (idx < LISTA.length - 1 ? idx + 1 : i) : i)), 320); if (idx === LISTA.length - 1) setTimeout(() => setPaso('cuenta'), 320) }
  const alternar = (v) => setResp((r) => { const a = r[q.id] || []; return { ...r, [q.id]: a.includes(v) ? a.filter((x) => x !== v) : [...a, v] } })
  const crearCuenta = (e) => {
    e.preventDefault()
    const c = cuenta
    const problema = c.nombre.trim().length < 2 ? 'Escribe tu nombre (mínimo 2 letras).' : c.apellido.trim().length < 2 ? 'Escribe tu apellido (mínimo 2 letras).'
      : !CORREO_OK.test(c.correo.trim()) ? 'Escribe un correo válido, por ejemplo nombre@correo.com.' : c.clave.length < 8 ? 'La contraseña debe tener al menos 8 caracteres.'
      : !/[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]/.test(c.clave) || !/\d/.test(c.clave) ? 'La contraseña debe tener al menos una letra y un número.' : ''
    if (problema) { setAviso(problema); return }
    setAviso(''); setPaso('armando')
  }
  const pct = paso === 'cuestionario' ? (idx / LISTA.length) * 90 : paso === 'bienvenida' ? 0 : 95

  return (
    <div className="brief exp">
      <div className="brief-fondo" aria-hidden="true"><i className="orbe o1" /><i className="orbe o2" /><i className="orbe o3" /></div>
      <div className="brief-prog" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(pct)}><i style={{ width: `${pct}%` }} /></div>
      <header className="brief-cab">
        <Logo height={26} color="#14211d" />
        {paso === 'cuestionario' && <span className="brief-paso" aria-live="polite">{idx + 1} de {LISTA.length}</span>}
        <span className="exp-lab">Laboratorio · se guarda en este navegador</span>
      </header>
      <main className="brief-main">
        {paso === 'bienvenida' && (
          <section className="pantalla foco entra-der exp-centro">
            <ShifuAvatar size={96} />
            <h1>Tu CRM, armado para tu negocio</h1>
            <p className="sub">Contesta unas preguntas, crea tu cuenta y Shifu arma tu CRM. Después cambias el diseño hablando con Shifu, y tus datos los llevas a mano o pidiéndoselo: cada pestaña es un cuaderno en blanco.</p>
            <div className="acciones"><button type="button" className="btn-pildora btn-grande brief-seguir" onClick={() => setPaso('cuestionario')}>Empezar</button></div>
          </section>
        )}

        {paso === 'cuestionario' && q && (
          <section key={idx} className="pantalla foco entra-der" aria-labelledby="exp-titulo">
            <span className="chip-cap">{q.capitulo}</span>
            {q.id === 'nombre' ? <ShifuAvatar size={84} /> : <div className="emoji" aria-hidden="true">{q.emoji}</div>}
            <h1 id="exp-titulo">{titulo}</h1>
            <p className="sub">{q.sub}</p>
            {q.tipo === 'texto' && <input className="campo" type="text" autoFocus maxLength={60} placeholder={q.placeholder} value={resp[q.id] || ''} aria-label={q.capitulo} onChange={(e) => poner(q.id, e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && valido(q, resp)) siguiente() }} />}
            {q.tipo === 'parrafo' && <textarea className="campo campo-parrafo" autoFocus rows={3} maxLength={300} placeholder={q.placeholder} value={resp[q.id] || ''} aria-label={q.capitulo} onChange={(e) => poner(q.id, e.target.value)} />}
            {(q.tipo === 'una' || q.tipo === 'varias' || q.tipo === 'ubicacion') && (
              <div className={`ops ${q.opciones.length <= 3 ? 'ops-pocas' : ''}`} role={q.tipo === 'varias' ? 'group' : 'radiogroup'}>
                {q.opciones.map((op, k) => {
                  const sel = resp[q.id]
                  const activa = q.tipo === 'varias' ? (sel || []).includes(op.v) : q.tipo === 'ubicacion' ? sel?.pais === op.v : sel === op.v
                  return <Opcion key={op.v} op={op} n={k + 1} activa={activa} multiple={q.tipo === 'varias'} onClick={() => (q.tipo === 'varias' ? alternar(op.v) : q.tipo === 'ubicacion' ? poner(q.id, { ...(resp[q.id] || {}), pais: op.v }) : elegirUna(op.v))} />
                })}
              </div>
            )}
            {q.tipo === 'ubicacion' && <input className="campo campo-chico" type="text" maxLength={50} placeholder="Tu ciudad" value={resp.ubicacion?.ciudad || ''} aria-label="Ciudad" onChange={(e) => poner('ubicacion', { ...(resp.ubicacion || {}), ciudad: e.target.value })} />}
            <div className="acciones">
              {idx > 0 && <button type="button" className="brief-atras" onClick={() => setIdx(idx - 1)}>← Atrás</button>}
              {q.tipo !== 'una' && <button type="button" className="btn-pildora btn-grande brief-seguir" disabled={!valido(q, resp)} onClick={siguiente}>{idx === LISTA.length - 1 ? 'Crear mi CRM' : 'Continuar'}</button>}
              {!q.requerido && q.tipo === 'una' && <button type="button" className="brief-atras" onClick={siguiente}>Omitir →</button>}
            </div>
          </section>
        )}

        {paso === 'cuenta' && (
          <form className="pantalla foco entra-der exp-cuenta" onSubmit={crearCuenta} noValidate>
            <span className="chip-cap">Último paso</span>
            <div className="emoji" aria-hidden="true">🔐</div>
            <h1>Crea tu cuenta para guardar tu CRM</h1>
            <p className="sub">En el laboratorio la cuenta es de prueba: tu CRM se guarda en este navegador y la contraseña no se guarda.</p>
            <div className="exp-campos">
              <input className="campo" placeholder="Nombre" value={cuenta.nombre} onChange={(e) => setCuenta({ ...cuenta, nombre: e.target.value })} aria-label="Nombre" autoFocus />
              <input className="campo" placeholder="Apellido" value={cuenta.apellido} onChange={(e) => setCuenta({ ...cuenta, apellido: e.target.value })} aria-label="Apellido" />
              <input className="campo" type="email" placeholder="Correo" value={cuenta.correo} onChange={(e) => setCuenta({ ...cuenta, correo: e.target.value })} aria-label="Correo" />
              <input className="campo" type="password" placeholder="Contraseña" value={cuenta.clave} onChange={(e) => setCuenta({ ...cuenta, clave: e.target.value })} aria-label="Contraseña" />
            </div>
            <p className="exp-ayuda">La contraseña lleva 8 caracteres o más, con al menos una letra y un número.</p>
            {aviso && <p className="exp-aviso" role="alert">{aviso}</p>}
            <div className="acciones"><button type="button" className="brief-atras" onClick={() => setPaso('cuestionario')}>← Atrás</button><button type="submit" className="btn-pildora btn-grande brief-seguir">Crear cuenta y armar mi CRM</button></div>
          </form>
        )}

        {paso === 'armando' && (
          <section className="pantalla foco entra-der exp-centro" role="status" aria-live="polite">
            <ShifuAvatar size={96} />
            <h1>Shifu está armando tu CRM{resp.nombre ? ` para ${resp.nombre}` : ''}</h1>
            <ul className="exp-pasos">
              <li style={{ '--i': 0 }}>Leyendo lo que vendes: «{String(resp.que_vendes || '').slice(0, 60)}»</li>
              <li style={{ '--i': 1 }}>{asig.ambiguo ? 'Tus respuestas dan para varios caminos: te haré una pregunta más' : `Lo armo según ${asig.recomendada.porque.join(', ') || 'tus respuestas'}`}</li>
              <li style={{ '--i': 2 }}>Pestañas, campos, gráficas y tu inicio, listos para que los cambies cuando quieras</li>
            </ul>
            <p className="brief-puntos" aria-hidden="true"><i /><i /><i /></p>
          </section>
        )}

        {paso === 'queLlevar' && (
          <section className="pantalla foco entra-der" aria-labelledby="exp-llevar">
            <span className="chip-cap">Una pregunta más</span>
            <div className="emoji" aria-hidden="true">🧭</div>
            <h1 id="exp-llevar">¿Qué quieres llevar principalmente?</h1>
            <p className="sub">Con esto Shifu arma tu primera versión. Después agregas o quitas lo que quieras.</p>
            <div className="ops" role="radiogroup">{QUE_LLEVAR.map((op, k) => <Opcion key={op.v} op={op} n={k + 1} activa={false} onClick={() => { setEleccion(op.v); setPaso('crm') }} />)}</div>
          </section>
        )}
      </main>
    </div>
  )
}
