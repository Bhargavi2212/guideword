"""The LOPA engine, pure code (spec 3.2 acceptance; plan PR 4, Q3, Q4, Q8, M2; PROJECT.md §5
Step 6.2, §18).

Candidates are chosen by code; Ultra only says whether a listed layer applies; code decides
credit in the plan's rule order and does the arithmetic. No conditional modifiers (P3-3).
"""

import json
from pathlib import Path
from typing import Any

import pytest

from guideword.config import Config
from guideword.lopa.candidates import Scenario, candidates, chain_scenario, line_scenario
from guideword.lopa.credit import NOT_ARGUED, LayerArgument, credit
from guideword.lopa.engine import (
    CODE_ONLY_FLAG,
    FREQUENCY_ASSUMED_FLAG,
    MODIFIER_REASON,
    NoLopa,
    UnknownLayerError,
    lopa_record,
)
from guideword.ranking.likelihood import PIPE_LEAK_LARGE_EVENT, likelihood
from guideword.ranking.rank import rank_findings
from guideword.reference import ReferenceSet
from guideword.schema import ids
from guideword.schema.enums import (
    Adequacy,
    Confidence,
    FailingComponentType,
    SectionKind,
    SectionType,
    SeverityClass,
    Tier,
)
from guideword.schema.plant import Plant, ReliefDevice, Safeguard
from guideword.schema.records import Chain, Finding, LopaRecord, Section

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "backend" / "tests" / "schema" / "fixtures" / "example_mixing_unit.json"
RUN = "run:test"
YES = LayerArgument(applies=True, reason="it acts on this deviation")


def example_plant(*edits: Any) -> Plant:
    """The §9 example plant, with each edit applied to its JSON first."""
    data: dict[str, Any] = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    for edit in edits:
        edit(data)
    return Plant.model_validate(data)


def finding(
    question: str = "m:S-MX-1:more:temperature",
    cause: str = "C01",
    kind: FailingComponentType = FailingComponentType.CONTROL_LOOP,
    components: tuple[str, ...] = ("TIC-1",),
    severity: SeverityClass | None = SeverityClass.S4,
) -> Finding:
    return Finding(
        id=ids.finding_id(question, Tier.ULTRA.value, list(components), cause_id=cause),
        run_id=RUN,
        question_id=question,
        tier=Tier.ULTRA,
        cause_id=cause,
        failing_component_type=kind,
        failing_component_ids=list(components),
        consequence="something bad",
        adequacy=Adequacy.UNKNOWN,
        severity_class=severity,
        severity_reason="test" if severity else None,
        confidence=Confidence.SURE,
    )


def section(section_id: str = "S-MX-1", object_ids: tuple[str, ...] = ("MX-1",)) -> Section:
    return Section(
        id=section_id,
        plant_record_id="plant:example",
        kind=SectionKind.EQUIPMENT,
        section_type=SectionType.MIXER,
        name=section_id,
        object_ids=list(object_ids),
        drawn_by="rule",
    )


def _guard(plant: Plant, guard_id: str) -> Safeguard:
    return next(g for g in plant.safeguards if g.id == guard_id)


def _relief(plant: Plant, device_id: str = "PSV-1") -> ReliefDevice:
    return next(r for r in plant.relief_devices if r.id == device_id)


def _set_guard(guard_id: str, **fields: Any) -> Any:
    def edit(data: dict[str, Any]) -> None:
        guard = next((g for g in data["safeguards"] if g["id"] == guard_id), None)
        if guard is None:
            data["safeguards"].append({"id": guard_id, **fields})
        else:
            guard.update(fields)

    return edit


def _inlet_valves(*valves: dict[str, Any]) -> Any:
    def edit(data: dict[str, Any]) -> None:
        for valve in valves:
            data["valves"].append({"kind": "relief_isolation", **valve})
        data["relief_devices"][0]["inlet_valve_ids"] = [v["id"] for v in valves]

    return edit


def _loop_scenario() -> Scenario:
    """C01 on TIC-1 in S-MX-1: example 1's scenario."""
    return line_scenario(finding(), section())


def _record(
    scenario: Scenario,
    plant: Plant,
    ref: ReferenceSet,
    config: Config,
    arguments: dict[str, LayerArgument] | None,
) -> LopaRecord:
    record = lopa_record(
        scenario, run_id=RUN, plant=plant, ref=ref, caps=config.caps, arguments=arguments
    )
    assert isinstance(record, LopaRecord)
    return record


