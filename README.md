# SOE Compliance Hub

面向央国企制度梳理、内控诊断和合规咨询场景的多 Agent 知识管理原型。

系统将制度文件解析、结构化知识抽取、GraphRAG 问答、确定性规则预审和制度增量更新组合成一条可演示的咨询业务闭环。项目用于数字化咨询校招作品集，不替代法律意见或企业正式审批。

## 业务问题

央国企制度管理通常存在四类问题：文件分散且版本复杂；跨制度检索成本高；审批条件与责任边界依赖人工解释；制度修订后知识更新不及时。本项目围绕这些问题提供：

- 制度、监管文件、内控手册和流程表的统一入库；
- 条款、责任部门、流程、风险、控制措施和适用范围的结构化抽取；
- 同时使用语义检索和知识图谱的合规问答；
- 返回文件名、页码、条款和置信度的可追溯引用；
- 对常用采购阈值进行确定性、可测试的规则预审；
- 制度修订后的增量解析和知识同步。

## 核心流程

```text
制度文件
  -> DocParserAgent：PDF / DOCX / 表格 / 图片解析和分块
  -> KnowledgeExtractAgent：条款、部门、风险、控制关系抽取
  -> ChromaDB + Neo4j：非结构化内容与结构化关系双存储
  -> QAAgent：查询改写、向量/图谱检索、重排、引用式回答
  -> KnowledgeUpdateAgent：变更检测、版本更新、失效知识清理
```

采购合规预审采用独立规则层：金额阈值和审批路径由 Python 规则计算，开放式制度解释由 GraphRAG 完成。这样既保留大模型处理复杂语言的能力，也避免将关键审批判断完全交给概率模型。

## 领域模型

知识实体：

`Policy`、`Clause`、`Regulation`、`Department`、`Role`、`Process`、`Risk`、`Control`、`Organization`、`Event`、`Time`、`Concept`

主要关系：

`contains_clause`、`governed_by`、`applies_to`、`owned_by`、`requires`、`mitigates`、`conflicts_with`、`supersedes`、`related_to`、`part_of`

关键属性包括制度版本、生效/失效日期、适用范围、风险等级、条款编号和来源文件。

## 🎯 项目简介

