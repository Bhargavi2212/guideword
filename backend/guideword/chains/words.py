"""Targets in words, named by handle, for the three later post-step prompts (target-handles plan,
approved 2026-10-21).

`severity_chain/v2`, `lopa_argument/v2` and `recommendation/v2` show no finding ID and no chain
ID: each target is a handle (`L<n>` for a line, `C<n>` for a chain, numbered in the order sent),
and a link is shown in words (a finding's question ID, cause, consequence and failing
components; a fact's ID and value). Code maps each handle back to its target exactly. The list
is never called a batch: each call states its count and handles (`count_text`).
"""

from collections.abc import Mapping, Sequence
from typing import Any

from guideword.lopa.lines import cause_words
from guideword.schema.records import Chain, Finding


def link_words(
    link: str,
    findings: Mapping[str, Finding],
    facts: Mapping[str, Any],
    causes: Mapping[str, str],
) -> dict[str, Any]:
    found = findings.get(link)
    if found is not None:
        return {
            "question_id": found.question_id,
            "cause": cause_words(found, causes),
            "consequence": found.consequence,
            "failing_component_ids": list(found.failing_component_ids),
        }
    return {"fact_id": link, "value": facts.get(link)}


def chain_words(
    chain: Chain,
    findings: Mapping[str, Finding],
    facts: Mapping[str, Any],
    causes: Mapping[str, str],
) -> dict[str, Any]:
    return {
        "description": chain.description,
        "links": [link_words(link, findings, facts, causes) for link in chain.links],
    }


def line_words(lead: Finding, causes: Mapping[str, str], section_id: str | None) -> dict[str, Any]:
    return {
        "question_id": lead.question_id,
        "cause": cause_words(lead, causes),
        "consequence": lead.consequence,
        "failing_component_ids": list(lead.failing_component_ids),
        "section_id": section_id,
    }


def handles_for(is_chain: Sequence[bool]) -> list[str]:
    """`L1, L2, …` for lines and `C1, C2, …` for chains, each counted in the order sent."""
    lines = chains = 0
    out = []
    for chain in is_chain:
        if chain:
            chains += 1
            out.append(f"C{chains}")
        else:
            lines += 1
            out.append(f"L{lines}")
    return out


def count_text(handles: Sequence[str]) -> dict[str, str]:
    """The code-only `{{count}}` and `{{handles}}` slots: how many were sent, and which."""
    return {"count": str(len(handles)), "handles": ", ".join(handles)}
