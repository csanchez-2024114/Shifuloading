"""
youtube_transcript — agente_v3

Detección determinística de links de YouTube en el texto del usuario +
obtención de su transcripción (subtítulos), tratada como cualquier documento
largo de texto por document_analyzer.py (cachea, trocea si excede el umbral,
etc.). NO hace análisis de frames/video, solo transcripción.

API verificada contra youtube-transcript-api==1.2.4 (instance-based en v1.x,
distinta al viejo YouTubeTranscriptApi.get_transcript() classmethod de v0.x):
  YouTubeTranscriptApi().fetch(video_id, languages=[...]) -> FetchedTranscript
  (iterable de FetchedTranscriptSnippet con .text/.start/.duration).
"""

import hashlib
import logging
import re

from youtube_transcript_api import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
    YouTubeTranscriptApi,
)

logger = logging.getLogger(__name__)

# Cubre youtube.com/watch?v=ID, youtu.be/ID, youtube.com/shorts/ID,
# youtube.com/embed/ID — con o sin parámetros adicionales (&t=30s, etc.)
_YOUTUBE_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?"
    r"(?:youtube\.com/(?:watch\?v=|shorts/|embed/)|youtu\.be/)"
    r"([A-Za-z0-9_-]{11})"
)

_TRANSCRIPT_LANGUAGES = ["es", "en"]

_api = YouTubeTranscriptApi()


def find_youtube_video_ids(text: str) -> list[str]:
    """Devuelve los video_ids (deduplicados, en orden de aparición) de todos
    los links de YouTube encontrados en el texto. Lista vacía si no hay ninguno."""
    if not text:
        return []
    seen: list[str] = []
    for match in _YOUTUBE_URL_RE.finditer(text):
        vid = match.group(1)
        if vid not in seen:
            seen.append(vid)
    return seen


def file_id_for_youtube(video_id: str) -> str:
    """file_id estable por video_id (no por URL completa), para que distintas
    variantes de link (watch?v=X&t=30s, youtu.be/X) deduplique al mismo id."""
    return "yt_" + hashlib.sha256(video_id.encode("utf-8")).hexdigest()[:24]


def fetch_youtube_transcript(video_id: str) -> dict:
    """Obtiene la transcripción de un video de YouTube. Nunca lanza — mismo
    shape que FileProvider.get_text_and_meta(): {"text", "engine",
    "page_count", "ocr_used", "error"}."""
    try:
        fetched = _api.fetch(video_id, languages=_TRANSCRIPT_LANGUAGES)
        text = " ".join(snippet.text for snippet in fetched if snippet.text)
        return {"text": text, "engine": "youtube_transcript", "page_count": None,
                "ocr_used": False, "error": None}
    except (NoTranscriptFound, TranscriptsDisabled) as e:
        logger.info("[youtube_transcript] sin subtítulos disponibles video_id=%s: %s", video_id, e)
        return {"text": "", "engine": "youtube_transcript", "page_count": None,
                "ocr_used": False, "error": "no_transcript_available"}
    except VideoUnavailable as e:
        logger.info("[youtube_transcript] video no disponible video_id=%s: %s", video_id, e)
        return {"text": "", "engine": "youtube_transcript", "page_count": None,
                "ocr_used": False, "error": "video_unavailable"}
    except Exception as e:
        logger.error("[youtube_transcript] error inesperado video_id=%s: %s", video_id, e)
        return {"text": "", "engine": "youtube_transcript", "page_count": None,
                "ocr_used": False, "error": f"transcript_failed: {e}"}