# --- credit rules ----------------------------------------------------------------------------


def test_shared_component_gets_no_credit(ref: ReferenceSet) -> None:
    """XV-STM fails, and SG-TRIP acts through XV-STM: no credit."""
    plant = example_plant()
    valve = finding(cause="C15", kind=FailingComponentType.OPERATOR, components=("XV-STM",))
    layer = credit(_guard(plant, "SG-TRIP"), line_scenario(valve, section()), plant, ref, YES)
    assert layer.credited is False and layer.pfd is None
    assert layer.reason == "no credit — shares component XV-STM with the cause"
    assert (layer.applies, layer.argument) == (True, YES.reason)


def test_shared_logic_solver_gets_no_credit_where_required(ref: ReferenceSet) -> None:
    """IPL-SIS-SIL1 requires independent logic; SG-TRIP on DCS-1, TIC-1's controller."""
    plant = example_plant(_set_guard("SG-TRIP", component_ids=["TS-2", "DCS-1", "XV-STM"]))
    layer = credit(_guard(plant, "SG-TRIP"), _loop_scenario(), plant, ref, YES)
    assert layer.credited is False and layer.pfd is None
    assert layer.reason == "no credit — shares logic solver DCS-1 with failing loop TIC-1"


def test_shared_sensor_gets_no_credit_where_required(ref: ReferenceSet) -> None:
    """IPL-HUMAN requires an independent sensor: an alarm on TT-1, TIC-1's own sensor."""
    plant = example_plant(
        _set_guard("SG-ALARM", layer_type="IPL-HUMAN", protects_id="MX-1", component_ids=["TT-1"])
    )
    layer = credit(_guard(plant, "SG-ALARM"), _loop_scenario(), plant, ref, YES)
    assert layer.credited is False and layer.pfd is None
    assert layer.reason == "no credit — shares sensor TT-1 with failing loop TIC-1"


def test_shared_final_element_gets_no_credit_where_required(ref: ReferenceSet) -> None:
    """IPL-SIS-SIL1 requires an independent final element: SG-TRIP acting through TV-1."""
    plant = example_plant(_set_guard("SG-TRIP", component_ids=["TS-2", "SIS-1", "TV-1"]))
    layer = credit(_guard(plant, "SG-TRIP"), _loop_scenario(), plant, ref, YES)
    assert layer.credited is False and layer.pfd is None
    assert layer.reason == "no credit — shares final element TV-1 with failing loop TIC-1"


@pytest.mark.parametrize("shared", ["TV-1", "DCS-1"])
def test_an_independence_flag_the_row_does_not_set_does_not_refuse_credit(
    ref: ReferenceSet, shared: str
) -> None:
    """IPL-HUMAN requires only an independent sensor: the loop's final element or logic solver
    among its components still gets its 0.1."""
    plant = example_plant(
        _set_guard(
            "SG-ALARM", layer_type="IPL-HUMAN", protects_id="MX-1", component_ids=["TS-2", shared]
        )
    )
    layer = credit(_guard(plant, "SG-ALARM"), _loop_scenario(), plant, ref, YES)
    assert layer.credited is True
    assert layer.pfd == next(r.pfd for r in ref.protection_layers if r.id == "IPL-HUMAN")


def test_the_loop_parts_are_not_failing_components(ref: ReferenceSet) -> None:
    """Q4: TIC-1 failing does not make TV-1 a failing component; independence covers it."""
    plant = example_plant(
        _set_guard("SG-ALARM", layer_type="IPL-HUMAN", protects_id="MX-1", component_ids=["TV-1"])
    )
    layer = credit(_guard(plant, "SG-ALARM"), _loop_scenario(), plant, ref, YES)
    assert layer.credited is True


def test_open_unlocked_inlet_valve_gets_pfd_if_isolatable(ref: ReferenceSet) -> None:
    plant = example_plant(
        _inlet_valves({"id": "HV-PSV", "normal_position": "open", "locked": False})
    )
    layer = credit(_relief(plant), _loop_scenario(), plant, ref, YES)
    row = next(r for r in ref.protection_layers if r.id == "IPL-PRV")
    assert layer.credited is True
    assert layer.pfd == row.pfd_if_isolatable == 0.1
    assert layer.layer_type == "IPL-PRV"
    assert layer.reason == "credited at pfd_if_isolatable — inlet valve HV-PSV unmanaged"


