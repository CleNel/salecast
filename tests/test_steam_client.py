import pytest

from salecast.clients import steam_client


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("21 Dec, 2020", "2020-12-21"),
        ("Dec 21, 2020", "2020-12-21"),
        ("21 December 2020", "2020-12-21"),
        ("Dec 2020", "2020-12-01"),
        ("2020", "2020-01-01"),
    ],
)
def test_parse_release_date_known_formats(raw, expected):
    assert steam_client._parse_release_date(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "Coming soon", "not a date"])
def test_parse_release_date_unparseable_returns_none(raw):
    assert steam_client._parse_release_date(raw) is None


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _appdetails_payload(app_id, success=True, data=None):
    entry = {"success": success}
    if data is not None:
        entry["data"] = data
    return {str(app_id): entry}


def test_get_app_details_maps_discounted_game(monkeypatch):
    data = {
        "name": "Old Good Game",
        "type": "game",
        "genres": [{"description": "RPG"}],
        "publishers": ["Great Publisher"],
        "release_date": {"date": "21 Dec, 2020", "coming_soon": False},
        "price_overview": {"final": 999, "discount_percent": 50},
        "recommendations": {"total": 12000},
    }
    monkeypatch.setattr(
        steam_client, "get_with_backoff",
        lambda session, url, params=None, retries=3: _FakeResponse(_appdetails_payload(42, data=data)),
    )

    details = steam_client.get_app_details(42)

    assert details == {
        "app_id": 42,
        "name": "Old Good Game",
        "type": "game",
        "genre": "RPG",
        "publisher": "Great Publisher",
        "release_date": "2020-12-21",
        "is_released": True,
        "price": 9.99,
        "discount_pct": 50,
        "review_count": 12000,
    }


def test_get_app_details_handles_free_game_with_no_price_overview(monkeypatch):
    data = {
        "name": "Free Game",
        "type": "game",
        "genres": [],
        "publishers": [],
        "release_date": {"date": "2020", "coming_soon": False},
        "recommendations": {},
    }
    monkeypatch.setattr(
        steam_client, "get_with_backoff",
        lambda session, url, params=None, retries=3: _FakeResponse(_appdetails_payload(7, data=data)),
    )

    details = steam_client.get_app_details(7)

    assert details["price"] is None
    assert details["discount_pct"] is None
    assert details["genre"] is None
    assert details["publisher"] is None
    assert details["review_count"] is None


def test_get_app_details_marks_unreleased_coming_soon_game(monkeypatch):
    data = {
        "name": "Unannounced",
        "type": "game",
        "release_date": {"date": "", "coming_soon": True},
    }
    monkeypatch.setattr(
        steam_client, "get_with_backoff",
        lambda session, url, params=None, retries=3: _FakeResponse(_appdetails_payload(1, data=data)),
    )

    details = steam_client.get_app_details(1)

    assert details["is_released"] is False
    assert details["release_date"] is None


def test_get_app_details_returns_none_when_entry_not_successful(monkeypatch):
    monkeypatch.setattr(
        steam_client, "get_with_backoff",
        lambda session, url, params=None, retries=3: _FakeResponse(
            _appdetails_payload(1, success=False)
        ),
    )

    assert steam_client.get_app_details(1) is None


def test_get_app_details_returns_none_when_no_data(monkeypatch):
    monkeypatch.setattr(
        steam_client, "get_with_backoff",
        lambda session, url, params=None, retries=3: _FakeResponse(_appdetails_payload(1)),
    )

    assert steam_client.get_app_details(1) is None


def test_get_app_details_returns_none_when_request_exhausted(monkeypatch):
    monkeypatch.setattr(
        steam_client, "get_with_backoff",
        lambda session, url, params=None, retries=3: None,
    )

    assert steam_client.get_app_details(1) is None


def test_get_app_details_returns_none_on_malformed_json(monkeypatch):
    class _BadResponse:
        def json(self):
            raise ValueError("not json")

    monkeypatch.setattr(
        steam_client, "get_with_backoff",
        lambda session, url, params=None, retries=3: _BadResponse(),
    )

    assert steam_client.get_app_details(1) is None
