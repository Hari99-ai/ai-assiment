"""Parse deployment YAML/JSON locally; semantic deployment checks require their runtimes."""

import json
from pathlib import Path

import yaml


def validate():
    count = 0
    for root in (Path("infra"), Path(".github")):
        for path in root.rglob("*.yml"):
            documents = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
            assert documents and all(isinstance(doc, dict) for doc in documents), path
            count += 1
    compose = yaml.safe_load(Path("docker-compose.yml").read_text())
    assert {"api", "migrate", "postgres", "redis", "worker", "beat"} <= compose["services"].keys()
    for path in Path("infra/monitoring").rglob("*.json"):
        assert json.loads(path.read_text())
        count += 1
    schema = json.loads(Path("docs/openapi.json").read_text())
    assert "/api/v1/consultations" in schema["paths"]
    assert "/api/v1/auth/mfa/verify" in schema["paths"]
    print(f"Parsed {count + 2} deployment/schema artifacts; runtime semantics require target tools")


if __name__ == "__main__":
    validate()
