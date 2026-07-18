from app.core.security import generate_invite_token


class InvitationService:
    """Persistent Party invite abstraction, replaceable by PartyInvite later."""

    def new_token(self) -> str:
        return generate_invite_token()

    def deep_link(self, bot_username: str, token: str) -> str:
        username = bot_username.removeprefix("@")
        return f"https://t.me/{username}?start=join_{token}"
