# Sentinel — Autonomous Software Testing Agent Harness

[![CI & Quality Gate](https://github.com/raihan12121/Software-Testing-Agent-Harness/actions/workflows/ci.yml/badge.svg)](https://github.com/raihan12121/Software-Testing-Agent-Harness/actions/workflows/ci.yml)
[![Tests Passing](https://img.shields.io/badge/tests-105%20passed-brightgreen.svg)](tests/)
[![Coverage](https://img.shields.io/badge/coverage-80%25-brightgreen.svg)](tests/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Docker Support](https://img.shields.io/badge/docker-ready-2496ED.svg)](Dockerfile)

> **Sentinel** is an enterprise-grade autonomous software testing agent harness. It discovers, plans, generates, executes, and evaluates tests across **REST APIs, Web Frontends (Playwright), Databases (SQL with automatic rollback), CLI binaries, Mobile, Desktop, and IoT platforms** under strict safety guardrails, dual evaluation oracles, and collaborative multi-agent architecture.

---

## 📑 Table of Contents

- [Key Capabilities](#-key-capabilities)
- [System Architecture](#-system-architecture)
- [Quick Start](#-quick-start)
- [Interactive Project Testing (`sentinel test`)](#-interactive-project-testing)
- [CLI Reference](#-cli-reference)
- [Configuration File (`sentinel.config.yaml`)](#-configuration-file)
- [LLM Provider Integration (Claude & Mock)](#-llm-provider-integration)
- [Deployment Options](#-deployment-options)
  - [Cloud Deployment (Railway / Render / Koyeb)](#1-cloud-deployment-railway--render)
  - [Docker & Docker Compose (VPS / Server)](#2-docker--docker-compose-vps--server)
  - [Local Team Network (Office LAN)](#3-local-team-network-office-lan)
  - [GitHub Actions CI/CD](#4-github-actions-cicd)
- [Safety Guardrails & Policies (`rules.md`)](#-safety-guardrails--policies)
- [Testing & Quality Verification](#-testing--quality-verification)
- [License](#-license)

---

## 🌟 Key Capabilities

1. **Autonomous Target Discovery & Scanning**:
   Auto-detects OpenAPI 3.0/3.1 specs, SQLite databases, Web frontends, and CLI binaries in any directory without manual configuration.
2. **Collaborative Multi-Agent Generation**:
   Coordinates specialized subagents:
   - **Functional Agent**: Synthesizes happy-path flows and core business transactions.
   - **Adversarial Agent**: Challenges authorization boundaries, boundary limits, and malformed inputs.
   - **Security Generator**: Generates OWASP Top 10 attack payloads (SQLi, IDOR, XSS, SSRF, Command Injection).
3. **Cognitive Planning (Rule & Risk-Based)**:
   Analyzes endpoint schemas, defect histories, and flakiness metrics from SQLite persistent memory to prioritize high-risk paths.
4. **Dual Evaluation Oracles**:
   - **Deterministic Oracle**: Safe AST-based Python assertion engine (`ast.List`, `ast.Tuple`, `ast.Set`, comparisons, attributes).
   - **LLM-as-a-Judge**: Evaluates fuzzy, visual, and semantic outputs with calibrated confidence scoring and mandatory natural-language reasoning.
5. **Human-in-the-Loop Review Queue**:
   Verdicts with confidence under 75% or ambiguous assertions route to the review queue (`sentinel review` or Web Dashboard).
6. **Strict Blast-Radius Safety & Sandboxing**:
   - **R-SAFE-1**: Mutating requests are blocked by default unless `--allow-mutations` is passed.
   - **R-SAFE-2**: Production mutations require explicit confirmation flag `--yes-i-know-prod`.
   - **R-EXEC-1**: Database queries execute inside SQL `SAVEPOINT` transactions and are automatically rolled back.
   - **R-SEC-2**: Sensitive data (API keys, bearer tokens, JWTs, passwords) are scrubbed by `default_redactor` before prompts reach external LLMs.
7. **Live Web Dashboard & REST API**:
   Starlette/Uvicorn server providing team-wide test run monitoring, defect tracking, review queue resolution, and interactive reports.

---

## 🏗️ System Architecture

```
                                 ┌─────────────────────────────────┐
                                 │       Sentinel CLI / Engine     │
                                 │   (run, test, review, dashboard)│
                                 └────────────────┬────────────────┘
                                                  │
           ┌──────────────────┬───────────────────┼───────────────────┬──────────────────┐
           │                  │                   │                   │                  │
  ┌────────▼───────┐ ┌────────▼────────┐ ┌────────▼────────┐ ┌────────▼────────┐ ┌───────▼────────┐
  │    Planner     │ │   Generators    │ │    Executor     │ │     Oracle      │ │  Memory & Team │
  │ (Rule & Risk)  │ │ (Functional,    │ │ (Thread Pool,   │ │ (Deterministic, │ │ (SQLite Store, │
  │                │ │  Adversarial,   │ │  Timeouts, R-1) │ │  LLM Judge, Diff│ │  Defect Filer, │
  │                │ │  Security Attack│ │                 │ │  Review Queue)  │ │  Quarantine)   │
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

## 🚀 Quick Start

### Prerequisites
- Python 3.11, 3.12, or 3.13
- [uv](https://github.com/astral-sh/uv) (recommended) or `pip`

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/raihan12121/Software-Testing-Agent-Harness.git
cd Software-Testing-Agent-Harness

# Sync all dependencies including dev tools
uv sync --all-extras
```

### 2. Install Globally as a CLI Tool (Optional)
To run `sentinel` from any directory on your computer:

```bash
uv tool install .
```

Now you can invoke `sentinel` directly in PowerShell or Bash:
```bash
sentinel --help
```

---

## 🔍 Interactive Project Testing

Sentinel includes an interactive scanner that examines any project folder and detects testable targets automatically:

```bash
# Interactively scan the current folder
sentinel test

# Or point to a specific directory
sentinel test "D:/MyProject"
```

Sentinel will detect:
- 🌐 **OpenAPI Specifications** (`.yaml`, `.yml`, `.json`)
- 🗄️ **SQLite Databases** (`.sqlite`, `.db`)
- 💻 **Web Applications** (`index.html`, React/Vue frontends)
- ⚙️ **CLI binaries and Python packages** (`setup.py`, `pyproject.toml`)

Select the target and Sentinel automatically builds a test plan, generates test cases, executes them, and prints a formatted summary table.

---

## ⚡ CLI Reference

### Commands

| Subcommand | Description |
|---|---|
| `sentinel test [PATH]` | Interactive project scanner and test execution wizard. |
| `sentinel scan [PATH]` | Alias for interactive test wizard. |
| `sentinel run [OPTIONS]` | Execute an automated test suite or auto-plan against a target. |
| `sentinel review` | Open interactive CLI review queue for pending / uncertain test verdicts. |
| `sentinel dashboard` | Launch the team web dashboard and REST API on port 8080. |

### `sentinel run` Flags & Options

| Flag | Type / Choices | Default | Description |
|---|---|---|---|
| `--env` | `local`, `staging`, `sandbox`, `production` | *Required* | Target environment per R-EXEC-4. |
| `-d`, `--project-dir` | `PATH` | `None` | Project folder to scan and test in batch mode. |
| `--target` | `STRING` | `None` | Target specification path, URL, command, or database file. |
| `--target-type` | `api`, `web`, `cli`, `database`, `mobile`, `desktop`, `iot`, `perf`, `stub` | `stub` | Adapter type to invoke. |
| `--base-url` | `URL` | `None` | Override server URL without modifying OpenAPI specs. |
| `--llm-provider` | `auto`, `mock`, `anthropic` | `auto` | LLM implementation to use for generation and judge. |
| `--config` | `PATH` | `sentinel.config.yaml` | Configuration YAML file path. |
| `--test-file` | `PATH` | `None` | Custom pre-authored test cases JSON/YAML file. |
| `--format` | `json`, `html` | `json` | Test report format. |
| `--output-dir` | `PATH` | `reports` | Directory where reports and artifacts are saved. |
| `--parallelism` | `INT` | `1` | Number of worker execution threads. |
| `--timeout` | `FLOAT` | `30.0` | Execution timeout in seconds per test step. |
| `--allow-mutations` | Flag | `False` | Allow mutating actions (`POST`, `DELETE`, `UPDATE`) (R-SAFE-1). |
| `--yes-i-know-prod` | Flag | `False` | Explicit confirmation required for production mutations (R-SAFE-2). |
| `--explore` | Flag | `False` | Enable autonomous exploration mode (prohibited on production). |

#### Examples:

```bash
# 1. Test an API using declared spec URL
sentinel run --env staging --target examples/petstore_spec.yaml --target-type api --allow-mutations

# 2. Test an API with a custom base URL override
sentinel run --env staging --target examples/petstore_spec.yaml --target-type api --base-url http://localhost:8765 --allow-mutations

# 3. Test a database query with automatic transaction rollback
sentinel run --env local --target ./data/app.db --target-type database

# 4. Generate an HTML report in custom directory
sentinel run --env local --target "python" --target-type cli --format html --output-dir my_reports
```

---

## ⚙️ Configuration File

Sentinel supports a `sentinel.config.yaml` configuration file for managing environments, safety policies, and targets:

```yaml
version: "1.0"
project: "petstore-service"

target:
  target_type: "api"
  name: "Petstore API"
  spec_path: "examples/petstore_spec.yaml"
  base_url: "http://127.0.0.1:8765"
  allowed_hosts:
    - "127.0.0.1"
    - "localhost"

defaults:
  parallelism: 2
  timeout_seconds: 30.0
  retry_budget: 2
  output_dir: "reports"

environments:
  local:
    env_name: "local"
    allow_mutations: true

  staging:
    env_name: "staging"
    allow_mutations: true

  sandbox:
    env_name: "sandbox"
    allow_mutations: false

  production:
    env_name: "production"
    allow_mutations: false
    environment_ack: "I understand this targets production"
```

---

## 🤖 LLM Provider Integration

Sentinel features a unified LLM architecture designed for strict structured output and privacy:

- **`AnthropicLLMProvider`**: Powered by Anthropic Claude 3.5 Sonnet / Haiku using tool-calling structured output. Guarantees output matches Pydantic schemas.
- **`MockLLMProvider`**: Fast, deterministic offline mock provider used for unit testing, offline development, and CI environments without API keys.

### Setting up Claude:

1. Obtain an API key from [console.anthropic.com](https://console.anthropic.com).
2. Set the environment variable:
   ```bash
   # Linux / macOS
   export ANTHROPIC_API_KEY="sk-ant-api03-..."

   # Windows PowerShell
   $env:ANTHROPIC_API_KEY="sk-ant-api03-..."
   ```
3. Sentinel automatically detects `ANTHROPIC_API_KEY` and uses `AnthropicLLMProvider`.

### Built-in Privacy & Cost Instrumentation:
- **Redaction Engine (R-SEC-2)**: Prompts and system messages are automatically sanitized by `default_redactor` before transmission.
- **Metrics Tracking (R-BUILD-3)**: Every LLM call records prompt hash, token counts, duration (ms), and cost (USD).

---

## 🌐 Deployment Options

### 1. Cloud Deployment (Railway / Render)

Deploy the Sentinel Web Dashboard with persistent storage:

#### Via Railway (1-Click Docker)
1. Sign in to [railway.com](https://railway.com) using GitHub.
2. Select **New Project** → **Deploy from GitHub repo** → select `Software-Testing-Agent-Harness`.
3. Railway automatically detects the [`Dockerfile`](Dockerfile) and builds the container.
4. Under **Settings** → **Networking**, click **Generate Domain** (e.g. `sentinel-production.up.railway.app`).
5. *(Optional)* In **Variables**, add `ANTHROPIC_API_KEY` if using Claude.

#### Via Render
1. Create a free account at [render.com](https://render.com).
2. Click **New +** → **Web Service** → Connect your repository.
3. Choose **Docker** environment and set **Port** to `8080`.
4. Click **Create Web Service**.

---

### 2. Docker & Docker Compose (VPS / Server)

Deploy on any Ubuntu, Debian, or Windows server using Docker Compose:

```bash
# Clone the repository on your server
git clone https://github.com/raihan12121/Software-Testing-Agent-Harness.git
cd Software-Testing-Agent-Harness

# Start Sentinel Dashboard in detached mode
docker compose up -d --build
```

Access the dashboard at `http://<your-server-ip>:8080`.
Data is persisted in the `sentinel_data` Docker volume.

---

### 3. Local Team Network (Office LAN)

To share your dashboard with teammates on the same local network:

```powershell
uv run sentinel dashboard --host 0.0.0.0 --port 8080
```
Teammates can visit `http://<your-local-ip>:8080` in their browsers.

---

### 4. GitHub Actions CI/CD

Sentinel includes a full CI/CD verification workflow in `.github/workflows/ci.yml`.
On every commit and pull request:
1. Runs code quality inspection via Ruff.
2. Executes all 105 automated unit and regression tests with code coverage.
3. Runs an autonomous self-test against CLI targets.
4. Publishes interactive HTML test reports as build artifacts.

---

## 🛡️ Safety Guardrails & Policies (`rules.md`)

Sentinel enforces strict, non-negotiable safety guardrails:

| Rule | Description |
|---|---|
| **R-SAFE-1** | Never mutate an environment without explicit `--allow-mutations`. Mutating requests (`POST`, `PUT`, `DELETE`, `DROP`) are blocked by default. |
| **R-SAFE-2** | Production mutations require explicit confirmation flag `--yes-i-know-prod` and matching config token. |
| **R-SAFE-3** | Autonomous exploration mode (`--explore`) is strictly blocked from running on production. |
| **R-EXEC-1** | Database operations must execute within transactional savepoints (`SAVEPOINT`) and be rolled back after step completion. |
| **R-EXEC-2** | Tests that pass only after a retry are flagged as `flaky` and logged in the quarantine registry, not marked as simple passes. |
| **R-ORACLE-2** | LLM judge evaluations with confidence score below 0.75 are routed to the human review queue as `pending_review`. |
| **R-SEC-1** | API keys, passwords, and tokens are never hardcoded or logged in plaintext. |
| **R-SEC-2** | All outgoing prompts are scrubbed by `default_redactor` before calling external LLMs. |
| **R-BUILD-3** | Every LLM call records prompt hash, token counts, duration (ms), and cost (USD). |

---

## 🧪 Testing & Quality Verification

Run the entire test suite (105 tests across all adapters, generators, oracles, and safety gates):

```bash
# Run tests with summary
uv run pytest -q

# Run with test coverage report
uv run pytest --cov=sentinel --cov-report=term-missing

# Run code linter
uv run ruff check .
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
