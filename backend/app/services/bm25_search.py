"""KnowledgeFlow BM25 关键词检索服务。"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.tokenizers import BertWordPieceTokenizer
from app.repositories import DocumentChunkRepository
from app.retrieval.bm25 import BM25Retriever
from app.retrieval.text_builder import RetrievalTextBuilder


@dataclass(frozen=True, slots=True)
class BM25SearchResult:
    """BM25 关键词检索结果。"""

    chunk_id: int
    document_id: int
    document_name: str
    chunk_index: int
    content: str
    token_count: int
    score: float


class BM25SearchService:
    """协调 SQLite 分块读取、Tokenizer 分词和 BM25 关键词召回。"""

    PAGE_SIZE = 500

    def __init__(
        self,
        session: AsyncSession,
        tokenizer: BertWordPieceTokenizer | None = None,
        repository: DocumentChunkRepository | None = None,
    ) -> None:
        """初始化 BM25 检索服务。"""
        self.tokenizer = tokenizer or BertWordPieceTokenizer()
        self.repository = repository or DocumentChunkRepository(session)

    @staticmethod
    def _validate_inputs(
        query: str,
        knowledge_base_id: int,
        top_k: int,
    ) -> None:
        """校验检索参数。"""
        if not isinstance(query, str) or not query.strip():
            raise ValueError("查询文本不能为空")

        if isinstance(knowledge_base_id, bool) or not isinstance(knowledge_base_id, int):
            raise TypeError("knowledge_base_id 必须是整数")
        if knowledge_base_id <= 0:
            raise ValueError("knowledge_base_id 必须大于 0")

        if isinstance(top_k, bool) or not isinstance(top_k, int):
            raise TypeError("top_k 必须是整数")
        if top_k <= 0:
            raise ValueError("top_k 必须大于 0")

    async def _load_chunks(self, knowledge_base_id: int):
        """分页读取知识库中所有已完成文档的分块。"""
        chunks = []
        offset = 0

        while True:
            page = await self.repository.get_by_knowledge_base(
                knowledge_base_id=knowledge_base_id,
                offset=offset,
                limit=self.PAGE_SIZE,
            )

            if not page:
                break

            chunks.extend(page)
            offset += len(page)

            if len(page) < self.PAGE_SIZE:
                break

        return chunks

    async def search(
        self,
        query: str,
        knowledge_base_id: int,
        top_k: int = 5,
    ) -> list[BM25SearchResult]:
        """检索指定知识库中的关键词相关分块。"""
        self._validate_inputs(query, knowledge_base_id, top_k)

        query_tokens = self.tokenizer.tokenize(query)
        if not query_tokens:
            return []

        chunks = await self._load_chunks(knowledge_base_id)
        if not chunks:
            return []

        corpus = [
            self.tokenizer.tokenize(
                RetrievalTextBuilder.build(
                    chunk.content,
                    chunk.chunk_metadata,
                )
            )
            for chunk in chunks
        ]
        retriever = BM25Retriever(corpus)
        ranked_results = retriever.search(query_tokens, top_k=top_k)

        results = []

        for item in ranked_results:
            chunk = chunks[item.document_index]
            results.append(
                BM25SearchResult(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    document_name=chunk.document.name,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    token_count=chunk.token_count,
                    score=item.score,
                )
            )

        return results
