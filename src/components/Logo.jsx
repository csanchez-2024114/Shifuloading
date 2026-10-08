/* Marca provisional de Shifu: un cuadrado redondeado con una "S". Se cambia por el logo real cuando exista. */
export default function Logo({ height = 32, texto = true, color = '#fff' }) {
  return (
    <span className="logo" style={{ color, height }}>
      <svg width={height} height={height} viewBox="0 0 32 32" aria-hidden="true">
        <defs>
          <linearGradient id="sf-g" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#7c5cff" />
            <stop offset="1" stopColor="#22d3a6" />
          </linearGradient>
        </defs>
        <rect width="32" height="32" rx="9" fill="url(#sf-g)" />
        <path d="M21.5 11.2c-.8-1.6-2.6-2.5-4.8-2.5-2.7 0-4.6 1.4-4.6 3.5 0 1.9 1.4 2.9 4.2 3.5l1.6.4c1.6.4 2.2.9 2.2 1.7 0 1-1 1.7-2.6 1.7-1.7 0-2.9-.7-3.4-1.9l-2.5 1.2c.9 2.1 3 3.3 5.9 3.3 3.1 0 5.2-1.5 5.2-3.9 0-2-1.3-3.1-4.3-3.8l-1.5-.4c-1.5-.4-2-.8-2-1.5 0-.9.9-1.5 2.3-1.5 1.3 0 2.2.5 2.7 1.4l2.4-1.2z" fill="#fff" />
      </svg>
      {texto && <span className="logo-texto" style={{ fontSize: height * 0.8 }}>shifu</span>}
    </span>
  )
}
