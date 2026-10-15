"""Thin, purpose-built layer over the FalkorDB Python client.

FalkorDB stores a property graph under a named key inside Redis. One instance can
hold thousands of isolated graphs, so BatchZero gives every agency tenant its own
graph and passes the tenant graph name through this module everywhere.

Everything the agent does — reads, algorithm calls, writes, provenance logging —
goes through ``GraphDB``. There is deliberately no ORM and no cache: the whole
point of the project is that every answer is a live traversal.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from falkordb import FalkorDB

from .config import get_settings


@dataclass
class QueryResult:
    """A normalized Cypher result: rows as dicts + query telemetry."""

    columns: list[str]
    rows: list[dict[str, Any]]
    ms: float
    graph: str
    query: str
    raw_meta: list[Any] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.rows)

    def first(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None

    def scalars(self, column: str) -> list[Any]:
        return [r.get(column) for r in self.rows]


class GraphDB:
    """Connection + query helper bound to one tenant graph."""

    _client: FalkorDB | None = None

    def __init__(self, graph_name: str | None = None) -> None:
        settings = get_settings()
        self.settings = settings
        self.graph_name = graph_name or settings.tenant_graph
        if GraphDB._client is None:
            kwargs: dict[str, Any] = {
                "host": settings.falkordb_host,
                "port": settings.falkordb_port,
            }
            if settings.falkordb_password:
                kwargs["password"] = settings.falkordb_password
            GraphDB._client = FalkorDB(**kwargs)
        self.client = GraphDB._client
        self.graph = self.client.select_graph(self.graph_name)

    # ------------------------------------------------------------------ queries
    def query(self, cypher: str, params: dict[str, Any] | None = None) -> QueryResult:
        start = time.perf_counter()
        res = self.graph.query(cypher, params or {})
        ms = (time.perf_counter() - start) * 1000.0
        return self._normalize(res, cypher, ms)

    def ro_query(self, cypher: str, params: dict[str, Any] | None = None) -> QueryResult:
        """Server-side read-only query (FalkorDB rejects writes)."""
        start = time.perf_counter()
        res = self.graph.ro_query(cypher, params or {})
        ms = (time.perf_counter() - start) * 1000.0
        return self._normalize(res, cypher, ms)

    def _normalize(self, res: Any, cypher: str, ms: float) -> QueryResult:
        # FalkorDB returns header as [[type_code, name], ...]; flatten to names.
        header = list(getattr(res, "header", None) or [])
        columns = [
            (h[1] if isinstance(h, (list, tuple)) and len(h) >= 2 else h) for h in header
        ]
        raw = getattr(res, "result_set", None) or []
        rows: list[dict[str, Any]] = []
        for record in raw:
            row: dict[str, Any] = {}
            for idx, col in enumerate(columns):
                row[col] = _serialize(record[idx]) if idx < len(record) else None
            rows.append(row)
        meta = getattr(res, "metadata", None)
        return QueryResult(
            columns=columns,
            rows=rows,
            ms=ms,
            graph=self.graph_name,
            query=cypher,
            raw_meta=[meta] if meta else [],
        )

    # ------------------------------------------------------------------ helpers
    def ping(self) -> bool:
        try:
            self.client.connection.ping()  # type: ignore[attr-defined]
            return True
        except Exception:
            try:
                self.graph.ro_query("RETURN 1")
                return True
            except Exception:
                return False

    def list_graphs(self) -> list[str]:
        return list(self.client.list())

    def delete_graph(self) -> None:
        try:
            self.graph.delete()
        except Exception:
            pass

    def node_count(self) -> int:
        return int(self.query("MATCH (n) RETURN count(n) AS c").first()["c"])  # type: ignore[index]

    def rel_count(self) -> int:
        return int(
            self.query("MATCH ()-[r]->() RETURN count(r) AS c").first()["c"]  # type: ignore[index]
        )

    def stats(self) -> dict[str, Any]:
        return {
            "graph": self.graph_name,
            "nodes": self.node_count(),
            "relationships": self.rel_count(),
        }


# ----------------------------------------------------------------- serialization
def _serialize(value: Any) -> Any:
    """Convert FalkorDB result objects into JSON-friendly Python values.

    Nodes and edges become plain dicts carrying an ``_id``-style key so the
    frontend can address them, and temporal values become ISO strings.
    """
    import datetime as _dt

    from falkordb.node import Node
    from falkordb.edge import Edge

    if isinstance(value, (_dt.date, _dt.datetime, _dt.time)):
        return value.isoformat()

    if isinstance(value, Node):
        return {
            "_type": "node",
            "id": value.id,
            "labels": list(value.labels),
            **{k: _serialize(v) for k, v in (value.properties or {}).items()},
        }
    if isinstance(value, Edge):
        return {
            "_type": "edge",
            "id": value.id,
            "type": value.relation,
            "src": value.src_node,
            "dst": value.dest_node,
            **{k: _serialize(v) for k, v in (value.properties or {}).items()},
        }
    if isinstance(value, (list, tuple)):
        return [_serialize(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    if hasattr(value, "iso_format"):
        return value.iso_format()
    if hasattr(value, "to_iso8601"):
        return value.to_iso8601()
    if hasattr(value, "__str__") and type(value).__module__.startswith("falkordb"):
        return str(value)
    return value


def graph_for(tenant: str | None = None) -> GraphDB:
    return GraphDB(tenant or get_settings().tenant_graph)
