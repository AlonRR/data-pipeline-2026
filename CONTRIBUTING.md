# 🧑‍💻 Contributing to the Course Repository

Welcome! 👋
If you're a student in the **Data Pipelines Workshop — 2026**, this guide walks you through submitting your assignments via GitHub.

---

## 📦 Step 1: Fork the Repository

1. Click the **"Fork"** button at the top-right corner of this page.
2. Choose your own GitHub account as the destination.
3. Wait for GitHub to create a copy of the repository under your account.

---

## 💻 Step 2: Clone Your Fork

After forking, open your terminal and run:

```bash
git clone https://github.com/<your-username>/<repo-name>.git
cd <repo-name>
```

> 🔁 Replace `<your-username>` and `<repo-name>` with your actual GitHub username and the repository name.

If you haven't set up Git, Python, or Docker yet, complete the [Student Setup Guide](docs/student-setup-guide.md) first.

---

## 🌱 Step 3: Create a Branch

```bash
git checkout -b assignment-1
```

Use a descriptive branch name per assignment (e.g. `assignment-2-web-scraping`).

---

## ✏️ Step 4: Work on the Assignment

Follow the instructions in the assignment's `README.md` file. Make sure your work is:

- Inside the correct assignment folder (e.g. `assignments/<assignment-name>`) — don't modify files outside your assignment folder or shared course materials.
- Runnable with the Python version and Docker setup from the [Student Setup Guide](docs/student-setup-guide.md) (Python 3.12+, `docker compose` with a space — not the legacy `docker-compose`).
- Free of committed secrets, virtual environments, or local data — see [What not to commit](#-what-not-to-commit) below.
- Documented where the logic isn't self-explanatory.

---

## ✅ Commit Message Conventions

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>
```

**Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

**Examples:**

```bash
git commit -m "feat(crawler): add lady gaga news scraper"
git commit -m "fix(pipeline): handle empty CSV files gracefully"
git commit -m "docs(readme): update installation instructions"
```

---

## 🚫 What Not to Commit

This repo's `.gitignore` already excludes these — never force-add them:

- `.venv/`, `venv/`, `__pycache__/`
- `.env` and other secret/credential files (`.env.example` is fine)
- `data/raw/`, `logs/`, `*.log`
- Editor/OS files (`.vscode/`, `.idea/`, `.DS_Store`)

If an assignment needs sample data, document how to fetch or generate it instead of committing raw data.

---

## 📤 Step 5: Commit and Push

```bash
git add .
git commit -m "feat: add lady gaga crawler assignment"
git push origin assignment-1
```

---

## 📬 Step 6: Open a Pull Request

1. Go to your fork on GitHub.
2. Click **"Compare & pull request"**.
3. Add a title and short description of what you did.
4. Add a label with your name to the pull request.
5. Click **"Create pull request"**.

That's it! 🎉

---

## 🧪 Before Submitting

- ✅ Did you test your code locally (and in Docker, if applicable)?
- ✅ Is it inside the correct assignment folder?
- ✅ Did you write a meaningful, conventional commit message?
- ✅ Did you check `git status` to confirm no secrets, `.venv/`, or raw data are staged?

---

## 📅 Deadlines

Make sure to submit your pull request **before the deadline** listed in the assignment instructions.

---

If you have any questions, feel free to open an Issue or ask in class!

Happy coding! 💻✨
