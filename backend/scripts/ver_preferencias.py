from app.core.mongo import get_sync_database
import os
from dotenv import load_dotenv
import json
from bson import json_util

load_dotenv()

def ver_preferencias(correo):
    # Conectar a MongoDB
    db = get_sync_database()
    preferences_collection = db["memory_users_preferences"]
    
    # Buscar preferencias del usuario
    user_prefs = preferences_collection.find_one({"correo": correo.lower()})
    
    if not user_prefs:
        print(f"❌ No se encontraron preferencias para {correo}")
        return
    
    # Mostrar resultados
    print("\n" + "="*50)
    print(f"📧 CORREO: {user_prefs.get('correo')}")
    print("="*50)
    
    # Mostrar preferencias actuales
    preferencias = user_prefs.get('preferencias', {})
    if preferencias:
        print("\n📝 PREFERENCIAS ACTUALES:")
        for key, value in preferencias.items():
            print(f"  • {key}: {value}")
    else:
        print("\n📝 No hay preferencias guardadas")
    
    # Mostrar historial de cambios
    historial = user_prefs.get('historial', [])
    if historial:
        print("\n📜 HISTORIAL DE CAMBIOS:")
        for i, entry in enumerate(historial, 1):
            timestamp = entry.get('timestamp', '')
            if hasattr(timestamp, 'strftime'):
                timestamp = timestamp.strftime('%Y-%m-%d %H:%M:%S')
            print(f"  {i}. {entry.get('key')} = {entry.get('value')} ({timestamp})")
    
    # Mostrar fecha última actualización
    updated_at = user_prefs.get('updated_at')
    if updated_at and hasattr(updated_at, 'strftime'):
        print(f"\n⏰ Última actualización: {updated_at.strftime('%Y-%m-%d %H:%M:%S')}")
    
    print("\n" + "="*50)

if __name__ == "__main__":
    # Cambia este email por el tuyo
    correo = "ecalcinap@unsa.edu.pe"
    ver_preferencias(correo)