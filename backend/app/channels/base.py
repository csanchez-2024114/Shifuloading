from abc import ABC, abstractmethod
from typing import Optional


class ChannelAdapter(ABC):
    """
    Abstract base for incoming message channels (WebSocket, WhatsApp, etc.).

    Each adapter normalizes channel-specific payloads into a common dict and
    sends AI responses back through the same channel.

    Minimum required fields in normalize() output:
      user_id         — identifies the sender (JWT sub, phone number, etc.)
      text            — the user's message text
      conversation_id — thread identifier for LangGraph checkpointer
      channel         — channel_id string for routing/logging
    """

    channel_id: str  # unique name, e.g. "websocket", "whatsapp"

    @abstractmethod
    async def normalize(self, raw: dict) -> Optional[dict]:
        """
        Convert a raw channel payload to a normalized message dict.
        Return None to skip (e.g. delivery receipts, non-text messages).
        """

    @abstractmethod
    async def reply(self, user_id: str, text: str, **kwargs) -> None:
        """Send the AI response back to the user through this channel."""
