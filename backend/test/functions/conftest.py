"""Entorno de prueba aislado: valores falsos para que ninguna prueba dependa del .env real ni toque Mongo/OpenAI.

Debe correr antes de importar app.* (config.py y app.core.security fallan sin estas variables).
"""
import os

os.environ.setdefault("MONGO_URI", "mongodb://localhost:27099")  # puerto que no existe: ningun test usa Mongo real
os.environ.setdefault("MONGO_DB_NAME", "shifu_functions_test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-0123456789-abcdefghijklmnop")
os.environ.setdefault("ENCRYPTION_KEY", "test-encryption-key-not-a-real-secret")
os.environ.setdefault("ENCRYPTION_SALT", "test-salt")
os.environ.setdefault("SECRETS_ENCRYPTION_KEY", "test-secrets-key-not-a-real-secret")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ["REDIS_URL"] = ""  # el limitador de ritmo usa memoria; ninguna prueba toca Redis (el .env real si lo define)
