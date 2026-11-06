# KnowledgeFlow

**KnowledgeFlow** 是一个基于混合检索与 Agent 工具调用的本地优先智能知识库系统。

KnowledgeFlow 已实现文档导入、向量检索、BM25 混合检索、RAG 问答、Agent 工具调用、MCP Server 和 Vue 3 前端。系统支持本地 Ollama 模型、知识来源溯源和扩展工具。后端全量回归测试为 1059 passed、1 skipped；前端已完成生产构建和核心业务浏览器验收。Docker 部署与服务联调已完成，检索质量评估与标题上下文实验已完成。专项性能和资源基准测试暂未开展。

> 当前 Phase 0～11 均已完成。Phase 10 已完成项目业务范围内的检索质量评估与实验分析。

## 项目目标

KnowledgeFlow 希望解决传统知识库系统在以下方面的不足：

- 文档内容难以统一管理和检索。
- 单一向量检索可能遗漏关键词匹配结果。
- 大模型回答缺少可靠的知识来源。
- Agent 工具调用缺乏明确的权限边界。
- 本地模型与知识库服务缺少统一的工程化架构。

项目采用本地优先的设计思路，尽可能使用本地模型和本地存储，降低对外部服务的依赖。

## 核心功能与当前状态

| 模块 | 功能 | 当前状态 |
|---|---|---|
| 知识库管理 | 知识库创建、列表、详情 | 已完成 |
| 文档导入 | PDF、DOCX、Markdown、TXT 上传与解析 | 已完成 |
| 文档处理 | 文本清洗、Token 计数、分块及持久化 | 已完成 |
| Embedding | Ollama 本地文本向量化 | 已完成 |
| 向量检索 | Chroma 向量数据库 | 已完成 |
| 关键词检索 | BM25 检索 | 已完成 |
| 混合检索 | 向量检索、BM25、RRF 融合 | 已完成 |
| RAG | 知识库问答、引用溯源 | 已完成 |
| Agent | 白名单工具调用与迭代控制 | 已完成 |
| MCP | stdio Server、knowledge_search、knowledge_rag | 已完成 |
| API | FastAPI 知识库、文档、检索、RAG、Agent 接口 | 已完成 |
| 数据层 | SQLite、SQLAlchemy 异步 ORM、Alembic | 已完成 |
| 前端 | Vue 3 + TypeScript + Vite，知识库管理、文档上传、混合检索、RAG、Agent | 已完成 |
| 系统评估 | Ground Truth、检索指标评估、检索方案对比与标题上下文实验 | 已完成（业务范围） |
| Docker | 容器化部署、服务联调与数据持久化 | 已完成 |
| 自动化测试 | pytest、集成测试、Ruff | 1059 passed，1 skipped |

## 技术架构规划

```text
                       KnowledgeFlow
                             |
                 +-----------+-----------+
                 |                       |
            Vue 3 前端               FastAPI 后端
                 |                       |
                 |                  API / Service
                 |                       |
                 |           +-----------+-----------+
                 |           |           |           |
                 |         文档管理     RAG 服务    Agent 服务
                 |           |           |           |
                 |           |        混合检索     工具调度
                 |           |           |           |
                 |           |      +----+----+      |
                 |           |      |         |      |
                 |           |    Chroma    BM25   MCP
                 |           |      |         |      |
                 |           +------+---------+------+
                 |                      |
                 |                 本地模型服务
                 |                    Ollama
                 |                      |
                 |              SQLite / 文件存储
                 |
                 +--------------------------------
```

系统已实现 Vue 3 前端和 FastAPI 后端。前端通过 Axios 调用知识库、文档上传、混合检索、RAG 和 Agent API；后端实现文档导入、Embedding、Chroma 向量存储、BM25 与 RRF 混合检索、RAG、Agent 工具调用和 MCP stdio Server。SQLite 保存业务数据与文档分块文本，Chroma 独立保存向量。

## 技术栈

### 后端与工程基础

- Python 3.12
- FastAPI
- Uvicorn
- Pydantic Settings
- pytest
- pytest-cov
- Ruff

### AI 与检索（已实现）

- Ollama：本地大语言模型服务
- Qwen2.5-Coder 7B：本地 Agent 与 RAG 使用的 LLM
- nomic-embed-text：本地 Embedding 模型
- Chroma：向量数据库
- BM25：关键词检索
- RRF：混合检索结果融合
- BGE Reranker：可选增强项，当前尚未接入

### 前端（已实现）

- Vue 3
- TypeScript
- Vite
- Axios：统一 HTTP 请求与错误处理。
- Pinia：知识库状态管理。
- Vue Router：页面路由。

