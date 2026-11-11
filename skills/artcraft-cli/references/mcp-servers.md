# MCP 服务器参考

> 快照日期：2026-11-11。来源：上游 `docs/mcp.md`（lightcraft、photocraft）与 `docs/agents.md`（filmcraft）的 main 分支；本次拉取的 URL 与 SHA256 见 `upstream-sources.md`。
> 三个应用的 MCP 服务器设计一致：**共享核心工具 + 应用专属工具 + resources**，会一个就会其余。
> 上游 photocraft 的 `docs/mcp.md` 已改写为「MCP conventions」，重点从工具清单转到 root 授权、作业与取消语义；本页已同步这些变化。

## 接入方式

```sh
# LightCraft
claude mcp add lightcraft     -- lightcraft-cli mcp ~/Pictures/shoot        # headless，启动时导入照片
claude mcp add lightcraft-app -- lightcraft-cli mcp --connect 127.0.0.1:7980  # 驱动运行中的应用

# FilmCraft（bridge 需要桌面端与客户端共享 FILMCRAFT_CONTROL_TOKEN）
export FILMCRAFT_CONTROL_TOKEN="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
claude mcp add filmcraft-headless -- filmcraft-cli mcp --demo                # headless（--project p.fcproj 打开工程）
claude mcp add filmcraft          -- filmcraft-cli mcp --bridge 127.0.0.1:9876

# PhotoCraft headless：读写 root 都要显式给（read root 可重复，write root 只能一个）
claude mcp add photocraft -- photocraft-cli mcp \
  --automation-read-root /work/project --automation-write-root /work/project
# PhotoCraft bridge：root 配在桌面应用上，CLI 侧传 root 是用法错误
claude mcp add photocraft-app -- photocraft-cli mcp --bridge 127.0.0.1:7878 --control-token-file /path/token
```

其他客户端（Claude Desktop、Cursor、Codex…）用标准 `mcpServers` JSON：

```json
{"mcpServers": {"photocraft": {"command": "/abs/path/photocraft-cli", "args": ["mcp", "--automation-read-root", "/work/project"]}}}
```

- `command` 必须是**绝对路径**，不要写 `~` 或 `$HOME`（客户端不做 shell 展开）。
- 桥接前必须先启动桌面应用并开控制通道；PhotoCraft 桥接还需 token 文件与应用端一致。
- 用绝对路径写 `--automation-read-root` / `--automation-write-root`：相对路径按客户端启动目录解析。
- PhotoCraft 支持**重复** `--automation-read-root`（按启动顺序查找相对路径）；重复 `--automation-write-root` 是用法错误（exit 2）。所有 root 必须是已存在的目录，否则启动失败而不是被忽略。读写授权互相独立，write root 不授予读。
- bridge 模式的 root 一律配在桌面应用进程；`photocraft-cli mcp --bridge` 传 root flag 会被拒。`--control-token` / `--control-token-file` 需要 `--bridge`（或 `PHOTOCRAFT_CONTROL_PORT`）且两者互斥；也可用 `PHOTOCRAFT_CONTROL_TOKEN[_FILE]`。
- MCP / `serve` 的启动选项（除 `--help`）都只接受一个非空值、不可重复。缺值、多余位置参数、模式不匹配的选项在 server 启动前写到 stderr 并以 exit 2 退出，stdout 留给协议消息。

## 共享核心工具（三家都有）

| 工具 | 参数 | 用途 |
|---|---|---|
| `command_list` | `filter?`, `enabled_only?` | 命令目录：id、label、menu、shortcut、参数文档、当前启用态 |
| `command_run` | `id`, `params?`, `wait?` | 运行任意命令（编辑可 undo） |
| `command_batch` | `steps: [{id, params?}]`, `stop_on_error?` | 顺序执行多个命令 → `{completed, failed, results}` |
| `doc_inspect` | — | 文档/库状态一 call 搞定（LightCraft=库状态+目录计数；FilmCraft=项目树+活动序列；PhotoCraft=图层树/历史/选择） |
| `render_preview` | `id?` / `index?`, `max_side?`, `format?` | 返回图片内容（不改选择、不存文件） |

跨应用约定：

