# Deploying the site (deploy plan D4)

The deployed site is the no-key landing on the recorded WG run: the frontend's static build, and
the API as one Vercel Python function that reads the run from its committed export
(`cases/demo/recorded/williams_geismar/`). It holds no key and cannot spend: it runs `hosted`,
every override on the recorded run gets 403, and no route calls a model or a search.

Bhargavi runs these steps; Claude Code never deploys (CLAUDE.md §4: outward-facing).

## Once

```powershell
npm i -g vercel          # a tool on your machine, not a repo dependency
vercel login
cd D:\Hackathon\guideword\guideword
vercel link              # a new project; framework "Other"
```

In the project's settings, set **no** environment variables. Every setting the site needs is in
`deploy/site.json` (not secret); never add `NEBIUS_API_KEY` or `TAVILY_API_KEY`.

## Each deploy

```powershell
cd D:\Hackathon\guideword\guideword
git switch main; git pull
vercel --prod
```

Vercel runs `vercel.json`: `npm ci` and `npm run build` in `frontend/`, served from
`frontend/dist`; the Python function `api/index.py` with the backend package, `config/`,
`prompts/`, `reference/`, `deploy/` and the recorded export bundled; and the rewrites that send
`/plants`, `/runs`, `/budget` and `/demo` to it.

Send Claude Code the production URL. It checks:

```powershell
curl https://<site>/demo                     # 200, the WG run, labelled recorded, start line named
curl https://<site>/runs/run%3A76f8ee0b5d1f078e/shortlist
```

and that the landing opens on the WG shortlist with the rank-2 startup chain marked "start here".

## After acceptance 4 (deploy plan done-when)

When the engineer's S3 → S4 override is made on `guideword-demo.db`, rerun the export, commit it
in a PR, and redeploy:

```powershell
python scripts/export_recorded.py run:76f8ee0b5d1f078e --store guideword-demo.db --out cases/demo/recorded/williams_geismar
```

## Later PRs

F3, F4, F5 and F6 each redeploy with `vercel --prod` once merged.
