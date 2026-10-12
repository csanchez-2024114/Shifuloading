# 🎯 Plan de Testing - Resumen Ejecutivo

## 📌 Para el Developer: Lee Esto Primero

Tienes que probar **33 aplicaciones de integración OAuth** y documentar cuáles funcionan, cuáles no, y por qué.

### ⏱️ Tiempo Total Estimado
- **Preparación:** 2-3 horas (Día 1)
- **Testing:** 12 horas (Días 2-5)
- **Documentación:** 2 horas (Día 6)
- **Total:** ~18 horas o ~3 días de trabajo

---

## 🚀 Empezar Aquí

### Paso 1: Leer Documentación (30 minutos)
1. Este archivo (TESTING_SUMMARY.md) ← Estás aquí
2. `PLAN_TESTING_INTEGRACIONES.md` - Plan completo
3. `TESTING_SCRIPTS_TEMPLATES.md` - Scripts para automatizar
4. `doc/INTEGRACIONES_FLUJO.md` - Cómo funciona OAuth

### Paso 2: Configurar Ambiente (1 hora)
```bash
# 1. Verificar backend está corriendo
curl http://localhost:8000/health  # Debería retornar 200

# 2. Verificar MongoDB está disponible
# (Abre MongoDB Compass o CLI)

# 3. Verificar frontend tiene variables de entorno correctas
cat .env
# Debería tener:
# VITE_GMAIL_CLIENT_ID=xxxx
# VITE_SLACK_CLIENT_ID=xxxx
# VITE_HUBSPOT_CLIENT_ID=xxxx
# etc...
```

### Paso 3: Preparar cuenta de test
```javascript
// En developer console (F12) del navegador:
localStorage.setItem('email', 'test@ejemplo.com');
localStorage.setItem('token', 'YOUR_JWT_TOKEN');
```

### Paso 4: Empezar testing (ver matriz abajo)

---

## 📊 Matriz de Testing por Categoría

### 🟢 TIER 1 - CRÍTICO (Probar Primero - Días 2)

```
┌─────────────────────────────────────────────────────────────┐
│ GOOGLE SERVICES (5 apps)                                    │
├─────────────────────────────────────────────────────────────┤
│ 📌 Gmail       → ✅ Espera estar funcionando                │
│ 📌 Drive       → ✅ Espera estar funcionando                │
│ ⚠️  Google Docs → ❌ PROBLEMA: No guarda datos              │
│ ⚠️  Google Sheets → ❌ PROBLEMA: No guarda datos            │
│ 📌 Google Slides → 🔲 No testado aún                        │
│                                                              │
│ ✅ Si 3 funcionan: PASS                                     │
│ ❌ Si menos de 3: FIX REQUERIDO                             │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ COMUNICACIÓN (5 apps) - CORE                                │
├─────────────────────────────────────────────────────────────┤
│ ⚠️  Slack      → ❌ PROBLEMA: "no hay credenciales"         │
│ 📌 Discord    → 🔲 Espera estar funcionando                │
│ 📌 Teams      → 🔲 Potencial problema Microsoft           │
│ ⚪ Telegram   → ⚠️  No es OAuth estándar                    │
│ ⚪ WhatsApp   → ⚠️  No es OAuth estándar                    │
│                                                              │
│ ✅ Si 2+ funcionan: ACCEPTABLE                              │
│ ❌ Si menos de 2: FIX REQUERIDO                             │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ CRM / NEGOCIOS (2-3 apps)                                   │
├─────────────────────────────────────────────────────────────┤
│ 📌 HubSpot    → Probablemente funciona                      │
│ ❌ Salesforce → Desactivado (decidir si probar)            │
│                                                              │
│ ✅ Si HubSpot funciona: PASS                                │
└─────────────────────────────────────────────────────────────┘
```

### 🟠 TIER 2 - IMPORTANTE (Días 3)

```
┌─────────────────────────────────────────────────────────────┐
│ GESTIÓN DE PROYECTOS (4 apps)                               │
├─────────────────────────────────────────────────────────────┤
│ 📌 ClickUp    → Probablemente funciona ✅                   │
│ ⚠️  Asana     → PROBLEMA: "invalid_request: client_id"     │
│ ⚠️  Monday    → PROBLEMA: "invalid_scope"                  │
│ 📌 Jira      → 🔲 Potencialmente OK                         │
│                                                              │
│ ✅ Si 2+ funcionan: ACCEPTABLE                              │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ PRODUCTIVIDAD (7 apps)                                      │
├─────────────────────────────────────────────────────────────┤
│ 📌 Notion     → Probablemente OK                            │
│ 📌 Trello     → Probablemente OK                            │
│ 📌 Dropbox    → ⚠️  PROBLEMA: No guarda datos               │
│ 📌 OneDrive   → ⚠️  Microsoft auth issues potenciales      │
│ 📌 Outlook    → ⚠️  Microsoft auth issues potenciales      │
│                                                              │
│ ✅ Si 3+ funcionan: ACCEPTABLE                              │
└─────────────────────────────────────────────────────────────┘
```

