"""KnowledgeFlow 统一配置管理模块。"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.paths import ENV_FILE


class Settings(BaseSettings):
    """KnowledgeFlow 全局应用配置。"""

    model_config = SettingsConfigDict(
        env_prefix="KLF_",
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        validate_default=True,
        str_strip_whitespace=True,
    )

    # 应用基础配置
    app_name: str = Field(default="KnowledgeFlow", min_length=1)
    app_version: str = Field(default="0.1.0", min_length=1)
    debug: bool = False

    # API 服务配置
    host: str = Field(default="127.0.0.1", min_length=1)
    port: int = Field(default=8000, ge=1, le=65535)
    api_prefix: str = Field(default="/api/v1", min_length=1)

    # 日志配置
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_file: str = Field(default="knowledgeflow.log", min_length=1)
    log_max_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    log_backup_count: int = Field(default=5, ge=0)

    # Ollama配置
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        min_length=1,
    )
    # Ollama 对话生成配置
    chat_model: str = Field(
        default="qwen2.5-coder:7b",
        min_length=1,
    )
    chat_timeout_seconds: float = Field(
        default=180.0,
        gt=0,
    )
    # Embedding 配置
    embedding_model: str = Field(
        default="nomic-embed-text:latest",
        min_length=1,
    )
    embedding_timeout_seconds: float = Field(
        default=60.0,
        gt=0,
    )

    # 文档上传配置
    max_upload_size_bytes: int = Field(
        default=20 * 1024 * 1024,
        gt=0,
    )

    # PDF 解析资源限制
    pdf_max_pages: int = Field(default=500, gt=0)
    pdf_max_page_chars: int = Field(default=200_000, gt=0)
    pdf_max_total_chars: int = Field(default=2_000_000, gt=0)

    @model_validator(mode="after")
    def validate_pdf_limits(self) -> "Settings":
        """确保 PDF 单页字符上限不超过全文字符上限。"""
        if self.pdf_max_page_chars > self.pdf_max_total_chars:
            raise ValueError("pdf_max_page_chars 不能大于 pdf_max_total_chars")

        return self

    @field_validator("api_prefix")
    @classmethod
    def validate_api_prefix(cls, value: str) -> str:
        """验证 API 路由前缀格式。"""
        if not value.startswith("/"):
            raise ValueError("api_prefix 必须以 '/' 开头")

        if value != "/" and value.endswith("/"):
            raise ValueError("api_prefix 不能以 '/' 结尾")

        if "//" in value:
            raise ValueError("api_prefix 不能包含连续的 '/'")

        if "?" in value or "#" in value:
            raise ValueError("api_prefix 不能包含查询参数或片段标识")

        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        """统一日志级别大小写。"""
        if isinstance(value, str):
            return value.strip().upper()

        return value

    @field_validator("log_file")
    @classmethod
    def validate_log_file(cls, value: str) -> str:
        """验证日志文件名，禁止目录穿越。"""
        if value in {".", ".."}:
            raise ValueError("log_file 必须是有效的文件名")

        if "/" in value or "\\" in value or "\0" in value:
            raise ValueError("log_file 不能包含目录路径")

        if Path(value).name != value:
            raise ValueError("log_file 必须是有效的文件名")

        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    获取全局配置实例。

    使用缓存避免重复创建 Settings 对象。
    测试环境可以通过 get_settings.cache_clear() 清除缓存。
    """
    return Settings()
