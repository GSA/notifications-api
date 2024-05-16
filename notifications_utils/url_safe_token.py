from itsdangerous import URLSafeTimedSerializer

from notifications_utils.formatters import url_encode_full_stops


def generate_token(payload, secret, salt):
    return url_encode_full_stops(URLSafeTimedSerializer(secret).dumps(payload, salt))


def check_token(token, secret, salt, max_age_seconds):
    ser = URLSafeTimedSerializer(secret)
    payload = ser.loads(token, max_age=max_age_seconds, salt=salt)
    return payload
