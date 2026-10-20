"""In-memory stand-in for the DB connection used by the route tests (no Postgres needed)."""

import re


class FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class FakeDb:
    """Holds rows for the tables a route reads.

    A query goes to the table named after its first FROM. Soft-deleted rows are dropped.
    Each named param filters the rows with the same column name (None means no filter).
    The `now` param applies the publish and expiry rule the SQL applies to `published_at`
    and `expires_at`. Rows are sorted by ORDER BY (ASC or DESC per column), then cut by
    OFFSET and LIMIT. The SQL text is checked separately in the tests, so a missing clause
    still fails.
    """

    SPECIAL_PARAMS = {"limit", "offset", "now"}

    def __init__(self, **tables):
        self.tables = tables
        self.queries = []
        self.params = []

    def execute(self, sql, params=None):
        params = params or {}
        self.queries.append(sql)
        self.params.append(params)
        table = re.search(r"FROM (\w+)", sql).group(1)
        rows = [row for row in self.tables.get(table, []) if row["deleted_at"] is None]
        for name, value in params.items():
            if name not in self.SPECIAL_PARAMS and value is not None:
                rows = [row for row in rows if row.get(name) == value]
        if params.get("now") is not None:
            rows = [row for row in rows if _is_live(row, params["now"])]
        order = re.search(r"ORDER BY ([^\n]+)", sql)
        if order:
            rows = _sort(rows, order.group(1))
        if params.get("offset"):
            rows = rows[params["offset"] :]
        if params.get("limit") is not None:
            rows = rows[: params["limit"]]
        return FakeCursor(rows)


def _is_live(row, now):
    if "published_at" not in row:
        return True
    return row["published_at"] <= now and (row["expires_at"] is None or row["expires_at"] > now)


def _sort(rows, order):
    # Sort by the least significant column first; each sort is stable.
    terms = [term.split() for term in order.split(",")]
    for column, *direction in reversed(terms):
        reverse = bool(direction) and direction[0].upper() == "DESC"
        key = column.split(".")[-1]
        rows = sorted(rows, key=lambda row: row[key], reverse=reverse)
    return rows
