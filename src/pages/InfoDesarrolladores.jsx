import { Link } from 'react-router-dom'
import Nav from '../components/Nav'
import { API_URL, HAY_SERVIDOR } from '../api/config'
import { auth } from '../api'

const BASE = HAY_SERVIDOR ? API_URL : 'https://TU-SERVIDOR/api/v1'

/* Rutas reales de la API del CRM (las mismas que describe API.md). */
const RUTAS = [
  ['POST', '/auth/login', 'Inicia sesión y te da tu token de acceso'],
  ['GET', '/crm', 'Lee tu CRM completo: contactos, tareas, secciones'],
  ['POST', '/crm/contactos', 'Agrega uno o varios contactos'],
  ['PATCH', '/crm/contactos/:id', 'Cambia un contacto (por ejemplo, su etapa)'],
  ['DELETE', '/crm/contactos/:id', 'Elimina un contacto'],
  ['POST', '/crm/tareas', 'Crea una tarea pendiente'],
  ['PATCH', '/crm/tareas/:id', 'Mueve una tarea de columna'],
  ['POST', '/crm/listas/:id/registros', 'Agrega un registro a una sección tuya (pedidos, gastos…)'],
  ['POST', '/crm/chat', 'Habla con Shifu y que él haga el cambio por ti'],
]

const EJEMPLO = `# 1. Entra y guarda tu token
curl -X POST ${BASE}/auth/login \\
  -H "Content-Type: application/json" \\
  -d '{"email":"tu@correo.com","password":"tu-contraseña"}'

# 2. Con ese token, pídele tu CRM
curl ${BASE}/crm \\
  -H "Authorization: Bearer TU_TOKEN"`

export default function InfoDesarrolladores() {
  const conSesion = auth.haySesion() && HAY_SERVIDOR
  const usuario = auth.usuario()

  return (
    <div className="home info">
      <Nav />
      <main className="info-main">
        <header className="info-cab">
          <Link to="/" className="info-volver">← Volver al inicio</Link>
          <h1>API y webhooks</h1>
          <p>Para que tu CRM hable con otros sistemas. Si nunca has oído estas palabras, empieza por aquí: lo explicamos sin tecnicismos.</p>
        </header>

        <section className="info-bloque">
          <h2>Primero, lo básico</h2>
          <div className="info-dos">
            <article className="info-card">
              <span className="info-ico" aria-hidden="true">🍽️</span>
              <h3>¿Qué es una API?</h3>
              <p>Es como el <b>mesero de un restaurante</b>. Tú no entras a la cocina: le pides algo al mesero y él te lo trae.</p>
              <p>Con la API de Shifu, otro programa (tu tienda en línea, tu hoja de cálculo, tu sistema de facturas) <b>le pide</b> datos a tu CRM o le <b>manda</b> datos nuevos, sin que tengas que copiar y pegar a mano.</p>
              <small>Tú preguntas → Shifu responde.</small>
            </article>
            <article className="info-card">
              <span className="info-ico" aria-hidden="true">🔔</span>
              <h3>¿Qué es un webhook?</h3>
              <p>Es como el <b>timbre de tu casa</b>. En vez de asomarte a la puerta cada cinco minutos para ver si llegó alguien, el timbre suena solo cuando pasa algo.</p>
              <p>Con un webhook, Shifu <b>avisa por su cuenta</b> a otro sistema cuando ocurre algo: por ejemplo, que entró un cliente nuevo.</p>
              <small>Shifu te avisa → no tienes que preguntar.</small>
            </article>
          </div>
          <div className="info-tabla" role="table" aria-label="Diferencia entre API y webhook">
            <div role="row" className="cab"><span role="columnheader" /><span role="columnheader">API</span><span role="columnheader">Webhook</span></div>
            <div role="row"><span role="cell">Quién empieza</span><span role="cell">Tú (tu sistema pregunta)</span><span role="cell">Shifu (te avisa solo)</span></div>
            <div role="row"><span role="cell">Sirve para</span><span role="cell">Leer o cambiar datos cuando tú quieras</span><span role="cell">Enterarte al instante de que pasó algo</span></div>
            <div role="row"><span role="cell">Ejemplo</span><span role="cell">“Dame mis contactos de hoy”</span><span role="cell">“Acaba de llegar un cliente nuevo”</span></div>
          </div>
        </section>

        <section className="info-bloque">
          <div className="info-titulo"><h2>La API de Shifu</h2><span className="info-etq disponible">Disponible</span></div>
          <p>Todo lo que haces en tu CRM también se puede hacer por la API. Para usarla necesitas tu token: se obtiene iniciando sesión y se manda en cada petición.</p>
          <div className="info-ruta-lista" role="table" aria-label="Rutas principales de la API">
            {RUTAS.map(([m, r, d]) => (
              <div role="row" key={m + r}>
                <b className={`m ${m.toLowerCase()}`}>{m}</b><code>{r}</code><span>{d}</span>
              </div>
            ))}
          </div>
          <pre className="info-codigo"><code>{EJEMPLO}</code></pre>
          <p className="info-nota">La lista completa de rutas y respuestas está en el archivo <code>API.md</code> del proyecto. Todas las rutas que cambian el CRM devuelven el CRM completo y actualizado.</p>
        </section>

        <section className="info-bloque">
          <div className="info-titulo"><h2>Webhooks de Shifu</h2><span className="info-etq pronto">Próximamente</span></div>
          <p>Todavía no hay webhooks para tu CRM. Estos son los avisos que estamos preparando:</p>
          <ul className="info-lista">
            <li><b>Contacto nuevo:</b> cuando entra un cliente a tu CRM.</li>
            <li><b>Cambio de etapa:</b> cuando un cliente pasa, por ejemplo, de “Cotización” a “Negociación”.</li>
            <li><b>Tarea vencida:</b> cuando se te pasa el día de un pendiente.</li>
          </ul>
          <p className="info-nota">Cuando estén listos, aquí mismo podrás crear los tuyos y ver cuántas veces se han enviado.</p>
        </section>

        <section className="info-bloque info-tuyo">
          <h2>Lo tuyo</h2>
          {conSesion ? (
            <div className="info-tuyo-cuerpo">
              <p>Hola{usuario?.nombre ? `, ${usuario.nombre}` : ''}. Esto es lo que tienes hoy:</p>
              <dl>
                <dt>Dirección de tu API</dt><dd><code>{BASE}</code></dd>
                <dt>Cómo entrar</dt><dd>Con tu correo y contraseña de Shifu (<code>POST /auth/login</code>) obtienes tu token.</dd>
                <dt>Clave de API personal</dt><dd>Todavía no existe: por ahora se usa tu token de sesión. <span className="info-etq pronto">Próximamente</span></dd>
                <dt>Tus webhooks</dt><dd>Ninguno por ahora. <span className="info-etq pronto">Próximamente</span></dd>
              </dl>
            </div>
          ) : (
            <div className="info-tuyo-cuerpo">
              <p>Inicia sesión para ver la dirección de tu API y, cuando existan, tus claves y tus webhooks.</p>
              <Link to="/login" className="btn-pildora">Iniciar sesión</Link>
            </div>
          )}
        </section>
      </main>
    </div>
  )
}
