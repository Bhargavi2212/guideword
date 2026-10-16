"""Content-built IDs (PROJECT.md §11 "IDs and enums", spec 0.5, decisions D4 and D10)."""

import ast
import hashlib
import inspect
import json
import subprocess
import sys
import unicodedata
from pathlib import Path

import pytest

from guideword.schema import ids
from guideword.schema.enums import (
    EvidenceKind,
    Guideword,
    HazopParameter,
    OperatingParameter,
    OverrideAction,
    QuestionKind,
    RunStatus,
)

IDS_SOURCE = Path(inspect.getfile(ids))

RUN_INPUTS = {
    "plant_id": "plant:example_mixing_unit:0123456789abcdef",
    "section_snapshot": ["S-MX-1", "S-L-12"],
    "reference_versions": {"causes.csv": "aa", "applicability.csv": "bb"},
    "routing_config": {"orchestrator": "ultra"},
    "caps": {"run_spend_cap_usd": 1.0},
    "prompt_versions": {"process": "v1"},
    "mode": "full",
}


# --- h() and canonical JSON -------------------------------------------------


def test_h_matches_hand_computed_value() -> None:
    expected = hashlib.sha256(b'{"a":1,"b":"x"}').hexdigest()[:16]
    assert ids.h({"b": "x", "a": 1}) == expected


def test_h_is_16_hex_characters() -> None:
    value = ids.h(["anything"])
    assert len(value) == 16
    assert all(c in "0123456789abcdef" for c in value)


def test_key_order_does_not_change_h() -> None:
    assert ids.h({"a": 1, "b": {"c": 2, "d": 3}}) == ids.h({"b": {"d": 3, "c": 2}, "a": 1})


def test_nfc_composed_and_decomposed_hash_the_same() -> None:
    composed = "café"
    decomposed = unicodedata.normalize("NFD", composed)
    assert composed != decomposed
    assert ids.h({"name": composed}) == ids.h({"name": decomposed})
    assert ids.h({composed: 1}) == ids.h({decomposed: 1})


def test_canonical_json_has_no_whitespace_and_keeps_unicode() -> None:
    assert ids.canonical_json({"b": [1, 2], "a": "é"}) == '{"a":"é","b":[1,2]}'


# --- normalise_text (D4) ------------------------------------------------------


@pytest.mark.parametrize(
    "a, b",
    [
        ("café", unicodedata.normalize("NFD", "café")),  # NFC
        ("over-pressure", "over–pressure"),  # en dash
        ("over-pressure", "over—pressure"),  # em dash
        ("over-pressure", "over‑pressure"),  # non-breaking hyphen
        ("high level", "high level"),  # non-breaking space
        ("high level", "high   \t level"),  # repeated whitespace
        ("high level", "  high level \n"),  # leading and trailing space
        ("high level", "HIGH Level"),  # case
    ],
)
def test_normalise_text_variants_hash_the_same(a: str, b: str) -> None:
    assert ids.normalise_text(a) == ids.normalise_text(b)
    assert ids.added_by_ai_question_id("S-MX-1", a) == ids.added_by_ai_question_id("S-MX-1", b)


def test_normalise_text_keeps_real_differences() -> None:
    assert ids.normalise_text("high level") != ids.normalise_text("low level")
    assert ids.engineer_question_id("S-MX-1", "high level") != ids.engineer_question_id(
        "S-MX-1", "low level"
    )


def test_every_hash_of_text_goes_through_normalise_text() -> None:
    """Any h() call whose argument uses a parameter named *text must wrap normalise_text()."""
    tree = ast.parse(IDS_SOURCE.read_text(encoding="utf-8"))
    checked = 0
    for func in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)):
        text_params = {a.arg for a in func.args.args + func.args.kwonlyargs if "text" in a.arg}
        if not text_params:
            continue
        for call in (n for n in ast.walk(func) if isinstance(n, ast.Call)):
            if not (isinstance(call.func, ast.Name) and call.func.id == "h"):
                continue
            for arg in call.args:
                names = {n.id for n in ast.walk(arg) if isinstance(n, ast.Name)}
                if names & text_params:
                    checked += 1
                    wrapped = [
                        n
                        for n in ast.walk(arg)
                        if isinstance(n, ast.Call)
                        and isinstance(n.func, ast.Name)
                        and n.func.id == "normalise_text"
                    ]
                    assert wrapped, f"{func.name} hashes raw text"
    assert checked >= 4  # ai:, eng:, rec: and outside-library causes


# --- fact IDs (D10) -------------------------------------------------------------


