class SessionManager:
    """
    Simple in-memory session store keyed by WhatsApp sender ID.
    Tracks each user's current state and collected data through a conversation flow.
    """

    def __init__(self):
        self._sessions: dict[str, dict] = {}

    def get(self, user_id: str) -> dict:
        if user_id not in self._sessions:
            self._sessions[user_id] = {"state": "IDLE", "data": {}}
        return self._sessions[user_id]

    def save(self, user_id: str, session: dict) -> None:
        self._sessions[user_id] = session

    def clear(self, user_id: str) -> None:
        self._sessions.pop(user_id, None)


# Singleton — imported and shared across all handlers
session_manager = SessionManager()
