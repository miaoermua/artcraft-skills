# 控制通道协议参考

> 快照日期：2026-11-11。来源：上游仓库 `storytold/{lightcraft,filmcraft,photocraft}` 的 `docs/control-protocol.md`（main 分支）+ 本机实测。
> 协议随版本演进。**方法名、参数、认证方式以运行中实例为准**：`engine.commands`（命令）、`methods`（方法）、上游仓库最新文档。刷新方式见 `upstream-sources.md`。

## 通用机制（三家一致的部分）

- **传输**：TCP，仅监听 `127.0.0.1`（loopback）。一行一个 JSON 请求，一行一个 JSON 回复，按序一一对应。
- **请求**：`{"id": <任意>, "method": "<字符串>", "params": <对象，可选>}`。
- **回复**：`{"id": <同请求>, "ok": true, "result": ...}` 或 `{"id": ..., "ok": false, "error": "..."}`。
- **严格解析**：每行必须是含字符串 `method` 的 JSON 对象。**非 JSON、数组、数字、缺 `method`、非法 UTF-8、超 4 MiB 的行会收到一条错误回复，然后连接被直接关闭**——之后同一连接上发的任何东西都不会执行。这是为了挡住网页跨源 `fetch` 把 HTTP 请求行走私成命令。
- **连接上限**：同时最多 16 个连接，超出的连接收到一行错误后被关闭。
- **调度**：请求在 UI 线程帧间执行。服务端回复上限 60s；socket 读写另有约 2 分钟的无进展超时。
- **超时语义**：应用 5s 不绘制帧且请求未启动 → 放弃该请求（可安全重发）；**已启动的命令超时后可能仍在运行**，重试前先查状态。FilmCraft 会区分"部分请求超时未派发"与"已派发未回"。
- **无推送**：只有请求-回复，没有事件流。要知道 GUI 侧发生了什么，轮询 inspect 方法对比快照。
- **快照语义**：每次请求都是独立快照。换了对象（照片 / 序列 / 文档）必须重读状态，不能拿缓存的 id 推断。
- **空闲断连**：PhotoCraft 应用侧 30s 空闲断连；bridge 客户端会自动重连（纯读工具重试一次，**编辑不自动重发**）。
- **命令注册表形状**：`engine.commands`（通道与 `serve`）、引擎命令 `command.list`、MCP `command_list` 都回**裸 JSON 数组**（`result:[…]`），没有 `{"commands":[…]}` 包装。每项含 `id` / `label` / `menu` / `shortcut` / `params`（人读文档字符串，非 schema）/ `enabled` / `disabledReason` / `needsDocument`，部分带 `keywords`。桌面通道的 `engine.commands` 不接受 filter，过滤由 MCP 侧完成。
- **后台作业**：长命令（`filter.*`、Content-Aware、Photomerge、文件打开/置入、交互式保存等）在桌面端跑成后台作业。`engine.execute` / `ui.menu.invoke` / `ui.dialog.confirm` / `app.save` 默认等结果；传 `"wait": false` 立刻拿 `{job, pending:true}`，再轮询 `jobs.list`（`state`: running/done/failed/cancelled、`progress` 0–1、结果或错误）并用 `jobs.cancel {job}` 停止。作业期间编辑同一文档的命令会失败；`ui.inspect` 的 `jobs` 字段列出进行中的作业。已开始替换文件的保存不可取消。
- **bridge 时限与地址**：客户端调用超时 55s，严格低于服务端 60s 回复上限。waited `command_run` 的引擎命令不受此限——bridge 只发一次 `engine.execute {wait:false}` 再轮询 `jobs.list`。bridge 只接受字面量 `127.0.0.1:<port>` / `[::1]:<port>`；`localhost` 不做 DNS 解析，直接当 `127.0.0.1`。

## 认证四态（2026-11-11 上游同步）

