import { useEffect } from 'react'

/* Miniatura flotante abajo a la derecha: "Por qué creamos Shifu". Al tocarla abre el video (aquí, un marcador de posición). */
export default function ChipVideo({ abierto, onAbrir, onCerrar }) {
  useEffect(() => {
    if (!abierto) return undefined
    const f = (e) => { if (e.key === 'Escape') onCerrar() }
    document.addEventListener('keydown', f)
    return () => document.removeEventListener('keydown', f)
  }, [abierto, onCerrar])

  return (
    <>
      <button type="button" className="chip-video" onClick={onAbrir} aria-label="Ver: Por qué creamos Shifu">
        <span className="chip-video-arte" aria-hidden="true" />
        <span className="chip-video-texto"><i aria-hidden="true">▶</i> Por qué creamos Shifu</span>
      </button>
      {abierto && (
        <div className="modal-video" role="dialog" aria-modal="true" aria-label="Por qué creamos Shifu" onClick={onCerrar}>
          <div className="modal-video-caja" onClick={(e) => e.stopPropagation()}>
            <button type="button" className="modal-video-x" onClick={onCerrar} aria-label="Cerrar">×</button>
            <div className="modal-video-pantalla">
              <span>▶</span>
              <p>Aquí va el video "Por qué creamos Shifu".</p>
              <small>Cuando el equipo lo tenga, se pone su archivo o enlace en este lugar.</small>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
