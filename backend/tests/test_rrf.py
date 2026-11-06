"""RRF 排名融合算法测试。"""

import pytest

from app.retrieval.rrf import ReciprocalRankFusion


def test_fuse_combines_two_rankings():
    """同时出现在两路召回中的分块应累加排名贡献。"""
    fusion = ReciprocalRankFusion(k=60)

    results = fusion.fuse(
        [
            [1, 2, 3],
            [2, 3, 4],
        ]
    )

    assert [item.chunk_id for item in results] == [2, 3, 1, 4]
    assert results[0].score == pytest.approx(1 / 62 + 1 / 61)
    assert results[1].score == pytest.approx(1 / 62 + 1 / 63)


def test_fuse_preserves_first_seen_order_for_equal_scores():
    """融合分数相同时保持首次出现顺序。"""
    fusion = ReciprocalRankFusion()

    results = fusion.fuse([[1, 2], [3, 4]])

    assert [item.chunk_id for item in results] == [1, 3, 2, 4]


def test_fuse_ignores_duplicate_ids_in_same_ranking():
    """同一路召回中的重复 ID 只计算首次排名。"""
    fusion = ReciprocalRankFusion(k=60)

    results = fusion.fuse([[1, 1, 2]])

    assert [item.chunk_id for item in results] == [1, 2]
    assert results[0].score == pytest.approx(1 / 61)
    assert results[1].score == pytest.approx(1 / 63)


def test_fuse_respects_top_k():
    """融合结果遵守 Top-K 限制。"""
    fusion = ReciprocalRankFusion()

    results = fusion.fuse([[1, 2, 3], [3, 4]], top_k=2)

    assert len(results) == 2
    assert [item.chunk_id for item in results] == [3, 1]


def test_fuse_handles_empty_rankings():
    """空召回结果不产生融合结果。"""
    fusion = ReciprocalRankFusion()

    assert fusion.fuse([]) == []
    assert fusion.fuse([[], []]) == []


def test_fuse_supports_multiple_rankings():
    """支持三路及以上检索结果融合。"""
    fusion = ReciprocalRankFusion(k=60)

    results = fusion.fuse(
        [
            [1, 2],
            [2, 3],
            [2, 4],
        ]
    )

    assert results[0].chunk_id == 2
    assert results[0].score == pytest.approx(1 / 62 + 2 / 61)


@pytest.mark.parametrize(
    ("k", "error"),
    [
        (0, ValueError),
        (-1, ValueError),
        (True, TypeError),
        (1.5, TypeError),
    ],
)
def test_init_rejects_invalid_k(k, error):
    """拒绝非法 RRF 平滑常数。"""
    with pytest.raises(error):
        ReciprocalRankFusion(k=k)


@pytest.mark.parametrize(
    ("top_k", "error"),
    [
        (0, ValueError),
        (-1, ValueError),
        (True, TypeError),
        ("5", TypeError),
    ],
)
def test_fuse_rejects_invalid_top_k(top_k, error):
    """拒绝非法 Top-K。"""
    fusion = ReciprocalRankFusion()

    with pytest.raises(error):
        fusion.fuse([[1, 2]], top_k=top_k)


@pytest.mark.parametrize(
    ("rankings", "error"),
    [
        ([[1, 0]], ValueError),
        ([[1, -2]], ValueError),
        ([[1, True]], TypeError),
        ([[1, "2"]], TypeError),
        ([None], TypeError),
        (None, TypeError),
    ],
)
def test_fuse_rejects_invalid_rankings(rankings, error):
    """拒绝非法排名数据。"""
    fusion = ReciprocalRankFusion()

    with pytest.raises(error):
        fusion.fuse(rankings)


def test_fuse_does_not_modify_input_rankings():
    """融合过程不修改调用方传入的排名数据。"""
    fusion = ReciprocalRankFusion()
    rankings = [[1, 2], [2, 3]]
    original = [ranking.copy() for ranking in rankings]

    fusion.fuse(rankings)

    assert rankings == original
