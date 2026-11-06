# Python 第三方依赖许可证索引

本文档记录 KnowledgeFlow Python 项目的直接依赖及其许可证信息。

许可证信息根据 Python 发行包元数据和上游项目许可证声明整理。
版本号为本次检查时开发环境中的实际安装版本，不代表项目锁定版本。

## 正式依赖

| 依赖包 | 检查版本 | 许可证 |
|---|---:|---|
| fastapi | 0.162.0 | MIT |
| uvicorn | 0.54.0 | BSD-3-Clause |
| pydantic-settings | 2.16.2 | MIT |
| sqlalchemy | 2.1.6 | MIT |
| aiosqlite | 0.22.1 | MIT |
| pypdf | 6.21.4 | BSD-3-Clause |
| python-docx | 1.2.0 | MIT |
| python-multipart | 0.0.33 | Apache-2.0 |
| aiofiles | 25.1.0 | Apache-2.0 |
| chromadb | 1.5.9 | Apache-2.0 |
| httpx | 0.28.1 | BSD-3-Clause |
| mcp | 1.30.0 | MIT |
| alembic | 1.20.1 | MIT |
| numpy | 1.26.4 | BSD-3-Clause |

## 开发依赖

| 依赖包 | 检查版本 | 许可证 |
|---|---:|---|
| pytest | 9.2.0 | MIT |
| pytest-asyncio | 1.4.1.post1 | Apache-2.0 |
| pytest-cov | 7.1.0 | MIT |
| ruff | 0.17.3 | MIT |

## 特别说明

1. 本文档仅列出 pyproject.toml 中声明的直接运行依赖和开发依赖，不是完整的传递依赖许可证清单。
2. 项目使用版本范围声明依赖，目前没有 Python 依赖锁定文件，因此安装时解析出的具体版本可能不同。
3. 部分 Python 包的发行元数据没有提供 SPDX License-Expression，许可证信息需要结合上游项目声明判断。
4. NumPy 自身采用 BSD-3-Clause 许可证，其二进制发行包还可能包含 OpenBLAS、LAPACK、GCC 运行库等第三方组件。相关组件可能具有独立许可证，应保留 NumPy 发行包附带的许可证和版权声明。
5. 本文档是许可证索引，不代替各依赖发行包附带的完整许可证文本及第三方版权声明。重新分发相关组件时，应遵守对应许可证的要求。

