/* Cara de Shifu para las conversaciones: gris es Shifu, azul es el dueño del negocio. */
export default function ShifuAvatar({ size = 28 }) {
  return <img className="av-shifu" src="/img/shifu-cabeza.webp" alt="Shifu" width={size} height={size} style={{ width: size, height: size }} />
}
