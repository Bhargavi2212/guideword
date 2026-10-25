"""The evidence step on whole $0 fake runs (Phase 4 spec 4.4; plan PR 5b, P4-2, P4-3, Q2, Q4,
Q15, G4-G6, G16, G17, G20). Every call goes through the fake gateway and a fake web search;
the precedent rows are synthetic (CLAUDE.md §5).

The run harness is the Phase 3 one (`test_post_analysis`), driven with evidence tools."""

import importlib.util
import json
import zlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from guideword.config import Config, load_config
from guideword.evidence.step import (
    CAP_REACHED,
    NO_PRECEDENT_TEXT,
    EvidenceTools,
    evidence_lines,
)
from guideword.gateway.cache import ResponseCache
from guideword.gateway.client import Gateway
from guideword.gateway.fake import reply
from guideword.gateway.ledgers import LaptopLedger
from guideword.gateway.replay import ReplayTransport, export_replay, load_replay
from guideword.gateway.transport import Reply
from guideword.recommend.step import current_shortlist
from guideword.reference import ReferenceSet, load_reference_set
from guideword.reference.precedents import PRECEDENT_INDEX, load_precedent_index
from guideword.runs.case import drive, steppers_for
from guideword.runs.extend import ExtendRefused, extend
from guideword.runs.machine import spend_matches_records
from guideword.runs.post_budget import evidence_setting, evidence_settings, post_spent
from guideword.schema import ids
from guideword.schema.enums import BudgetUse, EventType, EvidenceKind, RunStatus, Verdict
from guideword.schema.records import Run
from guideword.tools.web import FakeSearch, ReplaySearch, SearchFailed, WebSearch

REPO = Path(__file__).resolve().parents[3]


