"""ChromaDB 向量存储测试。"""

import pytest

from app.vectorstore.chroma import ChromaVectorStore


def test_create_collection(tmp_path):
    """验证集合可以正常创建。"""
    store = ChromaVectorStore(tmp_path / "chroma")
    collection = store.get_or_create_collection("knowledge_chunks")

    assert collection.name == "knowledge_chunks"
    assert collection.metadata["hnsw:space"] == "cosine"


def test_get_existing_collection(tmp_path):
    """验证重复获取返回同一个集合。"""
    store = ChromaVectorStore(tmp_path / "chroma")

    first = store.get_or_create_collection("knowledge_chunks")
    second = store.get_or_create_collection("knowledge_chunks")

    assert first.id == second.id


@pytest.mark.parametrize("name", ["", "   "])
def test_reject_empty_collection_name(tmp_path, name):
    """验证空集合名称被拒绝。"""
    store = ChromaVectorStore(tmp_path / "chroma")

    with pytest.raises(ValueError, match="集合名称不能为空"):
        store.get_or_create_collection(name)


def test_collection_persistence_after_reinitialization(tmp_path):
    """验证重新初始化客户端后集合仍然存在。"""
    persist_directory = tmp_path / "chroma"

    first_store = ChromaVectorStore(persist_directory)
    first_collection = first_store.get_or_create_collection("knowledge_chunks")
    collection_id = first_collection.id

    del first_collection
    del first_store

    second_store = ChromaVectorStore(persist_directory)
    second_collection = second_store.client.get_collection("knowledge_chunks")

    assert second_collection.id == collection_id
    assert second_collection.name == "knowledge_chunks"


def test_upsert_vectors(tmp_path):
    """验证批量向量写入及元数据保存。"""
    store = ChromaVectorStore(tmp_path / "chroma")

    store.upsert(
        collection_name="knowledge_chunks",
        ids=["1", "2"],
        embeddings=[[0.1, 0.2], [0.3, 0.4]],
        metadatas=[
            {"document_id": 10, "chunk_index": 0},
            {"document_id": 10, "chunk_index": 1},
        ],
    )

    result = store.client.get_collection("knowledge_chunks").get(
        ids=["1", "2"],
        include=["embeddings", "metadatas"],
    )

    assert set(result["ids"]) == {"1", "2"}
    assert result["metadatas"][0]["document_id"] == 10
    assert len(result["embeddings"]) == 2


def test_upsert_updates_existing_vector(tmp_path):
    """验证相同 ID 的向量会被更新。"""
    store = ChromaVectorStore(tmp_path / "chroma")

    store.upsert("knowledge_chunks", ["1"], [[0.1, 0.2]])
    store.upsert(
        "knowledge_chunks",
        ["1"],
        [[0.5, 0.6]],
        [{"document_id": 20}],
    )

    result = store.client.get_collection("knowledge_chunks").get(
        ids=["1"],
        include=["embeddings", "metadatas"],
    )

    assert result["metadatas"][0]["document_id"] == 20
    assert list(result["embeddings"][0]) == pytest.approx([0.5, 0.6])


@pytest.mark.parametrize(
    ("ids", "embeddings", "metadatas", "error"),
    [
        ([], [], None, ValueError),
        (["1"], [], None, ValueError),
        (["1", "1"], [[0.1], [0.2]], None, ValueError),
        (["1"], [[0.1], [0.2, 0.3]], None, ValueError),
        (["1"], [[float("nan")]], None, ValueError),
        (["1"], [[0.1]], [{}], ValueError),
        (["1"], [[0.1]], [{"nested": {"a": 1}}], TypeError),
    ],
)
def test_upsert_rejects_invalid_input(
    tmp_path,
    ids,
    embeddings,
    metadatas,
    error,
):
    """验证无效向量数据在写入前被拒绝。"""
    store = ChromaVectorStore(tmp_path / "chroma")

    with pytest.raises(error):
        store.upsert("knowledge_chunks", ids, embeddings, metadatas)


def test_get_vectors_by_ids(tmp_path):
    """验证按 ID 批量读取向量和元数据。"""
    store = ChromaVectorStore(tmp_path / "chroma")
    store.upsert(
        "knowledge_chunks",
        ["1", "2"],
        [[0.1, 0.2], [0.3, 0.4]],
        [{"document_id": 10}, {"document_id": 20}],
    )

    result = store.get("knowledge_chunks", ["2", "missing", "1"])

    assert set(result["ids"]) == {"1", "2"}
    assert len(result["embeddings"]) == 2
    metadata = dict(zip(result["ids"], result["metadatas"], strict=True))
    assert metadata["1"]["document_id"] == 10
    assert metadata["2"]["document_id"] == 20


