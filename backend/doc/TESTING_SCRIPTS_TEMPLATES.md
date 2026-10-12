# 🧪 Testing Automation Scripts y Templates

## 📝 Template de Testing por Aplicación

Copiar y rellenar para cada app:

```markdown
# Testing: [APP_NAME]

## 📋 Información Básica
- **Proveedor:** [Name]
- **Categoría:** [Category]
- **Importancia:** 🔴/🟠/🟡/🔵 [CRITICAL/HIGH/MEDIUM/LOW]
- **Fecha de Test:** 2026-03-24
- **Testeador:** [Developer Name]

## 🔍 Pre-Flight Checks

### Configuración
- [ ] Existe `VITE_[APP_NAME]_CLIENT_ID` en `.env`
  - Valor: `___________________`
  - ✅ Válido / ❌ Inválido

- [ ] Existe en `src/lib/oauthConfigs.ts`
  - Line: XXX
  - Configuración correcta: ✅ / ❌

- [ ] Existe en `src/data/apps1.ts` (catalog)
  - Name: `___________`
  - nameApi: `____________`
  - Active: true / false

### Dependencias
- [ ] OAuth provider account creado
- [ ] Scopes conocidos y correctos
- [ ] Redirect URI correcta: `https://hypershifu.com/chat`

---

## 🧪 Test 1: Connection Flow

### Paso 1: Iniciar Conexión
```
1. Abrir app en navegador
2. Navegar a sección de Integraciones
3. Buscar [APP_NAME]
4. Click en "Conectar"
5. ¿Abre URL de OAuth?
   - Sí: ✅ Continue
   - No: ❌ FAIL - Ver logs console
```

### Paso 2: Autorización en Proveedor
```
1. ¿Redirige a [Proveedor] login?
   - Sí: ✅ Continue
   - No: ❌ FAIL - URL no correcta
   
2. ¿Pide permisos?
   - Sí: Click "Autorizar"
   - No: ❌ FAIL - Scopes inválidos

3. ¿Redirige de vuelta a app?
   - Sí: ✅ Continue
   - No: ❌ FAIL - Redirect URI incorrecta
```

### Paso 3: Procesamiento del Código
```
1. URL debería ser: https://hypershifu.com/chat?code=XXXXX
2. ¿Procesa el código?
   - App mostrará: "Guardando integración..."
   - ✅ Si aparece: Continue
   - ❌ Si no aparece: Ver console error

3. ¿Muestra confirmación?
   - ✅ "¡Integración conectada!" = OK
   - ⚠️ "Error..." = FAIL
   - ❓ Nada = FAIL - Ver console
```

### Resultado Paso 1
- [ ] ✅ PASS - Connection flow works
- [ ] ❌ FAIL - See notes

**Notas:**
```
[Describe any issues]
```

---

## 🧪 Test 2: Backend Token Storage

### Verificación en Frontend
```typescript
// Abrir console (F12) y ejecutar:
localStorage.getItem('email')           // Debería mostrar email test
localStorage.getItem('token')           // Debería mostrar JWT
```

### Verificación en API
```bash
# Ejecutar en terminal:
curl -X GET "http://localhost:8000/api/integrations/get_integrations" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json"

# Debería retornar:
{
  "integrations": {
    "[app_name]": {
      "id": "...",
      "status": "active",
      "metadata": {...},
      "created_at": "...",
      "updated_at": "..."
    }
  }
}
```

### Verificación en MongoDB
```bash
# En terminal MongoDB o Compass:
db.oauth_vault.find({"provider": "[app_name]"})

# Debería retornar documento similar a:
{
  "_id": ObjectId("..."),
  "user_id": "...",
  "provider": "[app_name]",
  "status": "active",
  "security": {
    "encrypted_data": "<AES-256 BLOB>",
    "iv": "bundled",
    "version": "v2_api"
  },
  "metadata": {...},
  "created_at": ISODate("..."),
  "updated_at": ISODate("...")
}
```

### Resultado Paso 2
- [ ] ✅ PASS - Token stored in DB
- [ ] ⚠️ PARTIAL - Token stored but corrupted
- [ ] ❌ FAIL - Token not found

**Notas:**
```
[Any issues]
```

---

## 🧪 Test 3: Health Check Validation

