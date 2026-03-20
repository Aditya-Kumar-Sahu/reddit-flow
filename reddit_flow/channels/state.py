"""Conversation state helpers for messaging channels."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Set

from reddit_flow.models import ChannelSpec


@dataclass
class ConversationStateManager:
    """Track active jobs by channel, conversation, and user."""

    active_keys: Set[str] = field(default_factory=set)

    def build_key(self, channel: ChannelSpec) -> str:
        """Build a stable key from channel context."""
        conversation = channel.conversation_id or "unknown_conversation"
        user = channel.user_id or "unknown_user"
        return f"{channel.name}:{conversation}:{user}"

    def try_acquire(self, channel: ChannelSpec) -> bool:
        """Claim a conversation slot if it is not already active."""
        key = self.build_key(channel)
        if key in self.active_keys:
            return False
        self.active_keys.add(key)
        return True

    def release(self, channel: ChannelSpec) -> None:
        """Release a conversation slot."""
        self.active_keys.discard(self.build_key(channel))
