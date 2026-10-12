"""
WhatsAppAdapter — normalizes WhatsApp Cloud API webhooks and sends replies.

Expects webhook payload in the standard Meta Cloud API format:
  {"entry": [{"changes": [{"value": {"messages": [{"from": "...", "type": "text",
   "text": {"body": "..."}, "id": "..."}]}}]}]}

Environment variables used:
  WHATSAPP_PHONE_NUMBER_ID — Cloud API phone number ID
  WHATSAPP_API_TOKEN       — Meta graph API access token
"""

import logging
import os
from typing import Optional

import httpx

from .base import ChannelAdapter

logger = logging.getLogger(__name__)

_WA_API_VERSION = "v18.0"


class WhatsAppAdapter(ChannelAdapter):
    channel_id = "whatsapp"

    def __init__(
        self,
        phone_number_id: str | None = None,
        api_token: str | None = None,
    ) -> None:
        self._phone_number_id = phone_number_id or os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
        self._api_token       = api_token       or os.getenv("WHATSAPP_API_TOKEN", "")
        self._send_url = (
            f"https://graph.facebook.com/{_WA_API_VERSION}"
            f"/{self._phone_number_id}/messages"
        )

    async def normalize(self, raw: dict) -> Optional[dict]:
        try:
            entry   = (raw.get("entry")   or [{}])[0]
            changes = (entry.get("changes") or [{}])[0]
            value   = changes.get("value", {})
            msgs    = value.get("messages", [])
            if not msgs:
                return None
            msg = msgs[0]
            if msg.get("type") != "text":
                return None  # skip media, reactions, etc.
            phone = msg.get("from", "")
            text  = (msg.get("text") or {}).get("body", "").strip()
            if not text:
                return None
            return {
                "user_id":         phone,
                "text":            text,
                "conversation_id": phone,  # phone = stable per-user conv_id
                "channel":         self.channel_id,
                "raw_message_id":  msg.get("id"),
            }
        except (KeyError, IndexError, TypeError) as exc:
            logger.warning("[WhatsAppAdapter] normalize error: %s", exc)
            return None

    async def reply(self, user_id: str, text: str, **kwargs) -> None:
        if not self._phone_number_id or not self._api_token:
            logger.warning("[WhatsAppAdapter] reply skipped — missing credentials")
            return
        payload = {
            "messaging_product": "whatsapp",
            "to":   user_id,
            "type": "text",
            "text": {"body": text[:4096]},  # WhatsApp max text length
        }
        headers = {
            "Authorization": f"Bearer {self._api_token}",
            "Content-Type":  "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(self._send_url, json=payload, headers=headers)
                resp.raise_for_status()
                logger.debug("[WhatsAppAdapter] sent to %s (%d chars)", user_id, len(text))
        except Exception as exc:
            logger.error("[WhatsAppAdapter] send failed to %s: %s", user_id, exc)
