"""KnowledgeFlow 统一检索文本构建器。"""


class RetrievalTextBuilder:
    """为文档分块添加 Markdown 标题上下文。"""

    @staticmethod
    def build(
        content: str,
        metadata: dict | None = None,
    ) -> str:
        """构建检索文本，不修改原始分块正文。"""
        if not isinstance(content, str):
            raise TypeError("content 必须是字符串")

        if metadata is None:
            return content

        if not isinstance(metadata, dict):
            raise TypeError("metadata 必须是字典或 None")

        heading_path = metadata.get("heading_path")

        if not isinstance(heading_path, list):
            return content

        valid_headings = [
            heading.strip()
            for heading in heading_path
            if isinstance(heading, str) and heading.strip()
        ]

        if not valid_headings:
            return content

        return f"{' > '.join(valid_headings)}\n{content}"
