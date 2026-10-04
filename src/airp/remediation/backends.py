import json
import os
import time
from pathlib import Path
from typing import Any, Protocol

from kubernetes.client import ApiClient, AppsV1Api, Configuration
from kubernetes.config import load_kube_config

from airp.core.models import Plan, Snapshot, Target, digest
from airp.core.security import Forbidden, read_json
from airp.remediation.catalog import json_patch


class Backend(Protocol):
    @property
    def identity(self) -> str: ...
    def read(self, target: Target) -> Snapshot: ...
    def apply(self, plan: Plan, dry_run: bool = False) -> None: ...
    def observe(self, target: Target) -> Snapshot: ...


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        os.chmod(temporary, 0o600)
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


class FixtureBackend:
    def __init__(self, path: Path) -> None:
        self.path = path

    @property
    def identity(self) -> str:
        return "fixture:" + digest(str(self.path.resolve()))

    def read(self, target: Target) -> Snapshot:
        snapshot = Snapshot.model_validate(read_json(self.path))
        if snapshot.target != target:
            raise Forbidden("Fixture target mismatch")
        return snapshot

    def apply(self, plan: Plan, dry_run: bool = False) -> None:
        current = self.read(plan.target)
        if (
            current.uid != plan.before.uid
            or current.resource_version != plan.before.resource_version
        ):
            raise Forbidden("Fixture precondition failed")
        if dry_run:
            return
        updated = current.model_copy(
            update={
                "spec": plan.expected_spec,
                "resource_version": str(int(current.resource_version) + 1),
                "generation": current.generation + 1,
                "observed_generation": current.generation + 1,
            }
        )
        atomic_json(self.path, updated.model_dump(mode="json"))

    def observe(self, target: Target) -> Snapshot:
        return self.read(target)


class KubernetesBackend:
    def __init__(self, kubeconfig: Path, context: str, timeout: int = 90) -> None:
        configuration = Configuration()
        load_kube_config(
            config_file=str(kubeconfig), context=context, client_configuration=configuration
        )
        if not configuration.verify_ssl:
            raise Forbidden("Kubernetes TLS verification must be enabled")
        self.api_client = ApiClient(configuration)
        self.api = AppsV1Api(self.api_client)
        ca = Path(configuration.ssl_ca_cert).read_text() if configuration.ssl_ca_cert else "system"
        self._identity = "kubernetes:" + digest({"server": configuration.host, "ca": ca})
        self.timeout = timeout

    @property
    def identity(self) -> str:
        return self._identity

    def read(self, target: Target) -> Snapshot:
        deployment = self.api.read_namespaced_deployment(
            target.name, target.namespace, _request_timeout=(5, 15)
        )
        value = self.api_client.sanitize_for_serialization(deployment)
        metadata, state = value["metadata"], value.get("status", {})
        return Snapshot(
            target=target,
            uid=metadata["uid"],
            resource_version=metadata["resourceVersion"],
            generation=metadata["generation"],
            observed_generation=state.get("observedGeneration", 0),
            ready_replicas=state.get("readyReplicas", 0),
            updated_replicas=state.get("updatedReplicas", 0),
            available_replicas=state.get("availableReplicas", 0),
            spec=value["spec"],
        )

    def apply(self, plan: Plan, dry_run: bool = False) -> None:
        self.api_client.call_api(
            "/apis/apps/v1/namespaces/{namespace}/deployments/{name}",
            "PATCH",
            path_params={"namespace": plan.target.namespace, "name": plan.target.name},
            query_params=[("dryRun", "All")] if dry_run else [],
            header_params={
                "Content-Type": "application/json-patch+json",
                "Accept": "application/json",
            },
            body=json_patch(plan),
            response_type="V1Deployment",
            auth_settings=["BearerToken"],
            _return_http_data_only=True,
            _request_timeout=(5, 20),
        )

    def observe(self, target: Target) -> Snapshot:
        deadline = time.monotonic() + self.timeout
        while True:
            observed = self.read(target)
            if observed.healthy or time.monotonic() >= deadline:
                return observed
            time.sleep(1)
