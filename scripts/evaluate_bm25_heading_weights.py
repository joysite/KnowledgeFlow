"""离线比较正文 BM25、标题拼接 BM25 和双通道 BM25。"""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.paths import PROJECT_ROOT
from app.db.engine import create_database_engine
from app.db.session import create_session_factory
from app.evaluation.metrics import evaluate_ranking
from app.evaluation.runner import DEFAULT_DATASET, load_dataset
from app.ingestion.tokenizers import BertWordPieceTokenizer
from app.repositories import DocumentChunkRepository
from app.retrieval.bm25 import BM25Retriever
from app.retrieval.text_builder import RetrievalTextBuilder

TOP_K = 5
PAGE_SIZE = 500
ALPHAS = (0.1, 0.3, 0.5, 1.0)


def get_heading_text(metadata: dict[str, Any] | None) -> str:
    """提取有效标题路径。"""
    if not isinstance(metadata, dict):
        return ""

    path = metadata.get("heading_path")
    if not isinstance(path, list):
        return ""

    headings = [item.strip() for item in path if isinstance(item, str) and item.strip()]
    return " > ".join(headings)


async def load_corpora(
    dataset: list[dict[str, Any]],
    tokenizer: BertWordPieceTokenizer,
) -> dict[int, dict[str, Any]]:
    """按照正式 BM25 服务的查询条件加载分块。"""
    knowledge_base_ids = sorted({item["knowledge_base_id"] for item in dataset})

    engine = create_database_engine()
    session_factory = create_session_factory(engine)
    corpora = {}

    try:
        async with session_factory() as session:
            repository = DocumentChunkRepository(session)

            for kb_id in knowledge_base_ids:
                chunks = []
                offset = 0

                while True:
                    page = await repository.get_by_knowledge_base(
                        knowledge_base_id=kb_id,
                        offset=offset,
                        limit=PAGE_SIZE,
                    )
                    if not page:
                        break

                    chunks.extend(page)
                    offset += len(page)

                    if len(page) < PAGE_SIZE:
                        break

                corpora[kb_id] = {
                    "chunk_ids": [chunk.id for chunk in chunks],
                    "body": [tokenizer.tokenize(chunk.content) for chunk in chunks],
                    "heading": [
                        tokenizer.tokenize(get_heading_text(chunk.chunk_metadata))
                        for chunk in chunks
                    ],
                    "concat": [
                        tokenizer.tokenize(
                            RetrievalTextBuilder.build(
                                chunk.content,
                                chunk.chunk_metadata,
                            )
                        )
                        for chunk in chunks
                    ],
                }

                print(f"知识库 {kb_id}: 加载 {len(chunks)} 个分块")
    finally:
        await engine.dispose()

    return corpora


def score_all(
    retriever: BM25Retriever,
    query_tokens: list[str],
) -> list[float]:
    """按照 BM25Retriever 原始公式计算每个文档的分数。"""
    scores = []

    if not retriever.document_count or retriever.average_document_length == 0:
        return [0.0] * retriever.document_count

    query_terms = set(query_tokens)

    for index, frequencies in enumerate(retriever.term_frequencies):
        document_length = retriever.document_lengths[index]

        normalization = retriever.k1 * (
            1 - retriever.b + retriever.b * document_length / retriever.average_document_length
        )

        score = 0.0

        for term in query_terms:
            term_frequency = frequencies.get(term, 0)
            if not term_frequency:
                continue

            idf = retriever.inverse_document_frequencies.get(term, 0.0)
            denominator = term_frequency + normalization

            score += idf * term_frequency * (retriever.k1 + 1) / denominator

        scores.append(score)

    return scores


def dual_channel_search(
    body_retriever: BM25Retriever,
    heading_retriever: BM25Retriever,
    query_tokens: list[str],
    alpha: float,
) -> list[int]:
    """独立计算标题与正文 BM25，再进行加权融合。"""
    body_scores = score_all(body_retriever, query_tokens)
    heading_scores = score_all(heading_retriever, query_tokens)

    combined = []

    for index, (body_score, heading_score) in enumerate(
        zip(body_scores, heading_scores, strict=True)
    ):
        score = body_score + alpha * heading_score

        if score > 0:
            combined.append((index, score))

    combined.sort(key=lambda item: (-item[1], item[0]))

    return [index for index, _ in combined[:TOP_K]]


def metric_dict(ranked_ids: list[int], relevance: dict[int, int]):
    """计算并整理单条查询的指标。"""
    metrics = evaluate_ranking(ranked_ids, relevance, TOP_K)

    return {
        "precision": round(metrics.precision, 6),
        "recall": round(metrics.recall, 6),
        "mrr": round(metrics.mrr, 6),
        "ndcg": round(metrics.ndcg, 6),
    }


