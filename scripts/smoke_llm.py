"""LLM 连通性冒烟测试。

用法:
    python scripts/smoke_llm.py "上月各品类销售额是多少"
    python scripts/smoke_llm.py --provider deepseek "你好"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.llm.client import LLMClient, resolve_config  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM 连通性冒烟测试")
    parser.add_argument("question", nargs="?", default="用一句话介绍你自己")
    parser.add_argument(
        "--provider", default=None, help="临时指定服务商（glm/deepseek/qwen/openai）"
    )
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    config = resolve_config(provider=args.provider, model=args.model)
    print(
        f"provider={config.provider}  model={config.model}  base_url={config.base_url}  key={config.masked_key}"
    )

    client = LLMClient(config)
    result = client.chat(args.question, system="你是数据分析助手，回答保持简洁。")
    print(f"\n回复：{result.content}")
    print(f"用量：{result.usage}")


if __name__ == "__main__":
    main()