### 数据存储

- SQLite：业务元数据、文档元数据及文档分块文本。
- SQLAlchemy 2.x：异步 ORM。
- aiosqlite：SQLite 异步驱动。
- Alembic：数据库迁移管理，已完成异步迁移环境配置和初始迁移。
- Chroma：独立存储文档分块向量。
- 本地文件系统：原始文档及运行数据。

当前已实现 SQLite 异步数据库连接、Session 管理、外键约束，以及 KnowledgeBase、Document、DocumentChunk 三个 ORM 模型。Repository 层提供知识库、文档和文档分块的数据访问能力；Service 层负责知识库管理、文档元数据管理和文档导入编排。文档元数据与分块文本持久化在 SQLite 中，原始上传文件保存在本地文件系统。Alembic 已完成异步迁移环境配置，初始迁移已执行，数据库包含三张业务表。

## 项目目录

```text
KnowledgeFlow/
├── backend/
│   ├── app/
│   │   ├── agent/              # Agent 执行器与工具注册
│   │   ├── api/
│   │   │   └── routes/         # 知识库、文档、搜索、RAG、Agent API
│   │   ├── core/               # 配置、日志、路径
│   │   ├── db/                 # 异步数据库与 Session
│   │   ├── embeddings/         # Ollama Embedding
│   │   ├── ingestion/
│   │   │   ├── parsers/        # PDF、DOCX、Markdown、TXT
│   │   │   └── tokenizers/     # WordPiece Tokenizer
│   │   ├── llm/                # Ollama Chat 与工具调用
│   │   ├── mcp_server/         # MCP Server、Runtime、工具
│   │   ├── models/             # SQLAlchemy ORM
│   │   ├── repositories/       # 数据访问层
│   │   ├── retrieval/          # BM25、RRF
│   │   ├── services/           # 导入、检索、RAG、索引服务
│   │   ├── vectorstore/        # Chroma 向量存储
│   │   └── main.py             # FastAPI 应用入口
│   └── tests/                  # 后端单元测试与集成测试
├── alembic/                    # 数据库迁移
├── data/                       # SQLite、Chroma、上传文件及日志
├── docs/
│   └── DEVELOPMENT_LOG.md      # 分阶段开发记录
├── frontend/                   # Vue 3 前端（Phase 9）
├── .vscode/
├── .env.example
├── alembic.ini
├── pyproject.toml
└── README.md
```



## 环境要求

当前开发环境：

| 组件 | 版本或配置 |
|---|---|
| 操作系统 | Ubuntu 24.04 |
| Python | 3.12.16 |
| Conda 环境 | klf |
| Node.js | 24.16.0 |
| npm | 12.2.1 |
| Git | 2.43.0 |
| GPU | NVIDIA RTX 4060 Laptop 8GB |
| Ollama | 0.40.11 |

项目要求 Python 3.12。可以使用 Python `venv` 创建虚拟环境，也可以使用 Conda 管理环境。

## 安装与运行

### 1. 获取项目

```bash
git clone https://github.com/joysite/KnowledgeFlow.git
cd KnowledgeFlow
```

### 2. 创建并激活 Python 环境

使用 `venv`：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python --version
```

如果使用 Conda，请激活自己的 Python 3.12 环境。


### 3. 安装项目及开发依赖

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

### 4. 配置环境变量

```bash
cp .env.example .env
```

根据实际需要修改 `.env` 中的配置。不要将 `.env` 提交到 Git。

### 5. 启动后端服务

```bash
python -m uvicorn app.main:app \
    --app-dir backend \
    --host 127.0.0.1 \
    --port 8000 \
    --reload
