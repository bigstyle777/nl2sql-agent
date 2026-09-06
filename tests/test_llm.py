"""LLM 配置解析测试（不发起网络请求）。"""

import pytest

from src.llm.client import PROVIDERS, LLMClient, resolve_config


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in (
        "LLM_PROVIDER",
        "LLM_BASE_URL",
        "LLM_MODEL",
        "LLM_API_KEY",
        "LLM_TEMPERATURE",
        "LLM_MAX_TOKENS",
        "GLM_API_KEY",
        "DEEPSEEK_API_KEY",
        "QWEN_API_KEY",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)


def test_default_provider_with_dedicated_key(monkeypatch):
    monkeypatch.setenv("GLM_API_KEY", "sk-glm-123")
    config = resolve_config()
    assert config.provider == "glm"
    assert config.base_url == PROVIDERS["glm"].base_url
    assert config.model == PROVIDERS["glm"].default_model
    assert config.api_key == "sk-glm-123"


def test_explicit_args_override_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "glm")
    monkeypatch.setenv("LLM_MODEL", "glm-4-plus")
    config = resolve_config(provider="deepseek", model="deepseek-reasoner", api_key="sk-x")
    assert config.provider == "deepseek"
    assert config.model == "deepseek-reasoner"
    assert config.base_url == PROVIDERS["deepseek"].base_url


def test_generic_key_takes_priority(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-generic")
    monkeypatch.setenv("GLM_API_KEY", "sk-dedicated")
    config = resolve_config()
    assert config.api_key == "sk-generic"


def test_custom_endpoint_override(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-x")
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.setenv("LLM_MODEL", "my-local-model")
    config = resolve_config(provider="glm")
    assert config.base_url == "http://localhost:8000/v1"
    assert config.model == "my-local-model"


def test_provider_is_case_insensitive():
    assert resolve_config(provider="DeepSeek", api_key="sk-x").provider == "deepseek"


def test_unknown_provider_raises():
    with pytest.raises(ValueError, match="未知服务商"):
        resolve_config(provider="claude", api_key="sk-x")


def test_missing_key_raises_with_hint(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        resolve_config()


def test_chat_with_string_input_builds_messages(monkeypatch):
    """字符串入参应转成消息列表并插入 system。"""
    captured = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            resp = type("R", (), {})()
            choice = type("C", (), {})()
            choice.message = type("M", (), {"content": "ok"})()
            resp.choices = [choice]
            resp.model = "fake-model"
            resp.usage = None
            return resp

    monkeypatch.setenv("GLM_API_KEY", "sk-fake")
    client = LLMClient(resolve_config(), max_retries=1)
    client._client.chat.completions = FakeCompletions()

    result = client.chat("你好", system="你是助手", temperature=0.5, max_tokens=100)
    assert result.content == "ok"
    assert captured["messages"] == [
        {"role": "system", "content": "你是助手"},
        {"role": "user", "content": "你好"},
    ]
    assert captured["temperature"] == 0.5
    assert captured["max_tokens"] == 100
