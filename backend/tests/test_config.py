"""KnowledgeFlow 配置模块测试。"""

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.core.paths import ENV_FILE


@pytest.fixture(autouse=True)
def clear_settings_cache():
    """每次测试前后清理配置缓存。"""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_settings_default_values():
    """测试配置默认值。"""
    settings = Settings(_env_file=None)

    assert settings.app_name == "KnowledgeFlow"
    assert settings.app_version == "0.1.0"
    assert settings.debug is False
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.api_prefix == "/api/v1"
    assert settings.log_level == "INFO"
    assert settings.log_file == "knowledgeflow.log"
    assert settings.log_max_bytes == 10 * 1024 * 1024
    assert settings.log_backup_count == 5
    assert settings.max_upload_size_bytes == 20 * 1024 * 1024


def test_settings_reads_environment_variables(monkeypatch):
    """测试环境变量覆盖默认配置。"""
    monkeypatch.setenv("KLF_APP_NAME", "KnowledgeFlow-Test")
    monkeypatch.setenv("KLF_DEBUG", "true")
    monkeypatch.setenv("KLF_PORT", "9000")
    monkeypatch.setenv("KLF_LOG_LEVEL", "DEBUG")

    settings = Settings(_env_file=None)

    assert settings.app_name == "KnowledgeFlow-Test"
    assert settings.debug is True
    assert settings.port == 9000
    assert settings.log_level == "DEBUG"


def test_settings_reads_env_file(tmp_path):
    """测试从指定 .env 文件读取配置。"""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "KLF_APP_NAME=KnowledgeFlow-Env\nKLF_PORT=9001\nKLF_DEBUG=true\n",
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.app_name == "KnowledgeFlow-Env"
    assert settings.port == 9001
    assert settings.debug is True


def test_environment_variables_override_env_file(tmp_path, monkeypatch):
    """测试系统环境变量优先级高于 .env 文件。"""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "KLF_APP_NAME=KnowledgeFlow-Env\nKLF_PORT=9001\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("KLF_APP_NAME", "KnowledgeFlow-System")
    monkeypatch.setenv("KLF_PORT", "9002")

    settings = Settings(_env_file=env_file)

    assert settings.app_name == "KnowledgeFlow-System"
    assert settings.port == 9002


def test_settings_rejects_invalid_port():
    """测试非法端口号校验。"""
    with pytest.raises(ValidationError):
        Settings(port=70000, _env_file=None)


def test_settings_rejects_invalid_log_level():
    """测试非法日志级别校验。"""
    with pytest.raises(ValidationError):
        Settings(log_level="INVALID", _env_file=None)


def test_settings_normalizes_log_level():
    """测试日志级别自动转换为大写。"""
    settings = Settings(log_level=" debug ", _env_file=None)

    assert settings.log_level == "DEBUG"


def test_settings_rejects_invalid_log_size():
    """测试非法日志文件容量。"""
    with pytest.raises(ValidationError):
        Settings(log_max_bytes=0, _env_file=None)


def test_settings_rejects_empty_app_name():
    """测试应用名称不能为空。"""
    with pytest.raises(ValidationError):
        Settings(app_name="   ", _env_file=None)


def test_settings_rejects_empty_host():
    """测试服务地址不能为空。"""
    with pytest.raises(ValidationError):
        Settings(host="", _env_file=None)


@pytest.mark.parametrize(
    "api_prefix",
    [
        "api/v1",
        "/api/v1/",
        "/api//v1",
        "/api/v1?debug=true",
        "/api/v1#section",
    ],
)
def test_settings_rejects_invalid_api_prefix(api_prefix):
    """测试非法 API 前缀。"""
    with pytest.raises(ValidationError):
        Settings(api_prefix=api_prefix, _env_file=None)


def test_settings_accepts_root_api_prefix():
    """测试根路径 API 前缀合法。"""
    settings = Settings(api_prefix="/", _env_file=None)

    assert settings.api_prefix == "/"


@pytest.mark.parametrize(
    "log_file",
    [
        "",
        ".",
        "..",
        "../knowledgeflow.log",
        "/tmp/knowledgeflow.log",
        r"..\knowledgeflow.log",
        "logs/knowledgeflow.log",
    ],
)
def test_settings_rejects_invalid_log_file(log_file):
    """测试非法日志文件名。"""
    with pytest.raises(ValidationError):
        Settings(log_file=log_file, _env_file=None)


def test_settings_cache_returns_same_instance():
    """测试全局配置缓存。"""
    first = get_settings()
    second = get_settings()

    assert first is second


def test_settings_cache_can_be_cleared():
    """测试配置缓存可以主动清除。"""
    first = get_settings()

    get_settings.cache_clear()

    second = get_settings()

    assert first is not second


def test_settings_uses_absolute_env_file():
    """测试 Settings 使用项目根目录下的绝对环境变量文件路径。"""
    configured_env_file = Settings.model_config["env_file"]

    assert configured_env_file == ENV_FILE
    assert ENV_FILE.is_absolute()


def test_settings_env_file_is_independent_of_working_directory(tmp_path, monkeypatch):
    """测试切换工作目录不会改变环境变量文件路径。"""
    monkeypatch.chdir(tmp_path)

    settings = Settings()

    assert Settings.model_config["env_file"] == ENV_FILE
    assert ENV_FILE.is_absolute()
    assert settings.app_name


