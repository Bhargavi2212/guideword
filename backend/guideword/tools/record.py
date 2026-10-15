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
    arguments: type[BaseModel]
    run: Callable[[BaseModel, Plant, ReferenceSet], dict[str, Any]]


def _reactivity(args: BaseModel, plant: Plant, ref: ReferenceSet) -> dict[str, Any]:
    if not isinstance(args, ReactivityArgs):
        raise TypeError(f"reactivity_lookup got {type(args).__name__}")
    return reactivity_lookup(plant, ref, args.chemical_a, args.chemical_b)


# The agent tools that run in Phase 2; the rest arrive with their phases.
TOOLS: dict[str, _Tool] = {"reactivity_lookup": _Tool(ReactivityArgs, _reactivity)}


@dataclass(frozen=True)
class ToolOutcome:
    call: ToolCall
    result: dict[str, Any] | None
    refused_reason: str | None


def run_tool(
    writer: StepWriter,
    step_id: str,
    tool: str,
    arguments: dict[str, Any],
    *,
    plant: Plant,
    ref: ReferenceSet,
) -> ToolOutcome:
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
    call = ToolCall(
        id=ids.tool_call_id(step_id, tool, arguments),
        run_id=writer.run.id,
        agent_step_id=step_id,
        tool=tool,
        arguments=arguments,
        result=result,
        refused_reason=refused,
    )
    writer.add_tool_call(call)
    return ToolOutcome(call, result, refused)
