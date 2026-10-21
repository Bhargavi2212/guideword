"""Chain text without the connector's handles (target-handles plan, approved 2026-10-21).

After mapping, every `L<n>`/`P<n>` token in a chain's description and reason becomes the
mapped line's question ID (or "<question ID> (<cause ID>)" where two lines sent share it) or
the fact ID. A handle that was not sent is left as it is and flagged."""

from guideword.chains.connector import (
    HANDLES_REPLACED_FLAG,
    UNRESOLVED_HANDLE_FLAG,
    clean_chain_text,
    line_labels,
)

FACTS = {"P1": "HV-12.normal_position", "P2": "MX-1.design_pressure_kpa"}


def _line(question_id: str, cause_id: str, finding_id: str) -> dict[str, str]:
    return {"finding_id": finding_id, "question_id": question_id, "cause_id": cause_id}


def test_chain_text_handles_become_question_and_fact_ids() -> None:
    labels = line_labels(
        [
            _line("m:S-MX-1:more:temperature", "C01", "f:a"),
            _line("pair:KOH:SIH", "C30", "f:b"),
        ]
    )
    text, flags = clean_chain_text(
        "Steam stays on (L1) while HV-12 is shut (P1); then L2 reacts. L20x and PL1 stay.",
        labels,
        FACTS,
    )
    assert text == (
        "Steam stays on (m:S-MX-1:more:temperature) while HV-12 is shut "
        "(HV-12.normal_position); then pair:KOH:SIH reacts. L20x and PL1 stay."
    )
    assert flags == [HANDLES_REPLACED_FLAG]


def test_text_with_no_handle_is_unchanged_and_unflagged() -> None:
    labels = line_labels([_line("pair:KOH:SIH", "C30", "f:b")])
    assert clean_chain_text("Two reactive chemicals meet.", labels, FACTS) == (
        "Two reactive chemicals meet.",
        [],
    )


def test_an_unsent_handle_in_chain_text_is_left_and_flagged_unresolved() -> None:
    labels = line_labels([_line("pair:KOH:SIH", "C30", "f:b")])
    text, flags = clean_chain_text("L1 then L119 and P7.", labels, FACTS)
    assert text == "pair:KOH:SIH then L119 and P7."
    assert flags == [HANDLES_REPLACED_FLAG, UNRESOLVED_HANDLE_FLAG]
    text, flags = clean_chain_text("Only L9.", labels, FACTS)
    assert text == "Only L9." and flags == [UNRESOLVED_HANDLE_FLAG]


def test_two_lines_sharing_a_question_id_are_written_with_their_cause_id() -> None:
    """Bhargavi, Q4: each replacement names one line."""
    labels = line_labels(
        [
            _line("m:S-MX-1:more:temperature", "C01", "f:a"),
            _line("m:S-MX-1:more:temperature", "C03", "f:b"),
            _line("pair:KOH:SIH", "C30", "f:c"),
            # two outside-library causes on one question: the finding ID names the line
            _line("env:SIH:water", "outside_library", "f:d"),
            _line("env:SIH:water", "outside_library", "f:e"),
        ]
    )
    assert labels == {
        "L1": "m:S-MX-1:more:temperature (C01)",
        "L2": "m:S-MX-1:more:temperature (C03)",
        "L3": "pair:KOH:SIH",
        "L4": "f:d",
        "L5": "f:e",
    }
    text, _ = clean_chain_text("L1 and L2", labels, FACTS)
    assert text == "m:S-MX-1:more:temperature (C01) and m:S-MX-1:more:temperature (C03)"
