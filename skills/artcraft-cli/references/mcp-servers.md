# MCP 服务器参考

> 快照日期：2026-11-04。来源：上游仓库 `docs/mcp.md`（lightcraft、photocraft）与 `docs/agents.md`（filmcraft）。
> 三个应用的 MCP 服务器设计一致：**共享核心工具 + 应用专属工具 + resources**，会一个就会其余。

## 接入方式

```sh
# LightCraft
claude mcp add lightcraft     -- lightcraft-cli mcp ~/Pictures/shoot        # headless，启动时导入照片
claude mcp add lightcraft-app -- lightcraft-cli mcp --connect 127.0.0.1:7980  # 驱动运行中的应用

# FilmCraft（bridge 需要桌面端与客户端共享 FILMCRAFT_CONTROL_TOKEN）
export FILMCRAFT_CONTROL_TOKEN="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
claude mcp add filmcraft-headless -- filmcraft-cli mcp --demo                # headless（--project p.fcproj 打开工程）
claude mcp add filmcraft          -- filmcraft-cli mcp --bridge 127.0.0.1:9876

# PhotoCraft
claude mcp add photocraft -- photocraft-cli mcp --bridge 127.0.0.1:7878 --control-token-file /path/token
```

其他客户端（Claude Desktop、Cursor、Codex…）用标准 `mcpServers` JSON：

```json
{"mcpServers": {"photocraft": {"command": "/abs/path/photocraft-cli", "args": ["mcp", "--automation-read-root", "/work/project"]}}}
```

- `command` 必须是**绝对路径**，不要写 `~` 或 `$HOME`（客户端不做 shell 展开）。
- 桥接前必须先启动桌面应用并开控制通道；PhotoCraft 桥接还需 token 文件与应用端一致。
- 用绝对路径写 `--automation-read-root` / `--automation-write-root`：相对路径按客户端启动目录解析。

## 共享核心工具（三家都有）

| 工具 | 参数 | 用途 |
|---|---|---|
| `command_list` | `filter?`, `enabled_only?` | 命令目录：id、label、menu、shortcut、参数文档、当前启用态 |
| `command_run` | `id`, `params?`, `wait?` | 运行任意命令（编辑可 undo） |
| `command_batch` | `steps: [{id, params?}]`, `stop_on_error?` | 顺序执行多个命令 → `{completed, failed, results}` |
| `doc_inspect` | — | 文档/库状态一 call 搞定（LightCraft=库状态+目录计数；FilmCraft=项目树+活动序列；PhotoCraft=图层树/历史/选择） |
| `render_preview` | `id?`, `max_side?`, `format?` | 返回图片内容（不改选择、不存文件） |

跨应用约定：

- 每个工具带 `title` 与四个 MCP hints（`readOnlyHint`/`destructiveHint`/`idempotentHint`/`openWorldHint`），客户端可对只读工具免确认、编辑类先询问。
- **严格参数**：未知参数返回 JSON-RPC `-32602` 并列出合法参数（如 `unknown argument "filtr" for command_list; expected: enabled_only, filter`），不静默忽略。
- 错误：失败命令是 `isError` 结果带引擎消息；非 JSON 行 `-32700`（id null）后继续服务；命令 panic 报 `internal error: …`，会话保持可用。
- `command_batch` **不是事务**：前面的成功步骤不会回滚，失败后用 `doc_inspect` 查实际状态。
- 每个工具生成一个 `cmd_*` 一对一工具（"one tool per command"），参数仍是引擎自定义的自由格式。

## LightCraft MCP

- **Helper 工具**：`list_commands`、`run_command {command, params?}`、`import {paths, album?, mode?, destination?, organize?, rename?}`（`mode: "copy"|"move"`，`organize` 支持 `date` / `month` / `flat` / 模板如 `{date:%Y}/{date:%B}`，`rename` 模板用 `photo.renameTokens` 查可用标签）、`query_photos {filter?, sort?, offset?, limit?}`、`select_photos {ids, active?, mode?}`（未知 id 报错且不改选择）、`list_controls {section?}`、`get_develop {id?}`、`set_develop {id?, values?, settings?, label?}`、`apply_preset {preset, amount?, ids?}`、`crop {id?, rect?, angle?, reset?}`、`render_photo {id?, size?, format?, path?}`（默认长边 1024，PNG/JPEG）、`export {path|dir, id?|ids?, format?, longEdge?, ...}`。
- **Connect 模式专属**：`screenshot {maxSize?, format?, path?}`（等挂起渲染完成后抓窗）、`inspect_ui`、`set_ui {state}`、`list_widgets {filter?}` / `click {widget|x,y,...}`、`press_key {key,...}` / `type_text {text}`、`clipboard {action, text?}`、`pointer_gesture {events}`。
- **资源**（快照，无 subscribe）：`lightcraft://library`、`lightcraft://photos`、`lightcraft://photo/active`、`lightcraft://develop/active`、`lightcraft://controls`。
- headless 模式拥有独立引擎会话；**要反馈桌面应用里的编辑必须用 `--connect`**。

