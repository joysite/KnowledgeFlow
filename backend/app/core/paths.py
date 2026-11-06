"""KnowledgeFlow 项目路径统一管理模块。"""

from pathlib import Path
from typing import Final

# 项目根目录
PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[3]

# 项目目录
BACKEND_DIR: Final[Path] = PROJECT_ROOT / "backend"
APP_DIR: Final[Path] = BACKEND_DIR / "app"

# 数据目录
DATA_DIR: Final[Path] = PROJECT_ROOT / "data"
UPLOAD_DIR: Final[Path] = DATA_DIR / "uploads"
CHROMA_DIR: Final[Path] = DATA_DIR / "chroma"
LOG_DIR: Final[Path] = DATA_DIR / "logs"

# 配置文件
ENV_FILE: Final[Path] = PROJECT_ROOT / ".env"
ENV_EXAMPLE_FILE: Final[Path] = PROJECT_ROOT / ".env.example"

# 数据库文件
DATABASE_FILE: Final[Path] = DATA_DIR / "knowledgeflow.db"
