"""KnowledgeFlow 日志模块测试。"""

import pytest

import app.core.logging as logging_module
from app.core.config import Settings
from app.core.logging import get_logger, setup_logging


@pytest.fixture
def log_dir(tmp_path):
    """为每个测试创建独立日志目录。"""
    return tmp_path / "logs"


def test_setup_logging_creates_log_file(log_dir):
    """测试日志初始化及文件创建。"""
    logger = setup_logging(log_dir=log_dir)

    logger.info("测试日志文件创建")

    log_file = log_dir / "knowledgeflow.log"

    assert log_file.exists()
    assert "测试日志文件创建" in log_file.read_text(encoding="utf-8")


def test_get_logger_returns_child_logger(log_dir):
    """测试业务 Logger 的命名空间。"""
    setup_logging(log_dir=log_dir)

    logger = get_logger("app.services.document")

    assert logger.name == "knowledgeflow.app.services.document"
    assert logger.parent.name == "knowledgeflow"


def test_logging_level_filters_debug_messages(log_dir):
    """测试日志级别过滤。"""
    logger = setup_logging(
        log_level="WARNING",
        log_dir=log_dir,
    )

    logger.debug("这条 DEBUG 日志不应该出现")
    logger.warning("这是一条 WARNING 日志")

    log_content = (log_dir / "knowledgeflow.log").read_text(encoding="utf-8")

    assert "这条 DEBUG 日志不应该出现" not in log_content
    assert "这是一条 WARNING 日志" in log_content


def test_invalid_log_level_raises_error(log_dir):
    """测试非法日志级别。"""
    with pytest.raises(ValueError):
        setup_logging(
            log_level="INVALID",
            log_dir=log_dir,
        )


def test_logging_rotation(log_dir):
    """测试日志文件自动轮转。"""
    logger = setup_logging(
        log_level="INFO",
        log_dir=log_dir,
        max_bytes=200,
        backup_count=2,
    )

    for index in range(30):
        logger.info("轮转测试日志 %s：%s", index, "测试内容" * 10)

    assert (log_dir / "knowledgeflow.log").exists()
    assert (log_dir / "knowledgeflow.log.1").exists()


def test_setup_logging_uses_settings_defaults(tmp_path, monkeypatch):
    """测试日志初始化默认读取统一 Settings 配置。"""
    settings = Settings(
        log_level="DEBUG",
        log_file="custom.log",
        log_max_bytes=4096,
        log_backup_count=3,
    )

    monkeypatch.setattr(logging_module, "get_settings", lambda: settings)
    monkeypatch.setattr(logging_module, "LOG_DIR", tmp_path / "logs")

    logger = setup_logging()

    log_file = tmp_path / "logs" / "custom.log"
    file_handler = next(
        handler
        for handler in logger.handlers
        if isinstance(handler, logging_module.RotatingFileHandler)
    )

    assert log_file.exists()
    assert logger.level == 10
    assert file_handler.maxBytes == 4096
    assert file_handler.backupCount == 3


def test_setup_logging_explicit_arguments_override_settings(tmp_path, monkeypatch):
    """测试显式传入的参数优先于统一 Settings 配置。"""
    settings = Settings(
        log_level="ERROR",
        log_file="default.log",
        log_max_bytes=4096,
        log_backup_count=3,
    )

    monkeypatch.setattr(logging_module, "get_settings", lambda: settings)

    logger = setup_logging(
        log_level="WARNING",
        log_dir=tmp_path,
        log_file="custom.log",
        max_bytes=2048,
        backup_count=2,
    )

    file_handler = next(
        handler
        for handler in logger.handlers
        if isinstance(handler, logging_module.RotatingFileHandler)
    )

    assert (tmp_path / "custom.log").exists()
    assert not (tmp_path / "default.log").exists()
    assert logger.level == 30
    assert file_handler.maxBytes == 2048
    assert file_handler.backupCount == 2