def test_fact_id_top_level_round_trip() -> None:
    fid = ids.fact_id("MX-1", "design_pressure_kpa")
    assert fid == "MX-1.design_pressure_kpa"
    ref = ids.parse_fact_id(fid)
    assert (ref.object_id, ref.field, ref.parameter, ref.limit) == (
        "MX-1",
        "design_pressure_kpa",
        None,
        None,
    )


def test_fact_id_value_object_is_cited_by_parent_field() -> None:
    assert ids.fact_id("PSV-1", "discharge") == "PSV-1.discharge"
    with pytest.raises(ValueError):
        ids.parse_fact_id("PSV-1.discharge.location_id")


def test_operating_fact_id_round_trip() -> None:
    fid = ids.operating_fact_id("MX-1", OperatingParameter.TEMPERATURE, "trip_high")
    assert fid == "MX-1.operating.temperature.trip_high"
    ref = ids.parse_fact_id(fid)
    assert (ref.object_id, ref.field, ref.parameter, ref.limit) == (
        "MX-1",
        "operating",
        OperatingParameter.TEMPERATURE,
        "trip_high",
    )


@pytest.mark.parametrize(
    "bad",
    [
        "MX-1.operating.temperature.trip_highest",  # unknown limit
        "MX-1.operating.colour.trip_high",  # unknown parameter
        "MX-1.operating.temperature",  # no limit
        "MX-1",  # no field
        "MX-1.",  # empty field
    ],
)
def test_parse_fact_id_rejects_malformed(bad: str) -> None:
    with pytest.raises(ValueError):
        ids.parse_fact_id(bad)


def test_operating_fact_id_rejects_unknown_limit() -> None:
    with pytest.raises(ValueError):
        ids.operating_fact_id("MX-1", OperatingParameter.PRESSURE, "setpoint")


# --- plant and section IDs ----------------------------------------------------------


def test_plant_record_id() -> None:
    plant_file = {"plant_id": "p1", "schema_version": "1.0"}
    assert ids.plant_record_id("p1", plant_file) == f"plant:p1:{ids.h(plant_file)}"


def test_section_ids() -> None:
    assert ids.section_id("MX-1") == "S-MX-1"
    assert ids.split_section_id("L-12", "HV-12") == "S-L-12~HV-12"
    eng = ids.engineer_section_id(["P-1", "MX-1"])
    assert eng == f"S~eng~{ids.h(['MX-1', 'P-1'])}"
    assert eng == ids.engineer_section_id(["MX-1", "P-1"])


def test_merge_keeps_the_lowest_id() -> None:
    assert ids.merged_section_id(["S-P-1", "S-MX-1", "S-L-12"]) == "S-L-12"


# --- question IDs -------------------------------------------------------------------

QUESTION_SAMPLES = [
    (
        ids.matrix_question_id("S-MX-1", Guideword.MORE, HazopParameter.PRESSURE),
        "m:S-MX-1:more:pressure",
        QuestionKind.MATRIX,
    ),
    (ids.pair_question_id("SIH", "KOH"), "pair:KOH:SIH", QuestionKind.CHEMICAL_PAIR),
    (
        ids.environment_question_id("KOH", "water"),
        "env:KOH:water",
        QuestionKind.CHEMICAL_ENVIRONMENT,
    ),
    (ids.no_flow_question_id("L-12"), "nf:L-12", QuestionKind.NO_FLOW_LINE),
    (
        ids.procedure_question_id("P-CHARGE-1", Guideword.SKIPPED),
        "proc:P-CHARGE-1:skipped",
        QuestionKind.PROCEDURE_STEP,
    ),
    (ids.work_question_id("W-1", "MX-1"), "work:W-1:MX-1", QuestionKind.PLANNED_WORK),
    (ids.dust_question_id("DRY-1"), "dust:DRY-1", QuestionKind.DUST),
    (ids.relief_question_id("PSV-1"), "relief:PSV-1", QuestionKind.RELIEF_DISCHARGE),
    (
        ids.added_by_ai_question_id("S-MX-1", "Static from the tote"),
        f"ai:S-MX-1:{ids.h(ids.normalise_text('Static from the tote'))}",
        QuestionKind.ADDED_BY_AI,
    ),
    (
        ids.engineer_question_id("S-L-12~HV-12", "Hose left connected"),
        f"eng:S-L-12~HV-12:{ids.h(ids.normalise_text('Hose left connected'))}",
        QuestionKind.ENGINEER,
    ),
]