def test_inlet_valve_with_no_lock_fact_is_unmanaged(ref: ReferenceSet) -> None:
    plant = example_plant(_inlet_valves({"id": "HV-PSV", "normal_position": "open"}))
    layer = credit(_relief(plant), _loop_scenario(), plant, ref, YES)
    assert layer.pfd == 0.1


def test_all_inlet_valves_locked_open_gets_pfd(ref: ReferenceSet) -> None:
    plant = example_plant(
        _inlet_valves(
            {"id": "HV-PSV", "normal_position": "open", "locked": True},
            {"id": "HV-PSV2", "normal_position": "open", "locked": True},
        )
    )
    layer = credit(_relief(plant), _loop_scenario(), plant, ref, YES)
    assert layer.credited is True
    assert layer.pfd == next(r.pfd for r in ref.protection_layers if r.id == "IPL-PRV") == 0.01


def test_no_inlet_valve_gets_pfd(ref: ReferenceSet) -> None:
    plant = example_plant()
    layer = credit(_relief(plant), _loop_scenario(), plant, ref, YES)
    assert (layer.credited, layer.pfd) == (True, 0.01)


def test_closed_inlet_valve_gets_no_credit(ref: ReferenceSet) -> None:
    """The Williams Geismar case: a closed inlet valve isolates the relief (Q13 wording)."""
    plant = example_plant(
        _inlet_valves(
            {"id": "HV-PSV", "normal_position": "open", "locked": False},
            {"id": "HV-PSV2", "normal_position": "closed", "locked": True},
        )
    )
    layer = credit(_relief(plant), _loop_scenario(), plant, ref, YES)
    assert layer.credited is False and layer.pfd is None
    assert layer.reason == "no credit — inlet valve HV-PSV2 closed"


def test_relief_device_without_kind_gets_no_credit(ref: ReferenceSet) -> None:
    def no_kind(data: dict[str, Any]) -> None:
        data["relief_devices"][0].pop("kind")

    plant = example_plant(no_kind)
    layer = credit(_relief(plant), _loop_scenario(), plant, ref, YES)
    assert layer.credited is False and layer.pfd is None
    assert layer.reason == "no credit — no kind (PSV-1.kind), so no protection_layers row"


def test_no_layer_type_gets_no_credit(ref: ReferenceSet) -> None:
    plant = example_plant(_set_guard("SG-PLAIN", protects_id="MX-1", component_ids=[]))
    guard = _guard(plant, "SG-PLAIN")
    layer = credit(guard, _loop_scenario(), plant, ref, YES)
    assert layer.credited is False and layer.pfd is None
    assert layer.reason == "no credit — no layer_type"
    # and it is never a candidate (spec 3.2: safeguards with a layer_type)
    assert "SG-PLAIN" not in [c.id for c in candidates(_loop_scenario(), plant)]


def test_a_layer_that_is_itself_a_failing_component_gets_no_credit(ref: ReferenceSet) -> None:
    """A relief device cause on PSV-1 gives PSV-1 no credit against that cause."""
    plant = example_plant()
    stuck = finding(cause="C01", kind=FailingComponentType.RELIEF_DEVICE, components=("PSV-1",))
    layer = credit(_relief(plant), line_scenario(stuck, section()), plant, ref, YES)
    assert layer.credited is False
    assert layer.reason == "no credit — PSV-1 is itself a failing component"


def test_not_argued_comes_first_and_does_not_apply_second(ref: ReferenceSet) -> None:
    plant = example_plant(_set_guard("SG-PLAIN", protects_id="MX-1", component_ids=[]))
    guard = _guard(plant, "SG-PLAIN")
    not_argued = credit(guard, _loop_scenario(), plant, ref, None)
    assert not_argued.reason == NOT_ARGUED == "not argued — no credit"
    assert (not_argued.applies, not_argued.argument) == (None, None)
    no = credit(guard, _loop_scenario(), plant, ref, LayerArgument(applies=False, reason="why"))
    assert no.reason == "does not apply: why"
    assert (no.credited, no.pfd, no.applies, no.argument) == (False, None, False, "why")


# --- candidates --------------------------------------------------------------------------------


def test_candidates_are_layer_typed_safeguards_and_relief_devices_on_the_scenario(
    ref: ReferenceSet,
) -> None:
    plant = example_plant(
        _set_guard("SG-ALARM", layer_type="IPL-HUMAN", protects_id="TIC-1", component_ids=[]),
        _set_guard("SG-FAR", layer_type="IPL-HUMAN", protects_id="TOTE-1", component_ids=[]),
    )
    assert [c.id for c in candidates(_loop_scenario(), plant)] == ["PSV-1", "SG-ALARM", "SG-TRIP"]