### Ejecutar Health Check
```bash
# Verifi car estado del token
curl -X GET "http://localhost:8000/api/integrations/health_check/[app_name]" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# Posibles respuestas:

# ✅ ACTIVE - Token válido
{
  "provider": "[app_name]",
  "status": "active",
  "expires_in": 3600,
  "checked_at": "2026-03-24T10:15:30Z",
  "is_recoverable": false
}

# ⚠️ NEEDS_REFRESH - Token próximo a expirar
{
  "provider": "[app_name]",
  "status": "needs_refresh",
  "expires_in": 120,
  "checked_at": "2026-03-24T10:15:30Z",
  "is_recoverable": true
}

# ❌ EXPIRED - Token expirado
{
  "provider": "[app_name]",
  "status": "expired",
  "reason": "Token expirado o inválido",
  "checked_at": "2026-03-24T10:15:30Z",
  "is_recoverable": true
}

# ❓ UNKNOWN - No se pudo verificar
{
  "provider": "[app_name]",
  "status": "unknown",
  "reason": "Timeout al conectar con [provider]",
  "checked_at": "2026-03-24T10:15:30Z",
  "is_recoverable": true
}
```

### Resultado Paso 3
- [ ] ✅ PASS - Status is "active"
- [ ] ⚠️ WARNING - Status is "needs_refresh"
- [ ] ❌ FAIL - Status is "expired" or "unknown"

**Notas:**
```
[Details about status]
```

---

## 📊 Resultado Final

### Checklist de Éxito
- [ ] ✅ Connection successful
- [ ] ✅ Token stored in DB
- [ ] ✅ Token is encrypted
- [ ] ✅ Health check returns "active"
- [ ] ✅ Can disconnect without errors

### Clasificación Final
- [ ] ✅ **WORKING** - Integración completamente funcional
- [ ] ⚠️ **PARTIAL** - Funciona pero con problemas
- [ ] ❌ **BROKEN** - No funciona
- [ ] ⏭️ **SKIP** - No se puede testear (requiere setup especial)

### Problema Identificado (si aplica)
```
Descripción: 
Pasos para reproducir:
Logs relevantes:
Solución propuesta:
```

### Prioridad para Fix
- [ ] 🔴 CRITICAL - Debe funcionar YA
- [ ] 🟠 HIGH - Debería funcionar pronto
- [ ] 🟡 MEDIUM - Puede esperar
- [ ] 🔵 LOW - Baja prioridad
- [ ] ⚪ SKIP - No es necesario

---
```

---

## 🤖 Scipt Automatizado para Batch Testing

### `test_integrations.sh` (Bash/Shell)

```bash
#!/bin/bash

# Script para testear múltiples integraciones automáticamente
# Uso: ./test_integrations.sh <JWT_TOKEN> <APPS_LIST>

JWT_TOKEN="$1"
API_URL="http://localhost:8000/api/integrations"

# Lista de apps a testear
APPS=(
  "gmail"
  "drive"
  "slack"
  "hubspot"
  "notion"
  "clickup"
  "asana"
  "monday"
  "discord"
  "teams"
  "outlook"
  "onedrive"
)

# Colores
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Inicializar CSV de resultados
RESULTS_FILE="testing_results_$(date +%Y%m%d_%H%M%S).csv"
echo "App,Status,Expires_In,Is_Recoverable,Checked_At,Notes" > "$RESULTS_FILE"

echo -e "${BLUE}=== INTEGRATION HEALTH CHECK ===${NC}"
echo "Testing $(date)"
echo "Results will be saved to: $RESULTS_FILE"
echo ""

# Testear cada app
for app in "${APPS[@]}"; do
  echo -n "Testing ${BLUE}$app${NC}... "
  
  # Llamar a health check
  RESPONSE=$(curl -s -X GET "$API_URL/health_check/$app" \
    -H "Authorization: Bearer $JWT_TOKEN" \
    -H "Content-Type: application/json")
  
  # Extraer status
  STATUS=$(echo "$RESPONSE" | jq -r '.status // "unknown"')
  EXPIRES_IN=$(echo "$RESPONSE" | jq -r '.expires_in // "N/A"')
  IS_RECOVERABLE=$(echo "$RESPONSE" | jq -r '.is_recoverable // "unknown"')
  REASON=$(echo "$RESPONSE" | jq -r '.reason // ""')
  
  # Imprimir resultado
  case "$STATUS" in
    "active")
      echo -e "${GREEN}✅ ACTIVE${NC} (expires in $EXPIRES_IN seconds)"
      echo "$app,ACTIVE,$EXPIRES_IN,$IS_RECOVERABLE,$(date -u +%s)," >> "$RESULTS_FILE"
      ;;
    "needs_refresh")
      echo -e "${YELLOW}🔄 NEEDS_REFRESH${NC} (expires in $EXPIRES_IN seconds)"
      echo "$app,NEEDS_REFRESH,$EXPIRES_IN,$IS_RECOVERABLE,$(date -u +%s)," >> "$RESULTS_FILE"
      ;;
    "expired")
      echo -e "${RED}❌ EXPIRED${NC} - $REASON"
      echo "$app,EXPIRED,0,$IS_RECOVERABLE,$(date -u +%s),$REASON" >> "$RESULTS_FILE"
      ;;
    *)
      echo -e "${RED}❓ UNKNOWN${NC} - $REASON"
      echo "$app,UNKNOWN,N/A,N/A,$(date -u +%s),$REASON" >> "$RESULTS_FILE"
      ;;
  esac
  
  # Pequeño delay entre requests
  sleep 1
