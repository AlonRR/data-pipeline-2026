---
name: contributing-check
description: Verify a change in this repo (data-pipelines-workshop-2026) follows CONTRIBUTING.md before committing, pushing, or opening a pull request. Use whenever the user asks to commit, submit, push, or open a PR for an assignment, or asks "am I ready to submit" / "is this ready for a PR". Checks commit message format, folder scope, and for accidentally staged secrets/venv/data/log files.
---

# Contributing check

This repo's submission rules live in `CONTRIBUTING.md` (summarized in `CLAUDE.md`). Run this checklist before letting a commit, push, or PR go out. Report every violation found — do not silently fix and move on without telling the user what was wrong.

## 1. Check what's staged/changed

```bash
git status
git diff --cached --stat
```

## 2. Reject forbidden files

Fail the check if any of these appear in `git status` (staged or untracked-but-about-to-be-added) output:

- `.venv/`, `venv/`, `__pycache__/`, `*.pyc`
- `.env` or any secret/credential-looking file (not `.env.example`)
- `data/raw/`, `logs/`, `*.log`
- `.vscode/`, `.idea/`, `.DS_Store`

If any are present, tell the user exactly which files and that they must be unstaged (`git restore --staged <file>`) — do not commit them, and do not delete the user's files without asking.

## 3. Check folder scope

Confirm changed files live under a single `assignments/<assignment-name>/` folder (plus, if genuinely needed, docs the assignment explicitly asks to update). Flag it if the diff touches:

- Another student's/other assignment's folder
- Shared root files (`README.md`, `CONTRIBUTING.md`, `CLAUDE.md`, `.gitignore`) unless the task is specifically about updating course materials, not an assignment submission

## 4. Check the commit message

Conventional Commits format: `<type>(<scope>): <description>`, type one of `feat|fix|docs|style|refactor|test|chore`.

If the user gives you a commit message (or asks you to write one), verify/produce one matching this format. Reject vague messages like "update", "wip", "fix stuff".

## 5. Check the branch

Confirm the branch isn't `main`/`master`. Assignment work should be on a descriptively named branch (e.g. `assignment-2-web-scraping`).

## 6. Report

Summarize pass/fail per section above in a short list. Only proceed with `git commit` / `git push` / PR creation once all checks pass or the user explicitly accepts a flagged item.
