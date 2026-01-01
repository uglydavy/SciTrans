"""
Multi-User Session Management

Provides session isolation for multi-user deployments.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class UserSession:
    """Represents a user session."""

    user_id: str
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_activity: datetime = field(default_factory=datetime.utcnow)
    output_dir: Path = field(init=False)
    cache_dir: Path = field(init=False)

    def __post_init__(self):
        base_dir = Path("sessions") / self.user_id / self.session_id
        self.output_dir = base_dir / "outputs"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir = base_dir / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def update_activity(self):
        """Update last activity timestamp."""
        self.last_activity = datetime.utcnow()

    def is_expired(self, timeout_minutes: int = 60) -> bool:
        """Check if session has expired."""
        return datetime.utcnow() - self.last_activity > timedelta(minutes=timeout_minutes)


class SessionManager:
    """Manages user sessions."""

    def __init__(self, session_timeout_minutes: int = 60):
        self.sessions: dict[str, UserSession] = {}
        self.session_timeout = session_timeout_minutes

    def create_session(self, user_id: str) -> UserSession:
        """Create a new session for a user."""
        session = UserSession(user_id=user_id)
        self.sessions[session.session_id] = session
        logger.info(f"Created session {session.session_id} for user {user_id}")
        return session

    def get_session(self, session_id: str) -> UserSession | None:
        """Get session by ID."""
        session = self.sessions.get(session_id)
        if session:
            session.update_activity()
        return session

    def cleanup_expired(self) -> int:
        """Remove expired sessions."""
        expired = [
            sid
            for sid, session in self.sessions.items()
            if session.is_expired(self.session_timeout)
        ]

        for sid in expired:
            del self.sessions[sid]
            logger.debug(f"Removed expired session: {sid}")

        return len(expired)

    def get_user_sessions(self, user_id: str) -> list[UserSession]:
        """Get all sessions for a user."""
        return [s for s in self.sessions.values() if s.user_id == user_id]
