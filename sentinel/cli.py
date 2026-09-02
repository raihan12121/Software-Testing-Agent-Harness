"""Command line interface for Sentinel.

Commands:
- sentinel run: Execute test cases against target
- sentinel plan: Display test plan scenarios
- sentinel report: View or export run reports
- sentinel init: Scaffold starter configuration
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from rich.console import Console
from rich.table import Table

from sentinel.core.config import EnvironmentType, RunConfig, SentinelConfig, TargetConfig
from sentinel.core.orchestrator import Orchestrator
from sentinel.core.schemas import TestCase

console = Console()


def load_test_cases_from_file(file_path: Path) -> list[TestCase]:
    """Load test cases from a YAML or JSON file."""
    if not file_path.exists():
        raise FileNotFoundError(f"Test file not found: {file_path}")

    content = file_path.read_text(encoding="utf-8")
    raw = yaml.safe_load(content)

    if isinstance(raw, list):
        return [TestCase.model_validate(item) for item in raw]
    if isinstance(raw, dict):
        # Could be a single test case or a container with 'tests' key
        if "tests" in raw and isinstance(raw["tests"], list):
            return [TestCase.model_validate(item) for item in raw["tests"]]
        return [TestCase.model_validate(raw)]

    raise ValueError(f"Unrecognized test file structure in {file_path}")


def cmd_run(args: argparse.Namespace) -> int:
    """Execute tests via Orchestrator."""
    config_file = Path(args.config)
    env_name: EnvironmentType = args.env

    run_id = args.run_id or f"run-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"

    if getattr(args, "project_dir", None):
        from sentinel.scanner import ProjectScanner
        scanner = ProjectScanner(args.project_dir)
        targets = scanner.scan()
        if targets and not args.target:
            args.target = targets[0].target_path
            args.target_type = targets[0].target_type
            console.print(f"[cyan]Auto-detected target from '{args.project_dir}': {targets[0].name}[/cyan]")

    if config_file.exists():
        sentinel_conf = SentinelConfig.load(config_file)
        target_config = sentinel_conf.target
        if getattr(args, "base_url", None):
            target_config.base_url = args.base_url
        run_config = sentinel_conf.create_run_config(
            env=env_name,
            run_id=run_id,
            allow_mutations=args.allow_mutations,
            prod_confirmed=args.yes_i_know_prod,
            parallelism=args.parallelism,
            timeout=args.timeout,
            output_dir=Path(args.output_dir) if getattr(args, "output_dir", None) else None,
        )
        if getattr(args, "output_dir", None):
            run_config.output_dir = Path(args.output_dir)
    else:
        # Fallback to direct flags
        target_type = args.target_type or "stub"
        target_config = TargetConfig(
            target_type=target_type,
            name=args.target or f"{target_type}-target",
            spec_path=args.target,
            base_url=getattr(args, "base_url", None),
        )
        run_config = RunConfig(
            run_id=run_id,
            project_id=args.project or "default",
            environment=env_name,
            allow_mutations=args.allow_mutations,
            prod_confirmed=args.yes_i_know_prod,
            parallelism=args.parallelism or 1,
            timeout_seconds=args.timeout or 30.0,
            output_dir=Path(args.output_dir or "reports"),
        )

    llm_choice = getattr(args, "llm_provider", "auto")
    from sentinel.llm.provider import get_llm_provider
    llm_provider = get_llm_provider(provider_type=llm_choice)

    # Load test cases or run planner
    orchestrator = Orchestrator(target_config, run_config, llm_provider=llm_provider)

    if getattr(args, "explore", False):
        if env_name == "production":
            console.print("[bold red]SECURITY VIOLATION: Explore mode is strictly prohibited against production (R-SAFE-3). Aborting.[/bold red]")
            return 2
        from sentinel.adapters import get_adapter
        from sentinel.explorer import AutonomousExplorer

        explorer = AutonomousExplorer(target_config, run_config)
        adapter_cls = get_adapter(target_config.target_type)
        adapter = adapter_cls(target_config)
        console.print(f"[cyan]Running Autonomous Explore Mode on {target_config.target_type}...[/cyan]")
        test_cases = explorer.explore(adapter)
        report, exit_code = orchestrator.run_tests(test_cases, report_format=args.format)
    elif args.test_file:
        test_cases = load_test_cases_from_file(Path(args.test_file))
        report, exit_code = orchestrator.run_tests(test_cases, report_format=args.format)
    elif target_config.spec_path or args.target:
        console.print(f"[cyan]Auto-planning test suite from target '{target_config.name}'...[/cyan]")
        report, exit_code = orchestrator.plan_and_run(report_format=args.format)
    else:
        console.print("[yellow]No --test-file or --target provided. Generating sample stub test case.[/yellow]")
        from sentinel.core.schemas import ExpectedResult, TestStep

        test_cases = [
            TestCase(
                id="TC-0001",
                target_type=target_config.target_type,  # type: ignore
                title="Verify stub endpoint health status",
                priority="high",
                tags=["smoke", "health"],
                steps=[
                    TestStep(
                        action="http_request",
                        method="GET",
                        path="/health",
                        metadata={"status_code": 200, "response_body": {"status": "ok"}},
                    )
                ],
                expected=ExpectedResult(
                    oracle="deterministic",
                    assertions=["status_code == 200", "body.status == 'ok'"],
                ),
                generated_by="human",
            )
        ]
        report, exit_code = orchestrator.run_tests(test_cases, report_format=args.format)

    # Display results summary table
    table = Table(title=f"Sentinel Run Summary: {report.run_id}")
    table.add_column("Total", justify="center")
    table.add_column("Passed", justify="center", style="green")
    table.add_column("Failed", justify="center", style="red")
    table.add_column("Flaky", justify="center", style="yellow")
    table.add_column("Errors", justify="center", style="bold red")
    table.add_column("Pending Review", justify="center", style="cyan")
    table.add_column("Duration (ms)", justify="right")

    table.add_row(
        str(len(report.verdicts)),
        str(report.pass_count),
        str(report.fail_count),
        str(report.flaky_count),
        str(report.error_count),
        str(report.pending_count),
        str(report.duration_ms),
    )
    console.print(table)

    return exit_code


def cmd_plan(args: argparse.Namespace) -> int:
    """Generate and display a prioritized test plan for human review (FR-6)."""
    config_file = Path(args.config)
    if config_file.exists():
        sentinel_conf = SentinelConfig.load(config_file)
        target_config = sentinel_conf.target
    else:
        target_type = args.target_type or "api"
        target_config = TargetConfig(
            target_type=target_type,
            name=f"{target_type}-target",
            spec_path=args.target,
        )

    from sentinel.adapters.base import get_adapter
    from sentinel.planner.rule_based import RuleBasedPlanner

    adapter = get_adapter(target_config.target_type)
    target_model = adapter.discover(target_config)
    planner = RuleBasedPlanner()
    plan = planner.build_plan(target_model)

    table = Table(title=f"Test Plan for '{target_model.name}' ({len(plan.scenarios)} scenarios)")
    table.add_column("ID", justify="center", style="cyan")
    table.add_column("Priority", justify="center")
    table.add_column("Component", justify="left")
    table.add_column("Title", justify="left")
    table.add_column("Tags", justify="left", style="dim")

    for s in plan.scenarios:
        pri_style = "bold red" if s.priority == "critical" else ("red" if s.priority == "high" else "yellow")
        table.add_row(
            s.id,
            f"[{pri_style}]{s.priority}[/{pri_style}]",
            s.target_component,
            s.title,
            ", ".join(s.tags),
        )

    console.print(table)
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    """Inspect and resolve pending_review verdicts (R-ORACLE-2, R-ORACLE-5)."""
    from sentinel.memory.store import MemoryStore

    store = MemoryStore()
    pending = store.get_pending_reviews(run_id=args.run_id)

    if not pending:
        console.print("[green]No verdicts pending human review.[/green]")
        return 0

    if args.resolve_id:
        target_item = next((p for p in pending if p["test_id"] == args.resolve_id), None)
        if not target_item:
            console.print(f"[red]Pending review for test_id '{args.resolve_id}' not found.[/red]")
            return 1
        new_status = "pass" if args.as_pass else ("fail" if args.as_fail else "pass")
        rationale = args.rationale or "Manual human resolution"
        store.record_human_resolution(
            test_id=args.resolve_id,
            run_id=target_item["run_id"],
            original_status="pending_review",
            resolved_status=new_status,
            resolved_by=args.reviewer or "human_tester",
            rationale=rationale,
        )
        console.print(f"[green]Successfully resolved {args.resolve_id} as {new_status}.[/green]")
        return 0

    table = Table(title=f"Verdicts Pending Human Review ({len(pending)} items)")
    table.add_column("Test ID", justify="center", style="cyan")
    table.add_column("Run ID", justify="center")
    table.add_column("Title", justify="left")
    table.add_column("Confidence", justify="center", style="yellow")
    table.add_column("Judge Reasoning", justify="left")

    for p in pending:
        conf_str = f"{p['confidence']:.2f}" if p.get("confidence") is not None else "N/A"
        table.add_row(
            p["test_id"],
            p["run_id"],
            p["title"],
            conf_str,
            (p.get("reasoning") or "")[:80],
        )

    console.print(table)
    console.print("[dim]Use --resolve-id <test_id> --as-pass/--as-fail --rationale <text> to resolve.[/dim]")
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    """Scaffold a starter sentinel.config.yaml."""
    config_path = Path("sentinel.config.yaml")
    if config_path.exists() and not args.force:
        console.print("[red]sentinel.config.yaml already exists. Use --force to overwrite.[/red]")
        return 1

    starter_config = {
        "project_id": "my-project",
        "target": {
            "target_type": "api",
            "name": "sample-api",
            "spec_path": "openapi.yaml",
            "allowed_hosts": ["localhost", "127.0.0.1"],
        },
        "environments": {
            "local": {"env_name": "local", "allow_mutations": True},
            "staging": {"env_name": "staging", "allow_mutations": True},
            "production": {
                "env_name": "production",
                "allow_mutations": False,
                "environment_ack": None,
            },
        },
        "defaults": {"parallelism": 1, "timeout_seconds": 30.0},
    }

    config_path.write_text(yaml.dump(starter_config, sort_keys=False), encoding="utf-8")
    console.print(f"[green]Scaffolded configuration file: {config_path}[/green]")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        prog="sentinel",
        description="Sentinel — Universal SQA Testing Harness / Agent",
    )
    subparsers = parser.add_subparsers(dest="subcommand")

    # Run command
    run_parser = subparsers.add_parser("run", help="Execute test cases")
    run_parser.add_argument("--config", default="sentinel.config.yaml", help="Path to configuration file")
    run_parser.add_argument("--env", required=True, choices=["local", "staging", "sandbox", "production"], help="Target environment (R-EXEC-4)")
    run_parser.add_argument("-d", "--project-dir", default=None, help="Project folder to auto-scan for targets")
    run_parser.add_argument("--base-url", default=None, help="Explicit base URL override for API targets")
    run_parser.add_argument("--llm-provider", default="auto", choices=["auto", "mock", "anthropic"], help="LLM provider implementation (auto, mock, anthropic)")
    run_parser.add_argument("--target", default=None, help="Target spec, URL, or path")
    run_parser.add_argument("--target-type", default="stub", help="Target adapter type (stub, api, cli, web)")
    run_parser.add_argument("--test-file", default=None, help="Path to test cases YAML/JSON file")
    run_parser.add_argument("--run-id", default=None, help="Custom run identifier")
    run_parser.add_argument("--project", default="default", help="Project identifier")
    run_parser.add_argument("--format", default="json", choices=["json", "html"], help="Report output format")
    run_parser.add_argument("--output-dir", default="reports", help="Directory for reports and artifacts")
    run_parser.add_argument("--parallelism", type=int, default=1, help="Worker pool concurrency")
    run_parser.add_argument("--timeout", type=float, default=30.0, help="Execution timeout in seconds")
    run_parser.add_argument("--allow-mutations", action="store_true", help="Allow mutating actions (R-SAFE-1)")
    run_parser.add_argument("--yes-i-know-prod", action="store_true", help="Explicit production confirmation (R-SAFE-2)")
    run_parser.add_argument("--explore", action="store_true", help="Autonomous exploration mode (R-SAFE-3)")

    # Test / Scan command (interactive project folder selector)
    test_parser = subparsers.add_parser("test", help="Choose a project folder, auto-detect targets, and test interactively")
    test_parser.add_argument("path", nargs="?", default=None, help="Project directory to scan and test")

    scan_parser = subparsers.add_parser("scan", help="Scan a project folder and test interactively")
    scan_parser.add_argument("path", nargs="?", default=None, help="Project directory to scan and test")

    # Plan command
    plan_parser = subparsers.add_parser("plan", help="Generate and display test plan scenarios (FR-6)")
    plan_parser.add_argument("--config", default="sentinel.config.yaml", help="Path to configuration file")
    plan_parser.add_argument("--target", default=None, help="Target spec, URL, or path")
    plan_parser.add_argument("--target-type", default="api", help="Target adapter type")

    # Review command
    review_parser = subparsers.add_parser("review", help="Review and resolve pending verdicts (FR-16, R-ORACLE-2)")
    review_parser.add_argument("--run-id", default=None, help="Filter by run ID")
    review_parser.add_argument("--resolve-id", default=None, help="Test ID to resolve")
    review_parser.add_argument("--as-pass", action="store_true", help="Resolve verdict as PASS")
    review_parser.add_argument("--as-fail", action="store_true", help="Resolve verdict as FAIL")
    review_parser.add_argument("--reviewer", default="human_tester", help="Reviewer name")
    review_parser.add_argument("--rationale", default=None, help="Audit rationale for override")

    # Dashboard command
    dash_parser = subparsers.add_parser("dashboard", help="Start web dashboard for team metrics and reviews")
    dash_parser.add_argument("--port", type=int, default=8080, help="Web port (default 8080)")
    dash_parser.add_argument("--db", default="sentinel_memory.sqlite", help="Path to SQLite memory database")

    # Init command
    init_parser = subparsers.add_parser("init", help="Initialize sentinel.config.yaml")
    init_parser.add_argument("--force", action="store_true", help="Overwrite existing configuration file")

    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if args.subcommand in ("test", "scan"):
        from sentinel.scanner import interactive_scan_and_test
        return interactive_scan_and_test(console, args.path)
    if args.subcommand == "run":
        return cmd_run(args)
    if args.subcommand == "plan":
        return cmd_plan(args)
    if args.subcommand == "review":
        return cmd_review(args)
    if args.subcommand == "dashboard":
        return cmd_dashboard(args)
    if args.subcommand == "init":
        return cmd_init(args)

    # If no subcommand provided, launch interactive tester if terminal is interactive
    if not args.subcommand:
        if sys.stdin.isatty():
            from sentinel.scanner import interactive_scan_and_test
            return interactive_scan_and_test(console)
        parser.print_help()
        return 0
    return 0


def cmd_dashboard(args: argparse.Namespace) -> int:
    """Start Sentinel web dashboard server."""
    from sentinel.dashboard.server import start_dashboard_server

    console.print(f"[bold green]Starting Sentinel Dashboard on http://127.0.0.1:{args.port}/[/bold green]")
    start_dashboard_server(port=args.port, db_path=args.db, blocking=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
