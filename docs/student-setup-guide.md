# Student Setup Guide

## Data Pipelines Workshop — 2026

We will complete this setup **together during the first class**. You are not expected to install the course tools in advance. The goal of the session is to make sure that you can run Python code, work with Git, and launch Linux containers with Docker.

Bring the computer you plan to use during the course, its charger, and the credentials or administrator access required to install software. If your computer is managed by an employer or another organization, make sure you are allowed to install the required tools.

## 1. What you need

During the first class, we will install the following tools:

1. **Git** — source control and course repository access.
2. **Visual Studio Code** — the recommended code editor.
3. **Python** — for running scripts outside containers.
4. **Docker Desktop** — includes Docker Engine, the Docker CLI, and Docker Compose.

You will also need:

- A modern web browser.
- At least 10 GB of free disk space.
- Permission to install software on your computer.
- Hardware virtualization enabled. This is especially important on Windows.

> Kubernetes is part of the course, but we will not install a separate Kubernetes environment during the initial setup session. We will enable or install the required tools later.

## 2. Install Git

Download Git from the [official Git website](https://git-scm.com/downloads).

During installation, the default options are suitable for this course. Windows students may use either PowerShell or Git Bash, but the examples in class will generally use a Unix-style shell.

Open a new terminal and verify the installation:

```bash
git --version
```

The command should print a version number and exit without an error.

Configure the name and email that will appear in your commits:

```bash
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
```

Use your own name and an email address associated with your Git hosting account.

## 3. Install Visual Studio Code

Download and install [Visual Studio Code](https://code.visualstudio.com/Download).

Open VS Code and install these extensions from the Extensions view:

- **Python**, published by Microsoft.
- **Dev Containers**, published by Microsoft.
- **WSL**, published by Microsoft — Windows students only.

The Python interpreter and the Python extension are separate components; both must be installed. See the official [Python in VS Code quick start](https://code.visualstudio.com/docs/python/python-quick-start) if VS Code does not detect Python automatically.

Open the Command Palette in VS Code and run **Python: Select Interpreter**. Select the Python installation you intend to use for the course.

## 4. Install Python

Install a currently supported Python 3 release from [python.org](https://www.python.org/downloads/). Python 3.12 or newer is suitable for the course.

### Windows

Install Python using the official Python Install Manager or the installer from python.org. Close and reopen the terminal after installation.

Verify Python and `pip` in PowerShell:

```powershell
python --version
python -m pip --version
```

If `python` is not recognized but the `py` command works, use:

```powershell
py --version
py -m pip --version
```

### macOS and Linux

Open Terminal and run:

```bash
python3 --version
python3 -m pip --version
```

Do not replace or remove the Python version supplied by your operating system. Install an additional supported version if needed.

### Verify virtual environments

Create a temporary test directory and virtual environment.

On macOS or Linux:

```bash
mkdir course-setup-test
cd course-setup-test
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -c "print('Python setup OK')"
```

On Windows PowerShell:

```powershell
mkdir course-setup-test
cd course-setup-test
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -c "print('Python setup OK')"
```

If PowerShell blocks the activation script, you may use Command Prompt and run:

```bat
.venv\Scripts\activate.bat
```

The final command should print `Python setup OK`.

## 5. Install Docker Desktop

Install [Docker Desktop](https://docs.docker.com/desktop/) for your operating system. Docker Desktop includes Docker Engine, the Docker command-line client, and Docker Compose.

### Windows notes

Use the WSL 2 backend and Linux containers. Before installing Docker Desktop:

1. Confirm that hardware virtualization is enabled in BIOS/UEFI.
2. Install or update WSL from an Administrator PowerShell window:

   ```powershell
   wsl --install
   wsl --update
   wsl --version
   ```

3. Restart the computer if Windows requests it.
4. Install and start Docker Desktop.

Refer to Docker's current [Windows installation requirements](https://docs.docker.com/desktop/setup/install/windows-install/) if the installation reports a WSL or virtualization error.

### macOS notes

Download the correct Docker Desktop build for your processor:

- **Apple silicon** for M-series processors.
- **Intel** for older Intel-based Macs.

Start Docker Desktop and wait until it reports that the Docker engine is running.

### Linux notes

You may install Docker Desktop, or Docker Engine together with the Docker Compose plugin. Follow the instructions for your distribution. Do not use the legacy standalone `docker-compose` installation. The supported command used in this course is `docker compose` with a space.

See Docker's official [Compose installation guide](https://docs.docker.com/compose/install/).

## 6. Verify Docker and Docker Compose

Make sure Docker Desktop or Docker Engine is running, then execute:

```bash
docker version
docker compose version
docker run --rm hello-world
```

Expected result:

- `docker version` displays both a **Client** and a **Server** section.
- `docker compose version` displays a Compose version.
- The test container prints a `Hello from Docker!` message and exits.

Next, verify that Python runs inside a Linux container:

```bash
docker run --rm python:3.12-slim python -c "print('Container setup OK')"
```

The command should print `Container setup OK`.

## 7. End-of-class readiness check

Run the following commands in a new terminal:

```bash
git --version
docker version
docker compose version
```

Then verify your local Python command:

```bash
python3 --version
```

On Windows, use `python --version` or `py --version` instead.

By the end of the first class, all of the following should be true:

- [ ] Git prints a version number.
- [ ] VS Code opens and the Microsoft Python extension is installed.
- [ ] VS Code can select your Python interpreter.
- [ ] Python 3.12 or newer runs from the terminal.
- [ ] You can create and activate a virtual environment.
- [ ] `docker version` displays both Client and Server information.
- [ ] `docker compose version` works.
- [ ] The `hello-world` container runs successfully.
- [ ] The Python container prints `Container setup OK`.

## 8. Common problems

### The terminal cannot find a command

Close all terminal windows and open a new one. If the problem continues, restart the computer and verify that the program was added to your system's `PATH`.

### Docker shows Client information but no Server information

Docker Desktop is probably not running. Start it and wait for the engine to become ready. On Windows, also check that Docker Desktop is using Linux containers and the WSL 2 backend.

### Docker reports a virtualization or WSL error on Windows

Confirm that virtualization is enabled in BIOS/UEFI, update WSL with `wsl --update`, and restart Windows.

### VS Code uses the wrong Python version

Open the Command Palette, run **Python: Select Interpreter**, and choose the interpreter inside the project's `.venv` directory.

### A PowerShell activation script is blocked

Use Command Prompt with `.venv\Scripts\activate.bat`, or ask the course staff for help. Do not change organization-managed security policies without permission.

## 9. What not to install yet

Unless the course staff asks you to do so, do not install these tools during the initial setup session:

- A local database server.
- Kubernetes, Minikube, or Kind.
- Selenium browser drivers.
- Python packages such as Beautiful Soup, FastAPI, or database clients.

Course-specific services and Python dependencies will be provided through project files and containers so that everyone uses a reproducible environment.
