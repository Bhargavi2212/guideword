# Guideword

Guideword prepares a HAZOP study from a plant file. Code builds every question the study must answer (guideword × parameter per section, every chemical pair, every no-flow line, procedure step, planned job, dust and relief question). A Nemotron 3 Ultra orchestrator agent on Nebius Token Factory works through them with six specialist agents and tools, and code ranks the results by LOPA protection gap with evidence: physics calculations, accident precedent and a Tennessee Eastman simulation. Every number traces to a plant fact, a model call or a published reference table. The engineer decides.

Built for the Nebius × NVIDIA Global AI Hackathon (Best Apps and Agents). Licence: Apache 2.0.

## Setup (Windows, PowerShell)

```powershell
conda deactivate
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip pip-tools
pip-sync backend/requirements.txt backend/requirements-dev.txt
copy .env.example .env   # then fill in keys; never commit .env
pytest backend -q
```

Frontend: Node 22 LTS, `cd frontend; npm ci; npm run dev`.

See `PROJECT.md` for the full design and `CLAUDE.md` for contribution rules.