| 模式 | 适用 | 机制 | 缺凭据时 |
|---|---|---|---|
| `none` | LightCraft | 无 | 照常工作——**任何本机进程都能驱动，用完即关** |
| `field` | FilmCraft | 每个请求顶层带 `"token": "<64 hex>"` | **取决于版本**：上游 `main` 文档要求 token、缺失时不监听端口；**0.9.0 实测不强制**，无 token 甚至错 token 都照常返回结果 |
| `frame` | PhotoCraft（脚本 / 本 skill 的 `craft_ctl.py`） | 连接首帧 `{"id":"auth","method":"auth","params":{"token":"<64 hex>"}}` | 连接建得上，但请求被回 `{"error":"authentication required","ok":false}` |
| `challenge` | PhotoCraft 官方 bridge（`photocraft-cli mcp --bridge`） | `auth.challenge` → 校验 `serverProof` → `auth {proof}`，token 从不上线 | 监听方无法证明持有 token 时报 "the control token was not sent"；老版本应用直接被拒 |

> **本 skill 的 `craft_ctl.py` 只实现 `none` / `frame` / `field`**（对应 `--auth-mode` 的取值），挑战握手由官方 bridge 内部完成，脚本侧不用也不该自己实现。上游仍接受 `frame` 的 token 首帧，所以现有脚本继续可用。

挑战握手形状（HMAC-SHA256，密钥为 token 的 64 位小写 hex 的 ASCII，消息为 `<label>\n<clientNonce>\n<serverNonce>`，label 分别是 `photocraft-control-v1 server` / `photocraft-control-v1 client`）：

```json
{"id":1,"method":"auth.challenge","params":{"clientNonce":"<64 hex>"}}
{"id":1,"ok":true,"result":{"serverNonce":"<64 hex>","serverProof":"<64 hex>"}}
{"id":2,"method":"auth","params":{"proof":"<64 hex>"}}
{"id":2,"ok":true,"result":{"authenticated":true}}
```

客户端先校验 `serverProof`，不匹配就断开、不发 `auth`；挑战之后同一连接只接受 `auth {proof}`。token 认证会把 token 发给占着端口的进程，只在确认监听方就是应用时使用；官方 bridge 不会回退到它。**每连接只认证一次**，之后再发 `auth` / `auth.challenge` 会得到 `already authenticated`，但连接继续服务。

> **版本漂移警告（2026-11-04 实测）**：上游 `main` 分支文档描述 FilmCraft 强制 token，但已发布的 **0.9.0 二进制并不强制**——无 token 字段、错误 token 都正常返回 `engine.commands` 结果。因此**不要根据文档假设服务端会替你拦**，客户端要自己带上凭据（`craft_ctl.py --app film` 会自动带），也不要因为"文档说缺 token 连不上"就去排查错方向。

FilmCraft 的 token 通过**继承的环境变量**传给客户端：

```sh
export FILMCRAFT_CONTROL_TOKEN="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
filmcraft --control 9876 &
filmcraft-cli mcp --bridge 127.0.0.1:9876
```

凭据不对时：FilmCraft 回一条错误并**在派发任何请求前关闭连接**；PhotoCraft 的 `frame` 模式回 `authentication required` 并关闭连接，同一连接重复认证回 `already authenticated`。

安全：bearer token 即全部非文件控制面（UI 输入、命令执行、应用控制）。**不提交、不记录、不在共享系统上命令行直传**（进程列表可见）。协议不加密、仅 loopback——不要 tunnel 到不可信主机。loopback 只挡远程，不挡同机其他进程。

## LightCraft（RAW 修图）

**启动**：`lightcraft --control 7980` 或 `LIGHTCRAFT_CONTROL_PORT=7980`。
**隔离自动化**：`LIGHTCRAFT_CONFIG_DIR=<新目录>` 隔离全部配置/日志/GPU 标记；配 `--library <独立 scratch 库>`（配置覆盖不改变默认库位置 `~/Pictures/LightCraft Library`）；测试持久化时不要用 `--memory` / `LIGHTCRAFT_NO_PREFS`。

### 方法表

