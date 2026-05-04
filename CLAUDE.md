# CLAUDE.md — 直到一万点投资仪表盘

## 项目本质
这个项目把雪球博主"直到一万点"的15章投资方法论编程化为主动信号引擎。
- 方法论不是静态文档，是信号引擎
- 网页不是展示页，是操作终端
- 所有信号/策略必须可追溯到方法论章节

## 技术栈
- Python 3 (纯标准库 + SQLite，无框架)
- 前端: 单文件 HTML + Chart.js CDN，无构建工具
- 数据库: SQLite WAL模式，路径 `data/screener/screener.db`

## 核心文件
- `config.py` — 全局配置（路径/API/板块/权重）
- `screener/signals.py` — 信号引擎（方法论→可执行信号）
- `screener/scoring.py` — 0-100评分算法
- `screener/portfolio.py` — 持仓管理+web数据导出
- `screener/db.py` — 数据库schema+CRUD
- `web/server.py` — HTTP服务+REST API
- `data/web/index.html` — 5标签页仪表盘
- `knowledge_base/*.md` — 方法论知识库（永久文档）
- `run_daily.py` — 每日流水线

## 修改代码的优先级
1. 新增/修改方法论规则 → 先更新 `knowledge_base/*.md`，再改信号/评分逻辑
2. 所有信号必须有 `source_rule` 字段指向方法论章节
3. 数据库不可丢失 — 用户持仓在 `portfolio` 表，不能DROP或清空
4. 新增表用 `CREATE TABLE IF NOT EXISTS`
5. 中文注释和界面，数据库字段用英文

## 数据流
knowledge_base/*.md → signals.py (信号) / scoring.py (评分) → portfolio.py (导出) → index.html (展示)
