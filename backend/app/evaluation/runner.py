"""KnowledgeFlow 检索评估运行器。"""

import argparse
import asyncio
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from app.core.paths import PROJECT_ROOT
from app.db.engine import create_database_engine
from app.db.session import create_session_factory
from app.embeddings import EmbeddingService
from app.evaluation.metrics import evaluate_ranking
from app.services.bm25_search import BM25SearchService
from app.services.hybrid_search import HybridSearchService
from app.services.vector_search import VectorSearchService
from app.vectorstore import ChromaVectorStore

DEFAULT_DATASET = PROJECT_ROOT / "data" / "evaluation" / "ground_truth.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "evaluation" / "report.json"

METHODS = ("bm25", "vector", "hybrid")


def load_dataset(dataset_path: Path) -> list[dict[str, Any]]:
    """读取并校验人工标注的评估数据集。"""
    try:
        data = json.loads(dataset_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取评估数据集：{dataset_path}") from exc

    if not isinstance(data, list) or not data:
        raise ValueError("评估数据集必须是非空列表")

    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"第 {index} 条评估数据必须是对象")

        query = item.get("query")
        knowledge_base_id = item.get("knowledge_base_id")
        relevance = item.get("relevant_chunks")

        if not isinstance(query, str) or not query.strip():
            raise ValueError(f"第 {index} 条查询文本不能为空")

        if (
            isinstance(knowledge_base_id, bool)
            or not isinstance(knowledge_base_id, int)
            or knowledge_base_id <= 0
        ):
            raise ValueError(f"第 {index} 条 knowledge_base_id 必须是正整数")

        if not isinstance(relevance, dict) or not relevance:
            raise ValueError(f"第 {index} 条 relevant_chunks 必须是非空对象")

        normalized = {}
        for chunk_id, grade in relevance.items():
            try:
                parsed_id = int(chunk_id)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"第 {index} 条 chunk_id 必须是正整数") from exc

            if parsed_id <= 0:
                raise ValueError(f"第 {index} 条 chunk_id 必须大于 0")

            if isinstance(grade, bool) or not isinstance(grade, int) or grade not in (0, 1, 2):
                raise ValueError(f"第 {index} 条相关性等级只能是 0、1 或 2")

            normalized[parsed_id] = grade

        item["relevant_chunks"] = normalized

    return data


def _serialize_results(
    ranked_ids: list[int],
    relevance: dict[int, int],
    elapsed_ms: float,
    top_k: int,
) -> dict[str, Any]:
    """整理单种检索方法的结果。"""
    metrics = evaluate_ranking(ranked_ids, relevance, top_k)

    return {
        "ranked_chunk_ids": ranked_ids,
        "latency_ms": round(elapsed_ms, 3),
        "metrics": {
            "precision": round(metrics.precision, 6),
            "recall": round(metrics.recall, 6),
            "mrr": round(metrics.mrr, 6),
            "ndcg": round(metrics.ndcg, 6),
        },
    }


