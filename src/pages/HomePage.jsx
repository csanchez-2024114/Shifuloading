import { useState } from 'react'
import Footer from '../components/Footer'
import Nav from '../components/Nav'
import ProductShowcase from '../components/ProductShowcase'
import ChipVideo from '../components/home/ChipVideo'
import Hero from '../components/home/Hero'
import { Acompanamiento, Desarrolladores, Estadisticas, Integraciones, Pasos } from '../components/home/Plataforma'
import { CrmAMedida, ParaTodos, ReuneClientes, TodoEnUnLugar } from '../components/home/Secciones'

/* Inicio de Shifu, la plataforma para crear CRMs con IA: misma estructura y orden que la referencia, con contenido propio. */
export default function HomePage() {
  const [video, setVideo] = useState(false)
  return (
    <div className="home">
      <Nav />
      <main>
        <Hero onVideo={() => setVideo(true)} />
        <ReuneClientes />
        <TodoEnUnLugar />
        <CrmAMedida />
        <ParaTodos />
        <ProductShowcase />
        <Integraciones />
        <Desarrolladores />
        <Estadisticas />
        <Acompanamiento />
        <Pasos />
      </main>
      <Footer />
      <ChipVideo abierto={video} onAbrir={() => setVideo(true)} onCerrar={() => setVideo(false)} />
    </div>
  )
}
