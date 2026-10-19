import json,urllib.request,collections,sys
import os
CHAT = os.environ.get("BASE", "http://localhost:5190") + os.environ.get("RUTA_CHAT", "/api/lab/chat")  # D61: el mismo banco mide el laboratorio o el CRM
E={"vista":"inicio","bloques":[{"uid":"b0","vista":"kpis","seccion":"miembros","opciones":{"por":"estado"},"ancho":12,"alto":1},{"uid":"b1","vista":"vencimientos","seccion":"miembros","opciones":{"fecha":"vence","titulo":"nombre","dias":30},"ancho":6,"alto":2},{"uid":"b2","vista":"grafica","seccion":"miembros","opciones":{"tipo":"linea","fecha":"alta"},"ancho":6,"alto":2}]}
c=collections.Counter()
for i in range(int(sys.argv[1]) if len(sys.argv)>1 else 8):
  d=json.load(urllib.request.urlopen(urllib.request.Request(CHAT,data=json.dumps({"plantilla":"membresias","estado":E,"texto":"agrega una dona de los estados de los miembros"}).encode(),headers={"Content-Type":"application/json"}),timeout=120))
  c[tuple(x['herramienta'] for x in d['cambios'])]+=1
print(sys.argv[2] if len(sys.argv)>2 else '', dict(c))