async def run_evaluation(
    dataset_path: Path = DEFAULT_DATASET,
    output_path: Path = DEFAULT_OUTPUT,
    top_k: int = 5,
    collection_name: str | None = None,
    collection_knowledge_base_id: int = 2,
) -> dict[str, Any]:
    """运行 BM25、向量和混合检索评估。"""
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k <= 0:
        raise ValueError("top_k 必须是大于 0 的整数")

    if collection_name is not None:
        if not isinstance(collection_name, str):
            raise TypeError("collection_name 必须是字符串")
        if not collection_name.strip():
            raise ValueError("collection_name 不能为空")

    if (
        isinstance(collection_knowledge_base_id, bool)
        or not isinstance(collection_knowledge_base_id, int)
        or collection_knowledge_base_id <= 0
    ):
        raise ValueError("collection_knowledge_base_id 必须是正整数")

    dataset = load_dataset(dataset_path)

    engine = create_database_engine()
    session_factory = create_session_factory(engine)

    try:
        async with httpx.AsyncClient() as client:
            embedding_service = EmbeddingService(client=client)
            vector_store = ChromaVectorStore()

            query_reports = []

            for index, item in enumerate(dataset, start=1):
                query = item["query"]
                knowledge_base_id = item["knowledge_base_id"]
                relevance = item["relevant_chunks"]

                print(f"[{index}/{len(dataset)}] KB={knowledge_base_id} 查询：{query}")

                async with session_factory() as session:
                    bm25_service = BM25SearchService(session=session)
                    selected_collection = (
                        collection_name
                        if knowledge_base_id == collection_knowledge_base_id
                        else None
                    )

                    vector_service = VectorSearchService(
                        session=session,
                        embedding_service=embedding_service,
                        vector_store=vector_store,
                        collection_name=selected_collection,
                    )
                    hybrid_service = HybridSearchService(
                        session=session,
                        vector_search_service=vector_service,
                        bm25_search_service=bm25_service,
                    )

                    method_results = {}

                    for method, service in (
                        ("bm25", bm25_service),
                        ("vector", vector_service),
                        ("hybrid", hybrid_service),
                    ):
                        started = time.perf_counter()

                        results = await service.search(
                            query=query,
                            knowledge_base_id=knowledge_base_id,
                            top_k=top_k,
                        )

                        elapsed_ms = (time.perf_counter() - started) * 1000
                        ranked_ids = [result.chunk_id for result in results]

                        method_results[method] = _serialize_results(
                            ranked_ids=ranked_ids,
                            relevance=relevance,
                            elapsed_ms=elapsed_ms,
                            top_k=top_k,
                        )

                        print(f"  {method:>6}: 排名={ranked_ids} 耗时={elapsed_ms:.2f}ms")

                query_reports.append(
                    {
                        "query": query,
                        "knowledge_base_id": knowledge_base_id,
                        "relevant_chunks": {
                            str(chunk_id): grade for chunk_id, grade in relevance.items()
                        },
                        "results": method_results,
                    }
                )

        # 计算各方法在全部查询上的宏平均。
        averages = {}

        for method in METHODS:
            averages[method] = {}

            for metric in ("precision", "recall", "mrr", "ndcg", "latency_ms"):
                values = [
                    report["results"][method][
                        "metrics" if metric != "latency_ms" else "latency_ms"
                    ][metric]
                    if metric != "latency_ms"
                    else report["results"][method]["latency_ms"]
                    for report in query_reports
                ]

                averages[method][metric] = round(
                    sum(values) / len(values),
                    6,
                )

        report = {
            "generated_at": datetime.now(UTC).isoformat(),
            "dataset": str(dataset_path),
            "query_count": len(query_reports),
            "top_k": top_k,
            "vector_collection_override": (
                {
                    "knowledge_base_id": collection_knowledge_base_id,
                    "collection_name": collection_name,
                }
                if collection_name is not None
                else None
            ),
            "averages": averages,
            "queries": query_reports,
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return report

    finally:
        await engine.dispose()


def main() -> None:
    """命令行入口。"""
    parser = argparse.ArgumentParser(description="KnowledgeFlow BM25、向量和混合检索评估")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET,
        help="Ground Truth JSON 文件路径",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="评估报告输出路径",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="检索结果数量及指标计算 K 值",
    )
    parser.add_argument(
        "--collection",
        type=str,
        default=None,
        help="指定知识库使用的 Chroma 集合名称",
    )
    parser.add_argument(
        "--collection-knowledge-base-id",
        type=int,
        default=2,
        help="应用自定义集合名称的知识库 ID，默认 2",
    )

    args = parser.parse_args()

    report = asyncio.run(
        run_evaluation(
            dataset_path=args.dataset,
            output_path=args.output,
            top_k=args.top_k,
            collection_name=args.collection,
            collection_knowledge_base_id=args.collection_knowledge_base_id,
        )
    )

    print("\n===== 检索评估宏平均 =====")
    for method, metrics in report["averages"].items():
        print(
            f"{method:>6}: "
            f"P@{report['top_k']}={metrics['precision']:.4f} "
            f"R@{report['top_k']}={metrics['recall']:.4f} "
            f"MRR={metrics['mrr']:.4f} "
            f"nDCG={metrics['ndcg']:.4f} "
            f"耗时={metrics['latency_ms']:.2f}ms"
        )

    print(f"\n评估报告已保存：{args.output}")


if __name__ == "__main__":
    main()