## FilmCraft MCP

- 模式：headless（`--demo` / `--project p.fcproj`，进程内引擎，无窗口）与 bridge（`--bridge 127.0.0.1:9876`，需桌面端开着且共享 `FILMCRAFT_CONTROL_TOKEN`）。
- headless 可加 `--data-dir DIR`（用户预设）；**没有文件夹限制 flag**（无 `--automation-read-root`），服务器可读写用户权限内的任何位置——评估风险后使用。
- 工具：核心五件 + `project_inspect`（bins/items/ids/时长）、`sequence_inspect`（轨道、clips 的 start/end 与 sourceIn/sourceOut（ticks/frames）、speed、reverse、gainDb、效果、转场、标记、播放头、选择）、`media_import {paths, bin?, image_sequence?}`、`render_frame {seconds}`（headless 渲染；bridge 截 Program 监视器；只读）、`ui_inspect`/`ui_elements`/`ui_click`/`ui_drag`/`ui_key`/`ui_type`/`ui_screenshot`/`ui_control`（**仅 bridge**，`ui_control` 可直接调任意控制通道方法）。
- 典型循环：`project_inspect`/`sequence_inspect` → 拿 id → `command_run` → `render_frame`/`ui_screenshot` → 看结果 → 不对就 `edit.undo`。
- 资源：`filmcraft://document`、`filmcraft://commands`（application/json）。
- 长导出：`file.exportMedia` 带 `wait:true` 阻塞到写完，支持 MCP progress 与 cancellation；不带 `wait` 立即回 `{job, path}`，轮询 `jobs.list`、`jobs.cancel` 停止。作业带 `etaSeconds`、`offlineMedia`。

## PhotoCraft MCP

- Headless（`photocraft-cli mcp`）：进程内引擎会话，无窗口；文件访问需显式 root flag（env 形式不被 CLI 模式支持）。
- Bridge（`--bridge 127.0.0.1:7878 --control-token-file <path>`）：所有工具转发给运行中的应用；保持一条已认证 TCP 连接，空闲过久自动重连（纯读工具自动重试一次；**编辑不自动重发**——传输失败时报告"可能已完成"，重试编辑前先查文档）。仅接受 loopback。
- 工具→控制方法映射：

| MCP 工具 | 控制方法 |
|---|---|
| `command_run {id, params, wait?}` | `engine.execute {command: id, params, wait}` |
| `command_list {filter?, enabled_only?}` | `engine.commands` |
| `doc_new {…}` / `doc_inspect` | `engine.execute file.new` / `document.inspect` |
| `doc_open {path}` / `doc_save` / `doc_export` | `app.open` / `app.save` |
| `doc_place {path}` / `doc_export_layers {dir}` / `doc_import_data_sets {path}` | `file.placeEmbedded` / `file.export.layersToFiles` / `file.import.variableDataSets` |
| `doc_render_preview {max_side?}` | `ui.screenshot`（PNG 图片内容） |
| `ui_inspect` / `session_list` | `ui.inspect` |
| `ui_screenshot {max_side?}` / `ui_pointer {events,…}` / `ui_menu_invoke {id}` / `ui_set {fields}` | `ui.screenshot` / `ui.pointer` / `ui.menu.invoke` / `ui.set` |
| `jobs_list` / `jobs_cancel {job?}` | `jobs.list` / `jobs.cancel` |
| `control_call {method, params}` | 任意方法直通 |

- `doc_select`/`doc_close` 仅 headless；`ui_*` 与 `control_call` 仅 bridge（headless 下返回说明性工具错误）。
- 资源：`photocraft://document`、`photocraft://commands`（实时 JSON，不缓存）。
- 安全：token=bearer；root fail-closed；loopback only。`doc_save`/`doc_export` 只能覆盖 PhotoCraft 自己会写的图片/文档格式，其余文件（`src/main.rs`、`.env`）一律拒绝且不触碰。

## 进度与取消（MCP 2026-07-28）

带 `_meta.progressToken`（字符串或数字）的 `command_run` 会收到 `notifications/progress`：严格递增、限速每秒至多 10 次（完成时不限）、带 `total`。没有 token 就没有进度通知。

```json
{"jsonrpc":"2.0","id":20,"method":"tools/call","params":{"name":"command_run","arguments":{"id":"file.export.renderVideo","params":{"dir":"frames","format":"png"}},"_meta":{"progressToken":"export-20"}}}
{"jsonrpc":"2.0","method":"notifications/cancelled","params":{"requestId":20}}
```

取消会在帧边界停止（当前帧可能先做完）。只删除本次作业实际创建的文件，目标目录和其他文件保留。
