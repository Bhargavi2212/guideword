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
        "v1",
        "specialists/process/v1",
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