@pytest.mark.parametrize("built, expected, kind", QUESTION_SAMPLES)
def test_question_id_format(built: str, expected: str, kind: QuestionKind) -> None:
    assert built == expected


@pytest.mark.parametrize("built, expected, kind", QUESTION_SAMPLES)
def test_question_id_round_trip(built: str, expected: str, kind: QuestionKind) -> None:
    parsed = ids.parse_question_id(built)
    assert parsed.kind == kind
    assert ids.build_question_id(parsed) == built


def test_pair_id_is_order_independent() -> None:
    assert ids.pair_question_id("A", "B") == ids.pair_question_id("B", "A")


def test_environment_question_rejects_unknown_kind() -> None:
    with pytest.raises(ValueError):
        ids.environment_question_id("KOH", "fire")


def test_parse_question_id_rejects_unknown_prefix() -> None:
    with pytest.raises(ValueError):
        ids.parse_question_id("zz:S-MX-1")


def test_id_parts_may_not_contain_separators() -> None:
    with pytest.raises(ValueError):
        ids.no_flow_question_id("L:12")
    with pytest.raises(ValueError):
        ids.section_id("MX.1")


# --- run IDs -------------------------------------------------------------------------


def _attempt(status: RunStatus, cap: float = 1.0) -> ids.Attempt:
    return ids.Attempt(status=status, spend_cap_usd=cap)


def test_first_run_has_no_attempt_suffix() -> None:
    assert ids.run_id(RUN_INPUTS, [], spend_cap_usd=1.0) == f"run:{ids.h(RUN_INPUTS)}"


def test_spend_cap_is_not_part_of_the_run_id() -> None:
    assert ids.run_id(RUN_INPUTS, [], spend_cap_usd=1.0) == ids.run_id(
        RUN_INPUTS, [], spend_cap_usd=2.5
    )
    with pytest.raises(ValueError):
        ids.run_id({**RUN_INPUTS, "spend_cap_usd": 1.0}, [], spend_cap_usd=1.0)


@pytest.mark.parametrize("unfinished", [RunStatus.DRAFT, RunStatus.RUNNING])
def test_unfinished_run_with_identical_inputs_is_resumed(unfinished: RunStatus) -> None:
    first = ids.run_id(RUN_INPUTS, [], spend_cap_usd=1.0)
    assert ids.run_id(RUN_INPUTS, [_attempt(unfinished)], spend_cap_usd=1.0) == first


def test_stopped_budget_run_is_resumed() -> None:
    first = ids.run_id(RUN_INPUTS, [], spend_cap_usd=1.0)
    attempts = [_attempt(RunStatus.STOPPED_BUDGET)]
    assert ids.run_id(RUN_INPUTS, attempts, spend_cap_usd=1.0) == first


def test_stopped_cap_run_resumes_with_a_higher_cap() -> None:
    first = ids.run_id(RUN_INPUTS, [], spend_cap_usd=1.0)
    attempts = [_attempt(RunStatus.STOPPED_CAP, cap=1.0)]
    assert ids.run_id(RUN_INPUTS, attempts, spend_cap_usd=1.5) == first


@pytest.mark.parametrize("new_cap", [1.0, 0.5])
def test_stopped_cap_run_with_same_or_lower_cap_is_refused(new_cap: float) -> None:
    attempts = [_attempt(RunStatus.STOPPED_CAP, cap=1.0)]
    with pytest.raises(ids.CapReachedError, match="cap reached; raise spend_cap_usd to continue"):
        ids.run_id(RUN_INPUTS, attempts, spend_cap_usd=new_cap)


def test_stopped_cap_on_a_later_attempt_resumes_that_attempt() -> None:
    first = ids.run_id(RUN_INPUTS, [], spend_cap_usd=1.0)
    attempts = [_attempt(RunStatus.CANCELLED), _attempt(RunStatus.STOPPED_CAP, cap=1.0)]
    assert ids.run_id(RUN_INPUTS, attempts, spend_cap_usd=2.0) == f"{first}:2"


def test_cap_reached_error_is_a_value_error() -> None:
    assert issubclass(ids.CapReachedError, ValueError)


@pytest.mark.parametrize("ended", [RunStatus.FINISHED, RunStatus.CANCELLED, RunStatus.FAILED])
def test_new_attempt_after_an_ended_run(ended: RunStatus) -> None:
    first = ids.run_id(RUN_INPUTS, [], spend_cap_usd=1.0)
    assert ids.run_id(RUN_INPUTS, [_attempt(ended)], spend_cap_usd=1.0) == f"{first}:2"
    attempts = [_attempt(ended), _attempt(RunStatus.CANCELLED)]
    assert ids.run_id(RUN_INPUTS, attempts, spend_cap_usd=1.0) == f"{first}:3"


