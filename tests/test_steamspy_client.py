from salecast.clients import steamspy_client


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_get_app_stats_computes_review_score_pct(monkeypatch):
    monkeypatch.setattr(
        steamspy_client,
        "get_with_backoff",
        lambda session, url, params=None: _FakeResponse(
            {"appid": 730, "name": "Counter-Strike 2", "positive": 90, "negative": 10}
        ),
    )

    stats = steamspy_client.get_app_stats(730)

    assert stats == {"review_count": 100, "review_score_pct": 90.0}


def test_get_app_stats_returns_none_when_request_fails(monkeypatch):
    monkeypatch.setattr(
        steamspy_client, "get_with_backoff", lambda session, url, params=None: None
    )

    assert steamspy_client.get_app_stats(730) is None


def test_get_app_stats_returns_none_for_unknown_app(monkeypatch):
    monkeypatch.setattr(
        steamspy_client,
        "get_with_backoff",
        lambda session, url, params=None: _FakeResponse({"appid": 0, "name": None}),
    )

    assert steamspy_client.get_app_stats(999999999) is None


def test_get_app_stats_handles_zero_reviews(monkeypatch):
    monkeypatch.setattr(
        steamspy_client,
        "get_with_backoff",
        lambda session, url, params=None: _FakeResponse(
            {"appid": 1, "name": "New Game", "positive": 0, "negative": 0}
        ),
    )

    stats = steamspy_client.get_app_stats(1)

    assert stats == {"review_count": 0, "review_score_pct": None}
