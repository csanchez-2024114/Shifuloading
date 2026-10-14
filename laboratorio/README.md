# Laboratorio de plantillas visuales

App aparte del CRM de Shifu para probar las plantillas (todas, con datos vacíos/pocos/muchos, en 6 anchos y 2 temas)
sin tocar el sistema que ya funciona. Solo lee los estilos y el logo de `../src`.

```bash
# desde la raíz del repo (usa los node_modules del proyecto, no instala nada)
npx vite --config laboratorio/vite.config.js
# → http://localhost:5190
```

- `src/plantillas/`: plantillas como datos (`semillas.js`), catálogo de vistas (`vistas.jsx`), validador (`validar.js`), datos de ejemplo y el renderizador.
- `src/lab/`: el panel del laboratorio y la vista que va dentro de cada iframe.