@pytest.mark.parametrize(
    "ids",
    [
        [],
        [""],
        ["   "],
        ["1", "1"],
    ],
)
def test_get_rejects_invalid_ids(tmp_path, ids):
    """验证无效向量 ID 在读取前被拒绝。"""
    store = ChromaVectorStore(tmp_path / "chroma")

    with pytest.raises(ValueError):
        store.get("knowledge_chunks", ids)


def test_delete_vectors_by_ids(tmp_path):
    """验证按 ID 批量删除向量。"""
    store = ChromaVectorStore(tmp_path / "chroma")
    store.upsert(
        "knowledge_chunks",
        ["1", "2", "3"],
        [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]],
        [
            {"document_id": 10},
            {"document_id": 10},
            {"document_id": 20},
        ],
    )

    store.delete("knowledge_chunks", ["1", "3"])
    result = store.get("knowledge_chunks", ["1", "2", "3"])

    assert result["ids"] == ["2"]
    assert result["metadatas"][0]["document_id"] == 10


@pytest.mark.parametrize(
    "ids",
    [
        [],
        [""],
        ["   "],
        ["1", "1"],
    ],
)
def test_delete_rejects_invalid_ids(tmp_path, ids):
    """验证无效向量 ID 在删除前被拒绝。"""
    store = ChromaVectorStore(tmp_path / "chroma")

    with pytest.raises(ValueError):
        store.delete("knowledge_chunks", ids)


def test_delete_missing_id_is_safe(tmp_path):
    """验证删除不存在的向量 ID 不影响已有数据。"""
    store = ChromaVectorStore(tmp_path / "chroma")
    store.upsert("knowledge_chunks", ["1"], [[0.1, 0.2]])

    store.delete("knowledge_chunks", ["missing"])
    result = store.get("knowledge_chunks", ["1"])

    assert result["ids"] == ["1"]


def test_query_vectors_returns_similarity_results(tmp_path):
    """验证向量查询按相似度返回结果。"""
    store = ChromaVectorStore(tmp_path / "chroma")
    store.upsert(
        "knowledge_chunks",
        ["1", "2", "3"],
        [[1.0, 0.0], [0.9, 0.1], [0.0, 1.0]],
        [
            {"knowledge_base_id": 1, "document_id": 10},
            {"knowledge_base_id": 1, "document_id": 20},
            {"knowledge_base_id": 2, "document_id": 30},
        ],
    )

    result = store.query(
        "knowledge_chunks",
        [[1.0, 0.0]],
        n_results=2,
    )

    assert len(result["ids"][0]) == 2
    assert result["ids"][0][0] == "1"
    assert result["distances"][0][0] == pytest.approx(0.0)
    assert result["metadatas"][0][0]["document_id"] == 10


def test_query_vectors_filters_by_knowledge_base(tmp_path):
    """验证向量查询可以隔离不同知识库。"""
    store = ChromaVectorStore(tmp_path / "chroma")
    store.upsert(
        "knowledge_chunks",
        ["1", "2"],
        [[1.0, 0.0], [0.9, 0.1]],
        [
            {"knowledge_base_id": 1},
            {"knowledge_base_id": 2},
        ],
    )

    result = store.query(
        "knowledge_chunks",
        [[1.0, 0.0]],
        n_results=5,
        where={"knowledge_base_id": 2},
    )

    assert result["ids"] == [["2"]]
    assert result["metadatas"][0][0]["knowledge_base_id"] == 2


@pytest.mark.parametrize(
    ("embeddings", "n_results", "where", "error"),
    [
        ([], 5, None, ValueError),
        ([[]], 5, None, ValueError),
        ([[1.0], [1.0, 2.0]], 5, None, ValueError),
        ([[True, 0.0]], 5, None, TypeError),
        ([[float("nan")]], 5, None, ValueError),
        ([[float("inf")]], 5, None, ValueError),
        ([[1.0]], 0, None, ValueError),
        ([[1.0]], True, None, TypeError),
        ([[1.0]], 5, {}, ValueError),
    ],
)
def test_query_rejects_invalid_input(
    tmp_path,
    embeddings,
    n_results,
    where,
    error,
):
    """验证向量查询参数校验。"""
    store = ChromaVectorStore(tmp_path / "chroma")

    with pytest.raises(error):
        store.query(
            "knowledge_chunks",
            embeddings,
            n_results=n_results,
            where=where,
        )


def test_get_all_ids_supports_pagination(tmp_path):
    """验证全部 ID 可以通过分页读取。"""
    store = ChromaVectorStore(tmp_path / "chroma")

    store.upsert(
        "knowledge_chunks",
        ["1", "2", "3", "4", "5"],
        [[0.1, 0.2]] * 5,
    )

    ids = store.get_all_ids("knowledge_chunks", batch_size=2)

    assert len(ids) == 5
    assert set(ids) == {"1", "2", "3", "4", "5"}


def test_get_all_ids_returns_empty_for_empty_collection(tmp_path):
    """验证空集合返回空 ID 列表。"""
    store = ChromaVectorStore(tmp_path / "chroma")
    store.get_or_create_collection("knowledge_chunks")

    assert store.get_all_ids("knowledge_chunks") == []


