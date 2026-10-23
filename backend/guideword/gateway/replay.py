"""Replay fixtures (spec 2.9; plan R30, R45).

`export_replay` writes every response a run used to `bench/replay/<case>/<cache key>.json`,
plus a manifest with the run's ranked list, its whole-plant hypotheses with their question
links, the hybrid tiered lines, where the run stopped (R50, G10) and, from Phase 3, its chains
(ID, links), LOPA records (ID, gap) and recommendations (ID) (plan Q18). `load_replay` puts them
back into a response cache, and `ReplayTransport` stands in for Token Factory: it lists the
recorded models and raises `ReplayMiss` on any send, so a replay is served only from the
fixtures and a missing one fails loudly instead of calling out. Each response keeps its
stored cost, so a replay counts against its cap what the original did. From Phase 4 the run's
web searches travel with them, keyed from its `web_research` tool calls (`ReplaySearch`).
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from guideword.config import CapsConfig
from guideword.gateway.cache import ResponseCache
from guideword.gateway.transport import Reply
from guideword.ranking.rank import rank_findings
from guideword.ranking.tiers import lead_prefers_own_section, tiered
from guideword.reference import ReferenceSet
from guideword.runs.store import RunRepository
from guideword.schema.enums import AgentTool
from guideword.schema.plant import Plant
from guideword.schema.records import ToolCall

MANIFEST = "manifest.json"
# fixture files use LF line endings (CLAUDE.md §10)
LF = "\n"
CALL_PREFIX = "mc:"


def search_keys(tool_calls: Sequence[ToolCall]) -> set[str]:
    """The cache keys of a run's sent web searches (Phase 4 plan G18): each `web_research`
    tool call records its key, so the export writes the Tavily response with the models'."""
    return {
        call.result["cache_key"]
        for call in tool_calls
        if call.tool == AgentTool.WEB_RESEARCH
        and call.refused_reason is None
        and isinstance(call.result, dict)
        and isinstance(call.result.get("cache_key"), str)
    }


class ReplayMiss(RuntimeError):
    """A request with no fixture: the replay differs from the recorded run."""


@dataclass(frozen=True)
class Manifest:
    run_id: str
    case: str
    # the plant file, relative to the repo root
    plant_file: str
    status: str
    models: list[str]
    keys: list[str]
    # [finding ID, rating, frequency per year] in rank order
    ranked: list[list[Any]]
    spent_usd: float
    cap_spent_usd: float
    # R50 (G10): the step the run stopped at; [hypothesis ID, rank, question IDs] in rank
    # order; [tier, hypothesis ID or None, lead finding ID or None] in display order
    step: str = ""
    hypotheses: list[list[Any]] = field(default_factory=list)
    tiered: list[list[Any]] = field(default_factory=list)
    # Phase 3 (Q18): [chain ID, links]; [LOPA record ID, gap]; recommendation IDs
    chains: list[list[Any]] = field(default_factory=list)
    lopa: list[list[Any]] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    # Phase 4 (spec 4.4): [evidence ID, verdict]
    evidence: list[list[Any]] = field(default_factory=list)
    # unrecorded attempts (pre-fix): cache entries a replay needs that the run's records
    # missed, from before the refused-retry fix (2026-10-22); loaded like `keys`
    unrecorded_attempts: list[str] = field(default_factory=list)


class ReplayTransport:
    def __init__(self, manifest: Manifest) -> None:
        self._models = list(manifest.models)

    def models(self) -> list[dict[str, Any]]:
        return [{"id": m, "shutdown_date": ""} for m in self._models]

    def send(self, job: str, request: dict[str, Any]) -> Reply:
        raise ReplayMiss(f"no replay fixture for a {job} call to {request.get('model')}")