```

### 6. 检查服务

健康检查接口：

```bash
curl http://127.0.0.1:8000/api/v1/health
```

预期响应：

```json
{
  "code": 200,
  "message": "服务运行正常",
  "data": {
    "service": "KnowledgeFlow",
    "status": "healthy"
  }
}
```

Swagger API 文档：

```text
http://127.0.0.1:8000/docs
```

OpenAPI Schema：

```text
http://127.0.0.1:8000/openapi.json
```

### 7. 前端开发

前端要求 Node.js 24.x 和 npm。

```bash
cd frontend
npm ci
```

启动 Vite 开发服务器：

```bash
npm run dev
```

默认访问地址：

```text
http://localhost:5173
```

开发服务器通过 Vite Proxy 将 API 请求转发到本地后端 127.0.0.1:8000，因此需要先启动后端服务。

构建生产版本：

```bash
npm run build
```

生产构建产物生成在 frontend/dist/ 目录。

## Docker 部署

### 1. 部署架构

项目使用 Docker Compose 管理三个服务：

| 服务 | 作用 | 宿主机访问 |
|---|---|---|
| frontend | Nginx + Vue 3 前端 | http://127.0.0.1:8080 |
| backend | FastAPI 后端 | http://127.0.0.1:18000 |
| ollama-proxy | Ollama TCP 转发代理 | 172.30.0.1:11435 |

Ollama 模型服务运行在宿主机，不由 Compose 创建。

注意：
- 前端和后端端口默认绑定宿主机 `127.0.0.1`，仅允许部署机器本机访问，不直接对局域网开放。
- Docker 网络默认使用 `172.30.0.0/24`。如果修改网络网段或网关，需要同步检查 `compose.yaml` 和 `scripts/ollama_tcp_proxy.py` 中的监听地址及允许网段配置。

Backend 通过专用 Proxy 访问宿主机 Ollama：
- Proxy 监听 `172.30.0.1:11435`。
- 上游地址为 `127.0.0.1:11434`。
- 仅允许 `172.30.0.0/24` 网段的客户端连接。

### 2. 环境准备

需要预先安装 Docker Engine、Docker Compose 和 Ollama。

**平台说明：** 当前 Docker 部署配置面向 Linux 环境，依赖 Docker `network_mode: host` 和宿主机 Bridge 网络网关地址。Windows/macOS 的 Docker Desktop 网络模型不同，不能保证直接兼容，需要根据实际网络环境调整 Ollama Proxy 配置。

确认宿主机 Ollama 正常运行，检查模型：

`ollama list`

需要的模型：
- `nomic-embed-text:latest`
- `qwen2.5-coder:7b`

创建部署环境配置：

`cp .env.example .env`

Compose 会将 Backend 的 Ollama 地址覆盖为容器网络专用代理地址。不要将 `.env`、模型文件或运行数据提交到 Git。

### 3. 创建 Docker 网络

Compose 使用预先创建的外部 Bridge 网络：

```bash
docker network create \
  --driver bridge \
  --subnet 172.30.0.0/24 \
  --gateway 172.30.0.1 \
  knowledgeflow-net
```

如果网络已经存在，不需要重复创建。

### 4. 构建并启动

在项目根目录执行：

```bash
docker compose build
docker compose up -d
docker compose ps
```

查看服务日志：

```bash
docker compose logs -f
```
### 5. 服务访问与健康检查

前端：

`http://127.0.0.1:8080`

后端健康检查：

```bash
curl http://127.0.0.1:18000/api/v1/health
```

Swagger API 文档：

`http://127.0.0.1:18000/docs`

OpenAPI Schema：

`http://127.0.0.1:18000/openapi.json`
### 6. 数据持久化

宿主机 `data/` 目录挂载到 Backend 容器 `/app/data`：

| 数据 | 宿主机目录 |
|---|---|
| SQLite 数据库 | `data/knowledgeflow.db` |
| Chroma 向量数据 | `data/chroma/` |
| 上传文件 | `data/uploads/` |
| 应用日志 | `data/logs/` |

容器重启不会删除上述挂载目录中的数据。

### 7. 停止与重启

停止并移除 Compose 容器：

```bash
docker compose down
```

重新启动：

```bash
docker compose up -d
```

重启单个服务：

```bash
docker compose restart backend
```


`docker compose down` 不会删除宿主机 `data/` 目录，也不会自动删除外部网络。
### 8. MCP stdio 服务

MCP Server 使用 stdio 传输方式，模块入口：

`app.mcp_server.server`

项目根目录下可通过以下命令启动：

`python -m app.mcp_server.server`

Docker 环境中的 MCP 子进程需要继承 Compose 注入的环境变量，并使用 `/app` 作为工作目录、`/app/backend` 作为 Python 模块搜索路径。

已实现工具：
- `knowledge_search`
- `knowledge_rag`

---

## 配置管理

项目使用 Pydantic Settings 统一管理应用配置。

当前已实现：

- 应用名称、版本和调试模式配置。
- API 服务地址、端口和路由前缀配置。
- 日志级别、文件名、文件大小和备份数量配置。
- 环境变量和 `.env` 文件读取。
- 环境变量优先于 `.env` 文件的配置优先级。
- 配置字段校验与非法值处理。
- 使用项目根目录绝对路径定位 `.env` 文件。
- 使用缓存避免重复创建 Settings 实例。

环境变量统一使用 `KLF_` 前缀。

## 日志系统

当前日志模块支持：

