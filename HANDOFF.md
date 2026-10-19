# Handoff — etapa1/pantalla (19-oct-2026)

## Puntos cerrados (lista 31–38, 40)

| # | Qué | Cómo |
|---|-----|------|
| 31 | Chat no tapa la sección | Modo ventana en diseño (≥980px): riel 48px, columna 360px al lado o ventana libre arrastrable; posición en `localStorage` (`src/components/posicionChat.js`, `src/crm/plantillas/chat-ventana.css`, `ChatShifu` en `CrmPage.jsx`). |
| 32–35 | Chat compacto | Cabecera/sugerencias/campo reducidos; sugerencias contextuales (máx. 3) con wrap y toggle «Ocultar ideas» (`sugerenciasCrm.js`, `@lab/plantillas/sugerencias.js`). |
| 33 | Cambios / Deshacer discretos | Íconos en cabecera del chat vía portal (`ChatDiseno.jsx`, `chat-diseno.css`). |
| 36 | Buscador global | `src/crm/buscar.js`, `src/components/BuscadorGlobal.jsx`; abre ficha con evento `shifu:abrir-registro` en `DisenoCrm.jsx`. |
| 37 | Importar contactos | Modal `Importar` en lugar de sección oculta `importar` (diseño y clásico). |
| 38 | Logo | Backend en `a8b8a53` (`usar_logo` + `GET /crm/logo/{id}`). Frontend: `LogoMarca.jsx`, `LogoNegocio.jsx`, `desdeCrm.logoId`, cabecera en `CrmPage.jsx`. |
| 40 | Aviso deshacer en clásico | `src/crm/avisoDeshacer.js` — ya no «No se puede deshacer»; texto según si hay UI de deshacer. |

**No tocado:** comportamiento del agente (`agente_diseno.py` salvo commit previo de logo). Punto **39** (memoria Shifu en pantalla) fuera de alcance.

## Archivos principales

- `src/pages/CrmPage.jsx` — buscador, import modal, chat ventana, logo
- `src/crm/plantillas/*` — ChatDiseno, chat-ventana.css, DisenoCrm, LogoNegocio, sugerencias
- `src/components/BuscadorGlobal.jsx`, `posicionChat.js`
- `laboratorio/src/plantillas/LogoMarca.jsx`, `sugerencias.js`
- `scripts/capturas_pantalla.mjs`
- Capturas: `documentos/mediciones/2026-10-19_pantalla/crm_{1440,1024,390}px.png`

## Pruebas (ejecutadas aquí)

**Frontend** (`node --test`):

- `src/components/__pruebas__/posicionChat.test.mjs` — OK
- `src/crm/__pruebas__/buscar.test.mjs` — OK
- `src/crm/__pruebas__/avisoDeshacer.test.mjs` — OK
- `src/crm/plantillas/__pruebas__/desdeCrm.test.mjs` — OK (13)
- `src/crm/plantillas/__pruebas__/sugerenciasCrm.test.mjs` — OK (7)

**Backend** (`pytest test/crm`):

```bash
cd backend && MONGO_URI=mongodb://x:1 SECRET_KEY=prueba-local-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx OPENAI_API_KEY=sk-falso ENCRYPTION_KEY=Z0FCbV9mYWtlLWtleS1mb3ItdGVzdHMtMzJieXRlc2xvbmc= ENCRYPTION_SALT=c2FsdC1mYWtl \
  /Users/josueboror/CURSOR/HyperShifu/HyperShifu-crm-agent/backend/.venv/bin/python -m pytest test/crm -q -p no:cacheprovider
```

Resultado: **17874 passed, 1 failed** — `test_reloj.py::test_el_programador_llama_al_reloj_del_crm_y_si_falla_sigue` (import de `scheduler_loop` / `ENCRYPTION_KEY`; no relacionado con pantalla).

## Bancos con IA real

No corridos (sin clave OpenAI). Para el revisor, con servidor en memoria:

```bash
# Terminal 1
cd backend && CRM_DISENO=1 CRM_LAB_ADAPTER=1 MONGO_URI=mongodb://x:1 SECRET_KEY=prueba-local-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx OPENAI_API_KEY=sk-falso \
  ENCRYPTION_KEY=... ENCRYPTION_SALT=... \
  <venv>/python scripts/crm_dev_server.py --puerto 5206

# Terminal 2 (raíz worktree)
BASE=http://localhost:5206 RUTA_CHAT=/api/v1/crm/lab/chat \
  laboratorio/pruebas/banco2.py
# … banco_deshacer.py 3, banco_toma.py 1, banco_ficha.py, banco_datos.py 3, banco_pestanas.py 3
```

Guardar salidas en `documentos/mediciones/2026-10-19_pantalla/bancos/`.

## Capturas locales

```bash
cd backend && CRM_DISENO=1 MONGO_URI=... <venv>/python scripts/crm_dev_server.py --puerto 5206
cd .. && VITE_API_URL=http://localhost:5206/api/v1 VITE_CRM_DISENO=1 node_modules/.bin/vite --port 5205 --force
BASE=http://localhost:5205 node scripts/capturas_pantalla.mjs
```

## Qué falta

- **39** Memoria de Shifu en UI.
- Verificar bancos con IA real (revisor).
- Revisar fallo intermitente / entorno de `test_reloj.py` si el CI lo exige.
