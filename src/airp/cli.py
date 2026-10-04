import argparse
import hashlib
import json
import os
import secrets
import sys
from pathlib import Path
from typing import Any

from airp import observability as telemetry
from airp.agents import ReportingAgent
from airp.core.config import Settings
from airp.core.models import Run, State
from airp.core.security import Policy, Principal, authenticate, read_json
from airp.core.store import Store
from airp.integrations import collect
from airp.mcp.client import MCPReader
from airp.mcp.server import EvidenceBundle
from airp.providers import MockProvider, OpenAIProvider, Provider
from airp.remediation.backends import Backend, FixtureBackend, KubernetesBackend, atomic_json
from airp.workflow import OrchestratorAgent


def init_demo(settings: Settings) -> None:
    root = settings.state_dir
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if (root / "identities.json").exists():
        raise ValueError("Demo already initialized; use a new AIRP_STATE_DIR for a fresh run")
    os.chmod(root, 0o700)
    identities: dict[str, Any] = {}
    for role in ("planner", "approver", "executor"):
        token = secrets.token_urlsafe(32)
        identities[hashlib.sha256(token.encode()).hexdigest()] = {
            "name": f"demo-{role}",
            "roles": [role, "reader"],
        }
        atomic_json(root / f"{role}.token.json", {"token": token})
    atomic_json(root / "identities.json", identities)
    bundle = EvidenceBundle.model_validate(read_json(Path("demo/evidence.json")))
    atomic_json(root / "workload.json", bundle.workloads[0].model_dump(mode="json"))
    print("Initialized local DEMO identities and fixture. Tokens remain in private local files.")


def backend_for(settings: Settings) -> Backend:
    if settings.backend == "fixture":
        return FixtureBackend(settings.state_dir / "workload.json")
    return KubernetesBackend(settings.kubeconfig, settings.kube_context, settings.rollout_timeout)


def display(run: Run) -> None:
    print(
        json.dumps(
            {
                "run_id": run.id,
                "plan_digest": run.plan.hash if run.plan else None,
                "run": run.model_dump(mode="json"),
            },
            indent=2,
        )
    )


def report(store: Store, run: Run, directory: Path) -> None:
    with telemetry.agent_span("reporting", run.id):
        store.record(run.id, "reporting-agent", "report_generated")
        evidence = ReportingAgent().run(run, store.events(run.id), store.verify())
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        atomic_json(directory / f"{run.id}.json", evidence)
        lines = [
            "# Remediation Evidence",
            "",
            f"Run: `{run.id}`",
            f"State: `{run.state}`",
            f"Backend: `{run.backend_id}`",
            f"Finding: `{run.finding.id}`",
            f"Verified: `{evidence['verified']}`",
            "",
            "## Checks",
            "",
            "```json",
            json.dumps(run.validation.model_dump(mode="json") if run.validation else {}, indent=2),
            "```",
            "",
            f"Audit checkpoint: `{evidence['audit_checkpoint']}`",
            "",
            "Local checkpoints require external retention to resist administrator rewrite.",
            "",
        ]
        (directory / f"{run.id}.md").write_text("\n".join(lines), encoding="utf-8")


def demo_actor(settings: Settings, role: str) -> Principal:
    value: Any = read_json(settings.state_dir / f"{role}.token.json")
    return authenticate(settings.state_dir / "identities.json", value["token"])


