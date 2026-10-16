"""The orchestrator's tools in Phase 2 (spec 2.5): argument models and the schemas offered.

Later tools (`web_research`, `search_precedent`, `physics_calc`, `propose_chains`,
`run_lopa`, `run_simulation`) are not offered at all, so the model cannot ask for them.
Every tool carries a one-line `reason`, which becomes the agent step's reason.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Reason = Annotated[str, StringConstraints(min_length=1, max_length=200)]
AgentName = Literal["process", "chemistry", "piping", "procedures", "maintenance", "dust"]


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Reason


class CheckCoverage(_Args):
    pass


class Dispatch(_Args):
    agent: AgentName
    level: Literal["bulk", "hard", "unsure"] = "bulk"
    # left out: code picks the next questions for this agent at this level (R44)
    question_ids: Annotated[list[str], Field(min_length=1)] | None = None
    # with question_ids left out: the questions linked to the priority hypotheses first (2b.3)
    priority: bool = False


class Reactivity(_Args):
    chemical_a: str
    chemical_b: str


class Finish(_Args):
    pass


ARGUMENTS: dict[str, type[_Args]] = {
    "check_coverage": CheckCoverage,
    "dispatch_specialist": Dispatch,
    "reactivity_lookup": Reactivity,
    "finish": Finish,
}

DESCRIPTIONS = {
    "check_coverage": "The current coverage counts and the open, failed and unsure question IDs.",
    "dispatch_specialist": (
        "Send questions to one specialist agent. Leave question_ids out to send the next ones for "
        "that agent at that level; code batches them and runs the batches in parallel. "
        "With priority true, code sends the questions linked to the priority hazards first."
    ),
    "reactivity_lookup": (
        "What the EPA 1980 compatibility chart says about two chemicals of this plant."
    ),
    "finish": "End the analysis. Refused while any question is open.",
}


def tool_schemas() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": DESCRIPTIONS[name],
                "parameters": model.model_json_schema(),
            },
        }
        for name, model in ARGUMENTS.items()
    ]
