# Sentinel — Autonomous Software Testing Agent Harness

[![CI & Quality Gate](https://github.com/raihan12121/Software-Testing-Agent-Harness/actions/workflows/ci.yml/badge.svg)](https://github.com/raihan12121/Software-Testing-Agent-Harness/actions/workflows/ci.yml)
[![Tests Passing](https://img.shields.io/badge/tests-126%20passed-brightgreen.svg)](tests/)
[![Coverage](https://img.shields.io/badge/coverage-76%25-brightgreen.svg)](tests/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Docker Support](https://img.shields.io/badge/docker-ready-2496ED.svg)](Dockerfile)
[![Code Style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

> **Sentinel** is an enterprise-grade autonomous software testing agent harness and quality engineering platform. It autonomously discovers, plans, generates, executes, and evaluates test suites across **REST APIs, Web Frontends (Playwright), Databases (SQL & NoSQL with automatic rollback), CLI binaries, Mobile (Appium), Desktop (UI Automation), IoT platforms (MQTT & Serial UART), and Performance load testing**. All operations execute under strict blast-radius safety guardrails, dual deterministic and LLM-as-a-judge oracles, self-healing selectors, and collaborative multi-agent architecture.

---

## 📑 Table of Contents

- [Key Capabilities](#-key-capabilities)
- [Universal Adapter Support Matrix](#-universal-adapter-support-matrix)
- [System Architecture](#-system-architecture)
- [Quick Start](#-quick-start)
  - [Prerequisites](#prerequisites)
  - [Installation](#1-installation)
  - [Global CLI Installation](#2-install-globally-as-a-cli-tool-optional)
- [Interactive Project Testing (`sentinel test`)](#-interactive-project-testing)
- [CLI Reference](#-cli-reference)
  - [Subcommands](#subcommands)
  - [`sentinel run` Options & Flags](#sentinel-run-options--flags)
  - [Practical Command Examples](#practical-command-examples)
- [Configuration File (`sentinel.config.yaml`)](#-configuration-file)
- [LLM Provider Architecture & Data Privacy](#-llm-provider-architecture--data-privacy)
  - [Supported Providers](#supported-providers)
  - [Zero Data Leakage Redaction (R-SEC-2)](#zero-data-leakage-redaction-r-sec-2)
  - [Cost & Latency Instrumentation (R-BUILD-3)](#cost--latency-instrumentation-r-build-3)
- [Human-in-the-Loop Review Queue & Defect Management](#-human-in-the-loop-review-queue--defect-management)
- [Web Dashboard & REST API](#-web-dashboard--rest-api)
- [Deployment Options](#-deployment-options)
  - [1. Cloud Deployment (Railway / Render / Koyeb)](#1-cloud-deployment-railway--render)
  - [2. Docker & Docker Compose (VPS / Server)](#2-docker--docker-compose-vps--server)
  - [3. Local Team Network (LAN)](#3-local-team-network-lan)
  - [4. GitHub Actions CI/CD Pipeline](#4-github-actions-cicd-pipeline)
  - [5. Scheduled Nightly Autonomous Exploration](#5-scheduled-nightly-autonomous-exploration)
- [Safety Guardrails & Policies (`rules.md`)](#-safety-guardrails--policies)
- [Testing & Quality Verification](#-testing--quality-verification)
- [Phased Implementation Roadmap](#-phased-implementation-roadmap)
- [License](#-license)

---

## 🌟 Key Capabilities

1. **Autonomous Target Discovery & Interactive Wizard**:
   - Automatically detects OpenAPI 3.0/3.1 specifications, SQLite databases, Web frontends, and CLI binaries in any directory via `sentinel test` / `sentinel scan` without manual configuration.
2. **Collaborative Multi-Agent Generation**:
   - Deploys specialized subagent personas working together:
     - **Functional Agent**: Synthesizes happy-path business workflows and standard CRUD transactions.
     - **Adversarial Agent**: Challenges authorization boundaries, invalid types, extreme lengths, and edge cases.
     - **Security Test Generator**: Synthesizes non-destructive OWASP Top 10 probes (SQL injection, BOLA/IDOR, XSS, SSRF, Command Injection) under strict R-SAFE guardrails.
   - Pydantic schema validation, LLM repair-and-retry loops, and structural deduplication eliminate redundant scenarios.
3. **Cognitive & Risk-Based Planning**:
   - Employs rule-based testing techniques (equivalence partitioning, boundary value analysis, CRUD coverage matrix, auth checklists).
   - Integrates SQLite persistent memory metrics: prioritizes high-risk components using historical defect clustering, flaky test quarantine records, and git-diff recency scoring.
4. **Dual Evaluation Oracles & Visual Regression**:
   - **Deterministic AST Oracle**: Safe Python expression parser evaluating assertions (`ast.List`, `ast.Tuple`, `ast.Set`, status codes, body attributes, regex matching) without arbitrary code execution vulnerabilities.
   - **Visual Regression Engine**: Pixel-by-pixel screenshot diffing with configurable pixel difference thresholds.
   - **LLM-as-a-Judge**: Evaluates fuzzy, visual, and semantic outputs with calibrated confidence scoring and mandatory natural-language rationales.
5. **Self-Healing Web Selectors**:
   - When frontend UI layouts change, Sentinel inspects the live DOM accessibility tree and generates diff proposals to repair broken Playwright selectors automatically.
6. **Bounded Autonomous Exploration (`--explore`)**:
   - Discovers unmapped routes, interactive elements, and forms in staging and sandbox environments. Strictly blocked against production per `R-SAFE-3`.
7. **Strict Blast-Radius Safety & Zero-Footprint Sandboxing**:
   - **R-SAFE-1**: Mutating requests (`POST`, `PUT`, `DELETE`, `DROP`) are blocked by default unless `--allow-mutations` is explicitly provided.
   - **R-SAFE-2**: Production mutations require both `--yes-i-know-prod` flag and explicit `environment_ack` in configuration.
   - **R-EXEC-1**: Database queries execute inside SQL `SAVEPOINT` transactions and are automatically rolled back upon step completion, leaving zero persistent test data. Mobile and desktop adapters execute clean state resets between runs.
   - **R-SEC-2**: All outgoing prompts are scrubbed by `default_redactor` (masking API keys, Bearer tokens, passwords, and custom regex secrets) before transmission to external LLMs.
8. **Automated Defect Filer (GitHub Issues)**:
   - Formats reproducible defect reports with complete execution steps, environment details, and captured artifacts, filing them directly to GitHub Issues per `R-REPORT-1`.
9. **Persistent Memory & Team Collaboration**:
   - Central SQLite memory store supporting multi-project, multi-user, and team workflows (`project_id`, `user_id`, `team_id`), tracking run histories, defect clusters, quarantine registries, and human review decisions.
10. **Live Web Dashboard & REST API**:
    - Starlette and Uvicorn powered web dashboard for inspecting test trends, reviewing pending verdicts, tracking defects, and managing the flaky quarantine list.

---

## 🔌 Universal Adapter Support Matrix

Sentinel provides 8 pluggable target adapters covering every layer of the modern technology stack:

| Adapter | Target Type | Supported Platforms / Protocols | Status | Installation Extra | Prerequisites |
|---|---|---|---|---|---|
| **API** | `api` | REST, OpenAPI 3.0 / 3.1, JSON Schema | ✅ Production Ready | Built-in | None |
| **Web** | `web` | Chromium, Firefox, WebKit (Playwright) | ✅ Production Ready | Built-in | `playwright install chromium` |
| **CLI** | `cli` | Command-line binaries, Python tools, shell scripts | ✅ Production Ready | Built-in | None |
| **Database (SQLite)** | `database` | Embedded SQLite databases | ✅ Production Ready | Built-in | None |
| **Database (Extended)**| `database` | PostgreSQL, MongoDB (with atomic rollback) | ✅ Production Ready | `sentinel-sqa[db-extended]` | Running Postgres or MongoDB server |
| **Mobile** | `mobile` | Android & iOS via Appium / WebDriver | ✅ Real Driver Ready | `sentinel-sqa[mobile]` | Running Appium server (`http://127.0.0.1:4723`) |
| **Desktop** | `desktop` | Windows UI Automation (pywinauto), Linux (AT-SPI), macOS (AX) | ✅ Active (Windows) / Cross-OS Architecture | `sentinel-sqa[desktop]` | Target desktop application on host |
| **IoT & Embedded** | `iot` | MQTT pub/sub (`paho-mqtt`), Serial UART (`pyserial`) | ✅ Real Protocols | `sentinel-sqa[iot]` | MQTT broker or Serial device port |
| **Performance** | `perf` | HTTP load testing, concurrency, RPS, latency percentiles | ✅ Production Ready | Built-in | None |

---

## 🏗️ System Architecture

```
                                 ┌─────────────────────────────────┐
                                 │     Sentinel CLI / Dashboard    │
                                 │  (test, run, plan, review, web) │
                                 └────────────────┬────────────────┘
                                                  │
           ┌──────────────────┬───────────────────┼───────────────────┬──────────────────┐
           │                  │                   │                   │                  │
  ┌────────▼───────┐ ┌────────▼────────┐ ┌────────▼────────┐ ┌────────▼────────┐ ┌───────▼────────┐
  │    Planner     │ │   Generators    │ │    Executor     │ │     Oracles     │ │     Memory     │
  │ ────────────── │ │ ─────────────── │ │ ─────────────── │ │ ─────────────── │ │ ────────────── │
  │ • Rule-Based   │ │ • Functional    │ │ • Thread Pool   │ │ • AST Engine    │ │ • Run History  │
  │ • Risk-Scored  │ │ • Adversarial   │ │ • Timeout Guard │ │ • Visual Diff   │ │ • Defect Store │
  │ • Defect Aware │ │ • Security OWASP│ │ • Mutation Gate │ │ • LLM-as-Judge  │ │ • Quarantine   │
  │ • Git-Diff Rec │ │ • Schema Repair │ │ • Auto-Retry    │ │ • Review Router │ │ • Multi-Tenant │
  └────────────────┘ └─────────────────┘ └────────┬────────┘ └─────────────────┘ └────────────────┘
                                                  │
                         ┌────────────────────────▼────────────────────────┐
                         │              UNIVERSAL ADAPTER LAYER            │
                         │ ┌───────┐ ┌───────┐ ┌───────┐ ┌───────────────┐ │
                         │ │  API  │ │  Web  │ │  CLI  │ │   Database    │ │
                         │ │(REST) │ │(Play) │ │(Shell)│ │(SQL/Postgres) │ │
                         │ └───────┘ └───────┘ └───────┘ └───────────────┘ │
                         │ ┌───────┐ ┌───────┐ ┌───────┐ ┌───────────────┐ │
                         │ │Mobile │ │Desktop│ │  IoT  │ │  Performance  │ │
                         │ │(Appm) │ │ (UIA) │ │(MQTT) │ │(Concurrency) │ │
                         │ └───────┘ └───────┘ └───────┘ └───────────────┘ │
                         └─────────────────────────────────────────────────┘
                                                  │
                         ┌────────────────────────▼────────────────────────┐
                         │               SAFETY & PRIVACY GATE             │
                         │  • R-SAFE-1 / R-SAFE-2: Mutation Guardrails     │
                         │  • R-SAFE-3: Exploration Prohibited on Prod     │
                         │  • R-EXEC-1: SQL SAVEPOINT Atomic Rollbacks     │
                         │  • R-SEC-2: Outbound Prompt PII/Secret Scrub    │
                         └─────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites
- **Python**: 3.11, 3.12, or 3.13
- **Package Manager**: [uv](https://github.com/astral-sh/uv) (strongly recommended) or standard `pip`

### 1. Installation

#### Via Pip (PyPI Package)
```bash
# Standard installation with core adapters (API, Web, CLI, SQLite, Perf)
pip install sentinel-sqa

# Install with optional adapter extras
pip install "sentinel-sqa[mobile]"       # Appium mobile automation
pip install "sentinel-sqa[desktop]"      # Desktop UI Automation (Windows pywinauto)
pip install "sentinel-sqa[iot]"          # MQTT & Serial UART
pip install "sentinel-sqa[db-extended]"  # PostgreSQL & MongoDB drivers

# Or install all extras together
pip install "sentinel-sqa[all]"
```

#### From Source (Development)
```bash
# Clone repository
git clone https://github.com/raihan12121/Software-Testing-Agent-Harness.git
cd Software-Testing-Agent-Harness

# Synchronize virtual environment with all extras and dev dependencies via uv
uv sync --all-extras

# Install browser binaries for Web testing
uv run playwright install chromium
```

### 2. Install Globally as a CLI Tool (Optional)

Install Sentinel into an isolated global environment so `sentinel` can be invoked from any directory:

```bash
# Using uv (fastest)
uv tool install .

# Or using pipx
pipx install .
```

Verify your installation:
```bash
sentinel --help
```

---

## 🔍 Interactive Project Testing

Sentinel features an intelligent project scanner that discovers testable assets in any workspace:

```bash
# Interactively scan and test the current workspace
sentinel test

# Or scan an explicit project directory
sentinel test "D:/Workspace/MyBackendService"
```

Sentinel automatically detects:
- 🌐 **OpenAPI Specifications** (`openapi.yaml`, `swagger.json`, etc.)
- 🗄️ **SQLite Databases** (`*.db`, `*.sqlite`, `*.sqlite3`)
- 💻 **Web Applications** (`index.html`, React, Vue, Vite, Next.js projects)
- ⚙️ **CLI Binaries & Packages** (`pyproject.toml`, `setup.py`, CLI executables)

Select your target from the terminal menu, and Sentinel generates a prioritized plan, executes the test suite, evaluates assertions, and renders a rich summary table.

---

## ⚡ CLI Reference

### Subcommands

| Subcommand | Description |
|---|---|
| `sentinel test [PATH]` | Interactive project scanner and test execution wizard. |
| `sentinel scan [PATH]` | Alias for interactive project scanner. |
| `sentinel run [OPTIONS]` | Headless test execution against a target or test suite. |
| `sentinel plan [OPTIONS]` | Preview generated test scenarios and prioritization without running. |
| `sentinel review [OPTIONS]` | Interactive CLI review queue for pending or low-confidence verdicts. |
| `sentinel dashboard [OPTIONS]` | Launch the team web dashboard and REST API server. |
| `sentinel init [OPTIONS]` | Scaffold a starter `sentinel.config.yaml` configuration file. |

### `sentinel run` Options & Flags

| Flag | Type / Choices | Default | Description |
|---|---|---|---|
| `--env` | `local`, `staging`, `sandbox`, `production` | *Required* | Target environment per `R-EXEC-4`. |
| `-d`, `--project-dir` | `PATH` | `None` | Project folder to scan and test in batch mode. |
| `--target` | `STRING` | `None` | Specification path, endpoint URL, database file, or command. |
| `--target-type` | `api`, `web`, `cli`, `database`, `mobile`, `desktop`, `iot`, `perf`, `stub` | `stub` | Target adapter type. |
| `--base-url` | `URL` | `None` | Explicit base URL override for API targets. |
| `--llm-provider` | `auto`, `mock`, `anthropic` | `auto` | LLM implementation for planning, generation, and judging. |
| `--config` | `PATH` | `sentinel.config.yaml` | Path to YAML configuration file. |
| `--test-file` | `PATH` | `None` | Path to pre-authored test cases in JSON or YAML. |
| `--format` | `json`, `html` | `json` | Test execution report format. |
| `--output-dir` | `PATH` | `reports` | Directory where reports and artifacts are saved. |
| `--parallelism` | `INT` | `1` | Worker thread pool concurrency. |
| `--timeout` | `FLOAT` | `30.0` | Execution timeout in seconds per test step. |
| `--allow-mutations` | Flag | `False` | Allow mutating actions (`POST`, `PUT`, `DELETE`, `DROP`) (`R-SAFE-1`). |
| `--yes-i-know-prod` | Flag | `False` | Explicit confirmation for production mutations (`R-SAFE-2`). |
| `--explore` | Flag | `False` | Autonomous exploration mode (strictly blocked on production). |
| `--run-id` | `STRING` | Auto-generated | Custom identifier for the test run. |
| `--project` | `STRING` | `default` | Project identifier for persistent memory tracking. |

### Practical Command Examples

```bash
# 1. Test an API target using OpenAPI spec with mutations enabled
sentinel run --env staging --target examples/petstore_spec.yaml --target-type api --allow-mutations

# 2. Test an API with a base URL override
sentinel run --env local --target examples/petstore_spec.yaml --target-type api --base-url http://127.0.0.1:8000 --allow-mutations

# 3. Test a SQLite database with automatic transactional rollback
sentinel run --env local --target ./data/app.db --target-type database

# 4. Test a CLI binary and generate an interactive HTML report
sentinel run --env local --target "python" --target-type cli --format html --output-dir reports

# 5. Run autonomous exploration mode on a staging web app
sentinel run --explore --target-type web --base-url http://127.0.0.1:8898 --env staging

# 6. Preview prioritized test plan without executing
sentinel plan --target examples/petstore_spec.yaml --target-type api

# 7. Start the Team Web Dashboard on port 8080
sentinel dashboard --port 8080

# 8. Inspect and resolve verdicts in the human review queue
sentinel review
sentinel review --resolve-id "TC-0042" --as-pass --reviewer "alice" --rationale "Verified UI layout visually"
```

---

## ⚙️ Configuration File

Sentinel supports a centralized `sentinel.config.yaml` file to define targets, environment guardrails, and defaults:

```yaml
version: "1.0"
project: "petstore-service"

target:
  target_type: "api"
  name: "Petstore Service"
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
    # Explicit acknowledgement token required for production mutations (R-SAFE-2)
    environment_ack: "I understand this targets production"
```

Generate a starter configuration anytime with:
```bash
sentinel init
```

---

## 🤖 LLM Provider Architecture & Data Privacy

Sentinel employs an abstraction layer designed for structured generation, privacy, and zero data leakage:

### Supported Providers
- **`AnthropicLLMProvider`**: Leverages Anthropic Claude 3.5 Sonnet / Haiku using native tool-calling structured output. Guarantees 100% adherence to Pydantic schemas.
- **`MockLLMProvider`**: High-speed, deterministic offline provider used for unit testing, offline development, and CI environments without external API requirements.

Configure Claude via environment variables:
```bash
# Linux / macOS
export ANTHROPIC_API_KEY="sk-ant-api03-..."

# Windows PowerShell
$env:ANTHROPIC_API_KEY="sk-ant-api03-..."
```
When `ANTHROPIC_API_KEY` is detected and `--llm-provider auto` is specified, Sentinel automatically activates `AnthropicLLMProvider`.

### Zero Data Leakage Redaction (R-SEC-2)
Sentinel enforces strict data sanitation. Before any prompt, system instruction, or observation reaches an external LLM:
- **`default_redactor`** scrubs Bearer tokens, JWTs, API keys, basic authentication credentials, passwords, and custom sensitive patterns.
- Replaces matches with anonymized placeholders (e.g. `[REDACTED_API_KEY]`, `[REDACTED_BEARER_TOKEN]`).

### Cost & Latency Instrumentation (R-BUILD-3)
Every LLM call records telemetry in persistent memory:
- **Prompt Hash**: SHA-256 hash for deduplication and audit tracking.
- **Token Counts**: Input tokens, output tokens, and total usage.
- **Duration**: Request round-trip time in milliseconds.
- **Estimated Cost**: USD calculation based on token pricing.

---

## 👥 Human-in-the-Loop Review Queue & Defect Management

When evaluating non-deterministic outputs, Sentinel ensures human oversight where confidence is ambiguous:

1. **Uncertain Verdict Routing (`R-ORACLE-2`)**:
   - When the LLM Judge returns a confidence score below **0.75** or an inconclusive status, the test is not arbitrarily passed or failed.
   - It is marked as `pending_review` and routed to the Review Queue.
2. **Review Queue Resolution (`sentinel review`)**:
   - Testers can inspect the judge's reasoning and observations via CLI or the Web Dashboard.
   - Approvals or rejections are recorded in SQLite persistent memory alongside the reviewer's identity and audit rationale (`R-ORACLE-5`).
3. **Automated Defect Filing (`R-REPORT-1`)**:
   - High-confidence failures can be automatically filed to GitHub Issues via `DefectFiler`.
   - Each defect ticket includes structured Markdown with step-by-step reproduction instructions, expected vs. observed results, stack traces, and links to captured artifacts.
4. **Flaky Test Quarantine (`R-EXEC-2`)**:
   - Tests that succeed only after a retry attempt are flagged as `flaky` and tracked in the Quarantine Registry, preventing masking of intermittent bugs.

---

## 🌐 Web Dashboard & REST API

Launch the Sentinel Team Dashboard to monitor test runs across projects:

```bash
sentinel dashboard --port 8080
```

Open `http://localhost:8080` to access:
- 📊 **Run Overview & Trends**: Pass rates, flakiness ratios, error breakdowns, and duration tracking.
- 📋 **Human Review Queue**: Interactive interface to approve or reject `pending_review` verdicts.
- 🐛 **Defect Explorer**: Defect clustering and history.
- 🛡️ **Quarantine Management**: Flaky test identification.
- 🔌 **REST API Endpoints**:
  - `GET /api/runs`: List historical runs.
  - `GET /api/runs/{run_id}`: Detailed test execution report.
  - `GET /api/review`: List items awaiting human review.
  - `POST /api/review/{test_id}`: Submit human resolution override.
  - `GET /api/defects`: Defect list.
  - `GET /api/quarantine`: Quarantine registry.

---

## 🚢 Deployment Options

### 1. Cloud Deployment (Railway / Render)

Deploy Sentinel as a hosted service with persistent SQLite storage:

#### Via Railway (1-Click Docker)
1. Fork or push your code to GitHub.
2. Create a new project on [Railway](https://railway.com) from your repository.
3. Railway automatically detects the [`Dockerfile`](Dockerfile).
4. Under **Settings** → **Networking**, click **Generate Domain**.
5. Add environment variables:
   - `ANTHROPIC_API_KEY`: *(Optional, for Claude)*
   - `PORT`: `8080`

#### Via Render
1. Create a **Web Service** on [Render](https://render.com) connected to your repository.
2. Select **Docker** environment and specify port `8080`.
3. Add a persistent disk mounted at `/app/data` to persist test history.

---

### 2. Docker & Docker Compose (VPS / Server)

Run Sentinel on any Linux, macOS, or Windows host:

```bash
# Clone the repository
git clone https://github.com/raihan12121/Software-Testing-Agent-Harness.git
cd Software-Testing-Agent-Harness

# Build and start in detached mode
docker compose up -d --build
```

Access the dashboard at `http://<your-server-ip>:8080`. Data is safely stored in the `sentinel_data` named Docker volume.

---

### 3. Local Team Network (LAN)

Share Sentinel with teammates on your local office network:

```powershell
uv run sentinel dashboard --port 8080
```
Teammates can navigate to `http://<your-ip-address>:8080` in their browsers.

---

### 4. GitHub Actions CI/CD Pipeline

Sentinel includes a comprehensive quality gate workflow in `.github/workflows/ci.yml`. On every push and pull request:
1. Validates code style and imports via **Ruff**.
2. Runs the complete test suite of **126 automated unit and regression tests**.
3. Verifies CLI self-tests against real targets.
4. Archives interactive HTML test reports as downloadable workflow artifacts.

---

### 5. Scheduled Nightly Autonomous Exploration

Sentinel provides a scheduled GitHub Actions workflow in `.github/workflows/scheduled_run.yml`:

```yaml
name: Scheduled Nightly SQA Run

on:
  schedule:
    # Runs nightly at 02:00 UTC against staging
    - cron: '0 2 * * *'
  workflow_dispatch:

jobs:
  nightly-exploration:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: |
          pip install uv
          uv pip install --system -e ".[all]"
          playwright install --with-deps chromium
      - name: Run Sentinel Explore Mode
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          sentinel run \
            --explore \
            --target-type web \
            --base-url "https://staging.example.com" \
            --env staging \
            --format html \
            --output-dir reports \
            --allow-mutations
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: nightly-sqa-reports
          path: reports/
```

Failures discovered during nightly runs are automatically filed as GitHub Issues with step-by-step reproduction details and artifact attachments per `R-REPORT-1`.

---

## 🛡️ Safety Guardrails & Policies (`rules.md`)

Sentinel enforces strict, non-negotiable safety guardrails:

| Rule ID | Policy Name | Enforcement Mechanism |
|---|---|---|
| **R-SAFE-1** | No Unintended Mutations | Mutating actions (`POST`, `PUT`, `DELETE`, `DROP`) are blocked by default. Requires `--allow-mutations`. |
| **R-SAFE-2** | Production Blast Shield | Mutating production requires `--yes-i-know-prod` plus explicit `environment_ack` in config. |
| **R-SAFE-3** | Explore Mode Restriction | Autonomous exploration (`--explore`) is strictly prohibited against `production` environments. |
| **R-SAFE-5** | Hardware & Protocol Allowlist | IoT (MQTT/Serial) and network adapters enforce strict host/port allowlisting. |
| **R-EXEC-1** | Transactional Isolation | Database queries execute inside SQL `SAVEPOINT` transactions and rollback automatically. |
| **R-EXEC-2** | Flakiness Isolation | Tests passing only after a retry are flagged as `flaky` and logged in quarantine, never masked as passes. |
| **R-EXEC-4** | Mandatory Environment | `--env` argument is mandatory on every test run. |
| **R-ORACLE-2** | Human Review Gating | LLM judge evaluations with confidence score below 0.75 are routed to `pending_review`. |
| **R-ORACLE-5** | Review Audit Logging | All human overrides record reviewer identity, timestamp, and audit rationale. |
| **R-SEC-1** | Secret Confidentiality | Passwords, tokens, and keys are never logged or stored in plaintext. |
| **R-SEC-2** | Outbound Prompt Sanitization | Outgoing LLM prompts are scrubbed by `default_redactor` before transmission. |
| **R-BUILD-3** | LLM Cost & Telemetry Tracking | Every LLM call records prompt hash, token counts, duration (ms), and cost (USD). |

---

## 🧪 Testing & Quality Verification

Run the test suite across all adapters, generators, oracles, and safety gates:

```bash
# Run 126 automated tests
uv run pytest -q

# Run tests with code coverage report
uv run pytest --cov=sentinel --cov-report=term

# Run code style linter
uv run ruff check .
```

---

## 🗺️ Phased Implementation Roadmap

All milestone phases and exit gates have been implemented and verified:

- ✅ **Phase 0 — Foundations**: Schemas (`TestCase`, `Observation`, `Verdict`), abstract interfaces, config validation, secrets redaction, structured logging.
- ✅ **Phase 1 — REST API Adapter & Rule-based Core Loop**: OpenAPI 3.0/3.1 parser, equivalence partitioning, boundary value analysis, CRUD matrix, deterministic oracle, SQLite memory.
- ✅ **Phase 2 — Web (Playwright), CLI, LLM-as-a-Judge**: Browser automation, visual regression diffing, CLI subprocess adapter, review queue, self-healing selectors.
- ✅ **Phase 3 — Risk-Based Testing & Database Adapter**: SQLite/Postgres transactional rollback, git-diff risk scoring, flaky quarantine, explore mode, auto defect filing.
- ✅ **Phase 4 — Mobile, Desktop & Team Dashboard**: Appium driver integration, pywinauto Windows UI Automation, multi-user memory, Starlette web dashboard, collaborative multi-agent generation.
- ✅ **Phase 5 — Non-Functional Testing & IoT**: HTTP performance load testing, OWASP Top 10 security test generator, MQTT & Serial UART adapters.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
