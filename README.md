# TeleSkillHub V1.1

公司内部 Skill Hub（Anthropic Skill 协议）最小可用版本，支持：

- Skill 压缩包上传（`.zip/.rar`）、服务端解压、目录浏览与文件预览
- Skill 版本管理（历史版本查看、回滚）
- Skill 包直接下载 + 下载排行榜
- 部门 / 指定用户可见的数据权限
- 基础安全审查（风险扩展名 + 危险模式扫描 + 安全分）
- 按需求生成初版 Anthropic Skill（`SKILL.md` 模板 + references）



## 0. 本地 MySQL 连接信息（按你的环境）

- Host: `localhost`
- Port: `3306`
- User: `root`
- Password: `123456`

## 目录结构

- `backend/`：FastAPI 后端
- `frontend/`：纯静态前端（HTML + JS）
- `sql/init.sql`：MySQL 初始化脚本
- `data_storage/`：上传与生成文件存储目录

## 1. 初始化数据库

先在 MySQL 执行：

```sql
source /workspace/TeleSkillHub/sql/init.sql;
```

## 2. 启动后端（FastAPI）

```bash
cd /workspace/TeleSkillHub/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL='mysql+pymysql://root:123456@localhost:3306/teleskillhub?charset=utf8mb4'
export STORAGE_ROOT='/workspace/TeleSkillHub/data_storage'
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

> 默认通过 `X-User-Id` 请求头识别用户（默认用户是 `1:admin`）。

## 3. 启动前端

```bash
cd /workspace/TeleSkillHub/frontend
python -m http.server 5173
```

浏览器打开：`http://127.0.0.1:5173`

## 4. 关键 API

- `POST /skills/upload`：上传技能包并创建新版本
- `GET /skills`：技能列表（按权限过滤）
- `GET /skills/{skill_id}`：技能详情 + 版本历史 + 安全报告
- `POST /skills/{skill_id}/rollback/{version_no}`：回滚到历史版本（创建新版本）
- `GET /skills/{skill_id}/versions/{version_id}/files`：版本文件树
- `GET /skills/{skill_id}/versions/{version_id}/files/content?path=...`：文件内容预览
- `GET /skills/{skill_id}/download/{version_id}`：下载 Skill 包并记录下载次数
- `GET /leaderboard/downloads`：下载排行
- `POST /skills/generate`：生成初版 Anthropic Skill

## 5. V1.1 安全/实现说明

- 压缩包解压增加路径穿越保护（zip/rar 都会校验目标路径）。
- 回滚会生成新的 zip 包，确保回滚版本可直接下载。
- `.rar` 依赖系统可用的 unrar/bsdtar 工具（`rarfile` 库调用）。
- 当前认证是轻量实现（请求头用户），建议后续替换成公司 SSO。
