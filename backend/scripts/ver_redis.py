import os
from dotenv import load_dotenv
import redis

load_dotenv()  # Carga variables de entorno desde .env

# Obtén la URL de Redis desde la variable de entorno
redis_url = os.getenv("REDIS_URL")
print("URL de Redis:", redis_url)

if not redis_url:
    print("❌ La variable de entorno REDIS_URL no está definida")
    exit(1)
# Conectar a Redis
try:
    r = redis.from_url(redis_url)
    if r.ping():
        print("✅ Conexión exitosa a Redis")
    else:
        print("❌ No se pudo conectar a Redis")
        exit(1)
except Exception as e:
    print("❌ Error al conectar a Redis:", e)
    exit(1)

# Listar todas las claves
keys = r.keys("*")  # todas las claves en Redis

for key in keys:
    tipo = r.type(key).decode()
    borrar = False

    if tipo == "string":
        value = r.get(key)
        if value and b"ecalcinap@unsa.edu.pe" in value:
            borrar = True
    elif tipo == "hash":
        value = r.hgetall(key)
        if any(b"ecalcinap@unsa.edu.pe" in v for v in value.values()):
            borrar = True
    elif tipo == "list":
        value = r.lrange(key, 0, -1)
        if any(b"ecalcinap@unsa.edu.pe" in v for v in value):
            borrar = True
    elif tipo == "set":
        value = r.smembers(key)
        if any(b"ecalcinap@unsa.edu.pe" in v for v in value):
            borrar = True
    elif tipo == "zset":
        value = r.zrange(key, 0, -1)
        if any(b"ecalcinap@unsa.edu.pe" in v for v, _ in value):
            borrar = True

    if borrar:
        r.delete(key)
        print(f"🗑️ Clave borrada: {key.decode() if isinstance(key, bytes) else key}")