"""Project directory scanner and interactive test wizard for Sentinel.

Adheres to:
- PRD.md §6.1 FR-1 (Accept repo path / target definition)
- PRD.md §6.1 FR-2 (Auto-detect target type where possible)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table


@dataclass
class DiscoveredTarget:
    """A target automatically discovered within a project directory."""

    target_type: Literal["api", "web", "database", "cli", "stub"]
    name: str
    target_path: str
    description: str


class ProjectScanner:
    """Scans a filesystem folder and auto-detects testable targets."""

    def __init__(self, project_dir: Path | str) -> None:
        self.project_dir = Path(project_dir).resolve()

    def scan(self) -> list[DiscoveredTarget]:
        """Scan directory and return all detected testable targets."""
        targets: list[DiscoveredTarget] = []

        if not self.project_dir.exists() or not self.project_dir.is_dir():
            return targets

        # 1. Check for OpenAPI / Swagger specs in root and subdirectories
        search_dirs = [self.project_dir] + [
            self.project_dir / sub
            for sub in ("examples", "specs", "docs", "api")
            if (self.project_dir / sub).is_dir()
        ]

        for sdir in search_dirs:
            for ext in ("*.yaml", "*.yml", "*.json"):
                for file_path in sdir.glob(ext):
                    if file_path.name in ("package.json", "tsconfig.json", "uv.lock", "sentinel.config.yaml"):
                        continue
                    try:
                        content = file_path.read_text(encoding="utf-8", errors="ignore")[:3000]
                        if "openapi" in content.lower() or "swagger" in content.lower():
                            rel_name = file_path.relative_to(self.project_dir)
                            targets.append(
                                DiscoveredTarget(
                                    target_type="api",
                                    name=f"API Spec: {rel_name}",
                                    target_path=str(file_path),
                                    description=f"OpenAPI/Swagger specification file ({rel_name})",
                                )
                            )
                    except Exception:
                        continue

        # 2. Check for SQLite databases
        for ext in ("*.db", "*.sqlite", "*.sqlite3"):
            for file_path in self.project_dir.glob(ext):
                if "sentinel_memory" in file_path.name:
                    continue
                targets.append(
                    DiscoveredTarget(
                        target_type="database",
                        name=f"Database: {file_path.name}",
                        target_path=str(file_path),
                        description=f"SQLite database file ({file_path.name})",
                    )
                )

        # 3. Check for Web frontend (HTML or package.json)
        index_html = self.project_dir / "index.html"
        if index_html.exists():
            targets.append(
                DiscoveredTarget(
                    target_type="web",
                    name="Web UI (index.html)",
                    target_path=str(index_html),
                    description="Local static web UI page",
                )
            )

        pkg_json = self.project_dir / "package.json"
        if pkg_json.exists():
            try:
                data = json.loads(pkg_json.read_text(encoding="utf-8", errors="ignore"))
                scripts = data.get("scripts", {})
                if "dev" in scripts or "start" in scripts:
                    targets.append(
                        DiscoveredTarget(
                            target_type="web",
                            name=f"Web App: {data.get('name', 'node-app')}",
                            target_path="http://localhost:3000",
                            description="Node.js/Frontend web application (default http://localhost:3000)",
                        )
                    )
            except Exception:
                pass

        # 4. Fallback CLI target if python project detected
        pyproject = self.project_dir / "pyproject.toml"
        if pyproject.exists():
            targets.append(
                DiscoveredTarget(
                    target_type="cli",
                    name="Python Environment",
                    target_path="python",
                    description="Local Python runtime CLI",
                )
            )

        return targets


def interactive_scan_and_test(console: Console, project_dir_str: str | None = None) -> int:
    """Run an interactive wizard to choose a project folder, detect targets, and run tests."""
    from sentinel.core.config import RunConfig, TargetConfig
    from sentinel.core.orchestrator import Orchestrator

    console.print(
        Panel(
            "[bold cyan]Sentinel Interactive Project Tester[/bold cyan]\n"
            "Automatically scan any codebase or project folder, detect APIs, Web apps, Databases, and run tests.",
            border_style="cyan",
        )
    )

    if not project_dir_str:
        project_dir_str = Prompt.ask(
            "[bold green]Enter project folder path[/bold green] (press Enter for current directory)",
            default=".",
        )

    proj_path = Path(project_dir_str).resolve()
    if not proj_path.exists() or not proj_path.is_dir():
        console.print(f"[bold red]Error: Directory '{proj_path}' does not exist.[/bold red]")
        return 1

    console.print(f"[cyan]Scanning folder:[/cyan] [bold]{proj_path}[/bold]...")
    scanner = ProjectScanner(proj_path)
    targets = scanner.scan()

    if not targets:
        console.print("[yellow]No predefined targets automatically detected in this folder.[/yellow]")
        console.print("Choose a manual target type to test:")
        console.print("  [1] CLI command (e.g. python, git, or custom binary)")
        console.print("  [2] Web URL (e.g. http://localhost:3000)")
        console.print("  [3] OpenAPI Specification file")
        choice = Prompt.ask("Select option", choices=["1", "2", "3"], default="1")
        if choice == "1":
            cmd = Prompt.ask("Enter CLI executable/command", default="python")
            chosen_target = DiscoveredTarget("cli", f"CLI: {cmd}", cmd, "Manual CLI command")
        elif choice == "2":
            url = Prompt.ask("Enter Web URL", default="http://localhost:3000")
            chosen_target = DiscoveredTarget("web", f"Web: {url}", url, "Manual Web URL")
        else:
            spec = Prompt.ask("Enter OpenAPI spec path")
            chosen_target = DiscoveredTarget("api", f"API: {spec}", spec, "Manual OpenAPI spec")
    else:
        table = Table(title="Detected Testable Targets in Project")
        table.add_column("#", style="bold cyan", width=4)
        table.add_column("Type", style="magenta")
        table.add_column("Target Name", style="green")
        table.add_column("Path / Spec", style="blue")
        table.add_column("Description", style="white")

        for idx, t in enumerate(targets, 1):
            table.add_row(str(idx), t.target_type.upper(), t.name, t.target_path, t.description)

        console.print(table)
        choices = [str(i) for i in range(1, len(targets) + 1)]
        selection = Prompt.ask(
            f"[bold green]Select target to test [1-{len(targets)}][/bold green]",
            choices=choices,
            default="1",
        )
        chosen_target = targets[int(selection) - 1]

    env = Prompt.ask(
        "[bold green]Select environment[/bold green]",
        choices=["local", "staging", "sandbox", "production"],
        default="local",
    )

    fmt = Prompt.ask(
        "[bold green]Report format[/bold green]",
        choices=["html", "json"],
        default="html",
    )

    console.print(f"\n[bold cyan]Starting test run against {chosen_target.name} ({chosen_target.target_type}) in {env}...[/bold cyan]\n")

    run_id = f"run-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    target_config = TargetConfig(
        target_type=chosen_target.target_type,
        name=chosen_target.target_path,
        spec_path=chosen_target.target_path,
    )
    run_config = RunConfig(
        run_id=run_id,
        project_id=proj_path.name,
        environment=env,
        output_dir=Path("reports"),
    )

    orchestrator = Orchestrator(target_config, run_config)
    report, exit_code = orchestrator.plan_and_run(report_format=fmt)

    # Print summary table
    from sentinel.cli import print_report_summary
    print_report_summary(report)

    return exit_code
