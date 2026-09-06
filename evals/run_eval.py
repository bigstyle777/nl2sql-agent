"""评测入口 CLI。

用法（项目根目录）：
    python evals/run_eval.py --tag baseline                 # 全量 120 题
    python evals/run_eval.py --tag after-pruning --limit 10 # 快速冒烟
    python evals/run_eval.py --tag fix-case --qids 61,99    # 只跑指定题
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.eval.runner import git_commit, load_dataset, run_dataset  # noqa: E402
from src.llm.client import LLMClient, resolve_config  # noqa: E402

REPORT_DIR = Path(__file__).parent / "reports"


def main() -> None:
    parser = argparse.ArgumentParser(description="Text-to-SQL Agent 评测")
    parser.add_argument("--dataset", default="evals/dataset/v1.jsonl")
    parser.add_argument("--db", default="data/ecommerce.db")
    parser.add_argument("--tag", default="run", help="报告命名标签，如 baseline / after-pruning")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--limit", type=int, default=None, help="只跑前 N 题（冒烟用）")
    parser.add_argument("--qids", default=None, help="逗号分隔的题目 id，只跑这些题")
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--no-hints", action="store_true", help="关闭 schema 语义增强（消融用）")
    parser.add_argument(
        "--no-fewshot", action="store_true", help="关闭 few-shot 示例检索（消融用）"
    )
    parser.add_argument("--selection", action="store_true", help="开启动态 schema 裁剪（消融用）")
    args = parser.parse_args()

    qids = [int(x) for x in args.qids.split(",")] if args.qids else None
    items_total = len(load_dataset(Path(args.dataset)))
    print(
        f"评测集：{args.dataset}（共 {items_total} 题）"
        f"，本次跑 {min(args.limit or items_total, len(qids) * len(qids) if qids else items_total)} 题"
    )
    config = resolve_config()
    print(f"模型：{config.provider}/{config.model}，workers={args.workers}")

    client = LLMClient(config)
    t0 = time.monotonic()
    results, summary = run_dataset(
        Path(args.dataset),
        args.db,
        client,
        workers=args.workers,
        max_attempts=args.max_attempts,
        limit=args.limit,
        qids=qids,
        use_hints=not args.no_hints,
        use_fewshot=not args.no_fewshot,
        use_table_selection=args.selection,
        progress_cb=lambda done, total: (
            print(f"  进度 {done}/{total}", flush=True) if done % 10 == 0 or done == total else None
        ),
    )
    summary.update(
        {
            "tag": args.tag,
            "git_commit": git_commit(),
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "model": f"{config.provider}/{config.model}",
            "dataset": Path(args.dataset).name,
            "wall_time_s": round(time.monotonic() - t0, 1),
        }
    )

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stem = f"{args.tag}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    json_path = REPORT_DIR / f"{stem}.json"
    csv_path = REPORT_DIR / f"{stem}.csv"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].__dict__))
        writer.writeheader()
        for r in results:
            writer.writerow(r.__dict__)

    print(f"\n===== 评测报告（{args.tag}）=====")
    print(
        f"执行准确率      : {summary['exec_accuracy']}%  ({summary['correct']}/{summary['total']})"
    )
    print(f"首轮通过率      : {summary['first_round_pass']}%")
    print(
        f"自纠错挽回率    : {summary['saved_by_correction']}%  (挽回 {summary['saved_count']} 题)"
    )
    print(f"平均耗时 / P95  : {summary['avg_latency_s']}s / {summary['p95_latency_s']}s")
    print(
        f"平均 Token/题   : {summary['avg_total_tokens']}（平均 {summary['avg_llm_calls']} 次调用）"
    )
    for diff, d in summary["by_difficulty"].items():
        print(f"  {diff:<7}: {d['accuracy']}%  ({d['total']} 题)")
    print(f"失败归因        : {summary['attribution']}")
    print(f"\n报告已写入：{json_path}\n           {csv_path}")


if __name__ == "__main__":
    main()
