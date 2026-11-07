import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

# Официальный алгоритм проверки initData Telegram Mini Apps:
# https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
MAX_AUTH_AGE_SECONDS = 24 * 3600


def verify_init_data(init_data_raw, bot_token):
    pairs = parse_qsl(init_data_raw, keep_blank_values=True)

    received_hash = None
    data_pairs = []

    for key, value in pairs:
        if key == "hash":
            received_hash = value
        else:
            data_pairs.append((key, value))

    if not received_hash:
        return None

    data_check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(data_pairs)
    )

    secret_key = hmac.new(
        b"WebAppData", bot_token.encode(), hashlib.sha256
    ).digest()

    expected_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_hash, received_hash):
        return None

    data = dict(data_pairs)

    auth_date = data.get("auth_date")

    if not auth_date or time.time() - int(auth_date) > MAX_AUTH_AGE_SECONDS:
        return None

    user_raw = data.get("user")

    if not user_raw:
        return None

    try:
        user = json.loads(user_raw)
    except ValueError:
        return None

    return user
