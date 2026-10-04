import json

import httpx
import pytest
from openai import OpenAI
from pydantic import SecretStr, ValidationError
from test_core import finding

from airp.core.config import Settings
from airp.providers import Advice, OpenAIProvider


@pytest.mark.parametrize("provider", ["openai", "azure"])
def test_provider_structured_boundary(monkeypatch, provider):
    advice = Advice(
        impact="Credential exposure", uncertainty="Verify usage", possible_false_positive=False
    )

    def respond(request):
        body = json.loads(request.content)
        assert body["response_format"]["type"] == "json_schema"
        assert "tools" not in body
        return httpx.Response(
            200,
            json={
                "id": "test",
                "object": "chat.completion",
                "created": 1,
                "model": "fixture",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": advice.model_dump_json()},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    client = OpenAI(
        api_key="test",
        base_url="https://model.invalid/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(respond)),
        max_retries=0,
    )
    monkeypatch.setattr(
        "airp.providers.AzureOpenAI" if provider == "azure" else "airp.providers.OpenAI",
        lambda **kwargs: client,
    )
    configured = OpenAIProvider(
        Settings(
            provider=provider,
            api_key=SecretStr("test"),
            model="fixture",
            endpoint="https://model.invalid",
        )
    )
    assert configured.analyze(finding()) == advice
    client.close()


def test_provider_requires_explicit_secure_configuration():
    with pytest.raises(ValueError, match="required"):
        OpenAIProvider(Settings(provider="openai"))
    with pytest.raises(ValueError, match="HTTPS"):
        OpenAIProvider(
            Settings(
                provider="openai",
                api_key=SecretStr("test"),
                model="fixture",
                endpoint="http://model.invalid",
            )
        )
    with pytest.raises(ValidationError):
        Advice.model_validate(
            {
                "impact": "approve",
                "uncertainty": "none",
                "possible_false_positive": False,
                "command": "shell",
            }
        )
