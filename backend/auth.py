import hmac
import os

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

WEB_PASSWORD = os.environ["WEB_PASSWORD"]
SESSION_SECRET = os.environ["WEB_SESSION_SECRET"]

COOKIE_NAME = "kater_session"
SESSION_MAX_AGE = 90 * 24 * 3600  # 90 дней — свои устройства, не перелогиниваться каждый раз

_serializer = URLSafeTimedSerializer(SESSION_SECRET, salt="kater-session")


def check_password(password):
    # Сравнение постоянного времени — чтобы не утекало через тайминг.
    return hmac.compare_digest(password, WEB_PASSWORD)


def create_session_token():
    return _serializer.dumps({"owner": True})


def verify_session_token(token):
    if not token:
        return False

    try:
        data = _serializer.loads(token, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return False

    return bool(data.get("owner"))