### 🟡 TIER 3 - OPCIONAL (Días 4-5)

```
┌─────────────────────────────────────────────────────────────┐
│ REDES SOCIALES (7 apps)                                     │
├─────────────────────────────────────────────────────────────┤
│ 📌 Instagram   → ⚠️  Requiere Business Account              │
│ 📌 Facebook    → Probablemente OK                           │
│ 📌 LinkedIn    → Probablemente OK                           │
│ 📌 TikTok      → ⚠️  Requiere aprobación especial          │
│ 📌 X/Twitter   → ⚠️  Requiere aprobación especial          │
│ 📌 Threads     → 🔲 Metadata limited                        │
│ 📌 Kick        → ❌ No tiene OAuth público                  │
│                                                              │
│ ℹ️  Lower priority - muchas requieren setup manual          │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ MARKETING / EMAIL (3 apps)                                  │
├─────────────────────────────────────────────────────────────┤
│ 📌 Mailchimp  → Probablemente OK                            │
│ 📌 Brevo      → 🔲 No testado                               │
│                                                              │
│ ℹ️  Lower priority                                           │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ OTROS (5 apps)                                              │
├─────────────────────────────────────────────────────────────┤
│ 📌 OnlyFans   → ⚠️  Requiere creator account special       │
│ 📌 Kick       → ❌ No público                               │
│ 📌 Uber Eats  → ⚠️  Business account required               │
│ 📌 Pedidos Ya → ⚠️  Business account required               │
│ 📌 HubSpot    → Ya listado en CRM                           │
│                                                              │
│ ℹ️  Muy baja prioridad                                       │
└─────────────────────────────────────────────────────────────┘
```

---

## 📋 Procedimiento de Testing (Por Cada App)

### 3 Puntos de Verificación

```javascript
// Paso 1: CONEXIÓN (UI Level)
┌─ ¿Abre diálogo de OAuth?           → SÍ✅ / NO❌
│  ¿Redirige a proveedor?             → SÍ✅ / NO❌
│  ¿Vuelve con code en URL?           → SÍ✅ / NO❌
└─ ¿Muestra "Guardando..."?           → SÍ✅ / NO❌

// Paso 2: ALMACENAMIENTO (Backend Level)
┌─ ¿Token en oauth_vault BD?          → SÍ✅ / NO❌
│  ¿Está encriptado (encrypted_data)? → SÍ✅ / NO❌
│  ¿Status = "active"?                → SÍ✅ / NO❌
└─ ¿get_integrations retorna?         → SÍ✅ / NO❌

// Paso 3: VALIDACIÓN (Health Check)
┌─ GET /health_check/[app]            → ✅ ACTIVE / ⚠️ NEEDS_REFRESH / ❌ EXPIRED
│  ¿Valida con API proveedor?         → SÍ✅ / NO❌
└─ ¿Puede desconectarse sin error?    → SÍ✅ / NO❌

RESULTADO FINAL: ✅ WORKS / ⚠️ PARTIAL / ❌ BROKEN / ⏭️ SKIP
```

---

## 🔧 Herramientas Disponibles

### 1. Script Bash (Automático)
```bash
# Descarga y ejecuta:
./test_integrations.sh "YOUR_JWT_TOKEN"

# Genera CSV con resultados
testing_results_20260324_101530.csv
```

### 2. Script Python (Más Detallado)
```bash
python3 test_integrations.py "YOUR_JWT_TOKEN" gmail slack notion

# Genera JSON y CSV
```

### 3. Backend API (Manual pero confiable)
```bash
curl -X GET "http://localhost:8000/api/integrations/health_check" \
  -H "Authorization: Bearer TOKEN"
```

### 4. Frontend Console (Debug)
```javascript
// En console (F12):
fetch('http://localhost:8000/api/integrations/health_check', {
  headers: {'Authorization': `Bearer ${localStorage.getItem('token')}`}
}).then(r => r.json()).then(console.log)
```

---

## 📊 Registro Diario

### Día 1 - Preparación
```
Tareas:
- [ ] Leer documentos de referencia
- [ ] Configurar ambiente (backend + frontend)
- [ ] Crear cuenta test
- [ ] Verificar herramientas de testing

Nota: 
```

