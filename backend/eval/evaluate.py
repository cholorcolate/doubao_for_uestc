"""
检索质量评测：分别跑「纯向量」「混合检索」「混合+Rerank」三组，量化对比

指标：
- hit@1 / hit@5：期望 tid 出现在第 1 / 前 5 条结果中的比例
- MRR@5：首个命中结果排名的倒数平均

使用方法：
    python evaluate.py [--no-rerank]
说明：
- 只评检索（不调用生成），Rerank 组会调用硅基流动 Rerank API（约 47 次请求）
- 评测集：同目录 eval_set.jsonl，每行 {"q", "tid", "title", "board"}
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag import RagEngine  # noqa: E402

EVAL_FILE = Path(__file__).resolve().parent / "eval_set.jsonl"
TOP_K = 5


def loadCases():
    cases = []
    with open(EVAL_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def scoreRun(name: str, results: list, cases: list) -> dict:
    """results[i] 为第 i 条问题的召回列表（元素含 tid）"""
    hit1 = hit5 = 0
    rr = 0.0
    misses = []
    for case, hits in zip(cases, results):
        tids = [str(h.get("tid", "")) for h in hits]
        expected = str(case["tid"])
        if expected in tids:
            rank = tids.index(expected) + 1
            if rank == 1:
                hit1 += 1
            if rank <= TOP_K:
                hit5 += 1
                rr += 1.0 / rank
        else:
            misses.append(case["q"])
    n = len(cases)
    return {
        "name": name,
        "hit1": hit1 / n,
        "hit5": hit5 / n,
        "mrr": rr / n,
        "misses": misses,
    }


def runVectorOnly(engine: RagEngine, cases: list) -> list:
    """组A：纯向量（原基线）"""
    results = []
    for case in cases:
        hits = engine._vectorSearch(case["q"])[:TOP_K]
        results.append(hits)
    return results


def runHybrid(engine: RagEngine, cases: list, useRerank: bool) -> list:
    """组B/C：混合检索（可选 Rerank）"""
    results = []
    for case in cases:
        hits = engine.retrieve(case["q"], topK=TOP_K, useRerank=useRerank)
        results.append(hits)
    return results


def main():
    parser = argparse.ArgumentParser(description="检索质量评测")
    parser.add_argument("--no-rerank", action="store_true", help="跳过 Rerank 组")
    args = parser.parse_args()

    cases = loadCases()
    print(f"评测集: {len(cases)} 条\n")
    engine = RagEngine.instance()
    engine.warmup()

    runs = []

    print("[1/3] 组A：纯向量 ...", flush=True)
    t0 = time.time()
    vectorResults = runVectorOnly(engine, cases)
    runs.append(scoreRun("A 纯向量（基线）", vectorResults, cases))
    print(f"      完成，耗时 {time.time() - t0:.0f}s")

    print("[2/3] 组B：混合检索（向量+BM25 RRF） ...", flush=True)
    t0 = time.time()
    hybridResults = runHybrid(engine, cases, useRerank=False)
    runs.append(scoreRun("B 混合检索", hybridResults, cases))
    print(f"      完成，耗时 {time.time() - t0:.0f}s")

    if not args.no_rerank:
        print("[3/3] 组C：混合检索+Rerank ...", flush=True)
        t0 = time.time()
        rerankResults = runHybrid(engine, cases, useRerank=True)
        runs.append(scoreRun("C 混合+Rerank", rerankResults, cases))
        print(f"      完成，耗时 {time.time() - t0:.0f}s")

    print("\n" + "=" * 62)
    print(f"{'组别':<22}{'hit@1':>10}{'hit@5':>10}{'MRR@5':>10}")
    print("-" * 62)
    for r in runs:
        print(f"{r['name']:<22}{r['hit1']:>9.1%}{r['hit5']:>10.1%}{r['mrr']:>10.3f}")
    print("=" * 62)

    for r in runs:
        if r["misses"]:
            print(f"\n{r['name']} 未命中({len(r['misses'])}):")
            for q in r["misses"]:
                print(f"  - {q}")

    # 结果落盘便于回溯
    outPath = Path(__file__).resolve().parent / "eval_result.json"
    outPath.write_text(
        json.dumps(runs, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n结果已保存: {outPath}")


if __name__ == "__main__":
    main()
