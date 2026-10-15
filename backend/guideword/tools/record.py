"""Running a tool for an agent step (PROJECT.md §5 "Every tool argument is validated; every
tool call is logged before the next step").

`run_tool` validates the arguments, runs the tool, and records a `ToolCall` (with its event)
whether the call succeeded or was refused. A refusal returns its reason so the agent can
correct itself once; the agent loop decides what happens after that.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from guideword.reference import ReferenceSet
from guideword.runs.store import StepWriter
from guideword.schema import ids
from guideword.schema.plant import Plant
from guideword.schema.records import ToolCall
from guideword.tools.reactivity import ToolRefused, reactivity_lookup


class ReactivityArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    chemical_a: str
    chemical_b: str


@dataclass(frozen=True)
class _Tool:
    description: str
    arguments: type[BaseModel]
    run: Callable[[BaseModel, Plant, ReferenceSet], dict[str, Any]]


def _reactivity(args: BaseModel, plant: Plant, ref: ReferenceSet) -> dict[str, Any]:
    if not isinstance(args, ReactivityArgs):
        raise TypeError(f"reactivity_lookup got {type(args).__name__}")
    return reactivity_lookup(plant, ref, args.chemical_a, args.chemical_b)


# The agent tools that run in Phase 2; the rest arrive with their phases.
TOOLS: dict[str, _Tool] = {
    "reactivity_lookup": _Tool(
        "What the EPA 1980 compatibility chart says about two chemicals of this plant: hazard "
        "codes per pair of their reactive groups, not_listed (not proof of safety) or do_not_mix.",
        ReactivityArgs,
        _reactivity,
    )
}


@dataclass(frozen=True)
class ToolOutcome:
    call: ToolCall
    result: dict[str, Any] | None
    refused_reason: str | None


def execute_tool(
    run_id: str,
    step_id: str,
    tool: str,
    arguments: dict[str, Any],
    *,
    plant: Plant,
    ref: ReferenceSet,
) -> ToolCall:
    """Validate and run a tool; the ToolCall holds the result or the refused reason. Writes
    nothing, so it can run inside a parallel batch."""
    result: dict[str, Any] | None = None
    refused: str | None = None
    spec = TOOLS.get(tool)
    if spec is None:
        refused = f"{tool} is not a tool in this phase"
    else:
        try:
            parsed = spec.arguments.model_validate(arguments)
            result = spec.run(parsed, plant, ref)
        except ValidationError as error:
            refused = "bad arguments: " + "; ".join(
                f"{'.'.join(str(p) for p in e['loc']) or 'arguments'}: {e['msg']}"
                for e in error.errors()
            )
        except ToolRefused as error:
            refused = str(error)
    return ToolCall(
        id=ids.tool_call_id(step_id, tool, arguments),
        run_id=run_id,
        agent_step_id=step_id,
        tool=tool,
        arguments=arguments,
        result=result,
        refused_reason=refused,
    )


def run_tool(
    writer: StepWriter,
    step_id: str,
    tool: str,
    arguments: dict[str, Any],
    *,
    plant: Plant,
    ref: ReferenceSet,
) -> ToolOutcome:
    """Run a tool and record its ToolCall (with its event) in this step."""
    call = execute_tool(writer.run.id, step_id, tool, arguments, plant=plant, ref=ref)
    writer.add_tool_call(call)
    return ToolOutcome(call, call.result, call.refused_reason)