def aggregate(rows: list[dict[str, Any]]) -> dict[str, float]:
    """计算宏平均指标。"""
    count = len(rows)

    return {
        key: round(
            sum(row["metrics"][key] for row in rows) / count,
            6,
        )
        for key in ("precision", "recall", "mrr", "ndcg")
    }


def compare_mrr(
    rows: list[dict[str, Any]],
    baseline_name: str,
    method_name: str,
) -> dict[str, int]:
    """统计逐查询 MRR 的改善、持平和退化数量。"""
    improved = tied = regressed = 0

    for row in rows:
        baseline = row["results"][baseline_name]["metrics"]["mrr"]
        current = row["results"][method_name]["metrics"]["mrr"]

        if current > baseline:
            improved += 1
        elif current < baseline:
            regressed += 1
        else:
            tied += 1

    return {
        "improved": improved,
        "tied": tied,
        "regressed": regressed,
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="BM25 标题双通道权重离线实验")
    parser.add_argument(
        "--output",
        type=Path,
        default=(PROJECT_ROOT / "data" / "evaluation" / "bm25_heading_weights.json"),
    )
    args = parser.parse_args()

    dataset = load_dataset(DEFAULT_DATASET)
    tokenizer = BertWordPieceTokenizer()

    print(f"评估查询数: {len(dataset)}")
    print("正在加载 SQLite 分块并执行分词...")

    corpora = await load_corpora(dataset, tokenizer)

    retrievers = {}
    for kb_id, corpus in corpora.items():
        retrievers[kb_id] = {
            "body": BM25Retriever(corpus["body"]),
            "heading": BM25Retriever(corpus["heading"]),
            "concat": BM25Retriever(corpus["concat"]),
        }

    method_names = [
        "body_only",
        "heading_concat",
        *[f"dual_alpha_{alpha}" for alpha in ALPHAS],
    ]

    rows = []

    for query_index, item in enumerate(dataset, start=1):
        kb_id = item["knowledge_base_id"]
        query_tokens = tokenizer.tokenize(item["query"])
        relevance = item["relevant_chunks"]

        corpus = corpora[kb_id]
        models = retrievers[kb_id]
        chunk_ids = corpus["chunk_ids"]

        body_results = models["body"].search(query_tokens, top_k=TOP_K)
        concat_results = models["concat"].search(query_tokens, top_k=TOP_K)

        rankings = {
            "body_only": [chunk_ids[result.document_index] for result in body_results],
            "heading_concat": [chunk_ids[result.document_index] for result in concat_results],
        }

        for alpha in ALPHAS:
            indices = dual_channel_search(
                models["body"],
                models["heading"],
                query_tokens,
                alpha,
            )
            rankings[f"dual_alpha_{alpha}"] = [chunk_ids[index] for index in indices]

        results = {
            name: {
                "ranked_chunk_ids": rankings[name],
                "metrics": metric_dict(rankings[name], relevance),
            }
            for name in method_names
        }

        rows.append(
            {
                "query": item["query"],
                "knowledge_base_id": kb_id,
                "relevant_chunks": {str(key): value for key, value in relevance.items()},
                "results": results,
            }
        )

        print(f"[{query_index}/{len(dataset)}] {item['query'][:35]}")

    averages = {name: aggregate([row["results"][name] for row in rows]) for name in method_names}

    comparisons = {
        name: compare_mrr(rows, "body_only", name) for name in method_names if name != "body_only"
    }

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset": str(DEFAULT_DATASET.relative_to(PROJECT_ROOT)),
        "query_count": len(rows),
        "top_k": TOP_K,
        "alpha_values": list(ALPHAS),
        "averages": averages,
        "mrr_comparisons_vs_body_only": comparisons,
        "queries": rows,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\n===== BM25 双通道实验结果 =====")
    print(f"{'方法':<22} {'P@5':>9} {'R@5':>9} {'MRR@5':>9} {'nDCG@5':>9}")

    for name, metrics in averages.items():
        print(
            f"{name:<22} "
            f"{metrics['precision']:>9.4f} "
            f"{metrics['recall']:>9.4f} "
            f"{metrics['mrr']:>9.4f} "
            f"{metrics['ndcg']:>9.4f}"
        )

    print("\n===== 相对正文 BM25 的逐查询 MRR 变化 =====")
    for name, result in comparisons.items():
        print(
            f"{name}: 改善 {result['improved']}，持平 {result['tied']}，退化 {result['regressed']}"
        )

    print(f"\n实验报告: {args.output}")
    print("实验完成，未修改正式检索服务和向量索引。")


if __name__ == "__main__":
    asyncio.run(main())
