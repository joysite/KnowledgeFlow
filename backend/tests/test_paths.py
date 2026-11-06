"""KnowledgeFlow 项目路径模块测试。"""

from pathlib import Path

from app.core.paths import (
    APP_DIR,
    BACKEND_DIR,
    CHROMA_DIR,
    DATA_DIR,
    DATABASE_FILE,
    ENV_EXAMPLE_FILE,
    ENV_FILE,
    LOG_DIR,
    PROJECT_ROOT,
    UPLOAD_DIR,
)


def test_project_root_is_correct():
    """测试项目根目录定位正确。"""
    assert PROJECT_ROOT.is_absolute()
    assert PROJECT_ROOT.name == "KnowledgeFlow"
    assert (PROJECT_ROOT / "pyproject.toml").is_file()


def test_project_directory_relationships():
    """测试项目目录之间的层级关系。"""
    assert BACKEND_DIR == PROJECT_ROOT / "backend"
    assert APP_DIR == BACKEND_DIR / "app"


def test_data_directory_relationships():
    """测试数据目录之间的层级关系。"""
    assert DATA_DIR == PROJECT_ROOT / "data"
    assert UPLOAD_DIR == DATA_DIR / "uploads"
    assert CHROMA_DIR == DATA_DIR / "chroma"
    assert LOG_DIR == DATA_DIR / "logs"
    assert DATABASE_FILE == DATA_DIR / "knowledgeflow.db"


def test_environment_file_paths():
    """测试环境变量文件路径。"""
    assert ENV_FILE == PROJECT_ROOT / ".env"
    assert ENV_EXAMPLE_FILE == PROJECT_ROOT / ".env.example"


def test_all_paths_are_path_objects():
    """测试所有路径常量均为 Path 对象。"""
    paths = [
        PROJECT_ROOT,
        BACKEND_DIR,
        APP_DIR,
        DATA_DIR,
        DATABASE_FILE,
        UPLOAD_DIR,
        CHROMA_DIR,
        LOG_DIR,
        ENV_FILE,
        ENV_EXAMPLE_FILE,
    ]

    assert all(isinstance(path, Path) for path in paths)
    assert all(path.is_absolute() for path in paths)
