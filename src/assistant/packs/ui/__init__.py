"""Pack de UI: la interfaz de un solo archivo (index.html, sin build). La comparten los perfiles que no traen la suya;
traduce los mensajes en inglés del núcleo a etiquetas en español."""
from pathlib import Path

STATIC_DIR = Path(__file__).parent  # carpeta con index.html (AgentProfile.static_dir)
