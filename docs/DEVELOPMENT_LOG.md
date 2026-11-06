# KnowledgeFlow Development Log

本文档记录 KnowledgeFlow 的开发过程、阶段验收结果、测试数据和遗留事项。

开发记录以实际代码、命令输出和测试结果为准。未实现的功能不标记为已完成，未执行的测试不记录为通过。

---

## 2026-11-03：Phase 0 工程基础建设

### 1. 开发环境

| 项目 | 当前配置 |
|---|---|
| 操作系统 | Ubuntu 24.04 |
| Python | 3.12.16 |
| Conda 环境 | klf |
| Node.js | 24.16.0 |
| npm | 12.2.1 |
| Git | 2.43.0 |
| GPU | NVIDIA RTX 4060 Laptop 8GB |
| Ollama | 0.40.11 |

项目使用已有 Conda 环境 `klf`，不使用独立的 `backend/.venv`。

### 2. 已完成任务

#### Task 0.1：环境检查

- 确认 Ubuntu、Python、Node.js、Git 等开发工具。
- 确认 NVIDIA GPU 和 Ollama 环境。
- 确认 Python 3.12 可用于项目开发。

结果：通过。

#### Task 0.2：项目目录初始化

建立后端、前端、数据和文档目录。

结果：通过。

#### Task 0.3：Python 开发环境确认

- 使用 Conda 环境 `klf`。
- 确认项目使用的 Python 解释器。
- 保留原有 Conda 环境，不随意调整其他项目依赖。

结果：通过。

#### Task 0.4：Python 依赖管理

建立 `pyproject.toml`，配置：

- FastAPI
- Uvicorn
- Pydantic Settings
- pytest
- pytest-cov
- httpx2
- Ruff

通过 editable install 安装项目：

```bash
python -m pip install -e ".[dev]"
```

结果：通过。

#### Task 0.5：统一日志系统初始实现

新增：

```text
backend/app/core/logging.py
backend/app/core/__init__.py
backend/tests/test_logging.py
```

实现：

- 统一 Logger 命名空间。
- 中文控制台日志。
- UTF-8 文件日志。
- 日志级别配置。
- 日志文件自动轮转。
- 重复初始化时清理旧处理器。
- 非法参数校验。

初始测试结果：5 项通过。

#### Task 0.6：FastAPI 健康检查

新增：

```text
backend/app/main.py
backend/tests/test_health.py
```

实现：

- FastAPI 应用入口。
- 应用生命周期管理。
- 统一响应数据模型。
- `/api/v1/health` 健康检查接口。
- Swagger API 文档。

通过真实 HTTP 请求验证：

```bash
curl -i http://127.0.0.1:8000/api/v1/health
```

实际返回 HTTP 200 和正确的健康检查 JSON。

结果：通过。

#### Task 0.7：pytest 测试规范

完成：

- pytest 测试目录配置。
- 测试文件命名规范。
- 测试标记配置。
- pytest-cov 覆盖率统计。
- 最低覆盖率 90%。
- Ruff 代码检查和格式检查。
- `.gitignore` 测试产物忽略规则。

Phase 0 初始测试基线：

| 指标 | 结果 |
|---|---:|
| 测试用例 | 8 |
| 通过 | 8 |
| 失败 | 0 |
| 总覆盖率 | 93.42% |
| 最低覆盖率要求 | 90% |
| Ruff 检查 | 通过 |

结果：通过。

#### Task 0.8：项目文档初始整理

建立 README 和开发日志，记录项目目标、技术栈、运行方式和开发路线。

结果：初始文档建立，后续随 Phase 1 完成情况更新。

### 3. Phase 0 验收结果

Phase 0 完成了项目目录、Python 工程配置、FastAPI 应用入口、健康检查接口、基础日志系统和自动化测试体系。

结果：Phase 0 完成。

---

## 2026-11-03：Phase 1 配置管理与基础设施

### 1. 阶段目标

建立统一配置管理和基础设施，为后续数据库、文档处理、检索和 Agent 模块提供稳定的工程基础。

### 2. 已完成任务

#### Task 1.1：基础架构设计

确定项目基础技术路线：

- Python 3.12
- FastAPI
- Pydantic Settings
- pytest
- Ruff
- 本地优先的数据与模型部署方案

结果：完成。

#### Task 1.2：Settings 核心类

新增：

```text
backend/app/core/config.py
backend/tests/test_config.py
```

实现：

- 基于 Pydantic Settings 的统一配置类。
- 应用基础配置。
- API 服务配置。
- 日志配置。
- 全局配置实例缓存。
- 支持通过 `get_settings.cache_clear()` 清理缓存。

结果：完成。

#### Task 1.3：环境变量与 `.env` 文件

新增：

```text
.env.example
```

实现：

- 从环境变量读取配置。
- 从项目 `.env` 文件读取配置。
- 环境变量优先于 `.env` 文件。
- 忽略未声明的额外配置项。
- `.env` 纳入 Git 忽略规则。

测试验证了环境变量与 `.env` 文件的优先级。

结果：完成。

#### Task 1.4：统一项目路径管理

新增：

```text
backend/app/core/paths.py
backend/tests/test_paths.py
```

统一管理：

- `PROJECT_ROOT`
- `BACKEND_DIR`
- `APP_DIR`
- `DATA_DIR`
- `UPLOAD_DIR`
- `CHROMA_DIR`
- `LOG_DIR`
- `ENV_FILE`
- `ENV_EXAMPLE_FILE`