**AgentKnowledgeHub** 包含 **4个核心Agent**，通过 [LangGraph](https://langchain-ai.github.io/langgraph/) 有向图编排，实现企业知识的全链路智能处理。

### 4个Agent是什么，分别做什么？

| Agent | 中文名 | 职责 | 类比理解 |
|-------|--------|------|----------|
| `DocParserAgent` | 文档解析Agent | 把PDF/图片/表格等各种格式的文档"读懂"，切割成小段落 | 超强秘书，能看懂任何格式的文件 |
| `KnowledgeExtractAgent` | 知识抽取Agent | 从文本中自动提取人名、公司、关系等结构化信息 | 分析师，把信息整理成知识图谱 |
| `QAAgent` | 问答Agent | 接收用户问题，同时查向量库和知识图谱，生成精准答案 | 专家顾问，综合多源信息回答 |
| `KnowledgeUpdateAgent` | 知识更新Agent | 监听文档变更，只更新变化的部分，保持知识库最新 | 勤快管理员，实时维护知识库 |

### 五大技术亮点

| 亮点 | 说明 | 解决什么问题 |
|------|------|-------------|
| **多模态RAG** | 不只处理文字，还能理解PDF里的图片、表格、流程图 | 传统系统只能处理纯文字 |
| **GraphRAG (知识图谱)** | 用图数据库存储实体关系，支持多跳推理 | 纯向量检索无法处理"关系型"和"多步推理"问题 |
| **CDC增量更新** | 文档变了只更新变化的部分 | 传统方案每次全量重建，1000个文档改5个要30分钟 |
| **记忆系统** | 支持会话记忆、用户画像和个性设置 | 提供个性化对话体验 |
| **Checkpoint 容灾恢复** | MongoDB 持久化每步状态，OOM 崩溃后自动恢复 | 进程崩溃导致全部工作丢失，需从头重跑 |

---

## 🏗 系统架构

### 整体架构图

```
┌──────────────────────────────────────────────────────────┐
│                      用户接口层                            │
│         REST API / Vue Web UI / SDK                       │
└──────────────┬───────────────────────────┬───────────────┘
               │                           │
┌──────────────▼───────────────────────────▼───────────────┐
│            编排引擎 (LangGraph 有向图 + Checkpoint)         │
│    ┌─────────────┬──────────────┬──────────────┐         │
│    │ 文档入库流程  │   问答流程    │  增量更新流程  │         │
│    └──────┬──────┴──────┬───────┴──────┬───────┘         │
└───────────│─────────────│──────────────│─────────────────┘
            │             │              │
┌───────────▼──┐ ┌───────▼────┐ ┌───────▼──────┐ ┌────────────┐
│ 文档解析Agent │ │  问答Agent  │ │ 知识更新Agent │ │ 知识抽取Agent│
│              │ │            │ │              │ │            │
│ - PDF解析    │ │ - 意图识别  │ │ - 文件监听    │ │ - NER实体识别│
│ - 图片OCR    │ │ - 向量检索  │ │ - CDC消费    │ │ - 关系抽取  │
│ - 表格提取   │ │ - 图谱检索  │ │ - 差量对比    │ │ - 事件抽取  │
│ - 文档分块   │ │ - 混合排序  │ │ - 增量更新    │ │ - 三元组生成│
└──────┬───────┘ │ - 答案生成  │ │ - 版本管理    │ └─────┬──────┘
       │         └──┬────┬────┘ └──────┬───────┘       │
       │            │    │             │               │
┌──────▼────────────▼────│─────────────▼───────────────▼──┐
│                        存储层                              │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ ChromaDB /  │  │  Neo4j       │  │   SQLite     │     │
│  │ PGVector    │  │  知识图谱     │  │   记忆存储    │     │
│  │ 向量数据库   │  │              │  │              │     │
│  └─────────────┘  └──────────────┘  └──────────────┘     │
│  ┌───────────────────────────────────────────────────┐   │
│  │  MongoDB — LangGraph Checkpoint 状态持久化         │   │
│  │  (每步自动存档，崩溃后可恢复)                        │   │
│  └───────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
```

### 三条工作流水线（每个数据怎么流转的）

**流水线1：文档入库**（上传文档时触发）

```
用户上传文档
     │
     ▼
文档解析Agent  ←── 支持 PDF / Word / Excel / 图片 / Markdown
  ├── 识别文件类型
  ├── 解析内容（文字 + 图片OCR + 表格提取）
  └── 切割成小块（Chunk）
     │
     ▼
知识抽取Agent
  ├── 命名实体识别（NER）：找出人名、公司名、地名等
  ├── 关系抽取：找出实体之间的关系
  └── 生成三元组：("张三", "就职于", "腾讯")
     │
     ├──────────────────────────────┐
     ▼                              ▼
存入向量数据库                   存入知识图谱
(ChromaDB/PGVector)              (Neo4j)
```

**流水线2：智能问答**（用户提问时触发）

```
用户提问："张三负责什么业务？和李四有什么合作关系？"
     │
     ▼
意图识别 + 查询改写
     │
     ├──────────────────┐
     ▼                  ▼
向量检索              图谱检索
(语义相似度)          (关系路径查询)
     │                  │
     └────────┬─────────┘
              ▼
         混合重排序
     (图谱结果权重更高，因为更精准)
              │
              ▼
         LLM生成答案
              │
              ▼
    返回答案 + 来源引用
```

**流水线3：增量更新**（文档修改时触发）

```
文档被修改 / 数据库记录更新
     │
     ▼
CDC事件产生（通过文件监听或Kafka）
     │
     ▼
知识更新Agent
  ├── 差量分析：找出哪些部分变了
  ├── 增量解析：只重新处理变化的内容
  └── 版本管理：记录更新时间和版本号
     │
     ├──────────────┐
     ▼              ▼
更新向量库        更新知识图谱
```

---

## 🛠 技术栈

### 后端技术栈

| 组件 | 技术选型 | 为什么选它 |
|------|----------|------------|
| **Agent编排** | [LangGraph](https://langchain-ai.github.io/langgraph/) | 生产级Agent编排标准，有向图 + Checkpoint 状态持久化 |
| **LLM调用** | [LangChain](https://python.langchain.com/) + OpenAI | 最成熟的LLM应用框架，支持几十种LLM |
| **向量数据库** | [ChromaDB](https://www.trychroma.com/) / [PGVector](https://github.com/pgvector/pgvector) | ChromaDB开箱即用；PGVector适合已有PostgreSQL的企业 |
| **知识图谱** | [Neo4j](https://neo4j.com/) | 图数据库的事实标准，Cypher查询语言强大 |
| **Checkpoint存储** | [MongoDB](https://www.mongodb.com/) + [langgraph-checkpoint-mongodb](https://github.com/langchain-ai/langgraph) | LangGraph 原生支持，自动持久化每步状态，崩溃可恢复 |
| **消息队列** | [Apache Kafka](https://kafka.apache.org/) | CDC事件流处理的工业标准 |
| **API框架** | [FastAPI](https://fastapi.tiangolo.com/) | 异步高性能，自动生成OpenAPI/Swagger文档 |
| **文档解析** | [Unstructured](https://unstructured.io/) + PyPDF2 + Tesseract | 多模态文档解析全家桶 |
| **容器化** | [Docker Compose](https://docs.docker.com/compose/) | 一键启动所有依赖服务 |

### 前端技术栈

| 组件 | 技术选型 | 说明 |
|------|----------|------|
| **框架** | [Vue 3](https://vuejs.org/) | 渐进式JavaScript框架，Composition API |
| **UI组件库** | [Element Plus](https://element-plus.org/) | Vue 3生态最成熟的UI组件库 |
| **HTTP客户端** | [Axios](https://axios-http.com/) | 流行的HTTP客户端库 |

## 技术架构

| 层次 | 技术 | 用途 |
|---|---|---|
| Agent 编排 | LangGraph | 入库、问答、更新三条工作流及 checkpoint |
| API | FastAPI | 文档、问答、预审和管理接口 |
| 大模型 | LangChain + OpenAI 兼容接口 | 抽取、查询改写、答案生成 |
| 向量检索 | ChromaDB / PGVector | 制度原文语义检索 |
| 知识图谱 | Neo4j | 条款、责任、风险和流程关系查询 |
| 状态持久化 | MongoDB | LangGraph checkpoint |
| 变更处理 | Watchdog / Kafka | 制度增量更新 |
| 前端 | Vue 3 + Element Plus | 制度库、问答工作台与合规预审 |

安全约束包括上传扩展名与路径校验、模型生成 Cypher 的只读拦截、关系类型白名单以及删除文档时同步清理向量和图谱记录。

## 快速演示

仓库提供脱敏样例 [央国企采购制度示例.txt](./uploads/央国企采购制度示例.txt)，其中包含制度编号、版本、生效日期、审批阈值、职责和风险红线。

推荐演示顺序：

1. 登录前端演示账号 `admin / admin123`。
2. 在“制度知识库”上传采购制度样例。
3. 在“对话工作台”询问：`采购金额超过 100 万元需要哪些审批？`
4. 继续询问职责边界和重大合规风险，查看来源引用与处理过程。
5. 在“合规预审”分别输入 80 万、120 万和 500 万，对比审批路径。

更完整的咨询演示脚本见 [docs/consulting-scenario.md](./docs/consulting-scenario.md)。

## 本地运行

以下步骤已在 Windows + PyCharm 环境验证。推荐使用 Python 3.11；Python 3.14 可能暂时缺少部分 AI 依赖的兼容版本。

前置条件：

- Docker Desktop；
- PyCharm 及 Python 3.11；
- Node.js 18+（推荐 LTS 版本）；
- 同时支持对话模型和嵌入模型的 OpenAI 兼容 API。

### 1. 用 PyCharm 打开项目

在 PyCharm 中选择 `File -> Open`，打开仓库根目录 `AgentKnowledgeHub-main`，不要只打开 `python` 子目录。

点击右下角的 Python 版本，或进入 `File -> Settings -> Project -> Python Interpreter`，然后选择：

```text
Add Interpreter -> Add Local Interpreter -> Virtualenv
```

选择或下载 Python 3.11，并将虚拟环境位置设为项目根目录下的 `.venv`。创建完成后，PyCharm 右下角应显示类似 `Python 3.11 (.venv)`。

在 PyCharm 中新建 Terminal，确认当前目录是 `AgentKnowledgeHub-main`，然后安装后端依赖：

```powershell
python --version
python -m pip install --upgrade pip
python -m pip install -r .\python\requirements.txt
```

若终端没有自动使用虚拟环境，可将命令中的 `python` 替换为 `.\.venv\Scripts\python.exe`。

### 2. 配置模型 API

在项目根目录执行：

```powershell
Copy-Item .\python\.env.example .\python\.env
notepad .\python\.env
```

OpenAI 配置示例：

```env
OPENAI_API_KEY=在这里填写真实APIKey
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o
EMBEDDING_MODEL=text-embedding-3-small
```

阿里云百炼 OpenAI 兼容接口示例：

```env
OPENAI_API_KEY=在这里填写百炼APIKey
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
OPENAI_MODEL=qwen-plus
EMBEDDING_MODEL=text-embedding-v3
```

`OPENAI_MODEL` 用于问答和知识抽取，`EMBEDDING_MODEL` 用于将制度文档转换为检索向量。模型名称必须是当前 API 平台实际支持的名称。不要将包含真实密钥的 `python/.env` 上传到 GitHub 或发给他人。

其余数据库地址保持 `.env.example` 中的 `localhost` 默认值即可，因为本流程在 Windows 本机运行 API。

### 3. 启动 Docker 依赖

先启动 Docker Desktop，再从项目根目录执行：

```powershell
docker compose up -d neo4j chromadb zookeeper kafka mongodb
docker compose ps
```

本流程只在 Docker 中运行数据库和消息队列，不启动 Compose 中的 `api` 服务。

### 4. 启动后端

在第一个 PyCharm Terminal 中执行：

```powershell
cd .\python
python -m api.main
```

看到 `Application startup complete` 表示启动成功。访问 `http://localhost:8080/docs`，不要使用没有页面路由的 `http://localhost:8080/`。

### 5. 启动前端

保持后端终端运行，在 PyCharm 中新建第二个 Terminal：

```powershell
cd .\fontend\vue-aapp
npm.cmd install
npm.cmd run serve
```

看到 `App running at: http://localhost:8081/` 后打开前端。若浏览器显示 `ERR_CONNECTION_REFUSED`，说明前端终端尚未启动或已经退出。

访问地址：

- 前端：`http://localhost:8081`
- Swagger：`http://localhost:8080/docs`
- Neo4j Browser：`http://localhost:7474`

## 关键 API

| 方法 | 路径 | 功能 |
|---|---|---|
| POST | `/api/ingest/upload` | 上传并解析制度文件 |
| GET | `/api/ingest/documents` | 查询制度文件清单 |
| DELETE | `/api/ingest/documents/{file_name}` | 删除文件及关联知识 |
| POST | `/api/qa/ask` | GraphRAG 合规问答 |
| POST | `/api/compliance/procurement-check` | 采购审批规则预审 |
| POST | `/api/admin/update` | 触发制度增量更新 |
| GET | `/api/admin/stats` | 查询向量库与图谱统计 |
| GET | `/api/health` | 服务健康检查 |

预审请求示例：

```json
{
  "amount": 1200000,
  "scope": "集团总部及所属全资、控股子公司"
}
```

## 测试

```bash
cd python
pytest tests/
```

当前规则测试覆盖低于招标阈值、公开招标、总经理办公会审批和非法金额四种情况。

## 项目边界

- 当前登录是前端演示账号，不是生产级身份认证；
- 演示规则基于样例制度 `CG-2026-001 V2.1`，真实项目应由规则配置和审批矩阵驱动；
- 上线前需补充 RBAC、数据分级脱敏、操作审计、模型评测、人工复核和备份恢复；
- 涉及法律或重大经营决策时，系统输出只能作为检索与分析辅助。

## License

本项目基于 [JOYUONG/AgentKnowledgeHub](https://github.com/JOYUONG/AgentKnowledgeHub) 进行场景化二次开发，原项目 README 标注采用 MIT License。

原项目的版权归原作者 JOYUONG 及原项目贡献者所有。本项目保留原项目的版权与许可声明；使用、修改及分发时，请同时遵守原项目的许可要求。

本仓库中的新增与改造内容用于个人学习、作品展示及求职项目说明，不代表原作者参与或认可本次二次开发。项目材料中应如实说明上游来源与二次开发范围。
