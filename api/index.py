"""The deployed site's API: one Vercel Python function (deploy plan D4).

It serves the recorded WG run from its committed export (cases/demo/recorded/), with no key: the
site's settings come from deploy/site.json, and the environment overrides any of them. Vercel
bundles the backend package and its data folders with this file (vercel.json `includeFiles`).
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

# imported once the package is on the path
from guideword.api.app import create_app
from guideword.settings import Settings

SITE = json.loads((ROOT / "deploy" / "site.json").read_text(encoding="utf-8"))
for key, value in SITE["env"].items():
    os.environ.setdefault(key, value)
# the recorded export, wherever the function's working folder is
recorded = Path(os.environ["GUIDEWORD_RECORDED_DIR"])
if not recorded.is_absolute():
    os.environ["GUIDEWORD_RECORDED_DIR"] = str(ROOT / recorded)

# no .env on the site: every setting is the environment's or deploy/site.json's
settings = Settings(_env_file=None)
app = create_app(settings=settings)
