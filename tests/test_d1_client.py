from salecast.clients.d1_client import D1Row, D1Cursor


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