def _dump(value: Any) -> str:
    return json.dumps(value, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def export_replay(
    runs: RunRepository,
    cache: ResponseCache,
    run_id: str,
    out_dir: Path,
    *,
    plant: Plant,
    plant_file: str,
    ref: ReferenceSet,
    caps: CapsConfig,
    secrets: Sequence[str],
    case: str | None = None,
) -> Path:
    """Write the run's fixtures to `out_dir`, replacing any there. Nothing is written if a
    response holds one of `secrets` (the configured API keys)."""
    run = runs.get(run_id)
    if run is None:
        raise LookupError(f"no run {run_id}")
    calls = runs.model_calls(run_id)
    keys = sorted(
        {c.id.removeprefix(CALL_PREFIX) for c in calls} | search_keys(runs.tool_calls(run_id))
    )
    files: dict[str, str] = {}
    for key in keys:
        entry = cache.entry(key)
        if entry is None:
            raise LookupError(f"the run used cache entry {key}, which is not in the cache")
        model_id, prompt_version, response = entry
        files[f"{key}.json"] = _dump(
            {
                "key": key,
                "model_id": model_id,
                "prompt_version": prompt_version,
                "response": response,
            }
        )
    findings = runs.findings(run_id)
    hypotheses = runs.hypotheses(run_id)
    ranked = rank_findings(findings, plant, ref, caps)
    lines = tiered(
        ranked,
        hypotheses,
        findings,
        runs.questions(run_id),
        sections=runs.sections(run_id),
        prefer_own_section=lead_prefers_own_section(run.caps, runs.events(run_id)),
    )
    manifest = {
        "run_id": run.id,
        "case": case or plant.plant_id,
        "plant_file": plant_file,
        "status": run.status.value,
        "models": sorted({c.model_id for c in calls}),
        "keys": keys,
        "ranked": [[r.finding.id, r.rating, r.likelihood.frequency_per_year] for r in ranked],
        "spent_usd": run.spent_usd,
        "cap_spent_usd": run.cap_spent_usd,
        "step": run.step,
        "hypotheses": [
            [h.id, h.rank, list(h.question_ids)]
            for h in sorted(hypotheses, key=lambda h: (h.rank, h.id))
        ],
        "tiered": [
            [
                line.tier.value,
                line.hypothesis.id if line.hypothesis else None,
                line.lead.finding.id if line.lead else None,
            ]
            for line in lines
        ],
        "chains": [[c.id, list(c.links)] for c in runs.chains(run_id)],
        "lopa": [[r.id, r.gap] for r in runs.lopa_records(run_id)],
        "recommendations": [r.id for r in runs.recommendations(run_id)],
        "evidence": [[e.id, e.verdict.value] for e in runs.evidence(run_id)],
    }
    files[MANIFEST] = _dump(manifest)
    live = [s for s in secrets if s]
    for name, text in files.items():
        if any(secret in text for secret in live):
            raise ValueError(f"{name} holds a configured API key; nothing was written")
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.json"):
        old.unlink()
    for name, text in files.items():
        (out_dir / name).write_text(text, encoding="utf-8", newline="\n")
    return out_dir


def load_replay(fixtures: Path, sessions: sessionmaker[Session]) -> Manifest:
    """Put the fixtures into this store's response cache and return the manifest."""
    data = json.loads((fixtures / MANIFEST).read_text(encoding="utf-8"))
    manifest = Manifest(**data)
    cache = ResponseCache(sessions)
    for key in [*manifest.keys, *manifest.unrecorded_attempts]:
        path = fixtures / f"{key}.json"
        if not path.exists():
            continue  # its request then misses, and the replay fails on it
        entry = json.loads(path.read_text(encoding="utf-8"))
        if entry["key"] != key:
            raise ValueError(f"{path.name} holds entry {entry['key']}")
        cache.put_entry(key, entry["model_id"], entry["prompt_version"], entry["response"])
    return manifest


def add_unrecorded_attempts(
    out_dir: Path, cache: ResponseCache, keys: Sequence[str], *, secrets: Sequence[str]
) -> list[str]:
    """Add cache entries a run used but did not record to its fixtures, unchanged, and list
    them in the manifest as `unrecorded_attempts` (runs stored before the refused-retry fix,
    2026-10-22). A key not in the cache, or already in the fixtures, is refused; nothing is
    written if an entry holds one of `secrets`."""
    manifest_path = out_dir / MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    known = {*manifest["keys"], *manifest.get("unrecorded_attempts", [])}
    files: dict[str, str] = {}
    for key in keys:
        if key in known:
            raise ValueError(f"cache entry {key} is already in the fixtures")
        entry = cache.entry(key)
        if entry is None:
            raise LookupError(f"cache entry {key} is not in the cache")
        model_id, prompt_version, response = entry
        files[f"{key}.json"] = _dump(
            {
                "key": key,
                "model_id": model_id,
                "prompt_version": prompt_version,
                "response": response,
            }
        )
    live = [s for s in secrets if s]
    for name, text in files.items():
        if any(secret in text for secret in live):
            raise ValueError(f"{name} holds a configured API key; nothing was written")
    for name, text in files.items():
        (out_dir / name).write_text(text, encoding="utf-8", newline=LF)
    added = sorted(keys)
    manifest["unrecorded_attempts"] = sorted({*manifest.get("unrecorded_attempts", []), *added})
    manifest_path.write_text(_dump(manifest), encoding="utf-8", newline=LF)
    return added