done

echo ""
echo -e "${BLUE}=== SUMMARY ===${NC}"
echo "Active: $(grep -c 'ACTIVE' "$RESULTS_FILE")"
echo "Needs Refresh: $(grep -c 'NEEDS_REFRESH' "$RESULTS_FILE")"
echo "Expired: $(grep -c 'EXPIRED' "$RESULTS_FILE")"
echo "Unknown: $(grep -c 'UNKNOWN' "$RESULTS_FILE")"
echo ""
echo "Results saved to: $RESULTS_FILE"
```

**Uso:**
```bash
chmod +x test_integrations.sh
./test_integrations.sh "YOUR_JWT_TOKEN_HERE"
```

---

### Python Script para Testing Completo (`test_integrations.py`)

```python
#!/usr/bin/env python3

import requests
import json
from datetime import datetime
import sys
from typing import Dict, List, Tuple

class IntegrationTester:
    def __init__(self, api_url: str, jwt_token: str):
        self.api_url = api_url
        self.jwt_token = jwt_token
        self.headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Content-Type": "application/json"
        }
        self.results = []

    def test_health(self, app_name: str) -> Dict:
        """Testear health de una integración"""
        try:
            url = f"{self.api_url}/health_check/{app_name}"
            response = requests.get(url, headers=self.headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return {
                    "app": app_name,
                    "status": "success",
                    "data": data,
                    "http_code": 200
                }
            elif response.status_code == 404:
                return {
                    "app": app_name,
                    "status": "not_found",
                    "http_code": 404,
                    "message": f"{app_name} not connected"
                }
            else:
                return {
                    "app": app_name,
                    "status": "error",
                    "http_code": response.status_code,
                    "message": response.text
                }
        
        except requests.Timeout:
            return {
                "app": app_name,
                "status": "timeout",
                "message": "Request timeout"
            }
        except Exception as e:
            return {
                "app": app_name,
                "status": "exception",
                "message": str(e)
            }

    def test_all(self, apps: List[str]) -> None:
        """Testear múltiples aplicaciones"""
        print(f"🧪 Testing {len(apps)} integrations...")
        print(f"Time: {datetime.now().isoformat()}")
        print("-" * 80)
        
        for app in apps:
            result = self.test_health(app)
            self.results.append(result)
            
            # Imprimir resultado
            if result["status"] == "success":
                health_status = result["data"].get("status", "unknown")
                if health_status == "active":
                    print(f"✅ {app:15} → ACTIVE")
                elif health_status == "needs_refresh":
                    print(f"🔄 {app:15} → NEEDS_REFRESH")
                elif health_status == "expired":
                    print(f"❌ {app:15} → EXPIRED")
                else:
                    print(f"❓ {app:15} → {health_status}")
            elif result["status"] == "not_found":
                print(f"⚪ {app:15} → NOT_CONNECTED")
            else:
                print(f"❌ {app:15} → {result['status'].upper()}")

    def print_summary(self) -> None:
        """Imprimir resumen"""
        print("-" * 80)
        print("📊 SUMMARY")
        
        active = sum(1 for r in self.results if r.get("data", {}).get("status") == "active")
        needs_refresh = sum(1 for r in self.results if r.get("data", {}).get("status") == "needs_refresh")
        expired = sum(1 for r in self.results if r.get("data", {}).get("status") == "expired")
        not_connected = sum(1 for r in self.results if r.get("status") == "not_found")
        errors = sum(1 for r in self.results if r.get("status") in ["error", "timeout", "exception"])
        
        print(f"  ✅ Active:          {active}")
        print(f"  🔄 Needs Refresh:   {needs_refresh}")
        print(f"  ❌ Expired:         {expired}")
        print(f"  ⚪ Not Connected:   {not_connected}")
        print(f"  ⚠️  Errors:         {errors}")
        print("-" * 80)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python3 test_integrations.py <JWT_TOKEN> [APP1] [APP2] ...")
        sys.exit(1)
    
    jwt_token = sys.argv[1]
    apps = sys.argv[2:] if len(sys.argv) > 2 else [
        "gmail", "drive", "slack", "hubspot", "notion", "clickup",
        "asana", "monday", "discord", "teams"
    ]
    
    tester = IntegrationTester("http://localhost:8000/api/integrations", jwt_token)
    tester.test_all(apps)
    tester.print_summary()
    
    # Exportar a JSON
    with open(f"testing_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json", "w") as f:
        json.dump(tester.results, f, indent=2)
```

**Uso:**
```bash
python3 test_integrations.py "YOUR_JWT_TOKEN_HERE"

# O testear apps específicas:
python3 test_integrations.py "TOKEN" gmail slack hubspot
```

---

## 📋 Frontend Test Checklist

Pegar esto en el console del browser para testear frontend:

```javascript
// ==========================================
// INTEGRATION TESTING CHECKLIST
// ==========================================

console.log("🧪 Integration Testing Started");

// Test 1: Check localStorage
console.log("\n📋 Test 1: LocalStorage");
const email = localStorage.getItem('email');
const token = localStorage.getItem('token');
console.log(`  Email: ${email ? '✅' : '❌'} ${email}`);
console.log(`  Token: ${token ? '✅' : '❌'} ${token?.substring(0, 20)}...`);

// Test 2: Check if IntegrationsContext is available
console.log("\n📋 Test 2: Context Provider");
try {
  // Si usas React DevTools, puedes verificar el contexto
  console.log("  ✅ IntegrationsContext should be available in React DevTools");
} catch (e) {
  console.log("  ❌ Error: " + e.message);
}

// Test 3: Check API endpoint
console.log("\n📋 Test 3: API Health Check");
async function testAPI() {
  try {
    const response = await fetch('http://localhost:8000/api/integrations/health_check', {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      }
    });
    
    if (response.ok) {
      const data = await response.json();
      console.log("  ✅ API reachable");
      console.log(`  Total integrations: ${data.total_integrations}`);
      console.log(`  Active: ${data.status_counts.active}`);
      console.log(`  Expired: ${data.status_counts.expired}`);
      console.log(`  Summary: ${data.summary.message}`);
      
      // Log all integrations
      console.log("\n  Detailed status:");
      Object.entries(data.integrations).forEach(([app, status]) => {
        const icon = status.status === 'active' ? '✅' : status.status === 'expired' ? '❌' : '❓';
        console.log(`    ${icon} ${app}: ${status.status}`);
      });
    } else {
      console.log(`  ❌ API error: ${response.status}`);
    }
  } catch (error) {
    console.log(`  ❌ Error: ${error.message}`);
  }
}