- 统一的 `knowledgeflow` Logger 命名空间。
- 控制台和 UTF-8 文件双输出。
- 日志级别过滤。
- RotatingFileHandler 文件轮转。
- 日志参数从统一 Settings 配置读取。
- 显式传入参数覆盖默认配置。
- 重复初始化时清理旧处理器，避免重复输出。

默认日志目录为 `data/logs/`。

## 测试与代码质量

### 运行全部测试

```bash
python -m pytest backend/tests -v
```
默认运行全部自动化测试，其中真实 Ollama 集成测试会跳过。

### 运行真实 Ollama 集成测试

需要提前启动 Ollama，并确保已下载项目配置的 Embedding 模型（默认 nomic-embed-text:latest）。

```bash
KLF_RUN_LIVE_INTEGRATION=1 python -m pytest backend/tests/test_vector_search_integration.py -v
```

### 生成 HTML 覆盖率报告

```bash
python -m pytest backend/tests --cov-report=html
```

报告生成后可通过浏览器打开：

```text
htmlcov/index.html
```

### Ruff 代码检查

```bash
python -m ruff check backend/app backend/tests
```

### Ruff 格式检查

```bash
python -m ruff format --check backend/app backend/tests
```

### 自动修复

```bash
python -m ruff check backend/app backend/tests --fix
python -m ruff format backend/app backend/tests
```

## 开发路线

项目采用分阶段、渐进式开发。

| 阶段 | 开发内容 | 状态 |
|---|---|---|
| Phase 0 | 项目初始化与工程基础 | 已完成 |
| Phase 1 | 配置管理与基础设施 | 已完成 |
| Phase 2 | 数据层与数据库基础设施 | 已完成 |
| Phase 3 | 文档导入、解析与分块 | 已完成 |
| Phase 4 | Embedding 与向量存储 | 已完成 |
| Phase 5 | BM25 与混合检索 | 已完成 |
| Phase 6 | RAG 问答与引用溯源 | 已完成 |
| Phase 7 | Agent 工具调用 | 已完成 |
| Phase 8 | MCP Server | 已完成 |
| Phase 9 | Vue 前端 | 已完成 |
| Phase 10 | 系统测试与评估 | 已完成（业务范围） |
| Phase 11 | Docker 部署与项目完善 | 已完成 |

具体阶段任务将根据实际开发进度持续细化。

## 开发规范

- 每次只实现一个明确的功能模块。
- 新功能必须配套自动化测试。
- 修改已有代码前先检查现有实现和依赖关系。
- API 层不直接操作底层数据库或向量数据库。
- MCP 工具复用业务 Service 层能力。
- Agent 只能调用经过授权的白名单工具。
- 优先采用本地模型和本地数据存储。
- 中文代码注释和运行日志，英文类名、函数名、变量名及 API 路径。
- 不将密钥、环境变量和运行数据提交到 Git。
- 每个开发阶段完成后进行测试、验收和文档更新。

## 当前开发进度

### Phase 0：项目工程基础

<badge>已完成</badge>

- 项目目录与 Python 工程结构。
- FastAPI 应用入口及健康检查接口。
- 基础日志系统。
- pytest、pytest-cov 和 Ruff。

### Phase 1：核心配置管理

<badge>已完成</badge>

- Pydantic Settings 配置管理。
- 环境变量与 `.env` 配置加载。
- 统一项目路径管理。
- 配置校验和异常处理。
- 日志系统与配置集成。

### Phase 2：数据层与数据库基础设施

<badge color="success">Phase 2 已完成</badge>

已完成：

- SQLite 异步数据库连接与会话管理。
- SQLite 外键约束及数据库生命周期管理。
- SQLAlchemy ORM 声明式基类。
- KnowledgeBase、Document、DocumentChunk 三个 ORM 模型。
- 模型约束、双向关系和级联删除测试。
- Alembic 异步数据库迁移环境及初始迁移。
- BaseRepository 通用 CRUD。
- KnowledgeBaseRepository、DocumentRepository、DocumentChunkRepository。
- KnowledgeBaseService 知识库业务管理。
- DocumentService 文档元数据业务管理。
- Repository 与 Service 真实 SQLite 集成测试。

当前结果：

- Repository 层：已完成。
- Service 层：已完成。
- Repository 与 Service 集成测试：已完成。
- Phase 2 最终验收：正式通过（2026-11-03）。

### 历史测试基线（2026-11-04）

| 指标 | 结果 |
|---|---:|
| 全量测试 | 592 passed |
| 失败测试 | 0 |
| 总覆盖率 | 95.07% |
| 覆盖率要求 | 90% |
| Ruff 静态检查 | 通过 |
| Ruff 格式检查 | 通过（71 files） |

