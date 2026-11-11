# 三应用差异速查（app-matrix）

> 快照日期：2026-11-11，基于上游仓库 `storytold/{lightcraft,filmcraft,photocraft}` 的 `main` 分支文档 + 本机实测。
> **这份表会过期**：认证与 flag 都可能随版本改。动手前跑 `scripts/craft_env.py` 看本机实际状态；发现对不上时以运行中实例的 `methods` / `engine.commands` 为准，并更新本表。

## 一览

| | **LightCraft** | **FilmCraft** | **PhotoCraft** |
|---|---|---|---|
| 定位 | RAW 修图 / 照片管理（对标 Lightroom） | 非线性视频剪辑（对标 Premiere） | 位图编辑（对标 Photoshop） |
| Bundle ID | `ai.storyteller.lightcraft` | `ai.storyteller.filmcraft` | `ai.storyteller.photocraft` |
| 启动 flag | `--control PORT` | `--control <port>` | `--control <port>` |
| 端口环境变量 | `LIGHTCRAFT_CONTROL_PORT` | `FILMCRAFT_CONTROL_PORT` | `PHOTOCRAFT_CONTROL_PORT` |
| **通道认证** | **无** | **顶层 `token` 字段**（每个请求都带）——上游文档强制，**0.9.0 实测不强制** | **脚本：`auth` 首帧（token）；官方 bridge：`auth.challenge` 挑战握手，token 不上线** |
| 凭据来源 | — | `FILMCRAFT_CONTROL_TOKEN` 环境变量 | `--control-token-file` / `PHOTOCRAFT_CONTROL_TOKEN[_FILE]` |
| 缺凭据的后果 | — | 新版：应用不监听端口；**0.9.0 实测：照常放行**（无 token、错 token 都返回正常结果） | 连接可建，但请求被回 `authentication required` |
| 文件沙箱 | 无（用 `LIGHTCRAFT_CONFIG_DIR` 隔离配置） | 无 | **automation read/write root，fail closed** |
| 隔离配置 | `LIGHTCRAFT_CONFIG_DIR` | `FILMCRAFT_DATA_DIR` | `--automation-read-root` / `--automation-write-root` |
| 领域状态方法 | `library.state` `photo.inspect` `develop.get` `develop.controls` | `sequence.inspect` `project.inspect` | `document.inspect` |
| UI 状态方法 | `ui.inspect` | `ui.inspect` `ui.docking` | `ui.inspect` |
| 截图 | `ui.screenshot {path, headless?}` | `ui.screenshot {path, panel?}` | `ui.screenshot {path?, focus?}`（无 path 回 base64） |
| 输入注入 | `ui.clickWidget` `ui.dragWidget` `ui.pointer` `ui.key` | `ui.click` `ui.drag` `ui.key` `ui.type` `ui.timeline.hit` | `ui.pointer` `ui.click` `ui.key` `ui.type` |
| CLI 名 | `lightcraft-cli` | `filmcraft-cli` | `photocraft-cli` |
| CLI 独有能力 | `render`（单文件快导）、`snapshot`（无头整窗截图）、`controls`、`calibrate` | `commands`/`describe`（按关键词查命令）、`import`/`export`、`--save`、`--list-presets` | `run --cmd` 链、`batch --actions`、`commands --filter` |
| MCP 模式 | headless（带图库目录）/ `--connect` | headless（`--demo`/`--project`）/ `--bridge` | headless / `--bridge`（需 token） |
| MCP 特色工具 | `import` `query_photos` `select_photos` `list_controls` `set_develop` `apply_preset` `crop` `render_photo` `export` | `project_inspect` `sequence_inspect` `media_import` `render_frame` `ui_*`（仅 bridge） | `doc_new` `doc_open` `doc_save` `doc_export` `doc_place` `jobs_list` `control_call` |
| MCP 资源 | `lightcraft://library` `://photos` `://photo/active` `://develop/active` `://controls` | `filmcraft://document` `://commands` | `photocraft://document` `://commands` |
| 特色能力 | loupe 渲染状态、develop 滑块元数据、联系表导出 | 时间轴 ticks、`--control-input-only`、单面板截图、导出队列 | 对话框驱动、后台作业、智能对象、矢量蒙版 |
| `--help` | 完整可用 | 完整可用 | **没有**（会把 `--help` 当文件路径打开并启动 GUI） |

## 认证速查（四态）

```sh
# LightCraft：什么都不用给
python3 scripts/craft_ctl.py --app light --port 7980 engine.commands

# FilmCraft：token 放环境变量，客户端自动带上
export FILMCRAFT_CONTROL_TOKEN="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
python3 scripts/craft_ctl.py --app film --port 9876 engine.commands

# PhotoCraft：token 文件
python3 scripts/craft_ctl.py --app photo --port 7878 \
        --token-file ~/.photocraft/control.token engine.commands
```

若通道行为与上表不符，先查 `craft_env.py` 的 `auth` 字段，再用 `--auth-mode none|frame|field` 手动指定。第四态 `challenge` 由官方 `photocraft-cli mcp --bridge` 内部完成，`craft_ctl.py` 不实现也不需要提供——脚本继续用 `frame`。

## 命令注册表规模

命令数量随版本增长很快（PhotoCraft 0.8.x 时约 900 条）。**不要把整个注册表打进上下文**——用 `craft_ctl.py --discover --filter <关键词>` 拿精简表，或直接查某个命令的 `params` 文档。

## 跨应用共同约定

- 共享 MCP 核心工具五个：`command_list` `command_run` `command_batch` `doc_inspect` `render_preview`（`render_preview` 的参数三家不完全一致，见 `mcp-servers.md`）。
- `command_list` / `engine.commands` 回**裸 JSON 数组**，元素带 `enabled` / `disabledReason` / `needsDocument`；`params` 是文档字符串不是 schema。
- MCP `2026-07-28` 客户端会拿到 `ttlMs` / `cacheScope` 提示；hints 不是文件访问沙箱。
- 未知参数返回 JSON-RPC `-32602` 并列出合法参数，不静默忽略。
- 每个 MCP 工具带 title 与四个 hints（`readOnlyHint` / `destructiveHint` / `idempotentHint` / `openWorldHint`），客户端可据此决定是否弹确认框。
- 命令失败是 `isError` 结果（带引擎消息），会话保持可用；panic 报 `internal error: …`。