def _harness() -> Any:
    """The Phase 3 run harness (World, post_script, ...), loaded from its file: the suite
    imports test modules in importlib mode, so they can't import each other by name."""
    path = Path(__file__).resolve().parent / "test_post_analysis.py"
    spec = importlib.util.spec_from_file_location("post_analysis_harness", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pa = _harness()
HEADER = (
    "id,title,date,country,company,location,chemicals,equipment_types,mechanism_keywords,"
    "summary,url,source"
)
ROWS = [
    "P-1001,Mock mixer overpressure,2001-01-01,XX,,Mocktown,,mixer,pressure;outside,"
    "Outside heat raised the pressure in a mixer.,https://p.mock.invalid/1001,synthetic",
    "P-1002,Mock building release,2002-02-02,XX,,Sampleville,,building,outside;release,"
    "An outside event released vapour in a building.,https://p.mock.invalid/1002,synthetic",
    "P-1003,Blocked mixer fire,2003-03-03,XX,,Blockedtown,,mixer,pressure;outside;temperature,"
    "Outside heat raised the pressure and temperature in a mixer.,"
    "https://p.mock.invalid/1003,synthetic",
]
WEB = {
    "results": [
        {"title": "Web mixer report", "url": "https://w.mock.invalid/a", "content": "a mixer"},
        {"title": "Blockedtown story", "url": "https://w.mock.invalid/b", "content": "blocked"},
    ]
}
Judge = Callable[[list[dict[str, Any]]], Any]


@pytest.fixture(scope="module")
def ref() -> ReferenceSet:
    return load_reference_set()


@pytest.fixture(scope="module")
def config() -> Config:
    return load_config(global_budget_usd=25.0)


def _judged(handle: str, *, incident: bool, same: bool, reason: str) -> dict[str, Any]:
    """One precedent_judge/v2 judgement: is it an incident, and is it the same mechanism."""
    return {
        "candidate": handle,
        "is_incident": incident,
        "incident_reason": "an event at a site" if incident else "guidance, not an event",
        "same_mechanism": same,
        "reason": reason,
    }


def accept_mixers(candidates: list[dict[str, Any]]) -> Any:
    """Mixer candidates are incidents with the same mechanism; the rest are neither."""
    judgements = []
    for c in candidates:
        mixer = "mixer" in c["title"].lower()
        reason = "same heating of a closed mixer" if mixer else "another mechanism"
        judgements.append(_judged(c["handle"], incident=mixer, same=mixer, reason=reason))
    return {"judgements": judgements}


def reject_all(candidates: list[dict[str, Any]]) -> Any:
    return {
        "judgements": [
            _judged(c["handle"], incident=True, same=False, reason="no") for c in candidates
        ]
    }


def same_mechanism_but_no_incident(candidates: list[dict[str, Any]]) -> Any:
    """Every candidate shows the mechanism, and none is marked an incident: a web
    troubleshooting guide, say. Only CSB index rows can then be accepted."""
    return {
        "judgements": [
            _judged(c["handle"], incident=False, same=True, reason="the same physics")
            for c in candidates
        ]
    }


def with_judge(judge: Judge | None = accept_mixers, **post: Any) -> pa.Script:
    base = pa.post_script(**post)

    def script(job: str, request: dict[str, Any]) -> Reply:
        if job == "precedent_judge":
            if judge is None:
                return reply("not json")
            return reply(judge(pa.block(request, "candidates")))
        return base(job, request)

    return script


class Evidence:
    """A Phase 3 world with the evidence tools: a synthetic index and block list, and a fake
    web search sharing the run's cache and ledger."""

    def __init__(self, tmp_path: Path, ref: ReferenceSet, web: dict[str, Any] | None = None):
        self.world = pa.World(tmp_path / "world", ref)
        self.index_dir = tmp_path / "reference"
        self.index_dir.mkdir()
        (self.index_dir / PRECEDENT_INDEX).write_text(
            "\n".join([HEADER, *ROWS]) + "\n", encoding="utf-8", newline="\n"
        )
        self.cases = tmp_path / "cases"
        (self.cases / "dev").mkdir(parents=True)
        (self.cases / "dev" / f"{self.world.plant.plant_id}.block.txt").write_text(
            "# test terms\nBlockedtown\n", encoding="utf-8"
        )
        self.search = FakeSearch(lambda q, n: web if web is not None else WEB)

    @property
    def ledger(self) -> LaptopLedger:
        return LaptopLedger(self.world.dir / "l.jsonl")

    def tools(self, config: Config, *, enabled: bool = True, client: Any = None) -> EvidenceTools:
        web = WebSearch(
            client=client if client is not None else self.search,
            cache=ResponseCache(self.world.sessions),
            ledger=self.ledger,
            config=config,
            use=BudgetUse.DEVELOPMENT,
            phase="3",
            clock=lambda: pa.NOW,
        )
        return EvidenceTools(
            web=web,
            index=load_precedent_index(self.index_dir),
            cases_dir=self.cases,
            enabled=enabled,
        )

    def drive(
        self,
        run: Run,
        config: Config,
        script: pa.Script,
        *,
        use: BudgetUse = BudgetUse.DEVELOPMENT,
        tools: EvidenceTools | None = None,
        enabled: bool = True,
    ) -> tuple[Run, Any]:
        gateway, transport = pa.fake_gateway(
            config,
            script,
            sessions=self.world.sessions,
            ledger_path=self.world.dir / "l.jsonl",
            clock=lambda: pa.NOW,
            phase="3",
            use=use,
        )
        given = tools if tools is not None else self.tools(config, enabled=enabled)
        steppers = steppers_for(gateway, config, self.world.ref, self.world.plant, evidence=given)
        drive(self.world.runs, run.id, steppers)
        done = self.world.runs.get(run.id)
        assert done is not None
        return done, transport

    def run(self, config: Config, script: pa.Script, **kwargs: Any) -> tuple[Run, Any]:
        # the run starts on the use it is driven with (B2: the machine refuses another)
        use = kwargs.get("use", BudgetUse.DEVELOPMENT)
        return self.drive(self.world.start(config, use=use), config, script, **kwargs)

    def summary(self, run_id: str) -> dict[str, Any]:
        finished = [
            e.payload
            for e in self.world.runs.events(run_id)
            if e.type == EventType.STEP_FINISHED and e.payload.get("step") == "evidence"
        ]
        return finished[-1]


def judged(transport: Any) -> list[list[dict[str, Any]]]:
    return [pa.block(r, "candidates") for job, r in transport.sent if job == "precedent_judge"]


def tavily_lines(ev: Evidence) -> int:
    return sum(1 for e in ev.ledger.entries() if e.kind == "tavily")


# --- on, off and which lines (Q4, P4-3) ----------------------------------------------------------


def test_a_development_run_gets_evidence_on_its_top_lines(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    """An uploaded plant on use development (as an API run) gets evidence (Q4)."""
    ev = Evidence(tmp_path, ref)
    run, _ = ev.run(config, with_judge())
    assert run.status == RunStatus.FINISHED
    summary = ev.summary(run.id)
    assert summary["evidence"] == "on"
    precedent = [e for e in ev.world.runs.evidence(run.id) if e.kind == EvidenceKind.PRECEDENT]
    assert {e.target_id for e in precedent} == set(summary["lines"])
    assert len(summary["lines"]) == config.caps.evidence.evidence_top_n


def test_evidence_lines_are_the_top_n_confirmed_and_also_found_from_stored_records(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    ev = Evidence(tmp_path, ref)
    run, _ = ev.run(config, with_judge())
    with ev.world.runs.step(run.id) as writer:
        lines = current_shortlist(writer, ev.world.plant, ref, config)
    expected = [i.target_id for i in evidence_lines(lines, config.caps.evidence.evidence_top_n)]
    assert ev.summary(run.id)["lines"] == expected


@pytest.mark.parametrize("use", [BudgetUse.BENCHMARK, BudgetUse.TEST_5])
def test_a_benchmark_use_run_makes_no_evidence_call(
    tmp_path: Path, ref: ReferenceSet, config: Config, use: BudgetUse
) -> None:
    ev = Evidence(tmp_path, ref)
    run, transport = ev.run(config, with_judge(), use=use)
    assert run.status == RunStatus.FINISHED
    assert ev.summary(run.id)["evidence"] == "off"
    assert ev.summary(run.id)["reason"] == f"use {use}"
    assert not [j for j, _ in transport.sent if j == "precedent_judge"]
    assert ev.search.sent == [] and ev.world.runs.evidence(run.id) == []


def test_no_evidence_forces_it_off_for_any_use(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    ev = Evidence(tmp_path, ref)
    run, transport = ev.run(config, with_judge(), enabled=False)
    assert ev.summary(run.id) | {} and ev.summary(run.id)["reason"] == "--no-evidence"
    assert ev.search.sent == [] and ev.world.runs.evidence(run.id) == []


def test_a_run_without_evidence_tools_records_it_off(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    world = pa.World(tmp_path, ref)
    run, _ = world.run(config, with_judge())
    events = [
        e.payload
        for e in world.runs.events(run.id)
        if e.type == EventType.STEP_FINISHED and e.payload.get("step") == "evidence"
    ]
    assert events[-1]["evidence"] == "off"


# --- the precedent search (Q2, Q15, G5, G6, G20) -------------------------------------------------


def test_the_top_line_always_searches_and_judges_web_and_index_candidates_together(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    ev = Evidence(tmp_path, ref)
    run, transport = ev.run(config, with_judge())
    first = judged(transport)[0]
    assert {c["source"] for c in first} == {"incident index", "web"}
    assert len(ev.search.sent) >= 1
    top = ev.summary(run.id)["lines"][0]
    web_calls = [
        c
        for c in ev.world.runs.tool_calls(run.id)
        if c.tool == "web_research" and c.refused_reason is None
    ]
    assert web_calls and web_calls[0].result["cache_key"]
    steps = {s.id: s for s in ev.world.runs.steps(run.id)}
    assert steps[web_calls[0].agent_step_id].arguments["target_id"] == top


def test_a_block_term_removes_an_index_row_and_a_web_result_before_the_judge(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    ev = Evidence(tmp_path, ref)
    run, transport = ev.run(config, with_judge())
    shown = [c for batch in judged(transport) for c in batch]
    assert shown
    assert not [c for c in shown if "blocked" in json.dumps(c).lower()]
    assert ev.summary(run.id)["block_list"]["terms"] == 1


def test_each_accepted_incident_is_one_confirmed_record_with_its_judge_call(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    ev = Evidence(tmp_path, ref)
    run, _ = ev.run(config, with_judge())
    confirmed = [
        e
        for e in ev.world.runs.evidence(run.id)
        if e.kind == EvidenceKind.PRECEDENT and e.verdict == Verdict.CONFIRMED
    ]
    assert confirmed
    calls = {c.id for c in ev.world.runs.model_calls(run.id) if c.job == "precedent_judge"}
    tools = {c.id for c in ev.world.runs.tool_calls(run.id)}
    for record in confirmed:
        assert record.model_call_id in calls
        assert record.tool_call_id in tools
        assert "mixer" in record.sources[0].lower() and record.sources[1].startswith("https://")


def test_a_line_with_no_accepted_incident_gets_one_none_record(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    ev = Evidence(tmp_path, ref)
    run, _ = ev.run(config, with_judge(reject_all))
    for target in ev.summary(run.id)["lines"]:
        records = [
            e
            for e in ev.world.runs.evidence(run.id)
            if e.target_id == target and e.kind == EvidenceKind.PRECEDENT
        ]
        assert [(e.id, e.verdict, e.summary) for e in records] == [
            (ids.no_precedent_evidence_id(target), Verdict.NONE, NO_PRECEDENT_TEXT)
        ]


def test_a_search_past_the_per_run_cap_is_refused_and_recorded(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    """G6: past the cap, a tool call with its reason and an event, and no ledger line."""
    ev = Evidence(tmp_path, ref)
    capped = config.model_copy(
        update={
            "caps": config.caps.model_copy(
                update={
                    "evidence": config.caps.evidence.model_copy(
                        update={"tavily_searches_per_run": 1}
                    )
                }
            )
        }
    )
    run, _ = ev.run(capped, with_judge(reject_all))
    calls = [c for c in ev.world.runs.tool_calls(run.id) if c.tool == "web_research"]
    sent = [c for c in calls if c.refused_reason is None]
    refused = [c for c in calls if c.refused_reason == CAP_REACHED.format(cap=1)]
    assert len(sent) == 1 and refused
    assert tavily_lines(ev) == 1
    events = [e.payload for e in ev.world.runs.events(run.id) if e.type == EventType.TOOL_CALL]
    assert any(p["refused"] for p in events if p["tool"] == "web_research")
    flagged = [e for e in ev.world.runs.evidence(run.id) if CAP_REACHED.format(cap=1) in e.flags]
    assert flagged


def test_a_failed_judge_leaves_the_line_precedent_none_flagged(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    ev = Evidence(tmp_path, ref)
    run, _ = ev.run(config, with_judge(None))
    assert run.status == RunStatus.FINISHED
    precedent = [e for e in ev.world.runs.evidence(run.id) if e.kind == EvidenceKind.PRECEDENT]
    judged_lines = [e for e in precedent if e.model_call_id is not None]
    assert judged_lines and all(e.verdict == Verdict.NONE for e in precedent)
    assert all(any("precedent judge failed" in f for f in e.flags) for e in judged_lines)


def test_a_failed_search_leaves_the_line_flagged_and_the_run_goes_on(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    ev = Evidence(tmp_path, ref)

    def broken(query: str, n: int) -> dict[str, Any]:
        raise SearchFailed("Tavily TimeoutError: slow")

    run, _ = ev.run(config, with_judge(), tools=ev.tools(config, client=FakeSearch(broken)))
    assert run.status == RunStatus.FINISHED
    failed = [
        c for c in ev.world.runs.tool_calls(run.id) if (c.refused_reason or "").startswith("web")
    ]
    assert failed and tavily_lines(ev) == 0
    assert any(
        any(f.startswith("web search failed") for f in e.flags)
        for e in ev.world.runs.evidence(run.id)
    )


def test_an_unknown_or_repeated_handle_drops_that_item_and_the_rest_stand(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    def odd(candidates: list[dict[str, Any]]) -> Any:
        good = accept_mixers(candidates)["judgements"]
        first = good[0]
        return {"judgements": [*good, dict(first), {**first, "candidate": "K99"}]}

    ev = Evidence(tmp_path, ref)
    run, _ = ev.run(config, with_judge(odd))
    assert run.status == RunStatus.FINISHED
    assert ev.world.runs.evidence(run.id)


def test_the_judge_sees_handles_and_its_count_never_ids_or_batch(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    ev = Evidence(tmp_path, ref)
    _, transport = ev.run(config, with_judge())
    for job, request in transport.sent:
        if job != "precedent_judge":
            continue
        system, user = (m["content"] for m in request["messages"])
        candidates = pa.block(request, "candidates")
        handles = [c["handle"] for c in candidates]
        assert handles == [f"K{n}" for n in range(1, len(handles) + 1)]
        assert f"There are **{len(handles)} candidates** below" in system
        assert "batch" not in (system + user).lower()
        line = json.dumps(pa.block(request, "line"))
        assert "f:" not in line and "ch:" not in line and "http" not in json.dumps(candidates)


def mixer_lines(script: pa.Script) -> pa.Script:
    """Each S-MX-1 question gets its own cause, so it forms its own line. The matrix rule then
    brings each `more:` line its calculation on MX-1 (design pressure, a steam heat source):
    `more:pressure` gets blocked_in_heating. (The findings fail the building, so the blocked-in
    rule of review plan §0a, which needs the line to name MX-1 and a valve, never applies.)"""

    def wrapped(job: str, request: dict[str, Any]) -> Reply:
        answer = script(job, request)
        if not job.startswith("specialist") or answer.content is None:
            return answer
        data = json.loads(answer.content)
        for item in data.get("answers", []):
            if item["question_id"].startswith("m:S-MX-1:"):
                for found in item["findings"]:
                    # its own group, one per question: severity reads the last word as a
                    # number, so each question's is a stable number of its own
                    found["cause_text"] = f"outside {zlib.crc32(item['question_id'].encode())}"
        return reply(data)

    return wrapped


def _with_evidence(config: Config, **changes: Any) -> Config:
    evidence = config.caps.evidence.model_copy(update=changes)
    return config.model_copy(update={"caps": config.caps.model_copy(update={"evidence": evidence})})


def test_each_evidence_record_names_its_tool_call_step_and_model_call(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    """Every line gets evidence here (the top five are environment questions on a building),
    so the S-MX-1 lines get their physics cards too."""
    ev = Evidence(tmp_path, ref)
    run, _ = ev.run(_with_evidence(config, evidence_top_n=100), mixer_lines(with_judge()))
    steps = {s.id: s for s in ev.world.runs.steps(run.id)}
    calls = {c.id: c for c in ev.world.runs.tool_calls(run.id)}
    for record in ev.world.runs.evidence(run.id):
        assert record.tool_call_id in calls
        step = steps[calls[record.tool_call_id].agent_step_id]
        assert step.agent == "evidence" and step.arguments["target_id"] == record.target_id
    calc = [e for e in ev.world.runs.evidence(run.id) if e.kind == EvidenceKind.CALCULATION]
    assert calc
    for record in calc:
        call = calls[record.tool_call_id]
        assert call.tool == "physics_calc" and record.id in call.record_ids


# --- evidence changes nothing else (P4-2); spend (R45) -------------------------------------------


def _post(world: pa.World, run_id: str) -> dict[str, Any]:
    with world.runs.step(run_id) as writer:
        lines = current_shortlist(
            writer, world.plant, world.ref, load_config(global_budget_usd=25.0)
        )
    return {
        "order": [(i.target_id, i.planned.tier, i.planned.position) for i in lines],
        "chains": [c.model_dump(mode="json") for c in world.runs.chains(run_id)],
        "lopa": [r.model_dump(mode="json") for r in world.runs.lopa_records(run_id)],
        "recs": [r.model_dump(mode="json") for r in world.runs.recommendations(run_id)],
        "severities": sorted((f.id, f.severity_class) for f in world.runs.findings(run_id)),
    }


def test_evidence_changes_no_order_tier_lead_severity_lopa_or_recommendation(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    script = with_judge(connector=pa.first_two, severities={0: "S4", 1: "S5"})
    without = pa.World(tmp_path / "without", ref)
    plain, _ = without.run(config, script)
    ev = Evidence(tmp_path / "with", ref)
    run, _ = ev.run(config, script)
    assert ev.world.runs.evidence(run.id)
    assert _post(ev.world, run.id) == _post(without, plain.id)


def test_judge_spend_counts_against_the_post_cap_and_r45_holds(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    ev = Evidence(tmp_path, ref)
    run, _ = ev.run(config, with_judge())
    calls = ev.world.runs.model_calls(run.id)
    judge = [c for c in calls if c.job == "precedent_judge"]
    assert judge and post_spent(calls) >= sum(c.cap_cost_usd for c in judge)
    with ev.world.runs.step(run.id) as writer:
        assert spend_matches_records(writer)


# --- extension, re-runs and retries (G16, G17) ---------------------------------------------------


def test_extend_evidence_keeps_the_run_id_and_every_earlier_record(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    ev = Evidence(tmp_path, ref)
    script = with_judge()
    plain, _ = ev.run(config, script, enabled=False)
    before = pa.snapshot(ev.world, plain.id)
    extended = extend(
        ev.world.runs, plain.id, 0.5, config, evidence_only=True, use=BudgetUse.DEVELOPMENT
    )
    assert extended.id == plain.id and extended.step == "evidence"
    run, _ = ev.drive(extended, config, script)
    assert run.status == RunStatus.FINISHED
    after = pa.snapshot(ev.world, run.id)
    for table, rows in before.items():
        for key, value in rows.items():
            assert after[table][key] == value, (table, key)
    assert ev.world.runs.evidence(run.id)
    (event,) = [
        e
        for e in ev.world.runs.events(run.id)
        if e.type == EventType.RUN_EXTENDED and e.payload.get("evidence_only")
    ]
    assert event.payload["evidence_settings"]["evidence_top_n"]["value"] == 5


def test_evidence_twice_is_refused(tmp_path: Path, ref: ReferenceSet, config: Config) -> None:
    ev = Evidence(tmp_path, ref)
    run, _ = ev.run(config, with_judge())
    with pytest.raises(ExtendRefused, match="--rerun-from evidence"):
        extend(ev.world.runs, run.id, 0.5, config, evidence_only=True, use=BudgetUse.DEVELOPMENT)


def test_rerun_from_evidence_supersedes_only_the_evidence_pass(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    ev = Evidence(tmp_path, ref)
    run, _ = ev.run(config, with_judge())
    old_evidence = {e.id for e in ev.world.runs.evidence(run.id)}
    chains = [c.model_dump(mode="json") for c in ev.world.runs.chains(run.id)]
    analysis_steps = [s.id for s in ev.world.runs.steps(run.id) if s.agent != "evidence"]
    rerun = extend(
        ev.world.runs, run.id, 0.5, config, rerun_from="evidence", use=BudgetUse.DEVELOPMENT
    )
    assert rerun.step == "evidence"
    superseded = ev.world.runs.superseded(run.id)
    assert {k.kind for k in superseded} <= {"evidence", "agent_step", "tool_call", "model_call"}
    assert {k.record["id"] for k in superseded if k.kind == "evidence"} == old_evidence
    assert all(k.record["job"] == "precedent_judge" for k in superseded if k.kind == "model_call")
    assert all(k.record["agent"] == "evidence" for k in superseded if k.kind == "agent_step")
    done, _ = ev.drive(rerun, config, with_judge())
    assert done.status == RunStatus.FINISHED
    assert [c.model_dump(mode="json") for c in ev.world.runs.chains(run.id)] == chains
    assert [s.id for s in ev.world.runs.steps(run.id) if s.agent != "evidence"] == analysis_steps
    # the same inputs rebuild the same evidence: the judge's answers come from the cache
    assert {e.id for e in ev.world.runs.evidence(run.id)} == old_evidence


@pytest.mark.parametrize("rerun_from", ["chains", "lopa"])
def test_rerun_from_lopa_and_chains_supersede_the_old_evidence(
    tmp_path: Path, ref: ReferenceSet, config: Config, rerun_from: str
) -> None:
    ev = Evidence(tmp_path, ref)
    script = with_judge(connector=pa.first_two, severities={0: "S4", 1: "S5"})
    run, _ = ev.run(config, script)
    old = {e.id for e in ev.world.runs.evidence(run.id)}
    assert old
    changed = pa.changed(config)
    rerun = extend(
        ev.world.runs, run.id, 0.6, changed, rerun_from=rerun_from, use=BudgetUse.DEVELOPMENT
    )
    superseded = {k.record["id"] for k in ev.world.runs.superseded(run.id) if k.kind == "evidence"}
    assert superseded == old
    done, _ = ev.drive(rerun, changed, script)
    assert done.status == RunStatus.FINISHED
    assert ev.world.runs.evidence(run.id)


def test_a_retry_never_supersedes_an_orchestrator_or_specialist_step_or_tool_call(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    world, run, _ = pa._with_failed(tmp_path, ref, config)
    analysis_steps = [s.id for s in world.runs.steps(run.id)]
    analysis_calls = [c.id for c in world.runs.tool_calls(run.id)]
    extend(
        world.runs,
        run.id,
        0.30,
        config,
        retry_failed=True,
        retry_cap_usd=0.30,
        use=BudgetUse.DEVELOPMENT,
    )
    kinds = {k.kind for k in world.runs.superseded(run.id)}
    assert not kinds & {"agent_step", "tool_call"}
    kept_steps = [s.id for s in world.runs.steps(run.id)]
    assert kept_steps[: len(analysis_steps)] == analysis_steps
    assert [c.id for c in world.runs.tool_calls(run.id)][: len(analysis_calls)] == analysis_calls


# --- the D–H block lists (plan Q6) -------------------------------------------------------------


@pytest.mark.parametrize("case", ["case_d", "case_e", "case_f", "case_g", "case_h"])
def test_the_dev_case_block_lists_are_in_place(case: str) -> None:
    path = REPO / "cases" / "dev" / f"{case}.block.txt"
    text = path.read_text(encoding="utf-8")
    assert "whole word or phrase" in text
    assert [line for line in text.splitlines() if line.strip() and not line.startswith("#")]


# --- replay, settings, scripts and the API (R45, G4, G7, Q16) ------------------------------------


def test_a_run_with_evidence_replays_identically_with_its_web_search(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    """R45: the judge's calls and the Tavily search travel with the fixtures; the replay makes
    no call and gives the same evidence."""
    ev = Evidence(tmp_path / "original", ref)
    run, _ = ev.run(config, with_judge())
    out = export_replay(
        ev.world.runs,
        ResponseCache(ev.world.sessions),
        run.id,
        tmp_path / "fixtures",
        plant=ev.world.plant,
        plant_file=pa.EXAMPLE.relative_to(REPO).as_posix(),
        ref=ref,
        caps=config.caps,
        secrets=[],
    )
    again = Evidence(tmp_path / "replayed", ref)
    loaded = load_replay(out, again.world.sessions)
    gateway = Gateway(
        config=config,
        transport=ReplayTransport(loaded),
        cache=ResponseCache(again.world.sessions),
        ledger=again.ledger,
        use=BudgetUse.DEVELOPMENT,
        phase="3",
        clock=lambda: pa.NOW,
    )
    tools = again.tools(config, client=ReplaySearch())
    replayed = again.world.start(config)
    assert replayed.id == run.id
    steppers = steppers_for(gateway, config, ref, again.world.plant, evidence=tools)
    assert drive(again.world.runs, replayed.id, steppers) == RunStatus.FINISHED

    def records(world: Any) -> list[Any]:
        return [(e.id, e.verdict, e.summary) for e in world.runs.evidence(run.id)]

    assert records(again.world) == records(ev.world)
    done = again.world.runs.get(run.id)
    assert done is not None and done.spent_usd == 0.0
    assert tavily_lines(again) == 0


def test_evidence_top_n_is_read_from_the_runs_stored_caps_first(config: Config) -> None:
    """G4: D–G and the Phase 3 demo run store `evidence_top_n` in their caps. Only `caps` is
    read, so the records are built without their other fields."""
    stored = Run.model_construct(caps={"evidence_top_n": 2})
    assert evidence_setting(stored, config, "evidence_top_n") == 2
    assert evidence_settings(stored, config)["evidence_top_n"] == {
        "value": 2,
        "source": "run.caps",
    }
    fresh = Run.model_construct(caps={})
    assert evidence_setting(fresh, config, "evidence_top_n") == config.caps.evidence.evidence_top_n
    assert evidence_settings(fresh, config)["evidence_top_n"]["source"] == "config"


def test_run_case_and_extend_run_accept_use_video_and_the_evidence_flags() -> None:
    """G7 and Q7: the final demo run uses video (laptop); --no-evidence and --evidence."""
    import extend_run
    import run_case

    args = run_case._arguments(["plant.json", "--use", "video", "--no-evidence"])
    assert (args.use, args.no_evidence) == ("video", True)
    args = extend_run._arguments(["run:x", "--use", "video", "--evidence"])
    assert (args.use, args.evidence) == ("video", True)
    assert (
        extend_run._arguments(
            ["--use", "development", "run:x", "--rerun-from", "evidence"]
        ).rerun_from
        == "evidence"
    )
    with pytest.raises(SystemExit):
        run_case._arguments(["plant.json", "--use", "benchmark"])


def test_api_runs_charge_phase_5() -> None:
    """B2 moved API runs from Phase 4's cap to Phase 5's (specs/phase-5.md B2)."""
    from guideword.api.app import API_RUN_PHASE

    assert API_RUN_PHASE == "5"


# --- the reads (plan PR 5c): shortlist, flags, worksheet, record, dump, xlsx, manifest -----------


def _live(ev: Evidence, config: Config) -> Any:
    from guideword.api.live import LiveRuns

    def no_gateway(sessions: Any, use: Any) -> Any:
        raise AssertionError("reads make no call")

    return LiveRuns(
        ev.world.sessions,
        config=config,
        ref=ev.world.ref,
        gateway_factory=no_gateway,
        clock=lambda: pa.NOW,
    )


@pytest.fixture
def read_world(tmp_path: Path, ref: ReferenceSet, config: Config) -> tuple[Evidence, Run, Any]:
    """Every line gets evidence, MX-1's lines included (their contents have no vapour-pressure
    points, so their blocked-in heating check is skipped and names the missing facts)."""
    ev = Evidence(tmp_path, ref)
    wide = _with_evidence(config, evidence_top_n=100)
    run, _ = ev.run(wide, mixer_lines(with_judge()))
    return ev, run, _live(ev, wide)


def test_the_shortlist_shows_each_lines_evidence(
    read_world: tuple[Evidence, Run, Any],
) -> None:
    ev, run, live = read_world
    items = live.shortlist(run.id)
    shown = [i for i in items if i.evidence]
    assert shown
    for item in shown:
        assert {e.target_id for e in item.evidence} == {item.target_id}
    stored = {e.id for e in ev.world.runs.evidence(run.id)}
    assert {e.id for i in items for e in i.evidence} == stored


def test_line_flags_name_skipped_facts(read_world: tuple[Evidence, Run, Any]) -> None:
    _, run, live = read_world
    flags = [f for i in live.shortlist(run.id) for f in i.flags]
    skipped = [f for f in flags if f.startswith("evidence skipped: missing ")]
    assert skipped
    assert any("vapor_pressure_points" in f for f in skipped)


def test_the_card_and_worksheet_evidence_text_are_the_same(
    read_world: tuple[Evidence, Run, Any],
) -> None:
    """G12: the worksheet's Evidence column is the card's records in one formatter's words."""
    from guideword.review.display import evidence_text

    _, run, live = read_world
    cards = {i.target_id: i for i in live.shortlist(run.id) if i.evidence}
    rows = {r.row_id: r for r in live.worksheet(run.id)}
    compared = 0
    for target, item in cards.items():
        if target not in rows:
            continue  # a chain's card has no row of its own
        shown = rows[target].evidence
        assert shown is not None
        assert shown.removesuffix(" (scenario)") == evidence_text(item.evidence)
        assert all(e.id in rows[target].record_ids for e in item.evidence)
        compared += 1
    assert compared


def test_record_detail_returns_evidence_with_its_tool_call_and_judge_call(
    read_world: tuple[Evidence, Run, Any],
) -> None:
    ev, run, live = read_world
    judged_record = next(
        e for e in ev.world.runs.evidence(run.id) if e.model_call_id and e.tool_call_id
    )
    found, model_calls, tool_calls = live.record(run.id, judged_record.id)
    assert found.kind == "evidence"
    assert judged_record.target_id in found.parent_ids
    assert [c.id for c in model_calls] == [judged_record.model_call_id]
    assert judged_record.tool_call_id in [t.id for t in tool_calls]


def test_record_detail_returns_an_agent_step_with_its_tool_calls(
    read_world: tuple[Evidence, Run, Any],
) -> None:
    ev, run, live = read_world
    step = next(s for s in ev.world.runs.steps(run.id) if s.agent == "evidence")
    found, _, tool_calls = live.record(run.id, step.id)
    assert found.kind == "agent_step"
    assert tool_calls and all(t.agent_step_id == step.id for t in tool_calls)


def test_the_run_dump_and_xlsx_show_evidence(read_world: tuple[Evidence, Run, Any]) -> None:
    import io

    import openpyxl  # type: ignore[import-untyped]

    from guideword.api.mock import worksheet_xlsx

    ev, run, live = read_world
    dump = live.dump(run.id)
    assert {e.id for e in dump.evidence} == {e.id for e in ev.world.runs.evidence(run.id)}
    sheet = openpyxl.load_workbook(io.BytesIO(worksheet_xlsx(live.worksheet(run.id)))).active
    header = [c.value for c in sheet[1]]
    column = header.index("Evidence")
    values = [row[column].value for row in sheet.iter_rows(min_row=2)]
    assert any(v and "precedent:" in v for v in values)


def test_no_overrides_on_evidence_records(read_world: tuple[Evidence, Run, Any]) -> None:
    from guideword.api import models as api
    from guideword.review.overrides import OverrideRefused

    ev, run, live = read_world
    target = ev.world.runs.evidence(run.id)[0].id
    request = api.OverrideRequest(
        target_id=target, action="reject", new_value=None, reason="no", by="engineer"
    )
    with pytest.raises(OverrideRefused) as refused:
        live.add_override(run.id, request, pa.NOW)
    assert refused.value.status == 422
    assert ev.world.runs.overrides(run.id) == []


def test_the_replay_manifest_lists_the_evidence(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    ev = Evidence(tmp_path, ref)
    run, _ = ev.run(config, with_judge())
    out = export_replay(
        ev.world.runs,
        ResponseCache(ev.world.sessions),
        run.id,
        tmp_path / "fixtures",
        plant=ev.world.plant,
        plant_file=pa.EXAMPLE.relative_to(REPO).as_posix(),
        ref=ref,
        caps=config.caps,
        secrets=[],
    )
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["evidence"] == [[e.id, e.verdict.value] for e in ev.world.runs.evidence(run.id)]
    assert load_replay(out, Evidence(tmp_path / "again", ref).world.sessions).evidence


# --- precedent_judge/v2: an incident, and the same mechanism (Bhargavi, 2026-10-22) -------------


def test_accepts_needs_the_same_mechanism_and_an_incident_or_a_csb_row() -> None:
    from guideword.evidence.step import Candidate, Judgement, accepts

    def judgement(*, incident: bool, same: bool) -> Judgement:
        return Judgement.model_validate(_judged("K1", incident=incident, same=same, reason="r"))

    guide = Candidate("web", "https://w.mock.invalid/guide", "Troubleshooting guide", "u", {})
    report = Candidate("web", "https://w.mock.invalid/news", "Plant explosion", "u", {})
    row = Candidate("index", "P-1001", "Mock mixer overpressure", "u", {})
    # a web troubleshooting guide with the same mechanism is not an incident: none
    assert not accepts(guide, judgement(incident=False, same=True))
    # a web report of an actual event with the same mechanism: accepted
    assert accepts(report, judgement(incident=True, same=True))
    # an index row is a CSB investigation: the same mechanism is enough
    assert accepts(row, judgement(incident=False, same=True))
    # never without the same mechanism
    assert not accepts(row, judgement(incident=True, same=False))
    assert not accepts(report, judgement(incident=True, same=False))


def test_a_web_guide_with_the_same_mechanism_is_none_and_an_index_row_is_confirmed(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    ev = Evidence(tmp_path, ref)
    run, _ = ev.run(config, with_judge(same_mechanism_but_no_incident))
    confirmed = [
        e
        for e in ev.world.runs.evidence(run.id)
        if e.kind == EvidenceKind.PRECEDENT and e.verdict == Verdict.CONFIRMED
    ]
    assert confirmed
    # every accepted precedent is a CSB index row; no web result got through
    assert all(e.summary.startswith("CSB investigation: ") for e in confirmed)
    assert all("p.mock.invalid" in e.sources[1] for e in confirmed)


def test_each_precedent_names_its_source_type_verbatim(
    tmp_path: Path, ref: ReferenceSet, config: Config
) -> None:
    """The card shows the summary as stored: it starts with "CSB investigation" or "web
    result"."""
    ev = Evidence(tmp_path, ref)
    run, _ = ev.run(config, with_judge())
    confirmed = [
        e
        for e in ev.world.runs.evidence(run.id)
        if e.kind == EvidenceKind.PRECEDENT and e.verdict == Verdict.CONFIRMED
    ]
    kinds = {e.summary.split(": ", 1)[0] for e in confirmed}
    assert kinds == {"CSB investigation", "web result"}
    for record in confirmed:
        source = "web result" if "w.mock.invalid" in record.sources[1] else "CSB investigation"
        assert record.summary.startswith(f"{source}: {record.sources[0]}: ")
