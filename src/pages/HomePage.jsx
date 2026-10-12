import { useState } from 'react'
import Nav from '../components/Nav'
import ProductShowcase from '../components/ProductShowcase'
import ModalVideo from '../components/home/ModalVideo'
import Hero from '../components/home/Hero'
import { Desarrolladores, Estadisticas, Integraciones, Pasos } from '../components/home/Plataforma'
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
        <Pasos />
      </main>
      <ModalVideo abierto={video} onCerrar={() => setVideo(false)} />
    </div>
  )
}
