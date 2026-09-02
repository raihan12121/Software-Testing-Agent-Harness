# Sentinel — Autonomous Software Testing Agent Harness

> An intelligent, autonomous software testing agent harness that discovers, plans, generates, executes, and evaluates tests across APIs, Web applications, CLI tools, Databases, Mobile, and IoT platforms with strict safety guardrails and dual oracles.

[![CI & Quality Gate](https://github.com/raihan12121/Software-Testing-Agent-Harness/actions/workflows/ci.yml/badge.svg)](https://github.com/raihan12121/Software-Testing-Agent-Harness/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Coverage: 82%](https://img.shields.io/badge/coverage-82%25-brightgreen.svg)](tests/)

---

## 🚀 Quick Start

### 1. Installation
Requires Python 3.11+ and [uv](https://github.com/astral-sh/uv):

```bash
# Clone the repository
git clone https://github.com/raihan12121/Software-Testing-Agent-Harness.git
cd Software-Testing-Agent-Harness

# Install dependencies
uv sync
```

### 2. Run Sentinel Interactively on Any Project
Point Sentinel to any directory or codebase:

```bash
uv run sentinel test
```
Sentinel automatically scans the folder, detects testable targets (OpenAPI specs, SQLite databases, Web frontends, CLI tools), and executes the test suite.

---

## ⚡ Core CLI Commands

| Command | Description |
|---|---|
| `sentinel test [PATH]` | Interactively choose a project folder, auto-detect targets, and run tests. |
| `sentinel run -d <DIR> --env local` | Auto-detect and test a project directory in batch mode. |
| `sentinel run --target <SPEC> --target-type api --env staging` | Run against an OpenAPI specification file. |
| `sentinel run --target <URL> --target-type web --env staging` | Run browser UI automation tests via Playwright. |
| `sentinel run --target <CMD> --target-type cli --env local` | Test command line tools and verify exit codes/output. |
| `sentinel run --target <DB_FILE> --target-type database --env local` | Test database queries with automatic transaction rollback. |
| `sentinel review` | Inspect and resolve ambiguous LLM judge test decisions. |
| `sentinel dashboard --port 8080` | Start the live team monitoring web dashboard and REST API. |

---

## 🌐 Deploying Sentinel (So Everyone Can Use It)

### Option A: One-Click Cloud Deployment (Render / Railway / Fly.io)

You can host the **Sentinel Web Dashboard** on any cloud container service for your team:

#### Deploy to Render (Free / Cheap Cloud Hosting):
1. Create a free account at [render.com](https://render.com).
2. Click **New +** → **Web Service**.
3. Connect your GitHub repository: `https://github.com/raihan12121/Software-Testing-Agent-Harness.git`.
4. Render will automatically detect the `Dockerfile`.
5. Set:
   - **Environment**: Docker
   - **Port**: 8080
6. Click **Deploy Web Service**.
7. In ~2 minutes, Render gives you a public URL (e.g. `https://sentinel-dashboard.onrender.com`) that anyone can open in their browser to view reports, trends, and review queues!

---

### Option B: Deploy on Your Server / VPS with Docker Compose

If you have a Linux/Windows VPS or on-premise server:

```bash
# Start Sentinel Dashboard in the background
docker compose up -d
```
Access the dashboard on port `8080`: `http://your-server-ip:8080`.

---

### Option C: Team CI/CD Pipeline (GitHub Actions)

Sentinel includes a ready-to-use GitHub Actions workflow in `.github/workflows/ci.yml`.
Whenever anyone on your team pushes code or creates a Pull Request:
1. Sentinel runs automated regression suites.
2. It generates an interactive HTML report.
3. The report is published directly to GitHub Actions artifacts.

---

## 🏗️ Architecture

```
                               ┌─────────────────────────────────┐
                               │       Sentinel CLI / Engine     │
                               │   (run, plan, review, dashboard)│
                               └────────────────┬────────────────┘
                                                │
         ┌──────────────────┬───────────────────┼───────────────────┬──────────────────┐
         │                  │                   │                   │                  │
┌────────▼───────┐ ┌────────▼────────┐ ┌────────▼────────┐ ┌────────▼────────┐ ┌───────▼────────┐
│    Planner     │ │   Generators    │ │    Executor     │ │     Oracle      │ │  Memory & Team │
│ (Rule & Risk)  │ │ (LLM, Security, │ │ (Thread Pool,   │ │ (Deterministic, │ │ (SQLite, Audits│
│                │ │  Multi-Agent)   │ │  Timeouts, R-1) │ │  LLM Judge, Diff)│ │  Quarantine)   │
└────────────────┘ └─────────────────┘ └────────┬────────┘ └─────────────────┘ └────────────────┘
                                                │
                       ┌────────────────────────▼────────────────────────┐
                       │                   ADAPTER LAYER                  │
                       │ ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐│
                       │ │  API  │ │  Web  │ │  CLI  │ │  DB   │ │Mobile ││
                       │ └───────┘ └───────┘ └───────┘ └───────┘ └───────┘│
                       │ ┌───────┐ ┌───────┐ ┌───────┐ ┌───────────────┐ │
                       │ │Desktop│ │ Perf  │ │  IoT  │ │     Stub      │ │
                       │ └───────┘ └───────┘ └───────┘ └───────────────┘ │
                       └─────────────────────────────────────────────────┘
```

---

## 🛡️ Hard Safety Rules (`rules.md`)

- **R-SAFE-1**: Never mutate production without explicit `--allow-mutations` and `--yes-i-know-prod`.
- **R-SAFE-3**: Autonomous explore mode is strictly prohibited from running against production.
- **R-EXEC-1**: Database testing uses transactional savepoints (`SAVEPOINT`) and rolls back automatically.
- **R-ORACLE-2**: LLM-as-judge confidence below 75% routes to the human review queue.
- **R-SEC-1/2/3**: Automated redaction engine scrubs all API keys, bearer tokens, and PII before persistence or LLM invocation.

---

## 🧪 Testing

Run all 98 automated unit tests and adapter conformance suites:

```bash
uv run pytest -v
```

---

## 📄 License
MIT License.
