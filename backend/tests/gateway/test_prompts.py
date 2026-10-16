"""Loading and filling versioned prompts (plan R19)."""

from pathlib import Path

import pytest

from guideword.config import load_config
from guideword.gateway.prompts import load_prompt, render


def test_loads_the_version_named_in_routing_without_its_header() -> None:
    config = load_config(global_budget_usd=25.0)
    prompt = load_prompt("specialists/process", config)
    assert (prompt.name, prompt.version, prompt.label) == (
        "specialists/process",
        "v2",
        "specialists/process/v2",
    )
    assert prompt.body.startswith("You are the process deviations specialist")
    assert "Placeholders filled by code" not in prompt.body
    assert "{{context}}" in prompt.body


def test_a_prompt_not_in_routing_is_refused() -> None:
    with pytest.raises(KeyError):
        load_prompt("specialists/poetry", load_config(global_budget_usd=25.0))


def test_render_fills_each_placeholder_in_one_pass() -> None:
    body = "A {{context}} B {{questions}}"
    # data that itself looks like a placeholder is never expanded again
    text = render(body, {"context": "{{questions}}", "questions": "Q"})
    assert text == "A {{questions}} B Q"


def test_render_refuses_a_missing_or_an_unused_value() -> None:
    with pytest.raises(KeyError):
        render("{{context}} {{questions}}", {"context": "x"})
    with pytest.raises(KeyError):
        render("{{context}}", {"context": "x", "extra": "y"})


def test_every_specialist_prompt_has_its_placeholders() -> None:
    """Chemistry adds no questions (its questions have no section), so it has no cap to fill."""
    config = load_config(global_budget_usd=25.0)
    for agent in ("process", "chemistry", "piping", "procedures", "maintenance", "dust"):
        body = load_prompt(f"specialists/{agent}", config).body
        values = {"context": "C", "questions": "Q", "causes": "K"}
        if agent != "chemistry":
            values["max_added_questions"] = "2"
        assert "{{" not in render(body, values), agent


def test_prompts_dir_can_be_given(tmp_path: Path) -> None:
    config = load_config(global_budget_usd=25.0)
    (tmp_path / "section_suggestion").mkdir()
    (tmp_path / "section_suggestion" / "v1.md").write_text(
        "# head\n\n---\n\nBody {{x}}\n", encoding="utf-8"
    )
    assert load_prompt("section_suggestion", config, tmp_path).body == "Body {{x}}\n"


def test_test5a_prompt_has_only_the_package_placeholder() -> None:
    """5A sends the package text alone; the checklist and the answer schema are fixed text."""
    body = load_prompt("test5a", load_config(global_budget_usd=25.0)).body
    text = render(body, {"package": "P"})
    assert "{{" not in text
    assert "<package>\nP\n</package>" in text
    assert '"hazards"' in text and '"reason"' in text


def test_specialist_prompts_v2_rule_out_dismissing_for_missing_data() -> None:
    """Changed after the case D dev run: missing information or no fitting cause is never a
    reason for "not credible", and the failing-component mapping is stated per type (R46)."""
    config = load_config(global_budget_usd=25.0)
    for agent in ("process", "chemistry", "piping", "procedures", "maintenance", "dust"):
        body = load_prompt(f"specialists/{agent}", config).body
        assert "Missing information is never a reason" in body, agent
        assert "no listed cause or ID seems to fit" in body, agent
        assert "`control_loop`: a control loop, one of its instruments, or a control valve" in body
        assert "`regulator`: nothing in the plant file" in body, agent
