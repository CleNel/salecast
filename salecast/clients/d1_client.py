"""Thin sqlite3-compatible shim over Cloudflare D1's HTTP query API.

D1Connection mimics the subset of sqlite3.Connection/Cursor used by
salecast.discovery and salecast.backfill (execute/commit, cursor.rowcount,
dict-style row access), so those modules can target D1 or local SQLite
interchangeably without any changes to their logic.
"""
import logging
from typing import Any, Sequence

import requests

from salecast import config

logger = logging.getLogger(__name__)

QUERY_URL = (
    "https://api.cloudflare.com/client/v4/accounts/{account_id}/d1/database/{database_id}/query"
)


class D1Row:
    """dict-or-tuple row access, mirroring sqlite3.Row (row["col"] and row[0] both work)."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data
        self._keys = list(data.keys())

    def __getitem__(self, key: str | int) -> Any:
        if isinstance(key, int):
            return self._data[self._keys[key]]
        return self._data[key]

    def keys(self) -> list[str]:
        return self._keys

    def __repr__(self) -> str:
        return f"D1Row({self._data!r})"


class D1Cursor:
    def __init__(self, rowcount: int, rows: list[dict[str, Any]]) -> None:
        self.rowcount = rowcount
        self._rows = [D1Row(row) for row in rows]

    def fetchall(self) -> list[D1Row]:
        return self._rows

    def fetchone(self) -> D1Row | None:
        return self._rows[0] if self._rows else None

    def __iter__(self):
        return iter(self._rows)


class D1Connection:
    """Executes one statement per HTTP request against D1's remote query API."""

    def __init__(
        self,
        account_id: str = config.CLOUDFLARE_ACCOUNT_ID,
        database_id: str = config.CLOUDFLARE_D1_DATABASE_ID,
        api_token: str = config.CLOUDFLARE_API_TOKEN,
        session: requests.Session | None = None,
    ) -> None:
        if not (account_id and database_id and api_token):
            raise RuntimeError(
                "CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_D1_DATABASE_ID, and CLOUDFLARE_API_TOKEN "
                "must all be set (see .env.example) to use D1Connection"
            )
        self._url = QUERY_URL.format(account_id=account_id, database_id=database_id)
        self._headers = {"Authorization": f"Bearer {api_token}"}
        self._session = session or requests.Session()

    def execute(self, sql: str, params: Sequence[Any] = ()) -> D1Cursor:
        response = self._session.post(
            self._url,
            headers=self._headers,
            json={"sql": sql, "params": list(params)},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("success"):
            raise RuntimeError(f"D1 query failed: {payload.get('errors')}")

        result = payload["result"][0]
        if not result.get("success", True):
            raise RuntimeError(f"D1 query failed: {result.get('error')}")

        rows = result.get("results") or []
        rowcount = result.get("meta", {}).get("changes", len(rows))
        return D1Cursor(rowcount=rowcount, rows=rows)

    def commit(self) -> None:
        """No-op: each execute() call is committed remotely by D1 immediately."""

    def close(self) -> None:
        self._session.close()
