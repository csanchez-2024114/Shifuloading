import { useEffect } from 'react'

/* Ventana del video "Por qué creamos Shifu" (por ahora un marcador de posición). La abre el enlace del título del inicio. */
export default function ModalVideo({ abierto, onCerrar }) {
  useEffect(() => {
    if (!abierto) return undefined
    const f = (e) => { if (e.key === 'Escape') onCerrar() }
    document.addEventListener('keydown', f)
    return () => document.removeEventListener('keydown', f)
  }, [abierto, onCerrar])

  if (!abierto) return null
  return (
    <>
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
