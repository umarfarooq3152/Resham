from types import SimpleNamespace
from uuid import uuid4

from resham import security


def test_access_token_round_trip(monkeypatch):
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(jwt_secret_key="secret", jwt_expiry_days=30),
    )
    user_id = uuid4()

    token = security.create_access_token(user_id)

    assert security.decode_access_token(token) == user_id


def test_decode_invalid_token_returns_none(monkeypatch):
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(jwt_secret_key="secret", jwt_expiry_days=30),
    )

    assert security.decode_access_token("not-a-token") is None