| 方法 | 参数 | 结果 |
|---|---|---|
| `engine.execute`（别名 `ui.menu.invoke`） | `{command, params?}` | 运行任意引擎/UI 命令 |
| `engine.commands` | — | 命令注册表：id、label、menu、shortcut、params 文档、enabled |
| `ui.menu.list` / `ui.menu.tree` | — | 菜单项（扁平 / 树形，含 checked、子菜单） |
| `ui.inspect` | — | UI 状态、窗口、loupe 渲染状态（`source`/`pending`/`failed`）、画布/图像矩形、活动照片、选择、性能（fps、frameMs…）、导出/导入/任务活动栈、文件对话框、剪贴板 |
| `ui.widgets` | `{filter?}` | 屏上组件 `{id, rect:[x,y,w,h]}`（屏幕点） |
| `ui.clickWidget` / `ui.dragWidget` / `ui.hoverWidget` | `{id, count?, button?, fx?, fy?}` | 对组件的真实 egui 输入（`button:"right"` 右键） |
| `ui.move` / `ui.click` / `ui.drag` | `{x,y,...}` | 原始指针输入（屏幕点） |
| `ui.pointer` | `{events:[{kind:down/drag/up,x,y}], alt?, shift?, cmd?}` | 归一化图像坐标手势（笔刷、渐变、裁剪手柄） |
| `ui.key` / `ui.text` / `ui.clipboard` / `ui.scroll` / `ui.zoom` | 见官方文档 | 键盘/文本/剪贴板/滚轮/捏合缩放 |
| `ui.set` | 部分 UI 状态，如 `{"view":"detail"}` | 变更后的 UI 状态 |
| `ui.dialog.confirm` / `ui.dialog.cancel` | — | 关闭打开的对话框 |
| `ui.resize` / `ui.zoomFactor` | `{width,height}` / `{factor:0.5–3}` | 窗口大小 / 界面缩放 |
| `ui.screenshot` | `{path?, headless?}` | `{path,width,height}`；`headless:true` 用 CPU 绘制（无需合成器） |
| `ui.render` | `{id?, size?, path?}` | 渲染单张照片为 PNG |
| `activity.list` / `activity.cancel` | — / `{id}` 或 `{all:true}` | 长任务清单 / 请求取消 |
| `app.quit` | — | 退出应用 |

### 常用引擎命令（经 `engine.execute`）

| 任务 | 命令 | 结果 |
|---|---|---|
| 读选择与活动照片 | `library.state {}` | `selection:{ids,active}` |
| 读照片身份+设置 | `photo.inspect {}` 或 `{id}` | id、develop、rating、flag、history |
| 读滑块元数据+当前值 | `develop.controls {section?}` | `[{id,label,section,min,max,default,step,decimals,track,value}]` |
| 设绝对滑块值 | `develop.set {values:{"light.exposure":0.7}}` | 可 undo 的编辑；也接受 `{control,value}` |
| 相对调整 | `develop.adjust {control,delta}` | 加到当前值（clamp） |
| 换照片 | `library.select {ids:[...]}` / `library.next` / `library.previous` | 改活动照片 |
| Undo/Redo | `edit.undo` / `edit.redo` | — |
| 交互分组 | `develop.beginInteraction {label}` … `develop.endInteraction` | 一批滑块更新算一步 undo |
| 导出 | `app.export` | export 参数 + `preset`、`dir`/`path`、`ids`、`background`；`background:true` 立即返回 `{background,total}`，轮询 `ui.inspect → export` |

细节：`wb.temp` 在带色彩矩阵的 raw 上是 Kelvin，其余是相对刻度（6500 = as shot）；图像导航 `view.navigate {zoom?:"fit"|"fill"|{percent:≤800}, pan?:[0..1,0..1]}`；主题 `view.appearance {mode?}` / `view.theme {theme}`；遮罩笔刷 `tool.brush {}`。

**无头渲染**：运行中应用 `ui.screenshot {path, headless:true}`；无窗口 `lightcraft-cli snapshot --demo -o grid.png --size 1600x1000`（`--library DIR --script tour.jsonl` 可放逐行请求的脚本）。

## FilmCraft（视频剪辑）