def test_get_all_ids_rejects_missing_collection(tmp_path):
    """验证不存在的集合不会被自动创建。"""
    store = ChromaVectorStore(tmp_path / "chroma")

    with pytest.raises(Exception):
        store.get_all_ids("knowledge_chunks")

    assert "knowledge_chunks" not in {item.name for item in store.client.list_collections()}


@pytest.mark.parametrize("batch_size", [0, -1])
def test_get_all_ids_rejects_non_positive_batch_size(tmp_path, batch_size):
    """验证非正数分页大小被拒绝。"""
    store = ChromaVectorStore(tmp_path / "chroma")
    store.get_or_create_collection("knowledge_chunks")

    with pytest.raises(ValueError, match="batch_size 必须大于 0"):
        store.get_all_ids("knowledge_chunks", batch_size)


@pytest.mark.parametrize("batch_size", [True, 1.5, "10"])
def test_get_all_ids_rejects_invalid_batch_size_type(tmp_path, batch_size):
    """验证非法分页大小类型被拒绝。"""
    store = ChromaVectorStore(tmp_path / "chroma")
    store.get_or_create_collection("knowledge_chunks")

    with pytest.raises(TypeError, match="batch_size 必须是整数"):
        store.get_all_ids("knowledge_chunks", batch_size)


def test_get_all_records_supports_pagination(tmp_path):
    """验证 ID 和元数据可以分页读取。"""
    store = ChromaVectorStore(tmp_path / "chroma")

    store.upsert(
        "knowledge_chunks",
        ["1", "2", "3"],
        [[0.1, 0.2]] * 3,
        [
            {"knowledge_base_id": 1},
            {"knowledge_base_id": 1},
            {"knowledge_base_id": 2},
        ],
    )

    records = store.get_all_records("knowledge_chunks", batch_size=2)

    assert len(records) == 3

    metadata_by_id = {record["id"]: record["metadata"] for record in records}

    assert metadata_by_id["1"]["knowledge_base_id"] == 1
    assert metadata_by_id["2"]["knowledge_base_id"] == 1
    assert metadata_by_id["3"]["knowledge_base_id"] == 2


def test_get_all_records_returns_empty_for_empty_collection(tmp_path):
    """验证空集合返回空记录列表。"""
    store = ChromaVectorStore(tmp_path / "chroma")
    store.get_or_create_collection("knowledge_chunks")

    assert store.get_all_records("knowledge_chunks") == []


def test_get_all_records_rejects_missing_collection(tmp_path):
    """验证不存在的集合不会被自动创建。"""
    store = ChromaVectorStore(tmp_path / "chroma")

    with pytest.raises(Exception):
        store.get_all_records("knowledge_chunks")

    assert "knowledge_chunks" not in {item.name for item in store.client.list_collections()}


def test_rename_collection_preserves_data(tmp_path):
    """验证重命名后向量和元数据保持不变。"""
    store = ChromaVectorStore(tmp_path / "chroma")
    store.upsert(
        "knowledge_base_test",
        ["chunk-1"],
        [[0.1, 0.2]],
        [{"document_id": 10}],
    )

    store.rename_collection(
        "knowledge_base_test",
        "knowledge_base_test_backup",
    )

    names = {item.name for item in store.client.list_collections()}
    result = store.get("knowledge_base_test_backup", ["chunk-1"])

    assert "knowledge_base_test" not in names
    assert "knowledge_base_test_backup" in names
    assert result["ids"] == ["chunk-1"]
    assert result["metadatas"][0]["document_id"] == 10
    assert list(result["embeddings"][0]) == pytest.approx([0.1, 0.2])


def test_rename_collection_rejects_existing_target(tmp_path):
    """验证目标集合已存在时不会覆盖任何集合。"""
    store = ChromaVectorStore(tmp_path / "chroma")
    store.upsert("source", ["1"], [[0.1, 0.2]])
    store.upsert("target", ["2"], [[0.3, 0.4]])

    with pytest.raises(ValueError, match="目标集合已存在"):
        store.rename_collection("source", "target")

    assert store.get("source", ["1"])["ids"] == ["1"]
    assert store.get("target", ["2"])["ids"] == ["2"]


@pytest.mark.parametrize(
    ("old_name", "new_name", "error"),
    [
        ("", "target", ValueError),
        ("source", "   ", ValueError),
        ("source", "source", ValueError),
        (123, "target", TypeError),
        ("source", None, TypeError),
    ],
)
def test_rename_collection_rejects_invalid_names(
    tmp_path,
    old_name,
    new_name,
    error,
):
    """验证无效集合名称会被拒绝。"""
    store = ChromaVectorStore(tmp_path / "chroma")

    with pytest.raises(error):
        store.rename_collection(old_name, new_name)