def test_a_question_without_a_section_uses_only_the_failing_components() -> None:
    plant = example_plant()
    pair = finding(question="pair:KOH:SIH", components=("MX-1",))
    assert [c.id for c in candidates(line_scenario(pair, None), plant)] == ["PSV-1", "SG-TRIP"]
    elsewhere = finding(question="pair:KOH:SIH", components=("TOTE-1",))
    assert candidates(line_scenario(elsewhere, None), plant) == []


def test_chain_scenario_unions_its_finding_links_and_starts_from_the_first() -> None:
    """Q7, Q8: the first finding link in the model's order is the cause; candidates and failing
    components are the union over the finding links; fact links add nothing."""
    plant = example_plant()
    leak = finding(
        question="nf:L-12", cause="C20", kind=FailingComponentType.PIPE, components=("L-12",)
    )
    loop = finding()
    chain = Chain(
        id=ids.chain_id([leak.id, loop.id, "MX-1.design_temp_c"]),
        run_id=RUN,
        links=[leak.id, "MX-1.design_temp_c", loop.id],
        description="d",
        reason="r",
        severity_class=SeverityClass.S5,
    )
    scenario = chain_scenario(chain, [(leak, None), (loop, section())])
    assert scenario.target_id == chain.id
    assert scenario.finding == leak
    assert scenario.severity_class == SeverityClass.S5
    assert scenario.failing_component_ids == frozenset({"L-12", "TIC-1"})
    assert scenario.object_ids == frozenset({"L-12", "TIC-1", "MX-1"})
    assert [c.id for c in candidates(scenario, plant)] == ["PSV-1", "SG-TRIP"]


# --- the record --------------------------------------------------------------------------------


def test_per_metre_year_without_length_is_incomplete_naming_the_fact_and_no_default(
    ref: ReferenceSet, config: Config
) -> None:
    plant = example_plant()
    leak = finding(
        question="nf:L-12", cause="C20", kind=FailingComponentType.PIPE, components=("L-12",)
    )
    record = _record(line_scenario(leak, None), plant, ref, config, None)
    assert record.complete is False
    assert record.missing_fact_ids == ["L-12.length_m"]
    assert record.initiating_frequency_per_year is None
    assert record.mitigated_frequency_per_year is None and record.gap is None
    assert record.tolerable_per_year == next(
        t.tolerable_per_year for t in ref.tolerable_frequencies if t.severity_class == "S4"
    )


def test_per_lift_without_lift_count_is_incomplete_naming_the_fact(
    ref: ReferenceSet, config: Config
) -> None:
    def lift_job(data: dict[str, Any]) -> None:
        data["planned_work"].append({"id": "W-LIFT", "type": "lifting", "location_id": "BLDG-1"})

    plant = example_plant(lift_job)
    crane = finding(
        question="work:W-LIFT:MX-1",
        cause="C24",
        kind=FailingComponentType.EXTERNAL,
        components=("BLDG-1",),
    )
    record = _record(line_scenario(crane, None), plant, ref, config, None)
    assert record.complete is False
    assert record.missing_fact_ids == ["W-LIFT.lifts_per_year"]
    assert record.gap is None


def test_a_line_with_no_severity_gets_no_lopa(ref: ReferenceSet, config: Config) -> None:
    """Q11: never a default class."""
    unrated = finding(severity=None)
    result = lopa_record(
        line_scenario(unrated, section()),
        run_id=RUN,
        plant=example_plant(),
        ref=ref,
        caps=config.caps,
        arguments=None,
    )
    assert result == NoLopa(target_id=unrated.id, reason="no severity")


def test_a_line_with_no_frequency_and_no_missing_fact_gets_no_lopa(
    ref: ReferenceSet, config: Config
) -> None:
    """A cause that names no line or job has no frequency and no fact to name."""
    odd = finding(
        question="nf:L-12", cause="C20", kind=FailingComponentType.PIPE, components=("MX-1",)
    )
    result = lopa_record(
        line_scenario(odd, None),
        run_id=RUN,
        plant=example_plant(),
        ref=ref,
        caps=config.caps,
        arguments=None,
    )
    assert isinstance(result, NoLopa)
    assert result.reason == (
        "no likelihood: a per_metre_year cause names no line, so no length applies"
    )