**启动**：`filmcraft --control 9876` 或 `FILMCRAFT_CONTROL_PORT=9876`。上游 `main` 文档要求同时提供 `FILMCRAFT_CONTROL_TOKEN`（凭据放在每个请求的顶层 `token` 字段），但已发布的 0.9.0 二进制实测并不强制——不带或带错 token 都能正常返回。文档领先于二进制是常态，以运行中实例为准；详见 `known-pitfalls.md`。
**附加 flag**：`--control-input-only`（组件输入只接受来自控制通道）、`--demo`、`--empty`、`--project p.fcproj`、`--data-dir DIR`（env `FILMCRAFT_DATA_DIR`）、`--graphics default|dx12|software`。

### 方法

| 方法 | 参数 | 说明 |
|---|---|---|
| `engine.execute` / `ui.menu.invoke` | `{command, params}` | 任意引擎或 UI 命令 |
| `engine.commands` / `ui.menu.list` | — | 命令注册表 / 菜单树 |
| `ui.inspect` | — | UI 状态（tool、workspace、dock、timeline 视图、播放状态、fps…） |
| `ui.docking` | — | 面板布局、聚焦/最大化面板、每个停靠手势的命中矩形 |
| `ui.elements` | `{prefix?}` | 屏上所有可交互元素：id、label、rect |
| `ui.set` | `{tool, workspace, mode, theme, focused, playbackRes, timeline:{…}, program:{…}, source:{…}, clipDialog:{…}, menuDialog:{…}, panels:{…}, export:{…}, projectPanel:{…}, mediaBrowser:{…}}` | 改 UI 状态；未知字段在变更前即报错 |
| `ui.panel.show` / `ui.panel.close` | `{panel}` | 面板显隐 |
| `ui.click` / `ui.move` | `{id}` 或 `{x,y}`, `button`, `count`, `modifiers` | 合成指针输入（count 0–10） |
| `ui.drag` | `{from, to, steps, modifiers}` | 按下–移动–释放（steps 0–1024，默认 12） |
| `ui.scroll` | `{id|x,y, dx, dy, modifiers}` | 滚轮 / 触控板 |
| `ui.key` / `ui.type` | `{key}`（`Cmd+K`、`Space`…）/ `{text}` | 键盘 |
| `ui.timeline.hit` / `ui.timeline.locate` | `{x,y,modifiers?}` / `{clip, edge?}` | 时间轴命中测试：报 clip 边缘（In/Out）、trim 类型、标尺与工作区 |
| `ui.playback` | `{action: play|stop|toggle, speed?}` | 播放控制 |
| `ui.screenshot` | `{path?, panel?}` | 窗口或单个面板 PNG；10s 内没有帧则失败 |
| `ui.resize` / `app.quit` | `{width,height}` / `{}` | 调整窗口 / 直接退出（不弹保存提示） |
| `ui.focus` | `{}` / `{id}` | 激活窗口 / 给组件 egui 焦点 |
| `perf.stats` | — | 性能计数器（解码缓存、帧队列、渲染耗时…） |

要点：

- 时间基是 ticks（254016000000/s）；命令也接受 `seconds`、`frame`、`timecode`。
- 轨道参数是轨道 id 或名字（`"V1"` / `"A2"`）；`timeline.place` 的 `track` 放画面、`audioTrack` 放声音。
- 依赖选区的命令在无选择时禁用，除非在命令文档规定的键里点名目标（`clips`/`clip`、`items`/`item`）。
- 元素 id 来自上一帧；布局变化后元素短暂缺失时应用会在后续帧重试。
- `timeline.move` 在 Linked Selection 开启时会带联动伙伴。

## PhotoCraft（位图编辑）

**启动**：`photocraft --control 7878 [--control-token-file PATH] [--automation-read-root DIR] [--automation-write-root DIR]`；env：`PHOTOCRAFT_CONTROL_PORT`、`PHOTOCRAFT_CONTROL_TOKEN` / `_FILE`、`PHOTOCRAFT_AUTOMATION_READ_ROOT` / `WRITE_ROOT`。

### 认证握手（每个 TCP 连接第一帧）

```json
{"id": "auth", "method": "auth", "params": {"token": "<64 个十六进制字符>"}}
```

- token 文件不存在则应用创建（256-bit，Unix mode 0600，Windows 用用户专属 ACL）；已存在则复用；两者都没配则当次启动生成并打到 stderr。
- flag 优先于环境变量；空环境变量视为未设。**同时给了 token 和 token 文件，或给了 `--control` 又配了凭据，是用法错误（退出码 2）。**
- 每连接认证一次；重复 `auth` 回 `already authenticated`，连接继续服务。

