from itsdangerous import URLSafeTimedSerializer
from flask import current_app


def _serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


def generate_token(payload: str, salt: str) -> str:
    return _serializer().dumps(payload, salt=salt)


def verify_token(token: str, salt: str, max_age_seconds: int):
    try:
        return _serializer().loads(token, salt=salt, max_age=max_age_seconds)
    except Exception:
        return None
