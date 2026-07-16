from salecast.clients import itad_client


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_get_price_history_parses_events(monkeypatch):
    monkeypatch.setattr(itad_client, "_require_api_key", lambda: "fake-key")
    monkeypatch.setattr(
        itad_client,
        "get_with_backoff",
        lambda session, url, params=None, retries=3: _FakeResponse(
            [
                {
                    "timestamp": "2026-06-18T19:18:26+02:00",
                    "shop": {"id": 61, "name": "Steam"},
                    "deal": {
                        "price": {"amount": 3.99, "amountInt": 399, "currency": "USD"},
                        "regular": {"amount": 39.99, "amountInt": 3999, "currency": "USD"},
                        "cut": 90,
                    },
                },
                {
                    "timestamp": "2020-01-01T00:00:00+01:00",
                    "shop": {"id": 61, "name": "Steam"},
                    "deal": {
                        "price": {"amount": 39.99, "amountInt": 3999, "currency": "USD"},
                        "regular": {"amount": 39.99, "amountInt": 3999, "currency": "USD"},
                        "cut": 0,
                    },
                },
            ]
        ),
    )

    history = itad_client.get_price_history("itad-id-42", since="2015-01-01T00:00:00Z")

    assert history == [
        {"date": "2026-06-18", "price": 3.99, "discount_pct": 90},
        {"date": "2020-01-01", "price": 39.99, "discount_pct": 0},
    ]


def test_get_price_history_returns_empty_list_when_no_response(monkeypatch):
    monkeypatch.setattr(itad_client, "_require_api_key", lambda: "fake-key")
    monkeypatch.setattr(
        itad_client, "get_with_backoff", lambda session, url, params=None, retries=3: None
    )

    assert itad_client.get_price_history("itad-id-42") == []


def test_get_price_history_skips_events_missing_price(monkeypatch):
    monkeypatch.setattr(itad_client, "_require_api_key", lambda: "fake-key")
    monkeypatch.setattr(
        itad_client,
        "get_with_backoff",
        lambda session, url, params=None, retries=3: _FakeResponse(
            [{"timestamp": "2020-01-01T00:00:00Z", "deal": {"price": {}, "cut": 0}}]
        ),
    )

    assert itad_client.get_price_history("itad-id-42") == []
