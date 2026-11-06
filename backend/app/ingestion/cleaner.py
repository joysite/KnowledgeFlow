"""KnowledgeFlow 文档文本清洗模块。"""

import unicodedata


class DocumentCleaner:
    """负责规范化文档文本，不修改文档语义和结构。"""

    @staticmethod
    def clean(content: str) -> str:
        """
        清洗文档文本。

        Args:
            content: 解析器输出的原始文本。

        Returns:
            规范化后的文本。

        Raises:
            TypeError: 输入内容不是字符串。
        """
        if not isinstance(content, str):
            raise TypeError("待清洗内容必须是字符串")

        # 统一不同平台的换行符。
        normalized = content.replace("\r\n", "\n").replace("\r", "\n")

        # 删除控制字符，保留换行符和 Tab。
        normalized = "".join(
            char
            for char in normalized
            if char in {"\n", "\t"} or unicodedata.category(char) != "Cc"
        )

        # 清理每行末尾空格和 Tab，保留行首缩进。
        lines = [line.rstrip(" \t") for line in normalized.split("\n")]

        # 连续空行最多保留一个。
        cleaned_lines: list[str] = []
        for line in lines:
            if line:
                cleaned_lines.append(line)
            elif cleaned_lines and cleaned_lines[-1] != "":
                cleaned_lines.append("")

        # 删除文档开头和结尾的多余空行。
        while cleaned_lines and cleaned_lines[0] == "":
            cleaned_lines.pop(0)

        while cleaned_lines and cleaned_lines[-1] == "":
            cleaned_lines.pop()

        return "\n".join(cleaned_lines)