def demo(settings: Settings, auto_approve: bool) -> int:
    if settings.provider != "mock":
        raise ValueError("Recruiter demo requires AIRP_PROVIDER=mock; use plan for a live provider")
    backend = backend_for(settings)
    if settings.backend == "kubernetes" and settings.kube_context != "kind-airp":
        raise ValueError("The built-in demo is restricted to the kind-airp context")
    mode = "SIMULATED fixture" if settings.backend == "fixture" else "REAL local kind cluster"
    print(f"Mode: {mode}")
    policy = Policy.model_validate(read_json(settings.policy_file))
    snapshot = backend.read(policy.targets[0])
    evidence_path = settings.state_dir / "evidence.json"
    atomic_json(
        evidence_path,
        EvidenceBundle(backend_id=backend.identity, workloads=[snapshot]).model_dump(mode="json"),
    )
    store = Store(settings.state_dir / "workflow.db")
    workflow = OrchestratorAgent(store, policy)
    exit_code = 0
    try:
        for finding in collect(Path("demo/findings.json")):
            run = workflow.analyze(
                finding,
                demo_actor(settings, "planner"),
                backend.identity,
                MockProvider(),
                MCPReader(evidence_path),
            )
            print(f"{finding.severity.upper():8} {finding.id}: {run.state}")
            if run.plan is not None:
                print(
                    json.dumps(
                        {
                            "run_id": run.id,
                            "plan_digest": run.plan.hash,
                            "action": run.plan.action,
                            "target": run.plan.target.key,
                            "risk": run.reason,
                            "change": {"automountServiceAccountToken": False},
                        },
                        indent=2,
                    )
                )
                workflow.execute(run.id, demo_actor(settings, "executor"), backend, dry_run=True)
                accepted = (
                    auto_approve or input("Approve this demo plan? Type APPROVE: ") == "APPROVE"
                )
                if auto_approve:
                    print(
                        "Explicit --approve-demo flag: using separate local demo approver identity."
                    )
                run = workflow.approve(
                    run.id, demo_actor(settings, "approver"), run.plan.hash, deny=not accepted
                )
                if accepted:
                    run = workflow.execute(
                        run.id, demo_actor(settings, "executor"), backend, dry_run=False
                    )
                print(f"Outcome: {run.state}")
            if run.state in {State.FAILED, State.NEEDS_INTERVENTION}:
                exit_code = 1
            report(store, run, settings.state_dir / "reports")
        telemetry.export_metrics(str(settings.state_dir / "telemetry" / "metrics.prom"))
        print(f"Evidence: {settings.state_dir / 'reports'}")
        print(f"Audit checkpoint: {store.verify()}")
        return exit_code
    finally:
        store.close()


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Constrained infrastructure remediation")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("init-demo")
    commands.add_parser("snapshot")
    demo_parser = commands.add_parser("demo")
    demo_parser.add_argument(
        "--approve-demo",
        action="store_true",
        help="Explicitly approve using local demo identities; for reproducible CI",
    )
    plan = commands.add_parser("plan")
    plan.add_argument("findings", type=Path)
    plan.add_argument(
        "--format", choices=["normalized", "sarif", "dependabot", "trivy"], default="normalized"
    )
    for name in ("approve", "execute", "reconcile", "report", "inspect"):
        sub = commands.add_parser(name)
        sub.add_argument("run_id")
        if name == "approve":
            sub.add_argument("--digest", required=True)
            sub.add_argument("--deny", action="store_true")
        if name == "execute":
            sub.add_argument("--apply", action="store_true", help="Mutate; default is dry-run")
    commands.add_parser("verify-audit")
    return root


def execute_command(args: argparse.Namespace, settings: Settings) -> int:
    if args.command == "init-demo":
        init_demo(settings)
        return 0
    if args.command == "demo":
        return demo(settings, args.approve_demo)
    token = settings.token.get_secret_value() if settings.token else None
    actor = authenticate(settings.state_dir / "identities.json", token)
    if args.command == "snapshot":
        actor.require("reader")
        backend = backend_for(settings)
        policy = Policy.model_validate(read_json(settings.policy_file))
        atomic_json(
            settings.evidence_file,
            EvidenceBundle(
                backend_id=backend.identity,
                workloads=[backend.read(target) for target in policy.targets],
            ).model_dump(mode="json"),
        )
        return 0
    store = Store(settings.state_dir / "workflow.db")
    workflow = OrchestratorAgent(store, Policy.model_validate(read_json(settings.policy_file)))
    try:
        if args.command == "plan":
            actor.require("planner")
            bundle = EvidenceBundle.model_validate(read_json(settings.evidence_file))
            backend_id = (
                FixtureBackend(settings.state_dir / "workload.json").identity
                if settings.backend == "fixture"
                else bundle.backend_id
            )
            provider: Provider = (
                MockProvider() if settings.provider == "mock" else OpenAIProvider(settings)
            )
            outcomes = [
                workflow.analyze(
                    item, actor, backend_id, provider, MCPReader(settings.evidence_file)
                )
                for item in collect(args.findings, args.format)
            ]
            for run in outcomes:
                display(run)
            return int(any(run.state == State.FAILED for run in outcomes))
        if args.command == "verify-audit":
            actor.require("reader")
            print(store.verify())
            return 0
        if args.command == "approve":
            result = workflow.approve(args.run_id, actor, args.digest, args.deny)
        elif args.command == "execute":
            result = workflow.execute(
                args.run_id, actor, backend_for(settings), dry_run=not args.apply
            )
        elif args.command == "reconcile":
            result = workflow.reconcile(args.run_id, actor, backend_for(settings))
        else:
            actor.require("reader")
            store.verify()
            result = store.get(args.run_id)
            if args.command == "report":
                report(store, result, settings.state_dir / "reports")
        display(result)
        return int(result.state in {State.FAILED, State.NEEDS_INTERVENTION})
    finally:
        telemetry.export_metrics(str(settings.state_dir / "telemetry" / "metrics.prom"))
        store.close()


def main() -> None:
    os.umask(0o077)
    telemetry.configure()
    args = parser().parse_args()
    try:
        sys.exit(execute_command(args, Settings()))
    except (Exception, KeyboardInterrupt) as error:
        print(
            f"Operation stopped safely ({type(error).__name__}); inspect persisted state.",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