- 每个工具带 `title` 与四个 MCP hints（`readOnlyHint`/`destructiveHint`/`idempotentHint`/`openWorldHint`），客户端可对只读工具免确认、编辑类先询问。
- **严格参数**：未知参数返回 JSON-RPC `-32602` 并列出合法参数（如 `unknown argument "filtr" for command_list; expected: enabled_only, filter`），不静默忽略。
- 错误：失败命令是 `isError` 结果带引擎消息；非 JSON 行 `-32700`（id null）后继续服务；命令 panic 报 `internal error: …`，会话保持可用。
- `command_batch` **不是事务**：前面的成功步骤不会回滚，失败后用 `doc_inspect` 查实际状态。
- 每个工具生成一个 `cmd_*` 一对一工具（"one tool per command"），参数仍是引擎自定义的自由格式。LightCraft 可用 `--compact` 只列 helper 工具。
- `command_list` 返回**裸 JSON 数组**，不是 `{"commands":[...]}`。每项含 `id` / `label` / `menu` / `shortcut` / `params` / `enabled` / `disabledReason` / `needsDocument`，部分还有 `keywords`；`params` 是给人看的参数文档字符串，**不是 JSON schema**。桌面通道的 `engine.commands` 不过滤，过滤由 MCP 侧完成。
- `command_batch` 的 `stop_on_error` 默认为 `true`；失败后 `completed` / `results` 报已成功的步骤，不回滚。
- `render_preview` 三家参数不同：LightCraft 用 `id?` / `max_side?` / `format?`，PhotoCraft 用 `index` / `max_side`（默认 1024、上限 2048，只回有界 PNG），FilmCraft 与 `render_frame` 等价。
- MCP `2026-07-28` 客户端在 list/read 结果里会拿到 `ttlMs` / `cacheScope` 提示；resources 读取不缓存，但工具/资源目录缓存 10 分钟。四个 hints 只是客户端提示，**不是文件访问沙箱**。

## LightCraft MCP

- **Helper 工具**：`list_commands`、`run_command {command, params?}`、`import {paths, album?, mode?, destination?, organize?, rename?}`（`mode: "copy"|"move"`，`organize` 支持 `date` / `month` / `flat` / 模板如 `{date:%Y}/{date:%B}`，`rename` 模板用 `photo.renameTokens` 查可用标签）、`query_photos {filter?, sort?, offset?, limit?}`、`select_photos {ids, active?, mode?}`（未知 id 报错且不改选择）、`list_controls {section?}`、`get_develop {id?}`、`set_develop {id?, values?, settings?, label?}`、`apply_preset {preset, amount?, ids?}`、`crop {id?, rect?, angle?, reset?}`、`render_photo {id?, size?, format?, path?}`（默认长边 1024，PNG/JPEG）、`export {path|dir, id?|ids?, format?, longEdge?, ...}`。
- **Connect 模式专属**：`screenshot {maxSize?, format?, path?}`（等挂起渲染完成后抓窗）、`inspect_ui`、`set_ui {state}`、`list_widgets {filter?}` / `click {widget|x,y,...}`、`press_key {key,...}` / `type_text {text}`、`clipboard {action, text?}`、`pointer_gesture {events}`。
- **资源**（快照，无 subscribe）：`lightcraft://library`、`lightcraft://photos`、`lightcraft://photo/active`、`lightcraft://develop/active`、`lightcraft://controls`。
- headless 模式拥有独立引擎会话；**要反馈桌面应用里的编辑必须用 `--connect`**。`--library DIR` 打开持久图库（同一图库一次只能被一个程序占用，被占用时改用 connect 模式），`--compact` 跳过 `cmd_*` 工具。
- **结果未知不重发**：请求已发出但回复未到时断连，工具报 "the outcome is unknown" 且不重发（避免 undo 执行两次）；只有确认请求未送达才重发一次。回复上限 64 MiB，畸形/超大/id 不匹配的回复同样断连并报告未知结果。
- **新增能力（上游 2026-11-11）**：slideshow 命令集（`cmd_slideshow_layout` / `preview` / `playback` / `overlays` / `titles` / `templates_*` / `export`，导出为后台任务，用 `cmd_activity_list` / `cmd_activity_cancel` 管理）；`cmd_library_recheckPreviewOnly` 让 headless 会话重新检查"仅预览"的 RAW；`app.export` / `export` 支持 `addToPhotos: true` + `photosAlbum`（macOS 写入 Apple Photos）。
- **导出格式扩展**：`export` 支持 `.png/.jpg/.tif/.webp/.avif/.jxl`，以及 `format:"original"`（复制原文件 + XMP 边车）与 `format:"dng"`；尺寸策略新增 `fit:"widthHeight"`、`dontEnlarge`（默认 true），不带尺寸参数时默认 3000px 长边。

## FilmCraft MCP

