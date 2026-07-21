from salecast.clients.d1_client import D1Connection, D1Row, D1Cursor


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, payload):
        self._payload = payload
        self.last_request = None

    def post(self, url, headers=None, json=None, timeout=None):
        self.last_request = json
        return _FakeResponse(self._payload)


def test_d1row_supports_key_and_index_access():
    row = D1Row({"app_id": 730, "name": "CS2"})
    assert row["app_id"] == 730
    assert row[0] == 730
    assert row["name"] == "CS2"
    assert row[1] == "CS2"


def test_d1cursor_fetchone_and_fetchall():
    cursor = D1Cursor(rowcount=2, rows=[{"app_id": 1}, {"app_id": 2}])
    assert cursor.rowcount == 2
    assert cursor.fetchone()["app_id"] == 1
    assert [row["app_id"] for row in cursor.fetchall()] == [1, 2]


def test_d1cursor_fetchone_empty():
    cursor = D1Cursor(rowcount=0, rows=[])
    assert cursor.fetchone() is None


def test_execute_batch_sends_single_request_and_sums_changes():
    session = _FakeSession(
        {
            "success": True,
            "result": [
                {"success": True, "results": [], "meta": {"changes": 1}},
                {"success": True, "results": [], "meta": {"changes": 1}},
            ],
        }
    )
    conn = D1Connection(account_id="a", database_id="b", api_token="c", session=session)

    total = conn.execute_batch(
        [
            ("INSERT INTO t VALUES (?)", (1,)),
            ("INSERT INTO t VALUES (?)", (2,)),
        ]
    )

    assert total == 2
    assert session.last_request == {
        "batch": [
            {"sql": "INSERT INTO t VALUES (?)", "params": [1]},
            {"sql": "INSERT INTO t VALUES (?)", "params": [2]},
        ]
    }


def test_execute_batch_returns_zero_for_empty_statements():
    conn = D1Connection(account_id="a", database_id="b", api_token="c", session=_FakeSession({}))
    assert conn.execute_batch([]) == 0


def test_execute_batch_raises_on_statement_failure():
    session = _FakeSession(
        {
            "success": True,
            "result": [{"success": False, "error": "boom"}],
        }
    )
    conn = D1Connection(account_id="a", database_id="b", api_token="c", session=session)

    try:
        conn.execute_batch([("INSERT INTO t VALUES (?)", (1,))])
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "boom" in str(exc)
