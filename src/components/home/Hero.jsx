import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

/* Cada frase completa "Un CRM hecho para …" y va con una foto que la acompaña: quien emprende, un taller, un equipo y el orden de un escritorio. */
const ESCENAS = [
  { palabra: 'quien emprende solo', clase: 'esc1' },
  { palabra: 'tu taller o negocio local', clase: 'esc2' },
  { palabra: 'vender en equipo', clase: 'esc3' },
  { palabra: 'tener todo en orden', clase: 'esc4' },
]

/** Título que cambia de palabra solo, con un fondo que cambia a la par. */
export default function Hero({ onVideo }) {
  const [i, setI] = useState(0)
  const [sale, setSale] = useState(false)
  useEffect(() => {
    const t = setInterval(() => {
      setSale(true)
      setTimeout(() => { setI((n) => (n + 1) % ESCENAS.length); setSale(false) }, 500)
    }, 4200)
    return () => clearInterval(t)
  }, [])

  return (
    <section className="hero" id="inicio">
      {ESCENAS.map((e, k) => <div key={e.clase} className={`hero-escena ${e.clase} ${k === i ? 'hero-escena-on' : ''}`} aria-hidden="true" />)}
      <div className="hero-velo" aria-hidden="true" />
      <div className="hero-contenido">
        <h1 className="hero-titulo">
          <span>Un CRM hecho para</span>
          <span className={`palabra ${sale ? 'palabra-sale' : 'palabra-entra'}`}>{ESCENAS[i].palabra}</span>
        </h1>
        <p className="hero-texto">
          Piensa a lo grande y crea rápido en Shifu: arma tu CRM con inteligencia artificial, con tus contactos, tus ventas y tu seguimiento a tu medida.
        </p>
        <div className="hero-acciones">
          <Link to="/login" className="btn-pildora btn-grande">Comenzar gratis</Link>
          <a href="#planes" className="btn-borde btn-grande">Ver planes</a>
          <button type="button" className="hero-enlace" onClick={onVideo}><i aria-hidden="true">▸</i> Por qué creamos Shifu</button>
        </div>
      </div>
    </section>
  )
}
