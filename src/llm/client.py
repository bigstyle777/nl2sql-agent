"""LLM 统一调用层。

所有节点不直接 import openai，一律经由本模块调用，从而做到：
  - 服务商切换只改环境变量，不改代码（GLM / DeepSeek / 通义 / OpenAI 均为 OpenAI 兼容协议）
  - 重试、用量统计、超时等横切逻辑集中在一处
  - 后续 M5 扩展新服务商只需在 PROVIDERS 注册表加一行
"""

from __future__ import annotations

import os
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


@dataclass(frozen=True)
class Provider:
    base_url: str
    default_model: str
    key_env: str


PROVIDERS: dict[str, Provider] = {
    "glm": Provider("https://open.bigmodel.cn/api/paas/v4", "glm-4-flash", "GLM_API_KEY"),
    "deepseek": Provider("https://api.deepseek.com", "deepseek-chat", "DEEPSEEK_API_KEY"),
    "qwen": Provider(
        "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus", "QWEN_API_KEY"
    ),
    "openai": Provider("https://api.openai.com/v1", "gpt-4o-mini", "OPENAI_API_KEY"),
}

RETRYABLE_ERRORS = (ConnectionError, TimeoutError)


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    base_url: str
    model: str
    api_key: str

    @property
    def masked_key(self) -> str:
        return f"{self.api_key[:4]}***" if len(self.api_key) > 4 else "***"


@dataclass
class ChatResult:
    content: str
    model: str
    provider: str
    usage: dict[str, int] = field(default_factory=dict)


def resolve_config(
    provider: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
) -> LLMConfig:
    """解析 LLM 配置。显式参数 > 环境变量 > 内置注册表默认值。"""
    provider = (provider or os.getenv("LLM_PROVIDER", "glm")).lower()
    if provider not in PROVIDERS:
        raise ValueError(f"未知服务商 '{provider}'，可选：{sorted(PROVIDERS)}")
    p = PROVIDERS[provider]

    base_url = base_url or os.getenv("LLM_BASE_URL") or p.base_url
    model = model or os.getenv("LLM_MODEL") or p.default_model
    # 通用 Key 优先，其次服务商专属 Key
    api_key = api_key or os.getenv("LLM_API_KEY") or os.getenv(p.key_env) or ""
    if not api_key:
        raise ValueError(
            f"未配置 API Key：请在 .env 中设置 LLM_API_KEY 或 {p.key_env}（服务商: {provider}）"
        )
    return LLMConfig(provider, base_url, model, api_key)


class LLMClient:
    """OpenAI 兼容协议客户端。"""

    def __init__(
        self,
        config: LLMConfig | None = None,
        timeout: float = 60.0,
        max_retries: int = 3,
        retry_backoff: float = 2.0,
    ) -> None:
        self.config = config or resolve_config()
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self._client = OpenAI(
            api_key=self.config.api_key, base_url=self.config.base_url, timeout=timeout
        )

    def chat(
        self,
        messages: Sequence[dict[str, Any]] | str,
        model: str | None = None,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResult:
        """发送对话。messages 可传 OpenAI 格式消息列表，或直接传用户文本。"""
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]
        if system:
            messages = [{"role": "system", "content": system}, *messages]

        temperature = (
            temperature if temperature is not None else float(os.getenv("LLM_TEMPERATURE", "0"))
        )
        max_tokens = max_tokens or int(os.getenv("LLM_MAX_TOKENS", "2048"))

        last_err: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                resp = self._client.chat.completions.create(
                    model=model or self.config.model,
                    messages=list(messages),
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                choice = resp.choices[0]
                usage = {}
                if resp.usage:
                    usage = {
                        "prompt_tokens": resp.usage.prompt_tokens,
                        "completion_tokens": resp.usage.completion_tokens,
                        "total_tokens": resp.usage.total_tokens,
                    }
                return ChatResult(
                    content=choice.message.content or "",
                    model=resp.model,
                    provider=self.config.provider,
                    usage=usage,
                )
            except RETRYABLE_ERRORS as err:  # 网络/超时类错误，退避重试
                last_err = err
                time.sleep(self.retry_backoff**attempt)
        raise RuntimeError(
            f"LLM 调用失败（已重试 {self.max_retries} 次）: {last_err}"
        ) from last_err
