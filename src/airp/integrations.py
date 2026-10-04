from pathlib import Path
from typing import Any, Literal

from pydantic import TypeAdapter

from airp.core.models import Finding, digest
from airp.core.security import read_json

Format = Literal["normalized", "sarif", "dependabot", "trivy"]


def severity(value: str) -> str:
    return {
        "critical": "critical",
        "high": "high",
        "medium": "medium",
        "moderate": "medium",
        "low": "low",
        "error": "high",
        "warning": "medium",
        "note": "low",
    }.get(value.lower(), "unknown")


def normalized(
    source: str, category: str, rule: str, level: str, description: str, component: str
) -> Finding:
    return Finding.model_validate(
        {
            "id": digest({"source": source, "rule": rule, "component": component})[:32],
            "source": source,
            "category": category,
            "rule_id": rule[:160] or "unknown",
            "severity": severity(level),
            "description": description[:8000],
            "component": component[:300],
        }
    )


def collect(path: Path, format: Format = "normalized") -> list[Finding]:
    data: Any = read_json(path)
    findings: list[Finding] = []
    if format == "normalized":
        findings = TypeAdapter(list[Finding]).validate_python(data)
    elif format == "sarif":
        for run in data.get("runs", []):
            for result in run.get("results", []):
                locations = result.get("locations", [])
                component = (
                    locations[0]
                    .get("physicalLocation", {})
                    .get("artifactLocation", {})
                    .get("uri", "unknown")
                    if locations
                    else "unknown"
                )
                findings.append(
                    normalized(
                        "codeql",
                        "code",
                        result.get("ruleId", "unknown"),
                        result.get("level", "warning"),
                        result.get("message", {}).get("text", ""),
                        component,
                    )
                )
    elif format == "dependabot":
        for alert in data:
            advisory = alert["security_advisory"]
            findings.append(
                normalized(
                    "dependabot",
                    "dependency",
                    advisory["ghsa_id"],
                    advisory.get("severity", "unknown"),
                    advisory.get("summary", ""),
                    alert["dependency"]["package"]["name"],
                )
            )
    elif format == "trivy":
        for result in data.get("Results", []):
            for item in result.get("Vulnerabilities", []) or []:
                category = "os" if result.get("Class") == "os-pkgs" else "container"
                component = f"{result.get('Target', 'unknown')}:{item.get('PkgName', 'unknown')}"
                findings.append(
                    normalized(
                        "trivy",
                        category,
                        item["VulnerabilityID"],
                        item.get("Severity", "unknown"),
                        item.get("Title", ""),
                        component,
                    )
                )
    if not findings or len(findings) > 1000:
        raise ValueError("Expected between 1 and 1000 findings")
    unique: dict[str, Finding] = {}
    for item in findings:
        if item.id in unique and unique[item.id] != item:
            raise ValueError("Conflicting findings share an identifier")
        unique[item.id] = item
    priority = {"critical": 0, "high": 1, "medium": 2, "low": 3, "unknown": 4}
    return sorted(unique.values(), key=lambda item: (priority[item.severity], item.id))