避免不同模块重复计算项目目录。

结果：完成。

#### Task 1.5：配置校验与异常处理

完善 `Settings` 字段校验：

- 应用名称、版本和 Host 非空校验。
- Port 范围校验。
- API 路由前缀格式校验。
- 日志级别大小写规范化。
- 日志文件名校验。
- 日志文件路径穿越防护。
- 日志文件大小必须大于 0。
- 日志备份数量不能小于 0。

使用参数化测试覆盖非法配置和边界情况。

结果：完成。

#### Task 1.6：环境配置绝对路径与测试扩展

修改 `config.py`：

- 使用 `paths.py` 提供的 `ENV_FILE`。
- 不再依赖当前工作目录中的相对路径 `.env`。
- 增加绝对路径配置测试。
- 增加切换工作目录后的配置读取测试。

测试结果：

| 测试项目 | 结果 |
|---|---:|
| 配置模块测试 | 27 passed |
| 全量测试 | 40 passed |
| 总覆盖率 | 94.89% |
| Ruff 检查 | 修复导入排序后通过 |

额外进行跨目录验证：

从 `/tmp` 目录启动 Python，成功读取项目根目录下的 `.env` 文件。

验证结果：

```text
当前工作目录: /tmp
环境变量文件: /home/liu/桌面/Project/KnowledgeFlow/.env
应用名称: KnowledgeFlow
服务端口: 8000
```

结果：通过。

#### Task 1.7：日志系统接入统一配置

修改：

```text
backend/app/core/logging.py
backend/app/main.py
backend/tests/test_logging.py
```

主要调整：

1. 日志目录改为复用 `paths.py` 中的 `LOG_DIR`。
2. 删除日志模块内部重复计算项目根目录的逻辑。
3. 日志默认级别从 `Settings` 读取。
4. 日志文件名从 `Settings` 读取。
5. 日志文件最大容量从 `Settings` 读取。
6. 日志备份数量从 `Settings` 读取。
7. 显式传入参数时，优先使用调用者提供的参数。
8. FastAPI 应用启动时调用 `setup_logging()`，不再硬编码日志级别。

保留原有能力：

- 控制台与文件双输出。
- Logger 命名空间。
- 日志级别过滤。
- UTF-8 文件编码。
- RotatingFileHandler 自动轮转。
- 重复初始化时清理旧处理器。
- 非法参数校验。

新增测试：

- 默认日志配置读取统一 Settings。
- 显式参数覆盖统一 Settings。

日志模块测试结果：

| 测试项目 | 结果 |
|---|---:|
| 日志模块测试 | 7 passed |
| 失败 | 0 |

Phase 1 最终全量测试结果：

| 指标 | 结果 |
|---|---:|
| 测试用例 | 42 |
| 通过 | 42 |
| 失败 | 0 |
| 总覆盖率 | 95.04% |
| 最低覆盖率要求 | 90% |
| Ruff 检查 | 通过 |

结果：Task 1.7 完成。

### 3. Phase 1 最终文件结构

```text
KnowledgeFlow/
├── backend/
│   ├── app/
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── config.py
│   │   │   ├── logging.py
│   │   │   └── paths.py
│   │   ├── __init__.py
│   │   └── main.py
│   └── tests/
│       ├── test_config.py
│       ├── test_health.py
│       ├── test_logging.py
│       └── test_paths.py
├── data/
│   ├── chroma/
│   ├── logs/
│   └── uploads/
├── docs/
│   └── DEVELOPMENT_LOG.md
├── frontend/
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md
```

### 4. Phase 1 验收总结

Phase 1 已建立以下基础能力：

- 统一配置管理。
- 环境变量和 `.env` 文件读取。
- 配置优先级与字段校验。
- 项目路径统一管理。
- 基于绝对路径的环境配置加载。
- 统一日志系统。
- 日志系统与 Settings 配置集成。
- pytest 自动化测试。
- Ruff 代码检查与格式化。

最终测试基线为 42 项通过，总覆盖率 95.04%，达到项目最低覆盖率 90% 的要求。

结果：Phase 1 完成。

---

## 5. 当前遗留事项

- [ ] 补充 MIT LICENSE 文件。
- [ ] 检查 Git 提交内容，确保 `.env`、日志、数据库和上传文件不进入版本控制。
- [x] 完成 DocumentChunk ORM 模型设计与实现。
- [ ] 完成 Alembic 数据库迁移管理。
- [ ] 完成数据库 CRUD 基础操作。
- [ ] 后续逐步接入 Chroma 和 BM25。

---

## 6. Phase 2：数据层与数据库基础设施

### 阶段目标

建立 KnowledgeFlow 的业务数据持久化基础，为文档导入、解析、分块、检索和 RAG 提供可靠的数据管理能力。

技术方案：

| 项目 | 技术选型 |
|---|---|
| 关系型数据库 | SQLite |
| ORM | SQLAlchemy 2.x |
| 异步驱动 | aiosqlite |
| 数据库迁移 | Alembic |
| 数据库会话 | AsyncSession |
| 数据库文件 | `data/knowledgeflow.db` |

数据库负责存储知识库、文档及文档分块等业务元数据和文本内容。后续向量数据由 Chroma 独立管理。

### 6.1 已完成任务

#### Task 2.1：数据层架构设计与依赖选择

