from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AIRP_", extra="ignore")
    state_dir: Path = Path(".state")
    policy_file: Path = Path("policies/local.json")
    evidence_file: Path = Path("demo/evidence.json")
    provider: Literal["mock", "openai", "azure"] = "mock"
    api_key: SecretStr | None = None
    endpoint: str = "https://api.openai.com/v1"
    model: str = ""
    api_version: str = "2024-10-21"
    token: SecretStr | None = None
    backend: Literal["fixture", "kubernetes"] = "fixture"
    kube_context: str = "kind-airp"
    kubeconfig: Path = Path(".state/executor.kubeconfig")
    rollout_timeout: int = Field(default=90, ge=1, le=300)
