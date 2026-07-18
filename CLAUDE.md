# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Repository purpose

This is the course repository for Shenkar's **Data Pipelines Workshop — 2026** (course 3500834). Students fork this repo and submit assignments as pull requests. Topics covered over the semester: data pipelines & dev environment, web scraping/crawling, APIs, data cleaning/enrichment/storage, Docker/Compose/Kubernetes, high-scale architecture and observability, and a final project.

Current structure:
- `README.md` — course overview
- `docs/student-setup-guide.md` — Git, VS Code, Python 3.12+, Docker Desktop setup
- `assignments/<assignment-name>/` — per-assignment work (created as assignments are published)
- `CONTRIBUTING.md` — the submission workflow and rules students must follow

## Rules to enforce

All contribution rules live in [CONTRIBUTING.md](CONTRIBUTING.md). When helping a student (or reviewing their work), enforce it:

- **Commits** follow Conventional Commits: `<type>(<scope>): <description>` with types `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`. Never write or suggest a commit message that doesn't fit this format.
- **Scope of changes**: work stays inside the relevant `assignments/<assignment-name>/` folder. Don't edit shared course materials, other students' assignment folders, or repo-root config files as part of an assignment.
- **Never stage or commit**: `.venv/`, `venv/`, `__pycache__/`, `.env`/secret files, `data/raw/`, `logs/`, `*.log`, editor/OS files (`.vscode/`, `.idea/`, `.DS_Store`). If a change requires new data, document how to fetch/generate it — don't commit raw data.
- **Environment**: Python 3.12+, and `docker compose` (space) — never the legacy hyphenated `docker-compose` binary.
- **Branches**: one branch per assignment, named descriptively (e.g. `assignment-2-web-scraping`).
- **Before submitting**: code should be tested locally (and in Docker if the assignment uses containers), placed in the correct folder, and checked with `git status` for anything that shouldn't be committed.

Use the `contributing-check` skill before finalizing a commit or opening a PR in this repo to verify these rules are actually met, not just recalled.

## Notes

- This repo has no `DEVELOPMENT_GUIDELINES.md` — commit conventions and coding expectations live directly in `CONTRIBUTING.md`; keep the two in sync if either changes.
- Don't invent folder structure ahead of actual assignments — only create `assignments/<name>/` when an assignment exists to put there.
