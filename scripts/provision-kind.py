import argparse
import base64
import json
import os
import subprocess
from pathlib import Path

import yaml

from airp.admission import EXECUTOR
from airp.remediation.backends import atomic_json


def kubectl(*arguments: str) -> str:
    return subprocess.run(
        ["kubectl", "--context", "kind-airp", *arguments],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout


def main() -> None:
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument("--credentials-only", action="store_true")
    args = parser.parse_args()
    root = Path(".state")
    config = json.loads(kubectl("config", "view", "--raw", "--flatten", "--minify", "-o", "json"))
    for account in ("executor", "observer"):
        token = kubectl(
            "-n", "airp-system", "create", "token", f"airp-{account}", "--duration=1h"
        ).strip()
        credentials = {
            "apiVersion": "v1",
            "kind": "Config",
            "clusters": config["clusters"],
            "users": [{"name": account, "user": {"token": token}}],
            "contexts": [
                {
                    "name": "kind-airp",
                    "context": {"cluster": config["clusters"][0]["name"], "user": account},
                }
            ],
            "current-context": "kind-airp",
        }
        (root / f"{account}.kubeconfig").write_text(yaml.safe_dump(credentials))
        (root / f"{account}.kubeconfig").chmod(0o600)
    if not args.credentials_only:
        webhook = {
            "apiVersion": "admissionregistration.k8s.io/v1",
            "kind": "ValidatingWebhookConfiguration",
            "metadata": {"name": "airp-catalog-guard"},
            "webhooks": [
                {
                    "name": "catalog.airp.example",
                    "admissionReviewVersions": ["v1"],
                    "sideEffects": "None",
                    "failurePolicy": "Fail",
                    "timeoutSeconds": 5,
                    "matchConditions": [
                        {
                            "name": "executor-only",
                            "expression": f"request.userInfo.username == '{EXECUTOR}'",
                        }
                    ],
                    "clientConfig": {
                        "service": {
                            "name": "airp-admission",
                            "namespace": "airp-system",
                            "path": "/validate",
                            "port": 443,
                        },
                        "caBundle": base64.b64encode((root / "tls/tls.crt").read_bytes()).decode(),
                    },
                    "rules": [
                        {
                            "apiGroups": ["apps"],
                            "apiVersions": ["v1"],
                            "operations": ["UPDATE"],
                            "resources": ["deployments", "deployments/*"],
                            "scope": "Namespaced",
                        }
                    ],
                }
            ],
        }
        atomic_json(root / "webhook.json", webhook)
        kubectl("apply", "-f", str(root / "webhook.json"))
    print("Provisioned short-lived executor and observer credentials (not displayed).")


if __name__ == "__main__":
    main()