def test_settings_reads_max_upload_size_from_environment(monkeypatch):
    """测试通过环境变量配置最大上传文件大小。"""
    monkeypatch.setenv("KLF_MAX_UPLOAD_SIZE_BYTES", "10485760")

    settings = Settings(_env_file=None)

    assert settings.max_upload_size_bytes == 10 * 1024 * 1024


@pytest.mark.parametrize(
    "max_upload_size_bytes",
    [0, -1],
)
def test_settings_rejects_invalid_max_upload_size(max_upload_size_bytes):
    """测试拒绝非法上传文件大小限制。"""
    with pytest.raises(ValidationError):
        Settings(
            max_upload_size_bytes=max_upload_size_bytes,
            _env_file=None,
        )


def test_settings_default_pdf_limits():
    """测试 PDF 资源限制默认值。"""
    settings = Settings(_env_file=None)

    assert settings.pdf_max_pages == 500
    assert settings.pdf_max_page_chars == 200_000
    assert settings.pdf_max_total_chars == 2_000_000


def test_settings_reads_pdf_limits_from_environment(monkeypatch):
    """测试通过环境变量配置 PDF 资源限制。"""
    monkeypatch.setenv("KLF_PDF_MAX_PAGES", "300")
    monkeypatch.setenv("KLF_PDF_MAX_PAGE_CHARS", "100000")
    monkeypatch.setenv("KLF_PDF_MAX_TOTAL_CHARS", "1000000")

    settings = Settings(_env_file=None)

    assert settings.pdf_max_pages == 300
    assert settings.pdf_max_page_chars == 100_000
    assert settings.pdf_max_total_chars == 1_000_000


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("pdf_max_pages", 0),
        ("pdf_max_pages", -1),
        ("pdf_max_page_chars", 0),
        ("pdf_max_page_chars", -1),
        ("pdf_max_total_chars", 0),
        ("pdf_max_total_chars", -1),
    ],
)
def test_settings_rejects_invalid_pdf_limits(field, value):
    """测试拒绝非正数 PDF 资源限制。"""
    with pytest.raises(ValidationError):
        Settings(**{field: value}, _env_file=None)


def test_settings_rejects_page_limit_greater_than_total_limit():
    """测试单页字符上限不能大于全文字符上限。"""
    with pytest.raises(ValidationError, match="pdf_max_page_chars"):
        Settings(
            pdf_max_page_chars=2_000_001,
            pdf_max_total_chars=2_000_000,
            _env_file=None,
        )


def test_settings_default_embedding_values():
    """测试 Ollama 和 Embedding 配置默认值。"""
    settings = Settings(_env_file=None)

    assert settings.ollama_base_url == "http://localhost:11434"
    assert settings.embedding_model == "nomic-embed-text:latest"
    assert settings.embedding_timeout_seconds == 60.0


def test_settings_reads_embedding_environment_variables(monkeypatch):
    """测试从环境变量读取 Ollama 和 Embedding 配置。"""
    monkeypatch.setenv("KLF_OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    monkeypatch.setenv("KLF_EMBEDDING_MODEL", "nomic-embed-text:latest")
    monkeypatch.setenv("KLF_EMBEDDING_TIMEOUT_SECONDS", "90")

    settings = Settings(_env_file=None)

    assert settings.ollama_base_url == "http://127.0.0.1:11434"
    assert settings.embedding_model == "nomic-embed-text:latest"
    assert settings.embedding_timeout_seconds == 90.0


@pytest.mark.parametrize(
    "timeout",
    [0, -1, -0.1],
)
def test_settings_rejects_invalid_embedding_timeout(timeout):
    """测试拒绝非正数 Embedding 请求超时。"""
    with pytest.raises(ValidationError):
        Settings(embedding_timeout_seconds=timeout, _env_file=None)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("ollama_base_url", ""),
        ("embedding_model", ""),
    ],
)
def test_settings_rejects_empty_embedding_config(field, value):
    """测试拒绝空 Ollama 地址和 Embedding 模型名称。"""
    with pytest.raises(ValidationError):
        Settings(**{field: value}, _env_file=None)


def test_settings_default_chat_values():
    """测试 Ollama 对话配置默认值。"""
    settings = Settings(_env_file=None)

    assert settings.chat_model == "qwen2.5-coder:7b"
    assert settings.chat_timeout_seconds == 180.0


def test_settings_reads_chat_values_from_environment(monkeypatch):
    """测试通过环境变量配置 Ollama 对话服务。"""
    monkeypatch.setenv("KLF_CHAT_MODEL", "qwen2.5-coder:1.5b")
    monkeypatch.setenv("KLF_CHAT_TIMEOUT_SECONDS", "120")

    settings = Settings(_env_file=None)

    assert settings.chat_model == "qwen2.5-coder:1.5b"
    assert settings.chat_timeout_seconds == 120.0


@pytest.mark.parametrize("timeout", [0, -1])
def test_settings_rejects_invalid_chat_timeout(timeout):
    """测试拒绝非法对话超时时间。"""
    with pytest.raises(ValidationError):
        Settings(chat_timeout_seconds=timeout, _env_file=None)
