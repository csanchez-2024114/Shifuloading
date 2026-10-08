/* Íconos sencillos en SVG, para no depender de una librería en la barra y los botones. */
export function ChevronDown() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true" style={{ marginLeft: 6 }}>
      <path d="M2.5 4.5 6 8l3.5-3.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function ClaveDeAcceso() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <circle cx="7.5" cy="6.5" r="3" stroke="currentColor" strokeWidth="1.4" />
      <path d="M2.5 16c.4-2.6 2.3-4 5-4 1 0 1.900.2 2.600.6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
      <circle cx="14.500" cy="12" r="1.800" stroke="currentColor" strokeWidth="1.400" />
      <path d="M14.500 13.800V17m0-1.500h1.500" stroke="currentColor" strokeWidth="1.400" strokeLinecap="round" />
    </svg>
  )
}
