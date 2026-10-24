"""B2 (Q9, Q13, standing rule): a script that starts or extends a run names its use; there is
no default, because a run's use is fixed when it starts."""

from types import ModuleType

import extend_run
import pytest
import run_case
import screen_check


@pytest.mark.parametrize(
    ("script", "argv", "use"),
    [
        (extend_run, ["run:x"], "video"),
        (run_case, ["plant.json"], "video"),
        (screen_check, ["plant.json", "--cap", "0.05"], "test_5"),
    ],
    ids=["extend_run", "run_case", "screen_check"],
)
def test_the_script_requires_use(
    script: ModuleType, argv: list[str], use: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit):
        script._arguments(argv)
    assert "--use" in capsys.readouterr().err
    assert script._arguments([*argv, "--use", use]).use == use