def test_code_only_lopa_marks_every_layer_not_argued(ref: ReferenceSet, config: Config) -> None:
    plant = example_plant(
        _set_guard("SG-ALARM", layer_type="IPL-HUMAN", protects_id="MX-1", component_ids=["TS-2"])
    )
    record = _record(_loop_scenario(), plant, ref, config, None)
    assert [layer.layer_id for layer in record.layers] == ["PSV-1", "SG-ALARM", "SG-TRIP"]
    assert all(
        (layer.credited, layer.pfd, layer.reason) == (False, None, NOT_ARGUED)
        for layer in record.layers
    )
    assert CODE_ONLY_FLAG in record.flags
    assert record.model_call_id is None
    assert record.mitigated_frequency_per_year == record.initiating_frequency_per_year


def test_a_layer_left_out_of_the_argument_is_not_argued(ref: ReferenceSet, config: Config) -> None:
    record = _record(_loop_scenario(), example_plant(), ref, config, {"SG-TRIP": YES})
    by_id = {layer.layer_id: layer for layer in record.layers}
    assert by_id["PSV-1"].reason == NOT_ARGUED
    assert by_id["SG-TRIP"].credited is True
    assert CODE_ONLY_FLAG not in record.flags


def test_ultra_never_adds_a_layer(ref: ReferenceSet, config: Config) -> None:
    """SG-VENT protects BLDG-1, so code did not list it: an argument for it is refused."""
    with pytest.raises(UnknownLayerError, match="SG-VENT"):
        lopa_record(
            _loop_scenario(),
            run_id=RUN,
            plant=example_plant(),
            ref=ref,
            caps=config.caps,
            arguments={"SG-TRIP": YES, "SG-VENT": YES},
        )


def test_modifiers_not_applied_are_listed(ref: ReferenceSet, config: Config) -> None:
    record = _record(_loop_scenario(), example_plant(), ref, config, {"SG-TRIP": YES})
    kinds = list(dict.fromkeys(m.kind for m in ref.modifiers))
    assert [m.kind for m in record.modifiers_not_applied] == kinds
    assert all(m.reason == MODIFIER_REASON for m in record.modifiers_not_applied)
    assert record.modifiers == []


def test_gap_is_mitigated_over_tolerable(ref: ReferenceSet, config: Config) -> None:
    """S5 with SG-TRIP credited: 0.1 x 0.1 = 1e-02 over S5's 1e-06 = 1e4, unrounded."""
    severe = finding(severity=SeverityClass.S5)
    record = _record(
        line_scenario(severe, section()), example_plant(), ref, config, {"SG-TRIP": YES}
    )
    tolerable = next(
        t.tolerable_per_year for t in ref.tolerable_frequencies if t.severity_class == "S5"
    )
    assert record.tolerable_per_year == tolerable
    assert record.mitigated_frequency_per_year == pytest.approx(0.1 * 0.1, rel=1e-12)
    assert record.gap == pytest.approx((0.1 * 0.1) / tolerable, rel=1e-12)
    assert record.gap == record.mitigated_frequency_per_year / tolerable  # type: ignore[operator]


def test_screening_and_lopa_read_the_same_likelihood(ref: ReferenceSet, config: Config) -> None:
    """P3-4 in both: C20 on a 200 mm line uses IE-PIPE-LEAK-L in screening and in LOPA."""

    def big_line(data: dict[str, Any]) -> None:
        data["lines"][0].update({"size_mm": 200, "length_m": 100})

    plant = example_plant(big_line)
    leak = finding(
        question="nf:L-12", cause="C20", kind=FailingComponentType.PIPE, components=("L-12",)
    )
    record = _record(line_scenario(leak, None), plant, ref, config, None)
    [screened] = rank_findings([leak], plant, ref, config.caps)
    assert record.initiating_event_id == screened.likelihood.initiating_event_id
    assert record.initiating_event_id == PIPE_LEAK_LARGE_EVENT
    assert record.initiating_frequency_per_year == screened.likelihood.frequency_per_year