测试环境：Python 3.12.16，Conda `klf`。

### 最新后端测试基线（2026-11-05）

| 指标 | 结果 |
|---|---:|
| 全量测试 | 1059 passed，1 skipped |
| 失败测试 | 0 |
| Ruff 静态检查 | 通过 |
| Ruff 格式检查 | 通过（131 files） |
| 跳过测试 | 1 项，需要设置 `KLF_RUN_LIVE_INTEGRATION=1` 才运行 |

本次未重新统计覆盖率，不沿用历史覆盖率作为当前指标。

### Phase 3：文档导入、解析与分块

<badge color="success">已完成</badge>

已实现的基础能力：

- PDF、DOCX、Markdown、TXT 解析器及统一 ParserRegistry。
- 上传文件存储、文件类型与内容校验。
- DOCX ZIP 结构检查及解压资源限制。
- PDF 页面数量、单页文本长度和全文文本长度限制。
- 文档文本清洗与分块处理。
- TokenCounter Protocol 与 ChunkProcessor，支持后续接入真实 Token 计数实现。
- DocumentIngestionService 文档导入流程。
- 文档元数据及分块文本写入 SQLite。
- 文件重复检测、异常状态记录、事务回滚和文件清理处理。
- 解析器配置注入及相关单元测试、集成测试。

PDF 资源限制默认值：

| 配置项 | 默认值 |
|---|---:|
| `KLF_PDF_MAX_PAGES` | 500 |
| `KLF_PDF_MAX_PAGE_CHARS` | 200000 |
| `KLF_PDF_MAX_TOTAL_CHARS` | 2000000 |

当前回归结果：

| 指标 | 结果 |
|---|---:|
| 全量测试 | 592 passed |
| 总覆盖率 | 95.07% |
| Ruff 静态检查 | 通过 |
| Ruff 格式检查 | 通过 |

说明：PDF 字符数限制是在文本提取后检查，不能完全限制提取期间的临时内存和 CPU 消耗。`asyncio.to_thread()` 也不能通过取消协程强制终止已经运行的线程。更强的资源隔离需要后续考虑独立进程及操作系统级限制。

Phase 3 已完成验收。PDF 独立进程及操作系统级资源隔离属于后续增强事项。


### Phase 9：Vue 3 前端

<badge color="success">已完成</badge>

技术实现：

- Vue 3、TypeScript、Vite。
- Axios 统一 API 客户端、请求超时和错误信息处理。
- Pinia 管理知识库列表、当前知识库及加载状态。
- Vue Router 实现首页和知识库详情页路由。
- Vite 开发代理连接 FastAPI 后端。

核心功能：

- 知识库列表、分页、创建及详情展示。
- 文档上传，支持拖放、格式和大小校验、上传进度及错误反馈。
- 混合检索，展示文档分块、BM25、向量距离和 RRF 分数。
- RAG 问答，展示回答、上下文信息及来源引用。
- Agent 助手，展示回答、工具调用次数和迭代次数。
- 知识库工作台采用 Tab 导航，分别呈现概览、文档管理、混合检索、RAG 问答和 Agent 助手。
- 使用 `v-show` 保留业务组件状态，支持响应式布局。
- 首页、详情页及 favicon 使用统一的 KnowledgeFlow Logo 资源。

验收结果：

| 检查项 | 结果 |
|---|---|
| TypeScript 与 Vue 生产构建 | 通过 |
| 最近一次构建 | 108 modules transformed |
| Vite API 代理 | 真实请求 HTTP 200 |
| 知识库创建与详情 | 浏览器验收通过 |
| 文档上传与索引 | 真实上传及检索验证通过 |
| 混合检索 | 浏览器验收通过 |
| RAG 问答与来源展示 | 真实请求验收通过 |
| Agent 工具调用 | 真实请求验收通过 |
| 工作台 Tab 与状态保留 | 浏览器验收通过 |

说明：当前未配置独立的前端自动化测试套件，因此不将生产构建或人工验收计为自动化测试通过数量。

## License

KnowledgeFlow 采用 MIT License 开源，完整条款见根目录 LICENSE 文件。

第三方依赖许可证索引：
- Python 后端依赖许可证索引：backend/THIRD_PARTY_LICENSES.md
- 前端依赖许可证索引：frontend/THIRD_PARTY_LICENSES.md

第三方依赖仍受各自许可证约束。重新分发相关依赖或构建产物时，请遵守对应许可证的要求。