- [x] 确定 SQLite 作为本地关系型数据库。
- [x] 确定 SQLAlchemy 2.x 异步访问方案。
- [x] 确定 aiosqlite 异步数据库驱动。
- [x] 确定 Alembic 数据库迁移方案。
- [x] 明确关系型数据库与向量数据库的职责边界。

结果：Task 2.1 完成。

#### Task 2.2：数据库连接与会话管理

- [x] 安装 SQLAlchemy、aiosqlite 和 Alembic。
- [x] 配置 SQLAlchemy asyncio 依赖。
- [x] 统一管理 SQLite 数据库文件路径。
- [x] 实现异步数据库引擎创建。
- [x] 配置 SQLite 外键约束。
- [x] 实现 AsyncSession 会话工厂。
- [x] 实现 FastAPI 数据库会话依赖。
- [x] 接入 FastAPI lifespan，实现数据库引擎初始化与关闭。
- [x] 完成数据库连接、会话和生命周期测试。

结果：Task 2.2 完成。阶段验收时 51 项测试通过。

#### Task 2.3：ORM 基础与业务模型

##### Task 2.3.1：ORM 基类

- [x] 创建统一 DeclarativeBase。
- [x] 配置统一数据库约束和索引命名规则。
- [x] 完成 ORM 基类测试。

结果：Task 2.3.1 完成。

##### Task 2.3.2：KnowledgeBase 模型

- [x] 创建 `knowledge_bases` 数据表模型。
- [x] 定义知识库名称和描述字段。
- [x] 定义创建时间与更新时间。
- [x] 添加名称长度和非空约束。
- [x] 建立与 Document 模型的双向 ORM 关系。
- [x] 完成模型及 SQLite 集成测试。

结果：Task 2.3.2 完成。

##### Task 2.3.3：Document 模型

- [x] 创建 `documents` 数据表模型。
- [x] 定义知识库外键。
- [x] 定义文档名称、文件类型、文件路径和文件大小。
- [x] 定义文档内容哈希。
- [x] 定义文档处理状态及错误信息。
- [x] 定义创建时间与更新时间。
- [x] 添加字段长度、文件大小和状态检查约束。
- [x] 添加 `(knowledge_base_id, content_hash)` 联合唯一约束。
- [x] 配置与 KnowledgeBase 的双向 ORM 关系。
- [x] 配置外键级联删除。
- [x] 完成 Document 模型及 SQLite 集成测试。

说明：数据库级联删除只负责删除关联的文档元数据记录，不会自动删除磁盘上的原始文件，后续由业务 Service 层负责文件生命周期管理。

专项测试结果：37 项通过。

结果：Task 2.3.3 代码与测试验收通过，文档同步完成后正式关闭任务。

##### Task 2.3.4：DocumentChunk 模型与测试

**Task 2.3.4.1：DocumentChunk ORM 模型**

- [x] 创建 `document_chunks` 数据表模型。
- [x] 定义所属文档外键 `document_id`。
- [x] 定义文档内分块序号 `chunk_index`。
- [x] 定义分块文本 `content`。
- [x] 定义 Token 数量 `token_count`。
- [x] 定义原始文本起始位置 `start_index`。
- [x] 定义原始文本结束位置 `end_index`。
- [x] 定义 JSON 类型分块元数据 `chunk_metadata`。
- [x] 定义分块创建时间 `created_at`。
- [x] 配置分块序号、文本内容、Token 数量和字符位置检查约束。
- [x] 添加 `(document_id, chunk_index)` 联合唯一约束。
- [x] 配置与 Document 的双向 ORM 关系。
- [x] 配置文档删除时的分块级联删除。
- [x] 将 DocumentChunk 注册到统一模型导出模块。

结果：Task 2.3.4.1 完成。

**Task 2.3.4.2：DocumentChunk 单元测试与 SQLite 集成测试**

- [x] 验证 ORM 表名、字段和主键。
- [x] 验证外键和级联删除配置。
- [x] 验证唯一约束和 CHECK 约束。
- [x] 验证 JSON 元数据映射和默认值。
- [x] 验证 JSON 元数据数据库读写。
- [x] 验证默认字典对象相互独立。
- [x] 使用 `MutableDict.as_mutable(JSON)` 实现 JSON 字典顶层原地修改追踪。
- [x] 验证 Document 与 DocumentChunk 双向关系。
- [x] 验证重复分块序号被拒绝。
- [x] 验证无效分块数据被数据库拒绝。
- [x] 验证不存在的文档外键被拒绝。
- [x] 验证删除 Document 时级联删除 DocumentChunk。
- [x] 验证删除 KnowledgeBase 时级联删除 Document 和 DocumentChunk。

专项测试结果：

| 测试类型 | 通过数量 |
|---|---:|
| DocumentChunk 单元测试 | 11 |
| DocumentChunk SQLite 集成测试 | 14 |
| 合计 | 25 |

结果：Task 2.3.4 完成。

### 6.2 当前全量测试基线

2026-11-03，完成 Document 模型后的全项目回归测试：

| 指标 | 结果 |
|---|---:|
| 测试用例 | 94 |
| 通过 | 94 |
| 失败 | 0 |
| 总覆盖率 | 95.71% |
| 最低覆盖率要求 | 90% |
| Ruff 静态检查 | 通过 |
| Ruff 格式检查 | 通过 |

测试命令：

