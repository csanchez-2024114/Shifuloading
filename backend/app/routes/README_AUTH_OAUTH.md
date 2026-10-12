# Backend – Jira OAuth & Authentication Notes

Este directorio contiene las rutas relacionadas con autenticación
y servicios externos, incluyendo la integración con Jira mediante OAuth 2.0.

## 📁 Estructura relevante

La estructura actual es la siguiente:

app/
└── routes/
    ├── __pycache__/
    ├── apis/
    ├── core/
    └── auth_jira.py   ← (archivo ubicado directamente en routes)

El archivo `auth_jira.py` **se encuentra directamente dentro de `app/routes/`**
y no forma parte de los submódulos `apis` ni `core`.

Esta organización refleja el estado actual del proyecto y debe tenerse
en cuenta al mantener o refactorizar el código.

---

## 🔐 Flujo de autenticación esperado (Frontend ↔ Backend)

El frontend utiliza autenticación basada en JWT para habilitar
integraciones protegidas (como Jira).

El contrato esperado es:

1. El usuario inicia sesión en el frontend.
2. El backend valida credenciales.
3. El backend **debe emitir un JWT**.
4. El frontend guarda ese token en `localStorage` bajo la key: token


5. Las integraciones OAuth (Jira) utilizan ese token
para validar la identidad del usuario.

---

## ⚠️ Estado actual – Integración Jira

- El flujo OAuth de Jira en `auth_jira.py` está implementado y funcional.
- El frontend **ya está preparado** para trabajar con JWT.
- Actualmente, el endpoint de login **no emite un token JWT**.

### Consecuencia
Mientras el backend no devuelva el JWT en el login:
- El frontend permite acceder a la aplicación.
- Las integraciones protegidas (Jira) quedan bloqueadas correctamente.

Esto **no es un bug**, sino una medida de seguridad esperada.

---

## 🧠 Nota técnica importante

Una vez que el backend emita el JWT en el login:
- Jira quedará habilitado automáticamente.
- El mismo patrón podrá reutilizarse para futuras integraciones OAuth
sin cambios adicionales en el frontend.

Este README documenta el estado actual y el contrato esperado
para facilitar pruebas, mantenimiento y despliegue.


