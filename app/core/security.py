import secrets


def generate_invite_token() -> str:
    return secrets.token_urlsafe(24)


def mask_token(token: str) -> str:
    if len(token) < 8:
        return "***"
    return f"{token[:4]}…{token[-4:]}"