```bash
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

结果：94 项测试全部通过，总覆盖率 95.71%，Ruff 静态检查与格式检查全部通过。

### 6.3 DocumentChunk 完成后的全量回归

2026-11-03，完成 DocumentChunk ORM 模型及集成测试后，执行全项目回归：

| 指标 | 结果 |
|---|---:|
| 测试用例 | 119 |
| 通过 | 119 |
| 失败 | 0 |
| 总覆盖率 | 96.08% |
| 最低覆盖率要求 | 90% |
| Ruff 静态检查 | 通过 |
| Ruff 格式检查 | 通过 |

专项测试：

- DocumentChunk 单元测试：11 passed。
- DocumentChunk SQLite 集成测试：14 passed。

JSON 元数据测试发现普通 SQLAlchemy JSON 字典默认不追踪原地修改。通过 `MutableDict.as_mutable(JSON)` 修复顶层字典变更追踪，并通过 SQLite 集成测试验证修改持久化。

结果：全量回归通过，达到项目测试覆盖率要求。

### 6.4 当前数据库模块结构

```text
backend/
├── app/
│   ├── db/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── engine.py
│   │   └── session.py
│   └── models/
│       ├── __init__.py
│       ├── knowledge_base.py
│       ├── document.py
│       └── document_chunk.py
└── tests/
    ├── test_database_base.py
    ├── test_database_engine.py
    ├── test_database_lifecycle.py
    ├── test_database_session.py
    ├── test_knowledge_base.py
    ├── test_knowledge_base_integration.py
    ├── test_document.py
    ├── test_document_integration.py
    ├── test_document_chunk.py
    └── test_document_chunk_integration.py
