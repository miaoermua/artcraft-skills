---
name: artcraft-cli
description: 驱动 ArtCraft 套件桌面应用（LightCraft RAW 修图 / FilmCraft 视频剪辑 / PhotoCraft 位图编辑）的通用 agent skill，覆盖三大入口：JSON-lines 控制通道、命令行 CLI（lightcraft-cli / filmcraft-cli / photocraft-cli）、MCP 服务器。适用于操控运行实例、查询命令注册表、驱动 UI（点击/按键/拖拽/截图）、无头批量处理媒体、把应用接入 Claude 等 MCP 客户端，以及排查控制端口连接、认证凭据、命令 id 问题。触发词：ArtCraft、LightCraft、FilmCraft、PhotoCraft、craft-cli、--control、控制通道、MCP server、agent 驱动、自动化剪辑修图。本 skill 是面向 ArtCraft 系列软件的第三方 agent skill，并非 ArtCraft 官方仓库。
---

# ArtCraft 自动化：控制通道、CLI 与 MCP

## 声明

**本 skill 是针对 ArtCraft 系列软件的 agent skill，并非 ArtCraft 官方仓库。** ArtCraft / LightCraft / FilmCraft / PhotoCraft 的著作权与官方文档归 storyteller（github.com/storytold）所有；本仓库只是把官方公开的协议与 CLI 整理成给 AI agent 用的操作手册与工具脚本，与官方无隶属、无背书关系。上游文档与本仓库内容冲突时以官方为准。

