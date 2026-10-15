"""Fixed, neutral question templates (spec 1.4).

Filled only with IDs, names and enum values. They never add facts, hints or causes, and
never read `notes` or free text such as procedure step text.
"""

from guideword.schema.enums import Guideword, HazopParameter


def _words(value: str) -> str:
    return value.replace("_", " ")


def matrix(
    section_id: str, section_type: str, guideword: Guideword, parameter: HazopParameter
) -> str:
    return (
        f"{_words(guideword.value).capitalize()} {_words(parameter.value)} in {section_id} "
        f"({_words(section_type)}): what could cause it, what would happen, "
        "and is the existing protection adequate?"
    )


def chemical_pair(a: str, a_name: str, b: str, b_name: str) -> str:
    return (
        f"{a} ({a_name}) and {b} ({b_name}): could they come into contact anywhere in the "
        "plant, and what would happen if they did?"
    )


def chemical_environment(chemical: str, name: str, environment: str) -> str:
    return (
        f"{chemical} ({name}) with {environment}: what would happen on contact or exposure, "
        "and is the existing protection adequate?"
    )


def no_flow_line(line: str, no_flow: list[str]) -> str:
    return (
        f"No-flow line {line} ({', '.join(_words(n) for n in sorted(no_flow))}): what could "
        "accumulate there or be missing, and what would happen?"
    )


def procedure_step(step: str, procedure: str, kind: str, guideword: Guideword) -> str:
    return (
        f"Step {step} of {procedure} ({_words(kind)}), {_words(guideword.value)}: what could "
        "cause it, what would happen, and is the existing protection adequate?"
    )


def planned_work(job: str, work_type: str, target: str) -> str:
    if target == job:
        return (
            f"Planned job {job} ({_words(work_type)}): what could it affect, and are the "
            "existing isolation and protection adequate?"
        )
    return (
        f"Planned job {job} ({_words(work_type)}) and {target}: what could the work affect or "
        "be affected by, and are the existing isolation and protection adequate?"
    )


def dust(equipment: str, equipment_type: str) -> str:
    return (
        f"Dust and ignition in {equipment} ({_words(equipment_type)}): could a combustible dust "
        "cloud form and ignite, and is the existing protection adequate?"
    )


def relief_discharge(device: str, protects: str) -> str:
    return (
        f"Relief device {device} on {protects}: where does it discharge, what is there "
        "(people, ignition sources, other equipment), and is that acceptable?"
    )