def test_resume_returns_the_latest_unfinished_attempt() -> None:
    first = ids.run_id(RUN_INPUTS, [], spend_cap_usd=1.0)
    attempts = [_attempt(RunStatus.CANCELLED), _attempt(RunStatus.RUNNING)]
    assert ids.run_id(RUN_INPUTS, attempts, spend_cap_usd=1.0) == f"{first}:2"


def test_run_inputs_must_have_exactly_the_spec_keys() -> None:
    with pytest.raises(ValueError):
        ids.run_id({k: v for k, v in RUN_INPUTS.items() if k != "caps"}, [], spend_cap_usd=1.0)
    with pytest.raises(ValueError):
        ids.run_id({**RUN_INPUTS, "extra": 1}, [], spend_cap_usd=1.0)


# --- findings, chains, LOPA, recommendations, evidence ---------------------------------

Q = "m:S-MX-1:more:temperature"


def test_finding_id_format() -> None:
    fid = ids.finding_id(Q, "lightning", ["TV-1"], cause_id="C01")
    assert fid == f"f:{Q}:lightning:C01:{ids.h(['TV-1'])}"


def test_findings_differ_by_cause_and_by_component() -> None:
    a = ids.finding_id(Q, "lightning", ["TV-1"], cause_id="C01")
    b = ids.finding_id(Q, "lightning", ["TV-1"], cause_id="C02")
    c = ids.finding_id(Q, "lightning", ["TT-1"], cause_id="C01")
    assert len({a, b, c}) == 3


def test_finding_component_order_does_not_matter() -> None:
    a = ids.finding_id(Q, "ultra", ["TV-1", "TT-1"], cause_id="C03")
    b = ids.finding_id(Q, "ultra", ["TT-1", "TV-1"], cause_id="C03")
    assert a == b


def test_ultra_reanswer_is_a_different_finding() -> None:
    a = ids.finding_id(Q, "lightning", ["TV-1"], cause_id="C01")
    b = ids.finding_id(Q, "ultra", ["TV-1"], cause_id="C01")
    assert a != b


def test_outside_library_finding_uses_hash_of_normalised_text() -> None:
    fid = ids.finding_id(Q, "ultra", ["MX-1"], cause_text="Agitator  seized")
    assert fid == ids.finding_id(Q, "ultra", ["MX-1"], cause_text="agitator seized")
    assert fid == f"f:{Q}:ultra:{ids.h(ids.normalise_text('agitator seized'))}:{ids.h(['MX-1'])}"


def test_finding_needs_exactly_one_cause_and_some_components() -> None:
    with pytest.raises(ValueError):
        ids.finding_id(Q, "ultra", ["MX-1"])
    with pytest.raises(ValueError):
        ids.finding_id(Q, "ultra", ["MX-1"], cause_id="C01", cause_text="x")
    with pytest.raises(ValueError):
        ids.finding_id(Q, "ultra", [], cause_id="C01")


def test_chain_id_ignores_link_order() -> None:
    a = ids.chain_id(["f:x", "MX-1.design_pressure_kpa"])
    b = ids.chain_id(["MX-1.design_pressure_kpa", "f:x"])
    assert a == b == "ch:MX-1.design_pressure_kpa+f:x"


def test_chain_needs_two_links_without_plus() -> None:
    with pytest.raises(ValueError):
        ids.chain_id(["f:x"])
    with pytest.raises(ValueError):
        ids.chain_id(["f:x", "a+b"])


def test_lopa_and_recommendation_ids() -> None:
    fid = ids.finding_id(Q, "ultra", ["TV-1"], cause_id="C01")
    assert ids.lopa_id(fid) == f"lopa:{fid}"
    rec = ids.recommendation_id(fid, "Add an independent high-temperature trip")
    assert (
        rec == f"rec:{fid}:{ids.h(ids.normalise_text('add an independent high-temperature trip'))}"
    )
    assert rec == ids.recommendation_id(fid, "add an  independent high–temperature trip")


def test_evidence_ids() -> None:
    t = "ch:a+b"
    assert ids.evidence_id(t, EvidenceKind.CALCULATION, "overflow_time") == (
        f"ev:{t}:calculation:overflow_time"
    )
    assert ids.evidence_id(t, EvidenceKind.SIMULATION, "IDV6") == f"ev:{t}:simulation:IDV6"
    assert ids.precedent_evidence_id(t, precedent_id="P-0042") == f"ev:{t}:precedent:P-0042"
    url = "https://example.org/report"
    assert ids.precedent_evidence_id(t, url=url) == f"ev:{t}:precedent:{ids.h(url)}"
    with pytest.raises(ValueError):
        ids.precedent_evidence_id(t)


