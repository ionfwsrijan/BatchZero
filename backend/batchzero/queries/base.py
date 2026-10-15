"""Query helpers shared by every BatchZero read/write.

Every function in the ``queries`` package returns a :class:`QueryOutcome` that
carries not just the rows but the *Cypher that produced them* and, where a graph
algorithm was involved, which algorithm ran. That provenance is what the agent
writes back into the graph as evidence, so an investigator can always replay the
exact traversal behind a claim.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from ..db import GraphDB

# Ceiling of the incubation window, in days, per pathogen. Used to bound the
# temporal-fit query. Real CDC guidance lives in schema.INCUBATION_WINDOWS (hours);
# here we keep a day-granularity ceiling because meals are recorded as dates.
MAX_INCUBATION_DAYS = {
    "Salmonella": 3,
    "Norovirus": 3,
    "E. coli O157:H7": 10,
    "Listeria": 28,
}
DEFAULT_MAX_INCUBATION_DAYS = 7


@dataclass
class QueryOutcome:
    """A traced query result: rows + the traversal that produced them."""

    rows: list[dict[str, Any]]
    columns: list[str]
    cypher: str
    params: dict[str, Any] = field(default_factory=dict)
    ms: float = 0.0
    graph: str = ""
    algorithm: str | None = None
    title: str = ""

    def __len__(self) -> int:
        return len(self.rows)

    def first(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None

    def scalars(self, column: str) -> list[Any]:
        return [r.get(column) for r in self.rows]

    def digest(self, max_rows: int = 8) -> str:
        """Compact, LLM-friendly rendering used for tool-call logs and evidence."""
        head = f"{self.title or 'query'} [{len(self.rows)} rows, {self.ms:.1f}ms]"
        if self.algorithm:
            head += f" via {self.algorithm}"
        if not self.rows:
            return head + " -> no rows"
        lines = [head]
        for row in self.rows[:max_rows]:
            compact = ", ".join(f"{k}={_fmt(v)}" for k, v in row.items())
            lines.append("  - " + compact)
        if len(self.rows) > max_rows:
            lines.append(f"  … {len(self.rows) - max_rows} more rows")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "columns": self.columns,
            "rows": self.rows,
            "ms": round(self.ms, 3),
            "graph": self.graph,
            "algorithm": self.algorithm,
            "cypher": self.cypher,
            "params": self.params,
        }


def _fmt(value: Any) -> str:
    if isinstance(value, str) and len(value) > 60:
        return value[:57] + "…"
    if isinstance(value, list):
        return "[" + ", ".join(str(v) for v in value[:4]) + ("]" if len(value) <= 4 else " …]")
    return str(value)


def run_read(
    db: GraphDB,
    title: str,
    cypher: str,
    params: dict[str, Any] | None = None,
    algorithm: str | None = None,
) -> QueryOutcome:
    """Execute a read-only Cypher query and package it as an outcome."""
    res = db.ro_query(cypher, params or {})
    return QueryOutcome(
        rows=res.rows,
        columns=res.columns,
        cypher=cypher,
        params=params or {},
        ms=res.ms,
        graph=res.graph,
        algorithm=algorithm,
        title=title,
    )


def run_write(
    db: GraphDB,
    title: str,
    cypher: str,
    params: dict[str, Any] | None = None,
) -> QueryOutcome:
    """Execute a write Cypher query (still returns any produced rows)."""
    res = db.query(cypher, params or {})
    return QueryOutcome(
        rows=res.rows,
        columns=res.columns,
        cypher=cypher,
        params=params or {},
        ms=res.ms,
        graph=res.graph,
        title=title,
    )


def incubation_window(pathogen: str) -> tuple[int, int]:
    """Return (min_days, max_days) ceiling for a pathogen's incubation window."""
    max_days = MAX_INCUBATION_DAYS.get(pathogen, DEFAULT_MAX_INCUBATION_DAYS)
    return 0, max_days


def onset_window(onset_iso: str, pathogen: str) -> tuple[str, str]:
    """Compute the exposure date-range [min_date, onset] for a case.

    Because meals are recorded at day granularity and FalkorDB has no date
    subtraction, we compute the lower bound in Python and pass both bounds as
    ``date($param)`` into Cypher. A meal is a temporally-plausible exposure iff
    ``min_date <= meal_date <= onset`` — which also excludes meals recorded
    *after* onset (the temporal trap).
    """
    _, max_days = incubation_window(pathogen)
    onset = date.fromisoformat(onset_iso)
    min_date = onset - timedelta(days=max_days)
    return min_date.isoformat(), onset.isoformat()