### Día 2 - Google + Comunicación
```
Probar:
- [ ] Gmail
- [ ] Drive
- [ ] Google Docs
- [ ] Google Sheets
- [ ] Slack
- [ ] Discord
- [ ] Teams

Resultados:
```

### Día 3 - Proyectos + Productividad
```
Probar:
- [ ] ClickUp
- [ ] Asana
- [ ] Monday
- [ ] Jira
- [ ] Notion
- [ ] Trello
- [ ] OneDrive
- [ ] Outlook

Resultados:
```

### Día 4 - Redes + Marketing
```
Probar:
- [ ] Facebook
- [ ] LinkedIn
- [ ] Instagram
- [ ] TikTok
- [ ] X/Twitter
- [ ] Mailchimp
- [ ] Brevo

Resultados:
```

### Día 5 - Otros + Troubleshooting
```
Probar/Fijar:
- [ ] Apps que fallaron en días anteriores
- [ ] Investigar y documentar problemas
- [ ] Crear issues en GitHub si aplica

Resultados:
```

### Día 6 - Documentación
```
Deliverables:
- [ ] TESTING_REPORT_FINAL.md
- [ ] BROKEN_APPS_ANALYSIS.md
- [ ] Config fixes (si aplica)
- [ ] CSV con status final

Presentación:
```

---

## ✅ Checklist de Entrega Final

Al terminar, entregar:

```
📁 Testing Results/
├── 📄 TESTING_REPORT_FINAL.md
│   ├── Tabla: App | Status | Token Saved | Health Check | Notes
│   ├── Resumen de Issues
│   └── Recomendaciones
├── 📄 BROKEN_APPS_FIX_PLAN.md
│   ├── Por cada app rota: qué falta, cómo arreglarlo
│   └── Prioridad
├── 📊 results.csv
│   └── 33 apps con status final
└── 🐛 GITHUB_ISSUES
    └── Issues creados por defects encontrados
```

---

## 🎯 Métricas de Éxito

**Meta:** 80% de apps funcionando

| Métrica | Target | Critério |
|---------|--------|----------|
| **Google Suite** | 100% | Mínimo Gmail + Drive funcionando |
| **Comunicación** | 70% | Mínimo 2 de (Slack, Discord, Teams) |
| **Proyectos** | 75% | Mínimo 3 de 4 |
| **Productividad** | 70% | Mínimo 5 de 7 |
| **Overall** | 80% | Mínimo 26 de 33 |

---

## 🚨 Problemas Comunes y Soluciones

| Problema | Causa Probable | Solución |
|----------|---|---|
| "Client ID is missing" | Env var no definida | Agregar a .env |
| "Invalid scope" | Scopes incorrectos | Revisar docs de proveedor |
| "Token not saved" | Backend error | Ver logs backend |
| "Health check returns unknown" | Timeout | Reintentar, revisar net |
| "OAuth URL no abre" | Redirect URI mal | Revisar oauthConfigs.ts |

---

## 📞 Escalar Si

- ❌ No puedes conectarte a backend
- ❌ MongoDB no funciona
- ❌ Frontend no carga
- ❌ Problema con provider OAuth específico (contactar soporte proveedor)
- ❌ Necesitas consejos sobre arquitectura

---

## 📚 Documentos de Referencia

Dentro de `/doc`:
1. `PLAN_TESTING_INTEGRACIONES.md` - Plan detallado
2. `TESTING_SCRIPTS_TEMPLATES.md` - Scripts + templates
3. `INTEGRACIONES_FLUJO.md` - Cómo funciona flujo OAuth
4. `HEALTH_CHECK_INTEGRACIONES.md` - Endpoint de validación
5. `HEALTH_CHECK_EJEMPLOS.md` - Ejemplos de requests

---

## 🏁 Resumen

**Tienes que:**
1. ✅ Probar 33 apps de integración
2. ✅ Documentar cuáles funcionan
3. ✅ Documentar por qué fallan
4. ✅ Proponer soluciones
5. ✅ Crear issues en GitHub

**Tiempo:** ~18 horas distribuidas en 5-6 días

**Herramientas:**
- Backend API (`/api/integrations/health_check/`)
- Scripts de testing (bash/python)
- MongoDB para verificar datos
- Browser console para debugging

**Meta:** 80% de apps funcionando correctamente

---

**¿Listo para empezar? 🚀**

Próximo paso: Leer `PLAN_TESTING_INTEGRACIONES.md` para el plan detallado.