# --- model calls, tool calls, agent steps, overrides -------------------------------------


def test_model_call_id_is_the_cache_key() -> None:
    key = ids.cache_key("nvidia/model", "process/v1", {"messages": ["hi"]})
    assert key == ids.h(["nvidia/model", "process/v1", {"messages": ["hi"]}])
    assert ids.model_call_id("nvidia/model", "process/v1", {"messages": ["hi"]}) == f"mc:{key}"


def test_tool_calls_at_different_steps_differ() -> None:
    args: dict[str, object] = {}
    step1 = ids.agent_step_id("run:abc", "orchestrator", "check_coverage", args)
    step2 = ids.agent_step_id(step1, "orchestrator", "check_coverage", args)
    assert step1 != step2
    tc1 = ids.tool_call_id(step1, "check_coverage", args)
    tc2 = ids.tool_call_id(step2, "check_coverage", args)
    assert tc1 != tc2
    assert tc1 == f"tc:{step1}:check_coverage:{ids.h(args)}"


def test_agent_step_id_format() -> None:
    step = ids.agent_step_id("run:abc", "orchestrator", "dispatch_specialist", {"ids": ["q1"]})
    assert (
        step == f"step:{ids.h(['run:abc', 'orchestrator', 'dispatch_specialist', {'ids': ['q1']}])}"
    )


def test_override_ids_chain_through_replacements() -> None:
    fid = "f:x"
    first = ids.override_id(fid, OverrideAction.CHANGE_SEVERITY, "S4")
    assert first == f"ov:{fid}:{ids.h(['change_severity', 'S4', 'none'])}"
    second = ids.override_id(fid, OverrideAction.CHANGE_SEVERITY, "S4", replaces=first)
    assert second != first


# --- purity --------------------------------------------------------------------------------


def test_ids_module_has_no_randomness_counters_or_clock() -> None:
    tree = ast.parse(IDS_SOURCE.read_text(encoding="utf-8"))
    banned = {"random", "uuid", "time", "datetime", "secrets"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not {a.name.split(".")[0] for a in node.names} & banned
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in banned
            if node.module == "itertools":
                assert "count" not in {a.name for a in node.names}
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            assert not (node.value.id == "itertools" and node.attr == "count")


def _sample_ids() -> list[str]:
    return [
        ids.run_id(RUN_INPUTS, [], spend_cap_usd=1.0),
        ids.finding_id(Q, "ultra", ["TV-1", "TT-1"], cause_id="C01"),
        ids.chain_id(["b", "a"]),
        ids.added_by_ai_question_id("S-MX-1", "Static from the tote"),
        ids.override_id("f:x", OverrideAction.EDIT, {"text": "é"}),
    ]


def test_same_inputs_give_same_ids_in_another_process() -> None:
    code = (
        "import json, sys\n"
        f"sys.path.insert(0, {str(Path(__file__).parent)!r})\n"
        "import test_ids\n"
        "print(json.dumps(test_ids._sample_ids()))\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True, timeout=60
    )
    assert json.loads(out.stdout) == _sample_ids()


def test_hypothesis_id_is_built_from_rank_mechanism_and_components() -> None:
    """R50, Q3: `h:<rank>:<h(normalised mechanism, sorted component IDs)>`, no run in it."""
    a = ids.hypothesis_id(2, "Wrong  material charged", ["P-CHARGE-1", "MX-1"])
    assert a == ids.hypothesis_id(2, "wrong material charged", ["MX-1", "P-CHARGE-1"])
    assert (
        a == f"h:2:{ids.h([ids.normalise_text('Wrong material charged'), ['MX-1', 'P-CHARGE-1']])}"
    )
    assert a != ids.hypothesis_id(3, "wrong material charged", ["MX-1", "P-CHARGE-1"])
    assert a != ids.hypothesis_id(2, "valve left open", ["MX-1", "P-CHARGE-1"])
    assert "run:" not in a


def test_hypothesis_id_needs_components_and_a_rank_from_one() -> None:
    with pytest.raises(ValueError):
        ids.hypothesis_id(1, "x", [])
    with pytest.raises(ValueError):
        ids.hypothesis_id(0, "x", ["MX-1"])
