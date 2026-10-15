# Telegram Channel Manager

本地部署的 Telegram 频道管理与内容同步平台。它只使用当前已授权账号能够访问的频道；频道和消息的业务事实保存在 SQLite，网页关闭后后台任务继续运行。前端为中文 Vue 3 管理界面，后端为 FastAPI、Telethon 1.x 和单进程持久任务执行器。

## 运行环境

- Python 3.11 或 3.12；本项目在 Python 3.12.4 下开发。
- Node.js 20.19+ 或 22.12+；本项目在 Node.js 24 下开发。
- 默认仅监听 `127.0.0.1`，不需要 Docker。
- Telegram `TG_API_ID`、`TG_API_HASH` 和能够访问目标频道的用户账号。没有它们时，仍可浏览及导出数据库里已有的内容。

## 首次配置

在 `backend` 目录复制 `.env.example` 为 `.env`。`.env`、`backend/data`、Telethon session 与本地媒体均已被 Git 忽略。

```powershell
cd backend
uv sync --frozen --extra test --python 3.12
& .\.venv\Scripts\python.exe scripts\hash_admin_password.py
& .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

把密码脚本输出写入 `ADMIN_PASSWORD_HASH`，把随机字符串写入 `SESSION_SECRET`。密码明文不要写入 `.env`。管理员密码哈希和会话密钥是必填项；缺少时后端拒绝启动。Telegram 凭证填入 `TG_API_ID` 与 `TG_API_HASH`，也可稍后再填。`TG_API_ID` 和 `TG_API_HASH` 只在后端读取。如果直连 Telegram 超时，在后端 `.env` 中设置 `TG_PROXY_URL=http://127.0.0.1:10809`（也支持 `socks4://`、`socks5://`），然后安装更新后的后端依赖并重启后端。代理须允许连接 Telegram 的 TCP 端口；留空则直连。

如果没有 `uv`，可在 `backend` 目录运行 `python -m venv .venv`，再用虚拟环境的 Python 执行 `-m pip install -r requirements.txt`。`pyproject.toml` 声明兼容范围，`uv.lock` 锁定本次安装解析出的版本；`requirements.txt` 提供 pip 入口。

## 启动

两个终端分别运行：

```powershell
.\scripts\start-backend.ps1
.\scripts\start-frontend.ps1
```

也可以手动运行：

```powershell
cd backend
& .\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

```powershell
cd frontend
npm ci
npm run dev
```

访问 `http://127.0.0.1:5173`，先用管理员密码登录，再到“系统设置”发起 Telegram 登录。后端 API 位于 `http://127.0.0.1:8000/api/v1`；健康检查为 `/api/v1/health`。首次启动会运行 Alembic `upgrade head`，而不是无条件 `create_all`。

## 功能与数据约定

- “发现频道”读取授权账号实际可访问的频道或超级群；私有频道只显示标题、Chat ID 和授权访问状态，不构造公开链接。添加频道不会自动启动同步。
- 历史同步和校准按 Telegram 消息 ID 从新到旧分批扫描。每批的消息、事件和任务游标在同一 SQLite 事务内提交；重启会把运行中的任务重新排队，从已提交游标继续。消息以频道和 Telegram 消息 ID 唯一约束去重，内容相同不产生编辑事件。
- 一个后端进程只有一个 Telethon 客户端和一组全局新消息/编辑监听器。监听仅处理已管理且启用监听的频道。服务恢复后为监听频道排队校准。FloodWait 遵守 Telegram 等待时间，连续失败次数有上限；不使用规避限流的方式。
- 大任务由 HTTP 创建并返回任务 ID。运行中的历史同步和校准可在批次间暂停或取消；运行中的媒体下载和导出不提供暂停/取消，等待中的任务可以取消。任务状态、进度和错误保存在数据库中。
- JSON 快照来自 SQLite，`schema_version` 为 1。频道 ID 和消息 ID 在 API 与导出中均为字符串。JSONL 每行都有稳定 `event_id`。后台追加事件文件时先 `flush`/`fsync`，再标记数据库事件已导出；崩溃窗口可能产生重复行，消费端应按事件 ID 去重。可创建 JSONL 导出任务从 SQLite 重新生成事件文件。
- 导出支持单频道或所有已管理频道的 JSON、JSONL、JSON 加已下载媒体的 ZIP，以及单频道仅媒体 ZIP。快照写入临时文件并原子替换。ZIP 内路径由程序生成；媒体与导出下载路径必须落在 `DATA_ROOT` 下。
- `MEDIA_MAX_BYTES` 默认 100 MiB。历史扫描不会自动下载媒体，附件可从消息页单独创建下载任务。
- WebSocket `/api/v1/ws` 使用管理员 Cookie 和 Origin 校验。消息事件按频道订阅，前端重连后重新通过 REST 获取状态。事件通知不会作为持久数据来源。

## 安全与部署

管理员登录使用 Argon2 密码哈希、12 小时 HttpOnly SameSite Cookie、CSRF 请求头和登录/验证码/导出频率限制。敏感操作不记录验证码、密码、API Hash 或消息正文。Windows 上会尝试用 `icacls` 将 Telethon session 文件权限限制为当前用户；其他系统使用 `0600`。session 失效时可在设置页重新授权。

媒体与导出目录只能设置为 `DATA_ROOT` 下的安全相对路径。修改目录不会使已下载文件失联，因为数据库保存的是相对于 `DATA_ROOT` 的路径。删除本地数据要求输入完整 Chat ID；移出管理列表保留本地数据。

默认 CORS 允许 `http://127.0.0.1:5173`。如经 HTTPS 反向代理供其他设备访问，须设置具体的 `CORS_ORIGINS`、`COOKIE_SECURE=true`，并将后端置于可信代理之后；不要直接将管理端口暴露到公网。平台设计为单进程，**不要启动多个 Uvicorn worker**，否则会产生多个 Telegram 客户端与任务执行器。

## 测试

```powershell
cd backend
& .\.venv\Scripts\python.exe -m pytest -q
& .\.venv\Scripts\python.exe -m compileall -q app
cd ..\frontend
npm run typecheck
npm run build
npm run lint
npm test
```

自动化测试使用临时 SQLite 和模拟 Telegram 客户端，覆盖认证、频道离线读取、同步游标、去重、编辑、FloodWait、导出格式与文件路径。真实账号仍需按以下步骤人工验收：填入 Telegram 凭证，完成验证码及可能的两步验证；发现并添加一个有权访问的频道；启动历史同步并观察任务；启用监听后确认新消息与编辑；断网重启后执行校准；按需下载附件并检查 JSON/JSONL/ZIP。

## 备份、恢复和限制

备份前停止后端，然后复制整个 `backend/data`（或自定义 `DATA_ROOT`），包括 SQLite、session、媒体和导出文件。恢复时停止后端，将备份放回同一路径，检查文件权限，再启动后端；Alembic 会升级旧数据库。不要把备份或 session 提交到 Git。

当前实现不会把 Telegram 端已删除的消息自动从本地档案删除；历史校准用于补漏和更新编辑内容。完整端到端 Telegram 登录、实时事件与下载需要实际凭证及可访问频道才能验证。单进程 SQLite 架构适合本项目预期的小规模频道，不支持多个后端实例共享同一 session 或任务队列。