- 模式：headless（`--demo` / `--project p.fcproj`，进程内引擎，无窗口）与 bridge（`--bridge 127.0.0.1:9876`，需桌面端开着且共享 `FILMCRAFT_CONTROL_TOKEN`）。
- headless 可加 `--data-dir DIR`（用户预设）；**没有文件夹限制 flag**（无 `--automation-read-root`），服务器可读写用户权限内的任何位置——评估风险后使用。
- 工具：核心五件 + `project_inspect`（bins/items/ids/时长）、`sequence_inspect`（轨道、clips 的 start/end 与 sourceIn/sourceOut（ticks/frames）、speed、reverse、gainDb、效果、转场、标记、播放头、选择）、`media_import {paths, bin?, image_sequence?}`、`render_frame {seconds}`（headless 渲染；bridge 截 Program 监视器；只读）、`ui_inspect`/`ui_elements`/`ui_click`/`ui_drag`/`ui_key`/`ui_type`/`ui_screenshot`/`ui_control`（**仅 bridge**，`ui_control` 可直接调任意控制通道方法）。
- 典型循环：`project_inspect`/`sequence_inspect` → 拿 id → `command_run` → `render_frame`/`ui_screenshot` → 看结果 → 不对就 `edit.undo`。
- 资源：`filmcraft://document`、`filmcraft://commands`（application/json）。
- `render_preview` 与 `render_frame` 等价；`ui_screenshot` 可带 `panel` 只截一个面板；`doc_inspect` 一次给 `project_inspect` + `sequence_inspect`。
- **效果参数回复**：`effects.setParam` 回 `{"keyframes":0,"param":…,"value":…}` 时 `keyframes:0` 是**成功的静态编辑**，不是失败；`effects.addKeyframe` 是开关（回 `added:true/false`），`effects.deleteKeyframe` 回 `removed:true/false`。
- **长导出**：`file.exportMedia` 带 `wait:true` 阻塞到写完，作为后台作业运行，期间 `ping` / `doc_inspect` / `jobs.list` 仍可响应；`_meta.progressToken` 触发进度通知，`notifications/cancelled` 在下一批帧停止并删除本次输出。不带 `wait` 立即回 `{job, path, poll:"jobs.list", cancel:"jobs.cancel"}`。作业与 `export.queue.list` 的编码项带 `etaSeconds`（最近 15s 速度估算）与 `offlineMedia`；`file.exportMedia` / `export.quick` / `export.resolve` / `export.queue.add` 还返回 `warnings`（如 In/Out 只覆盖一帧且设有标记时建议 `range:"entire"`，不影响退出码）。图像序列自动编号（`a.png` → `a000.png`…），结果带 `path` / `lastPath` / `basePath`。

## PhotoCraft MCP

- Headless（`photocraft-cli mcp`）：进程内引擎会话，无窗口；文件访问必须显式给 root flag（env 形式不授予 headless CLI 访问）。`--gpu` / `PHOTOCRAFT_GPU=1` 可开 GPU 渲染并自动回退 CPU。`--bridge 7878` 是 `127.0.0.1:7878` 的简写；不给 `--bridge` 时 `PHOTOCRAFT_CONTROL_PORT` 决定 bridge 端口，两者都没有就跑 headless。
- **root 授权语义**：多个 read root 按启动顺序查找相对路径，headless 取第一个存在的普通文件；目录、权限、路径逃逸、解码错误会终止请求而不是回退到下一个 root。只有一个 write root，重复即 exit 2。目录型 `.pcraft` 文档与不共享 write root 能力的读取没有隐式保存目标，需显式 `doc_save {path}` 落在 write root 下。
- Bridge（`--bridge 127.0.0.1:7878 --control-token-file <path>`）：所有工具转发给运行中的应用；保持一条已认证 TCP 连接，空闲过久自动重连（纯读工具自动重试一次；**编辑不自动重发**——传输失败时报告"可能已完成"，重试编辑前先查文档）。仅接受字面量 loopback。
- **bridge 认证升级（2026-11-11）**：官方 bridge 现在走 `auth.challenge` 挑战握手，token 从不上线；脚本侧旧的 `auth {token}` 首帧仍被接受。老版本应用不支持挑战握手会被 bridge 拒绝，CLI 与应用要一起升级。握手细节见 `control-protocols.md`。
- **工具细节**：`doc_inspect` 每个图层（含组与嵌套）报 `hasMask` / `hasVectorMask` / `vectorMaskEnabled`；`render_preview` 用 `index` / `max_side`；限定导出工具是 `doc_export_layers` / `doc_export_data_sets`（都拒绝覆盖已有文件）。智能对象可用 `layer.smartObjects.editContents` / `convertToLayers` / `saveContents`，内存内操作不需要 root。
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

上游 2026-11-11 同步的补充：

- job-capable 命令（滤镜、Content-Aware Fill/Scale、Photomerge 等）默认后台化，可在 `jobs_list` 看到；期间其他调用仍被响应。取消后**文档保持不变**，已完成的作业不受影响。
- `command_batch` 的取消只停止后续步骤，已成功的步骤不回滚；`file.export.renderVideo` 作为 batch 步骤时**不上报进度、不可取消**。
- bridge 侧 waited `command_run` 由 `engine.execute {wait:false}` + 轮询 `jobs.list` 实现，可跨过 55s 客户端超时；非作业命令、UI 命令、启动回复丢失仍会在超时失败。
- LightCraft 的 connect 模式与 `command_batch` 内的导出仍是同步的，不提供 MCP 进度/取消；要进度就用直接 headless 导出调用。
