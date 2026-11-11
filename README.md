# artcraft-skill

把 ArtCraft 套件（LightCraft RAW 修图 / FilmCraft 视频剪辑 / PhotoCraft 位图编辑）变成可脚本化、可被 AI 代办的自动化能力。

覆盖三个应用，走同一套命令注册表的三个等价入口：**命令行 CLI**、**JSON-lines 控制通道**、**MCP 服务器**。

## 声明

> **本 skill 是针对 ArtCraft 系列软件的 agent skill，并非 ArtCraft 官方仓库。**
>
> ArtCraft / LightCraft / FilmCraft / PhotoCraft 及其文档、协议、CLI 的著作权归 storyteller（github.com/storytold）所有。本仓库只是把官方公开的协议与 CLI 整理成给 AI agent 用的操作手册和工具脚本，与官方无隶属、无背书关系；内容与官方冲突时以官方为准。
>
> 官方仓库：[lightcraft](https://github.com/storytold/lightcraft) · [filmcraft](https://github.com/storytold/filmcraft) · [photocraft](https://github.com/storytold/photocraft)


## 里面有什么

```
artcraft-skill/
├── .codebuddy-plugin/plugin.json     # 插件/专家元数据（安装成专家时用）
├── agents/
│   └── artcraft-automation.md        # 专家提示词：入口决策、工作流、安全边界
└── skills/
    └── artcraft-cli/
        ├── SKILL.md                   # 通用技能主体：入口选择、工作流、铁律
        ├── references/
        │   ├── app-matrix.md          # 三应用差异速查（先看这个）
        │   ├── control-protocols.md   # 控制通道协议 + 各家方法表
        │   ├── cli-reference.md       # 三个 CLI 的获取、子命令、参数语义
        │   ├── mcp-servers.md         # MCP 工具清单与两种模式
        │   ├── known-pitfalls.md      # 实测坑位与排障表
        │   └── upstream-sources.md    # 上游文档地址 + 快照维护方法
        └── scripts/
            ├── craft_ctl.py           # 控制通道客户端（三家认证差异已内置）
            └── craft_env.py           # 环境自检：应用/版本/CLI/通道/凭据
```

## 安装

**当普通 Skill 用**（只需要能力，不需要专家）：

```sh
cp -R skills/artcraft-cli ~/.workbuddy/skills/artcraft-cli
```

**当专家插件用**（连提示词一起装）：把整个仓库作为插件目录安装即可，专家名 `ArtCraft 自动化`，技能名 `artcraft-cli`。

## 快速上手

```sh
# 1. 先自检：装了什么版本、CLI 在哪、通道开着没、凭据在哪
python3 skills/artcraft-cli/scripts/craft_env.py --table

# 2. 起一个控制通道（LightCraft 的内存会话，测试首选）
nohup "/Applications/LightCraft.app/Contents/MacOS/LightCraft" \
      --control 7980 --memory > /tmp/lc.log 2>&1 & disown

# 3. 查这个实例现在能点什么（别把上千条注册表打进上下文）
python3 skills/artcraft-cli/scripts/craft_ctl.py --app light --port 7980 --discover --filter develop

# 4. 读状态、截图、编辑
python3 skills/artcraft-cli/scripts/craft_ctl.py --app light --port 7980 '{"method":"ui.inspect"}'
python3 skills/artcraft-cli/scripts/craft_ctl.py --app light --port 7980 \
        '{"method":"ui.screenshot","params":{"path":"/tmp/shot.png"}}'
```

三家认证方式不同，脚本已按 `--app` 自动适配：

| 应用 | 通道认证 | 用法 |
|---|---|---|
| LightCraft | 无认证 | `--app light --port PORT` |
| FilmCraft | 顶层 `token` 字段 | 先 `export FILMCRAFT_CONTROL_TOKEN=...`，再 `--app film --port PORT` |
| PhotoCraft | `auth` 首帧握手 | `--app photo --port PORT --token-file <路径>` |

## 为什么写成"通用"的样子

这套东西**随版本变**，而 ArtCraft 应用会通过 Launcher 自动更新。所以本项目刻意不把某台机器的结论写死：

1. **运行时发现优先**。`craft_env.py` 负责把"我以为的版本"换成"机器上的事实"；命令注册表永远现查现用，不硬编码命令 id。
2. **认证方式不写死**。`craft_ctl.py --app` 内置三家的差异；`craft_env.py` 会报出本机当前是哪一种。
3. **静态参考带快照日期**。每份 references 顶部都标注快照时间，来源和刷新方法见 `references/upstream-sources.md`。
4. **坑位清单只收实测过的**，每条注明适用应用与触发条件。

已知的版本漂移：上游 `main` 文档说 FilmCraft 控制通道**要求** `FILMCRAFT_CONTROL_TOKEN`（凭据放每个请求的顶层 `token` 字段），但实测**已发布的 0.9.0 二进制并不强制**——无 token、错 token 都正常返回。另一处是 PhotoCraft 的认证：上游新增了 `auth.challenge` 挑战握手（官方 bridge 用，token 不上线），脚本侧的 `auth {token}` 首帧仍被接受，本 skill 的 `craft_ctl.py` 用的就是后者。文档领先于二进制是常态，所以本项目的原则是：**运行时发现优先，静态文档只作导航**。详见 `references/upstream-sources.md` 的快照历史与 `references/known-pitfalls.md`。

## 刷新参考文档

```sh
mkdir -p /tmp/acdocs && cd /tmp/acdocs
base=https://raw.githubusercontent.com/storytold
for app in photocraft lightcraft filmcraft; do
  curl -fsSL -m 30 -o "$app-control-protocol.md" "$base/$app/main/docs/control-protocol.md"
done
curl -fsSL -m 30 -o filmcraft-agents.md "$base/filmcraft/main/docs/agents.md"
curl -fsSL -m 30 -o lightcraft-mcp.md  "$base/lightcraft/main/docs/mcp.md"
curl -fsSL -m 30 -o photocraft-mcp.md  "$base/photocraft/main/docs/mcp.md"
shasum -a 256 *.md
```

只拉实际存在的 6 份：`lightcraft` / `photocraft` 有 `control-protocol.md` + `mcp.md`，`filmcraft` 有 `control-protocol.md` + `agents.md`。刷完核对三件事：认证方式、方法表与工具/root 语义增删、各 references 顶部的快照日期；细节与本次校验值见 `skills/artcraft-cli/references/upstream-sources.md`。

## 授权

MIT，见 [LICENSE](LICENSE)。
