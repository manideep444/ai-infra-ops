from pathlib import Path

import yaml


def test_workload_and_executor_boundaries():
    documents = [
        document
        for path in Path("kubernetes").glob("*.yaml")
        for document in yaml.safe_load_all(path.read_text())
        if document
    ]
    deployments = [doc for doc in documents if doc["kind"] == "Deployment"]
    assert len(deployments) == 2
    for deployment in deployments:
        assert deployment["spec"]["replicas"] >= 2
        for container in deployment["spec"]["template"]["spec"]["containers"]:
            assert container["readinessProbe"] and container["livenessProbe"]
            assert container["resources"]["limits"]
            assert container["securityContext"]["readOnlyRootFilesystem"]
    executor = next(
        doc
        for doc in documents
        if doc["kind"] == "Role" and doc["metadata"]["name"] == "airp-executor"
    )
    assert executor["rules"] == [
        {
            "apiGroups": ["apps"],
            "resources": ["deployments"],
            "resourceNames": ["demo-web"],
            "verbs": ["get", "patch"],
        }
    ]
