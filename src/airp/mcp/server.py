import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from airp.core.models import Contract, Snapshot, Target
from airp.core.security import Forbidden, read_json

TOOLS = frozenset(
    {
        "workload",
        "vulnerability",
        "repository",
        "container",
        "configuration",
        "history",
        "validation",
    }
)


class EvidenceBundle(Contract):
    backend_id: str = "fixture"
    workloads: list[Snapshot] = Field(max_length=10)
    vulnerabilities: dict[str, dict[str, str]] = Field(default_factory=dict)
    repositories: dict[str, dict[str, str]] = Field(default_factory=dict)
    history: dict[str, list[dict[str, str]]] = Field(default_factory=dict)
    validations: dict[str, dict[str, bool]] = Field(default_factory=dict)


class EvidenceTools:
    def __init__(self, path: Path) -> None:
        self.bundle = EvidenceBundle.model_validate(read_json(path, 256_000))

    def workload(self, namespace: str, name: str) -> dict[str, Any]:
        target = Target(namespace=namespace, name=name)
        for snapshot in self.bundle.workloads:
            if snapshot.target == target:
                return snapshot.model_dump(mode="json")
        raise Forbidden("Target not in evidence allowlist")

    def vulnerability(self, identifier: str) -> dict[str, str]:
        if identifier not in self.bundle.vulnerabilities:
            raise Forbidden("Unknown vulnerability")
        return self.bundle.vulnerabilities[identifier]

    def repository(self, name: str) -> dict[str, str]:
        if name not in self.bundle.repositories:
            raise Forbidden("Unknown repository")
        return self.bundle.repositories[name]

    def container(self, namespace: str, name: str) -> dict[str, Any]:
        snapshot = self.workload(namespace, name)
        return {
            "images": [item["image"] for item in snapshot["spec"]["template"]["spec"]["containers"]]
        }

    def configuration(self, namespace: str, name: str) -> dict[str, Any]:
        snapshot = self.workload(namespace, name)
        pod = snapshot["spec"]["template"]["spec"]
        return {"automountServiceAccountToken": pod.get("automountServiceAccountToken")}

    def history(self, run_id: str) -> dict[str, Any]:
        if run_id not in self.bundle.history:
            raise Forbidden("Run not in exported history allowlist")
        return {"events": self.bundle.history[run_id]}

    def validation(self, run_id: str) -> dict[str, bool]:
        if run_id not in self.bundle.validations:
            raise Forbidden("Run not in exported validation allowlist")
        return self.bundle.validations[run_id]


def create_server(path: Path) -> FastMCP:
    server = FastMCP("airp-evidence")
    tools = EvidenceTools(path)
    for name in sorted(TOOLS):
        server.tool(name=name)(getattr(tools, name))
    return server


def main() -> None:
    create_server(Path(os.environ["AIRP_EVIDENCE_FILE"])).run(transport="stdio")


if __name__ == "__main__":
    main()
