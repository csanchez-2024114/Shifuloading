/* El guion del recorrido de bienvenida: lo que Shifu va explicando, parte por parte. Se arma con lo que tiene ESE negocio
 * (sus pestañas, lo que cada una significa, sus automatizaciones), no es un texto igual para todos. */

const AVISOS_DE = {
  recordatorios: 'cuando un cliente lleva varios días sin avanzar, te dejo una tarea para darle seguimiento',
  reparto: 'cuando entra un cliente nuevo y lo reparto entre tu equipo',
  resumen: 'cada semana, un resumen de cómo va tu CRM',
}

/** Lo que dice cada pestaña: la explicación que escribió la IA para ese negocio, o una general si no hay. */
const explicacionDe = (m, lista) => {
  if (lista?.descripcion) return lista.descripcion
  if (m.id === 'contactos') return 'Aquí van las personas con las que trabajas: cada una está en una etapa (por ejemplo, nueva o ya cliente) y puedes ver de un vistazo cómo va cada una.'
  return `Aquí llevas ${m.t.toLowerCase()}: cada fila es un registro y cada columna, un dato que quieres guardar de él.`
}

export function armarRecorrido({ negocio, menu, crm }) {
  const listas = Object.fromEntries((crm.listas || []).map((l) => [l.id, l]))
  const propias = menu.filter((m) => m.propia && m.grupo === 1)
  const seccionesDelRecorrido = (propias.length ? propias : menu.slice(0, 1)).slice(0, 4)
  const activas = (crm.automatizaciones || []).filter((a) => a.on && a.disponible !== false && AVISOS_DE[a.id])

  const pasos = [
    {
      id: 'hola', mascota: true, boton: 'Dale clic para continuar',
      titulo: '¡Hola, soy Shifu!',
      texto: (
        <>
          <p>Este es tu nuevo amigo en el día a día de <b>{negocio}</b>.</p>
          <p>Te voy a dar un recorrido rápido por tu CRM para que sepas qué hay en cada parte y todo lo que puedo hacer por ti. Dura un minuto.</p>
        </>
      ),
    },
    {
      id: 'pestanas', objetivo: 'menu', lado: 'derecha',
      titulo: 'Aquí están tus pestañas',
      texto: (
        <>
          <p>En esta parte guardas la información de tu negocio. <b>Yo las armé según a qué te dedicas</b>, a partir de lo que me contaste.</p>
          <p>Te cuento para qué sirve cada una.</p>
        </>
      ),
    },
    ...seccionesDelRecorrido.map((m) => ({
      id: `seccion-${m.id}`, objetivo: `seccion-${m.id}`, lado: 'derecha',
      titulo: m.t,
      texto: (
        <>
          <p>{explicacionDe(m, listas[m.id])}</p>
          <p>Puedes <b>agregar, editar y eliminar</b> lo que quieras tocando los botones, o pedírmelo en el chat y lo hago por ti.</p>
        </>
      ),
    })),
    {
      id: 'pedir', objetivo: 'pedir', lado: 'derecha',
      titulo: '¿Necesitas otra pestaña?',
      texto: (
        <>
          <p>Tu CRM empieza sencillo a propósito: <b>tú decides cómo crece</b>.</p>
          <p>Si quieres otra pestaña (por ejemplo gastos, pagos o pedidos), o un dato nuevo en las que ya tienes, solo dímelo aquí y lo agrego. Así lo vas armando a tu manera.</p>
        </>
      ),
    },
    {
      id: 'ajustes', objetivo: 'ajustes', lado: 'derecha',
      titulo: 'Ajustes',
      texto: (
        <>
          <p>Aquí personalizas tu CRM y cuidas tu cuenta:</p>
          <ul>
            <li><b>Apariencia:</b> cambia entre tema oscuro y claro, el que descanse más tu vista.</li>
            <li><b>Logotipo:</b> si tu negocio tiene uno, súbelo y aparecerá en la barra de arriba.</li>
            <li><b>Descargar en Excel:</b> te llevas todo lo que has trabajado, una hoja por pestaña, cuando quieras.</li>
            <li><b>Mi cuenta:</b> cerrar sesión.</li>
            <li><b>Repetir el cuestionario:</b> empezar de cero (te aviso antes de borrar nada).</li>
            <li><b>Ver este recorrido</b> otra vez, si lo necesitas.</li>
          </ul>
        </>
      ),
    },
    {
      id: 'importar', objetivo: 'importar', lado: 'abajo',
      titulo: 'Importar tus datos',
      texto: (
        <>
          <p>¿Ya llevas tus datos en un <b>Excel</b> o en un <b>bloc de notas</b>? Súbelos aquí y aparecen en tu CRM, sin escribir uno por uno:</p>
          <ul>
            <li>Elige tu archivo (Excel o CSV) o pega las celdas o notas.</li>
            <li>Yo emparejo las columnas con los datos de tu pestaña y tú revisas una vista previa antes de confirmar.</li>
            <li>Si tu Excel trae varias hojas, elijo la que se llama como la pestaña.</li>
            <li>Si te equivocas de archivo, puedes quitar lo importado (te aviso antes de borrar).</li>
          </ul>
          <p>¿Lo tienes en un cuaderno? <em>Mándame una foto en el chat</em> y yo la paso a tu CRM.</p>
        </>
      ),
    },
    {
      id: 'campana', objetivo: 'campana', lado: 'abajo',
      titulo: 'La campanita de avisos',
      texto: (
        <>
          <p>Aquí te dejo mis avisos para que no se te pase nada. Según tu negocio, te aviso de:</p>
          {activas.length
            ? <ul>{activas.map((a) => <li key={a.id}>{AVISOS_DE[a.id]}.</li>)}</ul>
            : <p>Los recordatorios y lo que vaya pasando en tu CRM (puedes pedirme que encienda automatizaciones cuando quieras).</p>}
          <p>Y las tareas con fecha y hora que me pidas. Los avisos también te llegan a tu correo.</p>
        </>
      ),
    },
    {
      id: 'chat', objetivo: 'chat', lado: 'izquierda', boton: '¡Empezar!',
      titulo: 'Y por último, tu mejor amigo: ¡yo!',
      texto: (
        <>
          <p>Estoy en este botón, siempre a la mano. <b>Háblame como a una persona</b>, con tus palabras; no hay que saber nada de computadoras. Esto es todo lo que puedo hacer:</p>
          <div className="tour-lista">
            <section>
              <h3>LO BÁSICO</h3>
              <ul>
                <li>«Agrega a Pedro, su teléfono es…»: agrego, cambio o elimino clientes (antes de borrar te pregunto).</li>
                <li>«Pasa a Ana a Cotización»: le cambio la etapa.</li>
                <li>«Anota una venta de Q250 a María»: guardo registros en tus pestañas.</li>
                <li>Si estás perdido, pregúntame «¿cómo hago…?» y te lo explico paso a paso.</li>
              </ul>
            </section>
            <section>
              <h3>TUS DATOS</h3>
              <ul>
                <li>Agrego, edito o elimino registros de cualquier pestaña: uno o muchos («borra todos los de Carla»).</li>
                <li>Te cuento cuántos hay, sumas y totales exactos, y te resumo cómo va tu CRM con tus datos reales.</li>
                <li>Cambio un dato en varios registros a la vez, o completo lo que les falta.</li>
              </ul>
            </section>
            <section>
              <h3>TU AGENDA</h3>
              <ul>
                <li>«Recuérdame llamar a Pedro mañana a las 9»: creo la tarea con fecha y hora, y te aviso en la campanita.</li>
                <li>La puedo mover de columna, cambiarle el día o borrarla.</li>
              </ul>
            </section>
            <section>
              <h3>TU CRM A TU MEDIDA</h3>
              <ul>
                <li>Creo, renombro, muestro, oculto o quito pestañas.</li>
                <li>Agrego, renombro, muevo o quito columnas, incluso columnas con opciones fijas (Estado: pendiente, realizado, cancelado).</li>
                <li>Cambio las etapas de tus clientes, enciendo o apago automatizaciones y agrego a tu equipo.</li>
              </ul>
            </section>
            <section>
              <h3>FOTOS Y CAPTURAS</h3>
              <ul>
                <li>Súbeme una foto de tu cuaderno, de una lista o de una tabla: la leo y la paso a tu CRM.</li>
                <li>Mándame una foto para completar lo que ya tienes (por ejemplo, ponerles nombre a los productos).</li>
                <li>Captura una parte de tu pantalla y dime «cambia esto»: entiendo a qué te refieres.</li>
              </ul>
            </section>
            <section>
              <h3>MÁS ALLÁ DEL CRM</h3>
              <ul>
                <li>Busco en internet (el clima, un dato, una noticia) y te lo cuento aquí mismo.</li>
                <li>Me acuerdo de ti: cómo prefieres que te hable (de tú o de usted, corto o detallado) y en qué quedamos la última vez.</li>
                <li>Te doy ideas para tu negocio y converso contigo de lo que necesites.</li>
              </ul>
            </section>
            <section>
              <h3>LO QUE TODAVÍA NO PUEDO</h3>
              <ul>
                <li>Importar un Excel desde el chat (eso se hace con el botón «Importar» de cada pestaña).</li>
                <li>Mandar WhatsApp o correos a tus clientes: llegará más adelante.</li>
              </ul>
            </section>
          </div>
          <p>Cuando cierres esto, te voy a saludar en el chat. ¡Vamos a trabajar juntos!</p>
        </>
      ),
    },
  ]
  return pasos
}
