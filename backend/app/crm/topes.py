"""Los topes de tamaño del CRM, en un solo lugar (punto 48).

Valen para los dos caminos que cambian la estructura: el de Carlos (`estructura`, `operaciones`) y el del modo diseño (`edicion`,
herramientas del chat), y para la siembra de plantillas (`sembrar`). Cada módulo los toma de aquí; los nombres viejos
(`estructura.MAX_CAMPOS`, `edicion.MAX_CAMPOS_SECCION`…) siguen existiendo como alias para no romper a quien los lea.

Por qué cada valor:
- CAMPOS_POR_SECCION = 20: antes había dos (15 en `estructura`, 8 en el modo diseño). Con 8, en la prueba manual del 19-oct el chat
  tuvo que quitar «Técnico» a un taller para poder agregar «Estado». Un solo tope, el mismo para secciones propias y campos extra de
  clientes.
- SECCIONES_PROPIAS = 12, REGISTROS_POR_SECCION = 2000, CONTACTOS = 5000: sin cambio. Existen porque todo el CRM vive en un solo
  documento de Mongo (límite de 16 MB); se revisan cuando se mida el peso real con datos (puntos 42 y 48 de la lista del 19-oct).
"""

SECCIONES_PROPIAS = 12
CAMPOS_POR_SECCION = 20
REGISTROS_POR_SECCION = 2000
CONTACTOS = 5000