```

### 6.5 Alembic 数据库迁移管理

2026-11-03，完成 Task 2.4 Alembic 数据库迁移管理。

#### 6.5.1 Alembic 初始化与配置

- 使用 Alembic 管理 SQLite 数据库版本和结构变更。
- 初始化 `alembic/` 迁移目录。
- 配置 `alembic.ini`。
- 迁移环境动态读取项目统一数据库路径 `DATABASE_FILE`。
- 使用异步 SQLAlchemy Engine 执行在线迁移。
- 使用 `AsyncConnection.run_sync()` 运行 Alembic 同步迁移操作。
- 支持 Offline SQL 生成。
- SQLite 迁移启用 `render_as_batch=True`。

#### 6.5.2 初始迁移

迁移版本：

`7ee22ff5dcf6`

迁移说明：

`create initial database schema`

初始迁移创建以下三张业务表：

| 数据表 | 主要内容 |
|---|---|
| knowledge_bases | 知识库基本信息 |
| documents | 文档元数据 |
| document_chunks | 文档分块内容和元数据 |

迁移包含：

- 主键和字段非空约束。
- CHECK 数据完整性约束。
- 复合唯一约束。
- 外键约束及 ON DELETE CASCADE。
- document_chunks.document_id 索引。
- JSON metadata 默认值。
- created_at、updated_at 时间字段默认值。

#### 6.5.3 迁移验证

真实执行：

```bash
python -m alembic upgrade head
```

验证结果：

- Alembic 当前版本：`7ee22ff5dcf6 (head)`。
- 三张业务表全部创建成功。
- Documents 到 KnowledgeBases 的外键级联删除正常。
- DocumentChunks 到 Documents 的外键级联删除正常。
- 复合唯一约束存在。
- `ix_document_chunks_document_id` 索引存在。
- `PRAGMA foreign_key_check` 返回空列表。
- `PRAGMA integrity_check` 返回 `ok`。

#### 6.5.4 Task 2.4 验收结果

| 子任务 | 内容 | 状态 |
|---|---|---|
| Task 2.4.1 | Alembic 初始化 | 已完成 |
| Task 2.4.2 | alembic.ini 配置 | 已完成 |
| Task 2.4.3 | 异步迁移环境 | 已完成 |
| Task 2.4.4 | 初始迁移生成与审查 | 已完成 |
| Task 2.4.5 | 迁移执行与验证 | 已完成 |

### 6.6 Phase 2 当前全量回归结果

2026-11-03，完成 Alembic 初始迁移及数据库结构验证后，执行全项目回归：

| 指标 | 结果 |
|---|---:|
| 测试用例 | 119 |
| 通过 | 119 |
| 失败 | 0 |
| 总覆盖率 | 96.08% |
| 最低覆盖率要求 | 90% |
| Ruff 静态检查 | 通过 |
| Ruff 格式检查 | 通过 |
| Alembic 当前版本 | 7ee22ff5dcf6 (head) |

测试命令：

```bash
python -m pytest --cov=app --cov-report=term-missing --cov-fail-under=90
python -m ruff check .
python -m ruff format --check .
python -m alembic current
```

结果：119 项测试全部通过，总覆盖率 96.08%，Ruff 检查和格式检查通过，Alembic 迁移状态正确。

### 6.7 Phase 2 任务完成状态

| 任务 | 内容 | 状态 |
|---|---|---|
| Task 2.3.1 | ORM 基类 | 已完成 |
| Task 2.3.2 | KnowledgeBase 模型 | 已完成 |
| Task 2.3.3 | Document 模型 | 已完成 |
| Task 2.3.4 | DocumentChunk 模型与测试 | 已完成 |
| Task 2.4 | Alembic 数据库迁移管理 | 已完成 |
| Task 2.5 | Repository 数据访问层 | 已完成 |
| Task 2.6.1 | KnowledgeBaseService | 已完成 |
| Task 2.6.2 | DocumentService | 已完成 |
| Task 2.7 | Repository 与 Service 集成测试 | 已完成 |
| Task 2.8 | Phase 2 全量测试与阶段验收 | 已完成 |

### 6.8 Repository 与 Service 层完成记录

2026-11-03，完成 Repository、Service 及相关集成测试。

#### Repository 层

- [x] BaseRepository 通用 CRUD。
- [x] KnowledgeBaseRepository 知识库查询。
- [x] DocumentRepository 文档查询。
- [x] DocumentChunkRepository 分块查询。
- [x] Repository 不主动提交事务，由 Service 管理事务。

#### Service 层

**KnowledgeBaseService**

- [x] 知识库创建、查询、名称搜索。
- [x] 知识库更新和删除。
- [x] 输入校验和事务异常回滚。
- [x] 删除知识库时级联删除文档及分块元数据。

**DocumentService**

- [x] 文档创建和字段校验。
- [x] 知识库存在性检查。
- [x] 同一知识库内 SHA-256 内容哈希去重。
- [x] 文档 ID、内容哈希、所属知识库和状态查询。
- [x] 文档分块预加载。
- [x] 文档元数据更新。
- [x] 文档处理状态更新和错误信息管理。
- [x] 文档删除及分块元数据级联删除。
- [x] 写操作事务提交和异常回滚。

说明：Service 删除操作只负责数据库元数据及关联分块记录，不负责删除磁盘上的原始文件。

#### Repository 与 Service 集成测试

使用真实 SQLite 测试数据库、SQLAlchemy AsyncSession 和 Repository 实现业务链路测试，不使用 Mock 替代数据库访问。

主要测试文件：

- `test_base_repository.py`
- `test_knowledge_base_repository.py`
- `test_document_repository.py`
- `test_document_chunk_repository.py`
- `test_knowledge_base_service.py`
- `test_document_service.py`

#### DocumentService 专项验收

| 指标 | 结果 |
|---|---:|
| 专项测试 | 45 passed |
| Ruff 静态检查 | 通过 |
| Ruff 格式检查 | 通过 |

#### Phase 2 当前全量回归

2026-11-03，完成 DocumentService 后执行全项目回归：

| 指标 | 结果 |
|---|---:|
| 测试用例 | 259 |
| 通过 | 259 |
| 失败 | 0 |
| 总覆盖率 | 93.85% |
| 最低覆盖率要求 | 90% |
| Ruff 静态检查 | 通过 |
| Ruff 格式检查 | 通过 |

结果：Repository、Service 及现有集成测试全部通过。Task 2.8 最终数据库完整性与迁移状态验收仍待执行。




### 6.9 Phase 2 最终验收记录

2026-11-03，Phase 2 全部开发任务完成，执行全量自动化测试、静态检查、Alembic 迁移状态检查及 SQLite 数据库完整性检查。

#### 自动化测试

| 指标 | 最终结果 |
|---|---:|
| 测试总数 | 259 |
| 通过 | 259 |
| 失败 | 0 |
| 总覆盖率 | 93.85% |
| 最低覆盖率要求 | 90% |

执行结果：

- [x] 全量 pytest 测试通过。
- [x] 覆盖率达到项目要求。

#### 代码质量检查

- [x] Ruff 静态检查：All checks passed。
- [x] Ruff 格式检查：47 files already formatted。

#### Alembic 迁移检查

- [x] 当前迁移版本：`7ee22ff5dcf6 (head)`。
- [x] 初始迁移历史存在：`create initial database schema`。
- [x] 数据库迁移版本与 Alembic head 一致。

#### SQLite 数据库完整性检查

正式数据库：`data/knowledgeflow.db`

- [x] 数据库文件存在。
- [x] `PRAGMA integrity_check` 返回 `ok`。
- [x] `PRAGMA foreign_key_check` 返回空结果 `[]`。
- [x] `alembic_version` 表存在。
- [x] `knowledge_bases` 表存在。
- [x] `documents` 表存在。
- [x] `document_chunks` 表存在。
- [x] Document 到 KnowledgeBase 的外键配置 `ON DELETE CASCADE`。
- [x] DocumentChunk 到 Document 的外键配置 `ON DELETE CASCADE`。

#### 最终验收结论

Phase 2 的数据库连接管理、ORM 模型、Alembic 迁移、Repository、Service 和集成测试全部完成。

全量测试、代码质量检查、迁移状态检查和 SQLite 数据库完整性检查均通过。

**Phase 2：数据层与数据库基础设施，正式验收通过。**


---

> 开发原则：坚持渐进式开发。每次只实现一个明确任务，先检查现状，再修改代码，完成自动化测试和验收后进入下一任务。所有进度和测试数据以实际结果为准。
---

## 2026-11-04：Phase 3 文档导入与 PDF 资源限制配置

### 1. 本轮目标

完善 PDF 解析器的资源限制，并将统一 Settings 配置注入 ParserRegistry，确保默认文档导入流程使用统一配置。

本轮完成的是 Phase 3 的一项专项任务，不代表整个 Phase 3 已经结束。

### 2. PDF 资源限制配置

在 `backend/app/core/config.py` 中增加 PDF 资源限制配置：

| 配置项 | 默认值 | 说明 |
|---|---:|---|
| `pdf_max_pages` | 500 | PDF 最大页面数量 |
| `pdf_max_page_chars` | 200000 | 单页最大提取字符数 |
| `pdf_max_total_chars` | 2000000 | 全文最大提取字符数 |

对应环境变量：

- `KLF_PDF_MAX_PAGES=500`
- `KLF_PDF_MAX_PAGE_CHARS=200000`
- `KLF_PDF_MAX_TOTAL_CHARS=2000000`

配置校验：

- 所有资源限制必须大于 0。
- 单页字符数上限不能大于全文字符数上限。
- 配置通过 Pydantic Settings 统一加载。

配置测试：39 passed。

### 3. PDFParser 资源限制实现

修改：

- `backend/app/ingestion/parsers/pdf.py`
- `backend/tests/test_ingestion_pdf_parser.py`

主要实现：

- 在提取页面文本前检查 PDF 页面数量。
- 提取每页文本后检查单页字符数。
- 累计检查全文字符数，并计算页面之间的换行分隔符。
- 超出限制时抛出 `DocumentParseError`。
- 使用 `asyncio.to_thread()` 执行同步 PDF 解析，避免直接阻塞事件循环。
- 保留单页提取失败警告，不因单页异常直接中断整个文档解析。
- 区分全部页面提取失败和扫描版 PDF 的提示。

专项测试结果：

| 指标 | 结果 |
|---|---:|
| PDF Parser 测试 | 21 passed |
| Ruff 静态检查 | 通过 |
| Ruff 格式检查 | 通过 |

### 4. ParserRegistry 配置注入

修改：

`backend/app/ingestion/parsers/registry.py`

实现：

- `ParserRegistry` 支持可选传入 `Settings`。
- 未传入配置时，通过 `get_settings()` 获取默认配置。
- 初始化 PDFParser 时显式传入解析器配置。
- 保留 `ParserRegistry()` 无参构造方式，兼容现有调用代码。
- 对非法配置对象进行类型校验。

新增测试：

- 验证传入的 Settings 对象被正确传递给 PDFParser。
- 验证非法 Settings 对象会触发 TypeError。

注册表与 PDF Parser 联合专项测试：

| 指标 | 结果 |
|---|---:|
| 测试数量 | 46 passed |
| Ruff 静态检查 | 通过 |
| Ruff 格式检查 | 通过 |

### 5. Phase 3 全量回归

2026-11-04，完成 PDF 资源限制和 ParserRegistry 配置注入后，执行后端全量回归。

实际结果：

| 指标 | 结果 |
|---|---:|
| 测试总数 | 592 |
| 通过 | 592 |
| 失败 | 0 |
| 总覆盖率 | 95.07% |
| 最低覆盖率要求 | 90% |
| Ruff 静态检查 | 通过 |
| Ruff 格式检查 | 通过 |
| 格式检查文件数 | 71 |

主要模块覆盖率：

| 模块 | 覆盖率 |
|---|---:|
| PDFParser | 98% |
| Settings | 97% |
| DocumentIngestionService | 96% |
| 文档校验器 | 94% |
| 文件存储 | 92% |

结果：本轮后端全量回归通过。

### 6. PDF 解析安全边界与遗留事项

当前已实现页面数量、单页字符数和全文字符数限制，但这些限制不等同于完整的解析资源隔离。

需要明确以下边界：

1. 单页字符数限制在 `extract_text()` 返回文本后检查，无法完全限制提取过程中产生的临时字符串和内存消耗。
2. 全文字符数限制能够控制最终累计文本规模，但不能完全约束 PDF 解析器内部的临时内存占用。
3. `asyncio.to_thread()` 可以将同步解析任务移出事件循环，但取消等待协程不能强制终止已经运行的线程。
4. 当前实现不具备操作系统级 CPU、内存或执行时间隔离能力。

后续可评估：

- 使用独立进程执行 PDF 解析。
- 设置进程级内存限制和执行时间限制。
- 对解析任务增加并发数量控制。
- 在隔离进程退出后回收资源。

以上属于后续增强事项，本轮不标记为已实现。

### 7. 本轮验收结论

本轮完成：

- PDF 三项资源限制配置。
- Settings 配置校验。
- PDFParser 页面数量和文本长度限制。
- ParserRegistry 到 PDFParser 的配置注入。
- 相关单元测试和专项测试。
- 后端全量回归。

**本轮专项任务验收通过。**

Phase 3 整体仍处于进行中，后续任务以实际代码实现、测试和阶段验收结果为准。

---

## 2026-11-05：Phase 3 最终验收及 Phase 4～8 完成记录

### 1. Phase 3 最终验收

在此前 PDF 解析资源限制、ParserRegistry 配置注入等工作基础上，继续完成文档导入 API、上传请求大小限制和真实文件导入验证。

完成内容：

- 文档上传 API。
- 上传文件类型和大小校验。
- 文件分块读取、SHA256 计算及临时文件原子替换。
- 上传失败时清理临时文件。
- 上传请求体大小限制中间件。
- 文档解析、分块、持久化和索引流程集成。
- 修复 FastAPI 与 Starlette UploadFile 类型兼容问题。

Phase 3 的核心文档导入链路已完成，相关测试及全量回归通过。

### 2. Phase 4：Embedding 与向量存储

完成 Ollama Embedding 服务和 Chroma 向量存储。

主要实现：

- 使用 Ollama `/api/embed` 接口生成文档向量。
- 使用共享异步 HTTP 客户端，EmbeddingService 不自行管理客户端生命周期。
- 校验 Embedding 响应结构、向量数量、维度及数值有效性。
- 使用 Chroma PersistentClient 持久化向量。
- 向量集合按知识库隔离。
- 实现向量写入、查询和删除。
- 实现 VectorIndexService，支持批量生成 Embedding 和写入向量。
- 保留 SQLite 中的文档及分块元数据，Chroma 独立保存向量。

真实 Ollama Embedding 请求已验证，返回向量维度为 768。

### 3. Phase 5：BM25 与混合检索

完成 BM25 全文检索、RRF 融合和混合检索服务。

主要实现：

- 基于现有 WordPiece Tokenizer 实现 BM25 检索。
- 实现 Reciprocal Rank Fusion（RRF）。
- 结合向量检索和 BM25 检索结果。
- 按 RRF 分数融合排序。
- 通过 SQLite 恢复分块及文档元数据。
- 实现 VectorSearchService、BM25SearchService 和 HybridSearchService。
- 提供知识库混合检索 API。

检索结果保留文档、分块及相关性信息，为后续 RAG 提供来源数据。

### 4. Phase 6：RAG 问答

完成上下文构建、RAG 服务和 RAG API。

主要实现：

- ContextBuilder 根据 TokenCounter 控制上下文长度。
- 按检索排名依次构建上下文。
- 超出上下文预算时停止追加，不截断分块内容。
- 保留来源编号、文档名称、分块编号及 RRF 分数。
- RAGService 复用 HybridSearchService 和 OllamaChatService。
- 无有效检索来源时不调用 LLM。
- 系统提示词要求基于知识库内容回答，并提供来源引用。
- 对检索内容进行不可信数据处理，避免执行文档中的指令。
- 提供知识库 RAG API。

真实 RAG 请求已验证，能够返回基于知识库内容的回答及来源信息。

### 5. Phase 7：Agent 工具调用

完成 Agent 工具注册、参数校验、执行循环和 Agent API。

主要实现：

- ToolDefinition 和 ToolRegistry。
- 工具名称、参数模型和异步处理函数校验。
- 工具参数通过 Pydantic 模型验证。
- 将工具定义转换为 Ollama Function Calling 格式。
- 实现知识库 RAG 工具 knowledge_rag。
- 实现 AgentExecutor，支持多轮工具调用及最大迭代次数限制。
- 工具异常转换为可供 Agent 处理的结果。
- 提供知识库 Agent API。

兼容本地 Ollama 模型对工具调用的不同输出形式，在安全校验通过后解析兼容格式。

真实本地 Ollama Agent 调用已验证，模型能够调用知识库 RAG 工具并生成最终回答。

### 6. Phase 8：MCP Server

完成独立 MCP Server，实现知识库检索和 RAG 工具暴露。

主要实现：

- 基于 MCP Python SDK 和 FastMCP。
- 使用 stdio 作为 MCP 通信传输方式。
- 实现独立 MCP Runtime。
- MCP 进程独立管理数据库、HTTP 客户端、Embedding、Chat 和 Chroma 依赖。
- 实现 knowledge_search 工具，复用现有混合检索服务。
- 实现 knowledge_rag 工具，复用现有 RAGService。
- 每次工具调用独立创建数据库 Session。
- MCP 资源关闭时释放 HTTP 客户端和数据库引擎。
- MCP 协议输出使用 stdout，日志使用 stderr。
- SQLite 和 Chroma 路径基于项目根目录解析，不依赖启动时的工作目录。

真实 MCP Client 子进程测试已完成：

- MCP 握手成功。
- 服务名称为 KnowledgeFlow。
- 成功发现 knowledge_search 和 knowledge_rag 工具。
- knowledge_search 真实调用成功。
- knowledge_rag 真实调用成功。
- 检索结果和 RAG 来源信息均正常返回。

MCP 与 Agent 相关专项测试：74 passed。

### 7. 真实业务链路验证

使用现有知识库执行真实业务验证，确认以下流程能够贯通：

1. 上传 TXT 文档。
2. 文件校验、解析和文本分块。
3. 文档及分块信息写入 SQLite。
4. 调用 Ollama 生成 Embedding。
5. 向量写入 Chroma。
6. 执行 BM25 和向量混合检索。
7. RRF 融合检索结果。
8. RAG 根据检索上下文生成回答及来源引用。
9. Agent 调用 knowledge_rag 工具并生成最终回答。
10. MCP Client 通过 knowledge_search 和 knowledge_rag 访问知识库。

真实验证表明，知识库文档导入、检索、RAG、Agent 和 MCP 核心链路已经贯通。

### 8. 2026-11-05 后端最终回归

本轮全量后端测试结果：

| 指标 | 结果 |
|---|---:|
| 测试通过 | 1059 |
| 测试跳过 | 1 |
| 测试失败 | 0 |
| Ruff 静态检查 | 通过 |
| Ruff 格式检查 | 通过 |
| 格式检查文件数 | 131 |

唯一跳过的测试为：

`backend/tests/test_vector_search_integration.py`

该测试需要显式设置 `KLF_RUN_LIVE_INTEGRATION=1` 才会执行。

本轮没有重新计算全量覆盖率，因此不将历史覆盖率作为本轮覆盖率结果。

### 9. 阶段验收结论与后续计划

截至 2026-11-05：

- Phase 0：项目基础与开发环境，已完成。
- Phase 1：基础架构与配置，已完成。
- Phase 2：数据库、ORM、Repository 和 Service，已完成。
- Phase 3：文档导入与处理，已完成。
- Phase 4：Embedding 与向量存储，已完成。
- Phase 5：BM25 与混合检索，已完成。
- Phase 6：RAG 问答，已完成。
- Phase 7：Agent 工具调用，已完成。
- Phase 8：MCP Server，已完成。
- Phase 9：Vue 3 前端，待开始。
- Phase 10：系统评估与性能优化，待开始。
- Phase 11：Docker 部署与交付，待开始。

**当前阶段结论：Phase 0～8 已完成，后端核心业务链路已通过真实调用验证及自动化回归。下一阶段进入 Phase 9，开始 Vue 3 前端开发。**


---

## 2026-11-05：Phase 9 Vue 3 前端完成

### 1. 前端工程与基础设施

完成 Vue 3 前端工程搭建：

- Vue 3 + TypeScript + Vite。
- Axios 统一 HTTP 客户端及错误处理。
- Pinia 知识库状态管理。
- Vue Router 页面路由。
- Vite `/api` 代理转发至本地 FastAPI 服务。
- 定义知识库、文档上传、混合检索、RAG 和 Agent API 类型及请求模块。

### 2. 知识库管理

完成首页 Dashboard：

- 知识库列表和分页。
- 创建知识库。
- 创建成功后跳转详情页。
- 加载、错误和空状态处理。

完成知识库详情页：

- 知识库基本信息和状态展示。
- 路由参数校验及知识库详情加载。
- 知识库工作台导航。

### 3. 核心业务组件

完成以下四个业务组件：

- `DocumentUploadPanel`：文件选择、拖放上传、文件格式和大小校验、上传进度、重复文件及异常反馈。
- `DocumentSearchPanel`：调用混合检索 API，展示文档分块内容、BM25 分数、向量距离和 RRF 分数。
- `RAGChatPanel`：调用 RAG API，展示回答、检索数量、上下文 Token 数量和来源引用。
- `AgentChatPanel`：调用 Agent API，展示回答、工具调用次数和执行迭代次数。

### 4. 工作台布局与 Logo

将知识库详情页调整为工作台布局：

- 概览、文档管理、混合检索、RAG 问答、Agent 助手五个导航区域。
- 使用 `v-show` 保留业务组件实例及其状态。
- 桌面端侧边导航、小屏横向导航和移动端响应式布局。
- 首页和详情页统一使用 KnowledgeFlow Logo。
- favicon 切换为 PNG 格式资源。

### 5. 前后端真实业务验证

已通过浏览器及真实 API 验证：

1. 知识库列表、创建和详情访问正常。
2. Vite 代理能够访问 FastAPI，知识库列表请求返回 HTTP 200。
3. 文档上传成功，返回文档 ID 及 completed 状态。
4. 上传文档能够进入解析、分块、Embedding 和 Chroma 索引流程。
5. 混合检索能够返回上传文档的正确分块及检索分数。
6. RAG 能够根据知识库内容回答并展示来源。
7. Agent 能够调用知识库工具并返回回答。
8. 工作台 Tab 切换及组件状态保留正常。

### 6. 前端生产构建

最近一次生产构建：

| 指标 | 结果 |
|---|---|
| TypeScript 检查 | 通过 |
| Vite 生产构建 | 通过 |
| 转换模块数 | 108 |
| 构建结果 | 成功 |

前端当前没有独立自动化测试套件。上述浏览器验收和生产构建不计入后端 pytest 测试数量。

### 7. Phase 9 验收结论

Phase 9 核心前端功能已完成，真实业务链路和浏览器交互验收通过。

截至 2026-11-05：

- Phase 0～8：已完成。
- Phase 9：Vue 3 前端，已完成。
- Phase 10：系统测试与评估，待开始。
- Phase 11：Docker 部署与交付，待开始。

**下一阶段进入 Phase 10：系统评估与性能优化。**

---

## 2026-11-06：Phase 11 Docker 部署与交付完成

### 1. Docker 部署架构

- 完成 Backend、Frontend 和 Ollama Proxy 的容器化部署。
- 创建独立 Docker 网络 `knowledgeflow-net`。
- 配置 Ollama TCP Proxy，使容器内后端能够访问宿主机 Ollama。
- Backend、Frontend 使用独立容器运行。
- 服务配置健康检查及启动依赖。

### 2. 服务访问与联调

- Backend 通过 `127.0.0.1:18000` 提供本地 API 服务。
- Frontend 通过 `127.0.0.1:8080` 提供 Nginx 静态页面服务。
- 验证前端生产构建产物及 Nginx 配置。
- 验证后端健康检查和 Docker 服务间通信。
- 验证混合检索、RAG、Agent 及 MCP stdio 工具调用链路。

### 3. 数据持久化

- 将宿主机 `./data` 挂载至后端容器 `/app/data`。
- SQLite、Chroma 向量数据、上传文件及日志保存在宿主机。
- 完成后端容器重启前后的数据持久性验证。
- 重启后 SQLite 文档与分块数据、Chroma 集合数据保持一致。

### 4. MCP 服务验证

- 验证 MCP Server stdio 启动方式。
- 验证 `knowledge_search` 和 `knowledge_rag` 工具调用。
- 确认 MCP 子进程能够继承容器运行环境及必要配置。

### 5. Phase 11 验收结论

Docker 容器构建、服务启动、健康检查、前后端联调、Ollama 代理通信、核心业务调用及数据持久化验证完成。

截至 2026-11-06：

- Phase 0～9：已完成。
- Phase 10：系统测试与评估，待开展。
- Phase 11：Docker 部署与交付，已完成。

**当前阶段结论：Phase 11 已完成，下一阶段应进入 Phase 10，开展系统测试、检索质量评估与性能分析。**
