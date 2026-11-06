"""KnowledgeFlow ChromaDB 向量存储模块。"""

import math
from pathlib import Path

import chromadb

from app.core.paths import CHROMA_DIR

type MetadataValue = str | int | float | bool


class ChromaVectorStore:
    """管理 ChromaDB 持久化客户端和向量集合。"""

    def __init__(self, persist_directory: Path | str | None = None) -> None:
        """初始化 ChromaDB 持久化客户端。"""
        self.persist_directory = Path(persist_directory or CHROMA_DIR)
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(self.persist_directory))

    def get_or_create_collection(self, name: str):
        """获取已有集合；不存在时创建集合。"""
        if not name or not name.strip():
            raise ValueError("集合名称不能为空")
        return self.client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert(
        self,
        collection_name: str,
        ids: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, MetadataValue]] | None = None,
    ) -> None:
        """批量新增或更新向量及其元数据。"""
        if not ids:
            raise ValueError("向量 ID 列表不能为空")
        if any(not isinstance(item, str) or not item.strip() for item in ids):
            raise ValueError("向量 ID 必须是非空字符串")
        if len(set(ids)) != len(ids):
            raise ValueError("向量 ID 不能重复")
        if len(ids) != len(embeddings):
            raise ValueError("向量 ID 数量必须与 Embedding 数量一致")
        if metadatas is not None and len(metadatas) != len(ids):
            raise ValueError("元数据数量必须与向量 ID 数量一致")

        vectors: list[list[float]] = []
        dimension = None

        for embedding in embeddings:
            if not isinstance(embedding, list) or not embedding:
                raise ValueError("Embedding 必须是非空列表")
            if dimension is None:
                dimension = len(embedding)
            elif len(embedding) != dimension:
                raise ValueError("所有 Embedding 的维度必须一致")

            vector = []
            for value in embedding:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise TypeError("Embedding 元素必须是数值")
                if not math.isfinite(value):
                    raise ValueError("Embedding 不能包含 NaN 或无穷大")
                vector.append(float(value))
            vectors.append(vector)

        if metadatas is not None:
            for metadata in metadatas:
                if not isinstance(metadata, dict) or not metadata:
                    raise ValueError("每条元数据必须是非空字典")
                for key, value in metadata.items():
                    if not isinstance(key, str) or not key.strip():
                        raise ValueError("元数据键必须是非空字符串")
                    if not isinstance(value, (str, int, float, bool)):
                        raise TypeError("元数据值只能是字符串、整数、浮点数或布尔值")
                    if isinstance(value, float) and not math.isfinite(value):
                        raise ValueError("元数据不能包含 NaN 或无穷大")

        collection = self.get_or_create_collection(collection_name)
        collection.upsert(ids=ids, embeddings=vectors, metadatas=metadatas)

    def query(
        self,
        collection_name: str,
        query_embeddings: list[list[float]],
        n_results: int = 5,
        where: dict | None = None,
    ) -> dict:
        """根据查询向量执行相似度检索。"""
        if not isinstance(query_embeddings, list) or not query_embeddings:
            raise ValueError("查询向量列表不能为空")

        if isinstance(n_results, bool) or not isinstance(n_results, int):
            raise TypeError("n_results 必须是整数")
        if n_results <= 0:
            raise ValueError("n_results 必须大于 0")

        if where is not None and (not isinstance(where, dict) or not where):
            raise ValueError("where 必须是非空字典或 None")

        vectors: list[list[float]] = []
        dimension = None

        for embedding in query_embeddings:
            if not isinstance(embedding, list) or not embedding:
                raise ValueError("查询 Embedding 必须是非空列表")

            if dimension is None:
                dimension = len(embedding)
            elif len(embedding) != dimension:
                raise ValueError("查询 Embedding 的维度必须一致")

            vector = []
            for value in embedding:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise TypeError("查询 Embedding 元素必须是数值")
                if not math.isfinite(value):
                    raise ValueError("查询 Embedding 不能包含 NaN 或无穷大")
                vector.append(float(value))

            vectors.append(vector)

        collection = self.client.get_collection(name=collection_name)
        return collection.query(
            query_embeddings=vectors,
            n_results=n_results,
            where=where,
            include=["metadatas", "distances"],
        )

    def get_all_ids(
        self,
        collection_name: str,
        batch_size: int = 500,
    ) -> list[str]:
        """分页读取集合中的全部向量 ID，不读取向量和元数据。"""
        if not isinstance(collection_name, str) or not collection_name.strip():
            raise ValueError("集合名称不能为空")

        if isinstance(batch_size, bool) or not isinstance(batch_size, int):
            raise TypeError("batch_size 必须是整数")
        if batch_size <= 0:
            raise ValueError("batch_size 必须大于 0")

        # 只获取已有集合，绝不自动创建。
        collection = self.client.get_collection(name=collection_name)

        ids: list[str] = []
        offset = 0

        while True:
            result = collection.get(
                limit=batch_size,
                offset=offset,
                include=[],
            )
            batch_ids = result["ids"]
            ids.extend(batch_ids)

            if len(batch_ids) < batch_size:
                break

            offset += len(batch_ids)

        return ids

    def get_all_records(
        self,
        collection_name: str,
        batch_size: int = 500,
    ) -> list[dict]:
        """分页读取集合中的 ID 和元数据，不读取 Embedding。"""
        if not isinstance(collection_name, str) or not collection_name.strip():
            raise ValueError("集合名称不能为空")

        if isinstance(batch_size, bool) or not isinstance(batch_size, int):
            raise TypeError("batch_size 必须是整数")
        if batch_size <= 0:
            raise ValueError("batch_size 必须大于 0")

        collection = self.client.get_collection(name=collection_name)

        records = []
        offset = 0

        while True:
            result = collection.get(
                limit=batch_size,
                offset=offset,
                include=["metadatas"],
            )

            ids = result["ids"]
            metadatas = result["metadatas"]

            if len(ids) != len(metadatas):
                raise RuntimeError("Chroma 返回的 ID 和元数据数量不一致")

            records.extend(
                {"id": vector_id, "metadata": metadata}
                for vector_id, metadata in zip(ids, metadatas, strict=True)
            )

            if len(ids) < batch_size:
                break

            offset += len(ids)

        return records

    def get(self, collection_name: str, ids: list[str]) -> dict:
        """根据向量 ID 批量读取向量和元数据。"""
        if not ids:
            raise ValueError("向量 ID 列表不能为空")
        if any(not isinstance(item, str) or not item.strip() for item in ids):
            raise ValueError("向量 ID 必须是非空字符串")
        if len(set(ids)) != len(ids):
            raise ValueError("向量 ID 不能重复")

        collection = self.client.get_collection(name=collection_name)
        return collection.get(
            ids=ids,
            include=["embeddings", "metadatas"],
        )

    def delete(self, collection_name: str, ids: list[str]) -> None:
        """根据向量 ID 批量删除向量及其元数据。"""
        if not ids:
            raise ValueError("向量 ID 列表不能为空")
        if any(not isinstance(item, str) or not item.strip() for item in ids):
            raise ValueError("向量 ID 必须是非空字符串")
        if len(set(ids)) != len(ids):
            raise ValueError("向量 ID 不能重复")

        collection = self.client.get_collection(name=collection_name)
        collection.delete(ids=ids)

    def rename_collection(self, old_name: str, new_name: str) -> None:
        """安全重命名集合，不覆盖已有集合。"""
        for name in (old_name, new_name):
            if not isinstance(name, str):
                raise TypeError("集合名称必须是字符串")
            if not name.strip():
                raise ValueError("集合名称不能为空")

        if old_name == new_name:
            raise ValueError("新旧集合名称不能相同")

        # 先获取源集合，确保源集合真实存在。
        collection = self.client.get_collection(name=old_name)

        existing_names = {item.name for item in self.client.list_collections()}
        if new_name in existing_names:
            raise ValueError(f"目标集合已存在: {new_name}")

        collection.modify(name=new_name)