官方仓库：[lightcraft](https://github.com/storytold/lightcraft) · [filmcraft](https://github.com/storytold/filmcraft) · [photocraft](https://github.com/storytold/photocraft)

## 这套东西是什么

ArtCraft 套件（github.com/storytold）的每个桌面应用都把 UI 里能点的每个菜单项、滑块、笔触实现成**带稳定 id 和 JSON 参数的命令**，并通过三个等价入口开放：

| 入口 | 长什么样 | 适合什么 |
|---|---|---|
| 控制通道 | 应用开一个 TCP 端口，说 JSON 行 | 操控用户正在看的窗口 |
| CLI | `lightcraft-cli` / `filmcraft-cli` / `photocraft-cli` | 无界面批处理 |
| MCP | `xxx-cli mcp` | 让 Claude 等客户端来使唤 |

三者调度**同一套命令注册表**，所以脚本和 agent 能像人一样操作，而且编辑可 undo。

## 四条铁律（先记住这四条，再看别的）

1. **运行时发现优先**。本 skill 里的参考文档是某个版本时点的快照，只用来导航和兜底；**事实以运行中实例为准**：`engine.commands`（命令注册表）、`methods`（方法表）、CLI 的 `--help` / `commands` / `controls`。**禁止凭记忆写命令 id**——各家各版本注册表都不一样。
2. **认证三家不同，且会变**。动手前先跑 `scripts/craft_env.py` 看本机的 `auth` 字段，别照抄任何博客里的端口命令。当前已知的几种：
   - LightCraft：通道**无认证**（任何本机进程都能驱动，用完即关）
   - FilmCraft：凭据放在**每个请求的顶层 `token` 字段**（较新版本强制；已发布的 0.9.0 实测并不强制）
   - PhotoCraft：脚本走**首帧 `auth {token}`**；官方 bridge 走 `auth.challenge` 挑战握手（token 不上线）。两者当前版本都接受，文件访问被 automation 读写根目录 fail-closed 限制
   `scripts/craft_ctl.py --app <light|film|photo>` 会自动套用对应方式；缺凭据时它不擅自失败，而是交给服务端判定并把错误原样读出来。
3. **凭据不进命令行、不进日志、不进仓库**。用 token 文件（Unix mode 0600）或环境变量；不要在共享机器上把 token 明文传给进程。
4. **编辑前先说影响**。动用户的真实图库/工程前，讲清楚会改哪些东西、是否可 undo、导出到哪；不确定范围就问。

## 起步：先做环境自检

```sh
python3 scripts/craft_env.py --table     # 装了什么版本、CLI 在哪、通道开着没、凭据在哪
python3 scripts/craft_env.py             # 同样内容的 JSON
```

这一步取代"我记得我装了 X 版本"。它只读不写。

## 入口决策

| 用户想要 | 选 | 一句话理由 |
|---|---|---|
| "我现在开着这个软件，你帮我点/看" | 控制通道 | 唯一能看见真实窗口状态的入口 |
| "把这 200 张批量处理掉" | CLI headless | 不依赖窗口渲染，跑得更快更稳 |
| "以后我直接跟 AI 说这件事" | MCP | 一次接线，长期使用 |
| "现在到底能点什么命令" | 任一入口的 `engine.commands` / `command_list` | 唯一权威清单 |

## A. 控制通道

### 启动

三个应用都用 `--control PORT` 开通道，但**启动 flag 和凭据要求不同**，先查 `craft_env.py` 与 `references/app-matrix.md`：

```sh
# LightCraft：一次性内存会话，测试首选，不写盘
nohup "/Applications/LightCraft.app/Contents/MacOS/LightCraft" --control 7980 --memory > /tmp/lc.log 2>&1 & disown

# FilmCraft：需要先导出凭据，否则不监听
export FILMCRAFT_CONTROL_TOKEN="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
nohup "/Applications/FilmCraft.app/Contents/MacOS/FilmCraft" --control 9876 > /tmp/fc.log 2>&1 & disown

# PhotoCraft：token 文件（应用首次启动时自动创建，mode 0600）
nohup "/Applications/PhotoCraft.app/Contents/MacOS/PhotoCraft" --control 7878 \
      --control-token-file ~/.photocraft/control.token > /tmp/pc.log 2>&1 & disown
```

> **进程保活**：裸 `&` 启动的 GUI 会随启动它的 shell 退出被回收，之后连接一律被拒。用 `nohup ... & disown`，或把「启动→操控→退出」写在同一条命令里。

### 操控

用自带的客户端，别每次重写 socket 代码：

```sh
# 通用形式：--app 决定认证方式，--port 给端口
python3 scripts/craft_ctl.py --app light --port 7980 engine.commands
python3 scripts/craft_ctl.py --app film  --port 9876 --method engine.execute --params '{"command":"sequence.inspect"}'
python3 scripts/craft_ctl.py --app photo --port 7878 --token-file ~/.photocraft/control.token '{"method":"ui.inspect"}'

# 条件发现：命令注册表精简表（--filter 过滤，避免上千行刷屏）
python3 scripts/craft_ctl.py --app light --port 7980 --discover --filter develop

# 脚本模式：stdin 每行一个请求，'#' 开头为注释
echo '{"method":"engine.commands"}' | python3 scripts/craft_ctl.py --app light --port 7980
```

退出码：`0` 全部 ok / `1` 有 ok=false / `2` 用法或连接错误。

## B. CLI（无头批处理）

CLI 是**独立 release 资产**，不在 `.app` 里，ArtCraft Launcher 也不装它。获取与安装见 `references/cli-reference.md`。

```sh
lightcraft-cli run --import in.dng develop.set control=light.exposure value=0.7 app.export path=out.jpg longEdge=2048
lightcraft-cli render in.dng -o out.jpg --set light.exposure=0.5
lightcraft-cli commands --json                 # 命令注册表（等价于通道的 engine.commands）
lightcraft-cli controls --json                 # develop 滑块 id 与范围

photocraft-cli run wave.psd --cmd filter.sharpen.smartSharpen --params '{"amount":80}' --out out.png
photocraft-cli batch --actions grade.json --in ./raw --out ./graded

filmcraft-cli commands razor                   # 按关键词找命令 id
filmcraft-cli describe timeline.razor          # 单命令的菜单/快捷键/参数/当前启用态
filmcraft-cli --project p.fcproj --save exec timeline.razor seconds=3.5
filmcraft-cli --bridge 127.0.0.1:9876 exec window.workspace.color   # 反控运行中的应用
```

通用规则：选项位置任意；输出 JSON；**退出码 0=成功 / 1=命令失败 / 2=用法错误**；`key=value` 能解析成 JSON 就按 JSON 解析，否则当字符串；点号键表示嵌套（`color.r=1`）。

## C. MCP（接入 Claude 等客户端）

```sh
claude mcp add lightcraft     -- lightcraft-cli mcp ~/Pictures/shoot
claude mcp add lightcraft-app -- lightcraft-cli mcp --connect 127.0.0.1:7980
claude mcp add filmcraft      -- filmcraft-cli mcp --bridge 127.0.0.1:9876
claude mcp add photocraft     -- photocraft-cli mcp \
      --automation-read-root /work/project --automation-write-root /work/project
claude mcp add photocraft-app -- photocraft-cli mcp --bridge 127.0.0.1:7878 --control-token-file /path/token
```

headless（进程内引擎，无窗口）与 bridge（驱动已启动的应用）两种模式，凭据要求见 `references/mcp-servers.md`。

## 核心工作流：发现 → 执行 → 验证 → 回退

1. **发现**：`engine.commands` / `command_list` 拿注册表，按 label/menu 找目标命令 id 与参数文档。
2. **执行**：`engine.execute {command, params}`。注意语义差别——`ui.menu.invoke` 是"菜单点击"（无参数时会打开命令的对话框），`engine.execute` 直接以默认参数运行、不开对话框。
3. **验证**：读状态而不是猜。`ui.inspect` 是通用 UI 状态；各应用另有领域状态方法（LightCraft `library.state` / `photo.inspect` / `develop.get`，FilmCraft `sequence.inspect`，PhotoCraft `document.inspect`）。
4. **看结果**：`ui.screenshot {path}` 抓窗口（渲染完成后才抓；窗口不绘制帧时用 headless 截图）。
5. **回退**：`edit.undo` / `edit.redo`。agent 的编辑同样进 undo 栈。

协议铁律（三家一致的部分）：

- 一行一个 JSON 请求、一行一个回复，按序对应：`{"id":N,"method":...,"params":{...}}` → `{"id":N,"ok":true,"result":...}` 或 `{"id":N,"ok":false,"error":"..."}`。
- **无事件推送**：通道只回请求。想知道 GUI 侧发生了什么，轮询 inspect 方法对比快照。
- **每次请求是独立快照**：换了对象必须重读状态，别拿缓存的 id 推断当前状态。
- 服务端回复上限 60s；超时的命令可能仍在跑，重试前先查状态。长任务用 `wait:false` 再轮询 `jobs.list`。

## 安全边界

- 所有通道只监听 `127.0.0.1`，协议不加密——**不要 tunnel 或代理到不可信主机**。loopback 只挡远程，挡不住同机其他进程。
- LightCraft 通道无认证：按需开启，用 `LIGHTCRAFT_CONFIG_DIR` 隔离配置做自动化，不用时关掉。
- PhotoCraft 文件系统 fail-closed：自动化读写限制在 `--automation-read-root` / `--automation-write-root` 之内，未授权即拒绝；`file.open` / `file.save` 被通道拒绝，改用 `app.open` / `app.save`。read root 可重复、write root 只能一个且不可与 bridge 混配；所有 root 必须是已存在的绝对目录。
- PhotoCraft 挑战握手：官方 bridge 用 `auth.challenge`，token 不上线；本 skill 的 `craft_ctl.py` 仍用 `frame`（首帧 token），上游继续支持。老版本应用不认挑战握手，升级时 CLI 与应用要一起换。
- FilmCraft 的 `FILMCRAFT_CONTROL_TOKEN` 等同于全部控制权限：保密、不要进命令行历史或 MCP 配置。
- 默认不碰用户既有数据（例如 LightCraft 的 `~/Pictures/LightCraft Library`），除非用户明确要求。

## 出问题先查这里

`references/known-pitfalls.md` 收录了实测踩过的坑（连接被拒、无帧超时、PhotoCraft 没有 `--help`、导出原子保存被系统策略拦截、图层原点偏移、`quad` 相对坐标等），另有一节来自上游文档、尚未本机实测的坑位并标注了来源。**先查表，别重复试同一个错命令。**

## 参考文档索引

| 文件 | 内容 |
|---|---|
| `references/app-matrix.md` | 三应用差异速查（启动 flag、凭据、沙箱、状态方法、CLI/MCP 入口）——**先看这个** |
| `references/control-protocols.md` | 控制通道协议：通用机制 + 各家方法表 + 认证四态 |
| `references/cli-reference.md` | 三个 CLI 的获取、子命令、参数语义、退出码 |
| `references/mcp-servers.md` | MCP 服务器工具清单、两种模式、接入方式 |
| `references/known-pitfalls.md` | 实测坑位与排障路径 + 上游文档新增坑位（标注来源，未实测的会写明） |
| `references/upstream-sources.md` | 上游文档地址、快照日期与校验值、**怎么刷新**这份参考 |
| `scripts/craft_ctl.py` | 控制通道客户端（三家认证差异已内置） |
| `scripts/craft_env.py` | 环境自检：应用、版本、CLI、通道、凭据 |
