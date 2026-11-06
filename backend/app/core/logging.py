"""KnowledgeFlow 统一日志管理模块。"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Final

from app.core.config import get_settings
from app.core.paths import LOG_DIR

LOGGER_NAME: Final[str] = "knowledgeflow"

LOG_FORMAT: Final[str] = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
DATE_FORMAT: Final[str] = "%Y-%m-%d %H:%M:%S"


def setup_logging(
    log_level: str | None = None,
    log_dir: str | Path | None = None,
    log_file: str | None = None,
    max_bytes: int | None = None,
    backup_count: int | None = None,
) -> logging.Logger:
    """
    初始化 KnowledgeFlow 全局日志系统。

    未显式传入的参数从统一 Settings 配置中读取。

    Args:
        log_level: 日志级别，支持 DEBUG、INFO、WARNING、ERROR、CRITICAL。
        log_dir: 日志保存目录，默认使用项目 data/logs 目录。
        log_file: 日志文件名称。
        max_bytes: 单个日志文件最大容量。
        backup_count: 保留的历史日志文件数量。

    Returns:
        配置完成的 KnowledgeFlow 根 Logger。
    """
    settings = get_settings()

    # 优先使用显式参数，否则读取统一配置。
    effective_level = log_level if log_level is not None else settings.log_level
    effective_dir = Path(log_dir) if log_dir is not None else LOG_DIR
    effective_file = log_file if log_file is not None else settings.log_file
    effective_max_bytes = max_bytes if max_bytes is not None else settings.log_max_bytes
    effective_backup_count = backup_count if backup_count is not None else settings.log_backup_count

    normalized_level = effective_level.strip().upper()
    level = getattr(logging, normalized_level, None)

    if not isinstance(level, int):
        raise ValueError(f"不支持的日志级别: {effective_level}")

    if effective_max_bytes <= 0:
        raise ValueError("max_bytes 必须大于 0")

    if effective_backup_count < 0:
        raise ValueError("backup_count 不能小于 0")

    if not effective_file or "\0" in effective_file or Path(effective_file).name != effective_file:
        raise ValueError("log_file 必须是有效的文件名，不能包含目录路径")

    effective_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False

    # 避免重复初始化时产生重复日志输出。
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(
        fmt=LOG_FORMAT,
        datefmt=DATE_FORMAT,
    )

    # 控制台处理器。
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    # 文件处理器：达到容量后自动轮转。
    file_path = effective_dir / effective_file
    file_handler = RotatingFileHandler(
        filename=file_path,
        maxBytes=effective_max_bytes,
        backupCount=effective_backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    logger.info("KnowledgeFlow 日志系统初始化成功")
    logger.info("日志目录: %s", effective_dir.resolve())
    logger.info("日志级别: %s", normalized_level)

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    获取 KnowledgeFlow 业务 Logger。

    Args:
        name: 模块名称，通常传入 __name__。

    Returns:
        对应模块的 Logger。
    """
    if not name or not name.strip():
        raise ValueError("Logger 名称不能为空")

    if name == LOGGER_NAME or name.startswith(f"{LOGGER_NAME}."):
        logger_name = name
    else:
        logger_name = f"{LOGGER_NAME}.{name}"

    return logging.getLogger(logger_name)
