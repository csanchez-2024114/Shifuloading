import { useState } from 'react'
import Footer from '../components/Footer'
import Nav from '../components/Nav'
import ProductShowcase from '../components/ProductShowcase'
import ChipVideo from '../components/home/ChipVideo'
import Hero from '../components/home/Hero'
import { Apps, Capital, Desarrolladores, Estadisticas, Pasos } from '../components/home/Plataforma'
import { Internacional, LlegaATodasPartes, ParaTodos, VendeDondeCompra } from '../components/home/Secciones'

/* Inicio de Shifu: misma estructura y orden que la página de referencia, con contenido propio. */
export default function HomePage() {
  const [video, setVideo] = useState(false)
  return (
    <div className="home">
      <Nav />
      <main>
        <Hero onVideo={() => setVideo(true)} />
        <VendeDondeCompra />
        <LlegaATodasPartes />
        <Internacional />
        <ParaTodos />
        <ProductShowcase />
        <Apps />
        <Desarrolladores />
        <Estadisticas />
        <Capital />
        <Pasos />
      </main>
      <Footer />
      <ChipVideo abierto={video} onAbrir={() => setVideo(true)} onCerrar={() => setVideo(false)} />
    </div>
  )
}