def test_likelihood_flags_reach_the_record(ref: ReferenceSet, config: Config) -> None:
    def no_size(data: dict[str, Any]) -> None:
        data["lines"][0].pop("size_mm")
        data["lines"][0]["length_m"] = 100

    plant = example_plant(no_size)
    leak = finding(
        question="nf:L-12", cause="C20", kind=FailingComponentType.PIPE, components=("L-12",)
    )
    record = _record(line_scenario(leak, None), plant, ref, config, {})
    assert record.flags == list(likelihood(leak, plant, ref, config.caps).flags)
    assert record.flags == ["size assumed ≤ 150 mm (L-12.size_mm)"]


def test_an_assumed_frequency_is_flagged(ref: ReferenceSet, config: Config) -> None:
    odd = finding().model_copy(update={"cause_id": "outside_library", "cause_text": "firmware"})
    record = _record(line_scenario(odd, section()), example_plant(), ref, config, None)
    assert record.frequency_assumed is True
    assert record.flags == [FREQUENCY_ASSUMED_FLAG, CODE_ONLY_FLAG]
    # PROJECT.md section 5 Step 6.2's wording, the same as screening (Bhargavi, 2026-10-19)
    assert FREQUENCY_ASSUMED_FLAG == "frequency assumed — engineer to confirm"


def test_engine_is_pure(ref: ReferenceSet, config: Config) -> None:
    plant = example_plant()
    first = _record(_loop_scenario(), plant, ref, config, {"SG-TRIP": YES, "PSV-1": YES})
    again = _record(_loop_scenario(), plant, ref, config, {"PSV-1": YES, "SG-TRIP": YES})
    assert first == again
    assert first.model_dump_json() == again.model_dump_json()


# --- a chain's refusal names the link that caused it (Bhargavi, 2026-10-19) ----------------------


def _leak_and_loop_chain(*extra: Finding) -> tuple[Chain, Scenario]:
    leak = finding(
        question="nf:L-12", cause="C20", kind=FailingComponentType.PIPE, components=("L-12",)
    )
    loop = finding()
    links = [leak, loop, *extra]
    chain = Chain(
        id=ids.chain_id([f.id for f in links]),
        run_id=RUN,
        links=[f.id for f in links],
        description="d",
        reason="r",
        severity_class=SeverityClass.S4,
    )
    sections = {loop.id: section()}
    return chain, chain_scenario(chain, [(f, sections.get(f.id)) for f in links])


def test_a_chain_refusal_for_a_shared_component_names_the_link(ref: ReferenceSet) -> None:
    chain, scenario = _leak_and_loop_chain()
    plant = example_plant(
        _set_guard("SG-LINE", layer_type="IPL-SIS-SIL1", protects_id="MX-1", component_ids=["L-12"])
    )
    layer = credit(_guard(plant, "SG-LINE"), scenario, plant, ref, YES)
    leak_link = chain.links[0]
    assert not layer.credited
    assert (
        layer.reason == f"no credit — shares component L-12 with the cause (chain link {leak_link})"
    )


def test_a_chain_refusal_for_a_shared_loop_part_names_the_link(ref: ReferenceSet) -> None:
    """IPL-HUMAN on the failing loop's sensor: the loop is the second finding link."""
    chain, scenario = _leak_and_loop_chain()
    plant = example_plant(
        _set_guard("SG-ALARM", layer_type="IPL-HUMAN", protects_id="MX-1", component_ids=["TT-1"])
    )
    layer = credit(_guard(plant, "SG-ALARM"), scenario, plant, ref, YES)
    loop_link = chain.links[1]
    assert layer.reason == (
        f"no credit — shares sensor TT-1 with failing loop TIC-1 (chain link {loop_link})"
    )


def test_a_chain_refusal_for_a_layer_that_is_itself_failing_names_the_link(
    ref: ReferenceSet,
) -> None:
    relief = finding(
        question="relief:PSV-1",
        cause="C11",
        kind=FailingComponentType.RELIEF_DEVICE,
        components=("PSV-1",),
    )
    chain, scenario = _leak_and_loop_chain(relief)
    plant = example_plant()
    layer = credit(_relief(plant), scenario, plant, ref, YES)
    assert layer.reason == (
        f"no credit — PSV-1 is itself a failing component (chain link {relief.id})"
    )


def test_a_line_refusal_names_no_link(ref: ReferenceSet) -> None:
    plant = example_plant(
        _set_guard("SG-ALARM", layer_type="IPL-HUMAN", protects_id="MX-1", component_ids=["TT-1"])
    )
    layer = credit(_guard(plant, "SG-ALARM"), _loop_scenario(), plant, ref, YES)
    assert layer.reason == "no credit — shares sensor TT-1 with failing loop TIC-1"