// Run async test
testAPI();

console.log("\n✅ Testing complete");
```

---

## 📊 Resultado CSV Template

Para agrarios manualmente o generados por scripts:

```csv
App,Active,Env_Var,Works,Token_Saved,Health_Check,Notes,Priority,Status
Gmail,✅,✅,✅,✅,✅,Working perfectly,HIGH,✅ WORKING
Drive,✅,✅,✅,✅,✅,Working perfectly,HIGH,✅ WORKING
Google Docs,✅,❌,❌,❌,❌,Missing VITE_GOOGLE_DOCS_CLIENT_ID,HIGH,❌ BROKEN
Google Sheets,✅,❌,❌,❌,❌,Missing VITE_GOOGLE_SHEETS_CLIENT_ID,HIGH,❌ BROKEN
Slack,✅,❌,❌,❌,❌,No credenciales stored,HIGH,❌ BROKEN
Discord,✅,✅,✅,✅,✅,Working,HIGH,✅ WORKING
Notion,✅,✅,✅,✅,✅,Working,HIGH,✅ WORKING
ClickUp,✅,✅,✅,✅,✅,Working,HIGH,✅ WORKING
Asana,✅,❌,❌,❌,❌,Invalid scope,HIGH,❌ BROKEN
Monday,✅,⚠️,⚠️,✅,❌,Invalid scope in config,HIGH,⚠️ PARTIAL
...
```

