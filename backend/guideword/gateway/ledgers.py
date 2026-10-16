"""The two spend ledgers (PROJECT.md §7, §11 hosting; decision 2026-10-11).

The laptop ledger is `budget/ledger.jsonl` (git-ignored); the hosted ledger is the
`spend_ledger` table, because the hosted filesystem is read-only. Each enforces only its own
environment's allowances and never reads the other; the weekly dashboard check reconciles
them.
"""

import threading
from pathlib import Path
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from guideword.runs.db import SpendLedgerRow
from guideword.schema import ids
from guideword.schema.enums import BudgetUse, Environment
from guideword.schema.records import SpendEntry
from guideword.settings import Settings

DEFAULT_LEDGER = Path(__file__).resolve().parents[3] / "budget" / "ledger.jsonl"


class Ledger(Protocol):
    environment: Environment

    def entries(self) -> list[SpendEntry]: ...

    def append(self, entry: SpendEntry) -> None: ...

    def spent(self, *, phase: str | None = None, use: BudgetUse | str | None = None) -> float: ...


def _spent(
    entries: list[SpendEntry],
    environment: Environment,
    phase: str | None,
    use: BudgetUse | str | None,
) -> float:
    return sum(
        e.cost_usd
        for e in entries
        if e.environment == environment
        and (phase is None or e.phase == phase)
        and (use is None or e.use == use)
    )


class LaptopLedger:
    """The laptop ledger: one SpendEntry per line. Every limit check reads it."""

    environment = Environment.LAPTOP

    def __init__(self, path: Path = DEFAULT_LEDGER) -> None:
        self.path = path
        self._lock = threading.Lock()

    def entries(self) -> list[SpendEntry]:
        """Every complete line. Reads take the append lock; and since every append ends with a
        newline, an unterminated last line can only be a write in progress (from another
        process, or another ledger object on the same file): it is skipped, never parsed."""
        with self._lock:
            if not self.path.exists():
                return []
            text = self.path.read_text(encoding="utf-8")
        complete, _, _unfinished = text.rpartition("\n")
        return [
            SpendEntry.model_validate_json(line) for line in complete.split("\n") if line.strip()
        ]

    def append(self, entry: SpendEntry) -> None:
        if entry.environment != self.environment:
            raise ValueError(f"the laptop ledger takes laptop entries, not {entry.environment}")
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8", newline="\n") as f:
                f.write(entry.model_dump_json() + "\n")

    def spent(self, *, phase: str | None = None, use: BudgetUse | str | None = None) -> float:
        """Laptop spend, optionally for one phase or one use."""
        return _spent(self.entries(), self.environment, phase, use)


class HostedLedger:
    """The hosted ledger: the `spend_ledger` table. It reads only hosted entries."""

    environment = Environment.HOSTED

    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions
        self._lock = threading.Lock()

    def entries(self) -> list[SpendEntry]:
        with self._sessions() as session:
            rows = session.scalars(
                select(SpendLedgerRow).where(SpendLedgerRow.environment == self.environment.value)
            ).all()
            entries = [SpendEntry.model_validate(r.record) for r in rows]
        return sorted(entries, key=lambda e: (e.ts, e.purpose))

    def append(self, entry: SpendEntry) -> None:
        if entry.environment != self.environment:
            raise ValueError(f"the hosted ledger takes hosted entries, not {entry.environment}")
        dumped = entry.model_dump(mode="json")
        with self._lock, self._sessions.begin() as session:
            session.merge(
                SpendLedgerRow(key=ids.h(dumped), environment=self.environment.value, record=dumped)
            )

    def spent(self, *, phase: str | None = None, use: BudgetUse | str | None = None) -> float:
        return _spent(self.entries(), self.environment, phase, use)


def ledger_for(
    settings: Settings, sessions: sessionmaker[Session], path: Path = DEFAULT_LEDGER
) -> Ledger:
    """The ledger of this environment (`settings.guideword_env`)."""
    if Environment(settings.guideword_env) == Environment.HOSTED:
        return HostedLedger(sessions)
    return LaptopLedger(path)