### 文件系统边界（fail closed）

未授予 read/write root 时一切文件访问拒绝。路径必须是非空前向斜杠相对路径且在 root 之下，或位于 root 内的绝对路径；`..` 与越界拒绝。

`file.open` / `file.save` / `file.saveAs` / `file.saveACopy` **被通道拒绝**——用 `app.open`（读 root）/ `app.save`（写 root，无 path 时存回文档自身 PSD/PSB/.pcraft）。

env 形式的 root 只被桌面 `photocraft` 进程支持；headless CLI（`mcp` / `serve`）必须显式传 flag；bridge 模式在桌面进程上配 root（bridge 侧传 root 会被拒绝）。

### 主要方法

| 方法 | 说明 |
|---|---|
| `engine.execute {command, params}` | 任意引擎/UI 命令；`params` 必须是对象（`null`/省略=无参数），数组/字符串/数字/布尔是错误 |
| `engine.commands {filter?}` | 命令注册表（裸数组，含 `enabled`/`disabledReason`/`needsDocument`） |
| `ui.inspect` | 完整 UI 状态（tool、panels、views、dialogs、windows、窗口尺寸、perf.gpuInfo）；不含菜单树 |
| `ui.menu.invoke {id, params?, wait?}` / `ui.menu.list` | 菜单点击语义（无参数时开命令对话框）；后台作业 `wait:false` 立即回 `{job,pending:true}` |
| `ui.set {…}` | 改 UI 状态（tool、zoom、theme、brushSize、dock、shapeStroke…）；未知字段在变更前即报错 |
| `ui.dialog.open/set/confirm/cancel` | 驱动原生对话框（含 Layer Style、Fill、Save for Web、未保存提示 `discard`、shell 对话框） |
| `ui.pointer {events, modifiers?, button?}` | 文档坐标驱动当前工具（压力/倾斜/旋转模拟压感笔；`command:true` 临时变移动工具） |
| `ui.click {x,y,button?,count?}` / `ui.move` / `ui.key {key,…}` / `ui.type {text}` / `ui.resize` / `ui.focus` / `ui.scroll` | 合成输入（屏幕点）；所有参数先校验后排队 |
| `ui.screenshot {path?, focus?}` | 抓主窗口 PNG；无 path 回 base64；path 相对 automation write root；macOS 被遮挡窗口会停止渲染 |
| `app.open {path}` / `app.save {path?, tgaBits?}` | 经 root 的文件 I/O，回 `warnings` |
| `jobs.list` / `jobs.cancel` | 后台作业列表 / 取消 |
| `app.quit` | 退出 |

`ui.gpu.simulateLoss {error?}` 可模拟 GPU 设备丢失（测试 CPU 回退）。首帧后每个连接可用 `methods` 方法拿到方法列表。

## 跨应用对照

| | LightCraft | FilmCraft | PhotoCraft |
|---|---|---|---|
| 启动 flag | `--control PORT` | `--control <port>` | `--control <port>` |
| 环境变量 | `LIGHTCRAFT_CONTROL_PORT` | `FILMCRAFT_CONTROL_PORT` | `PHOTOCRAFT_CONTROL_PORT` |
| 认证 | 无 | 顶层 token 字段 | auth 首帧 |
| 文件沙箱 | 无（靠 CONFIG_DIR 隔离配置） | 无 | automation read/write root（fail closed） |
| 输入注入 | `ui.clickWidget`/`ui.pointer`/`ui.key` | `ui.click`/`ui.key`/`ui.type` | `ui.pointer`/`ui.click`/`ui.key` |
| 截图 | `ui.screenshot {path,headless?}` | `ui.screenshot {path,panel?}` | `ui.screenshot {path?,focus?}`（可 base64） |
| 特色 | loupe 渲染状态、develop 滑块、snapshot 无头 | 时间轴 ticks、`--control-input-only`、面板截图、导出队列 | 对话框驱动、后台作业、智能对象、矢量蒙版 |
