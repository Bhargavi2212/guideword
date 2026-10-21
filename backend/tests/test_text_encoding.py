"""No tracked text file holds UTF-8 read back as cp1252 ("â€" where a dash should be): such
text reaches the cards and the worksheet garbled."""

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
# the first two characters of an en or em dash, a quote or an ellipsis after a bad round trip
MISDECODED = "â€"


def test_no_tracked_text_file_is_double_encoded() -> None:
    listed = subprocess.run(
        ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.split("\n")
    bad = []
    for name in filter(None, listed):
        path = REPO / name
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
        if MISDECODED in text and path != Path(__file__):
            bad.append(name)
    assert bad == []
