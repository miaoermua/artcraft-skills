# 上游来源与快照维护

> 快照日期：2026-11-11。

这份 skill 的静态参考是**上游文档的蒸馏快照**。它会过期，所以必须写清楚：哪份是权威、快照什么时候的、怎么刷新。

## 权威顺序

从高到低，冲突时以上面的为准：

1. **运行中实例的自我描述** —— `engine.commands`（命令注册表）、`methods`（方法表）、`ui.inspect`（当前状态）。这是应用此刻的真实能力。
2. **CLI 自述** —— `<cli> --help`、`<cli> commands`、`<cli> controls`。与已安装的二进制同版本。
3. **上游仓库文档** —— 下表列出的地址，取 `main` 分支。
4. **本 skill 的 references** —— 蒸馏后的快照，只作导航与兜底。

## 上游文档地址

| 应用 | 仓库 | 协议文档 | MCP 文档 | 其他 |
|---|---|---|---|---|
| LightCraft | https://github.com/storytold/lightcraft | `docs/control-protocol.md` | `docs/mcp.md` | `README.md`、`docs/process-versions.md` |
| FilmCraft | https://github.com/storytold/filmcraft | `docs/control-protocol.md` | `docs/agents.md`（含 MCP 与 CLI） | `docs/monitors.md`、`docs/keyboard.md` |
| PhotoCraft | https://github.com/storytold/photocraft | `docs/control-protocol.md` | `docs/mcp.md` | `docs/ui-dialogs.md`、`docs/shape-strokes.md` |

原始地址形如：

```
https://raw.githubusercontent.com/storytold/<app>/main/docs/<doc>.md
```

## 一键刷新脚本

只拉实际存在的 6 份文档（三重循环会对 3 个不存在的路径产生 404）：

```sh
mkdir -p /tmp/acdocs && cd /tmp/acdocs
base=https://raw.githubusercontent.com/storytold
for app in photocraft lightcraft filmcraft; do
  curl -fsSL -m 30 -o "$app-control-protocol.md" "$base/$app/main/docs/control-protocol.md"
done
curl -fsSL -m 30 -o filmcraft-agents.md  "$base/filmcraft/main/docs/agents.md"
curl -fsSL -m 30 -o lightcraft-mcp.md   "$base/lightcraft/main/docs/mcp.md"
curl -fsSL -m 30 -o photocraft-mcp.md   "$base/photocraft/main/docs/mcp.md"
shasum -a 256 *.md
```

2026-11-11 实测的有效路径：`lightcraft` 与 `photocraft` 有 `control-protocol.md` + `mcp.md`；`filmcraft` 有 `control-protocol.md` + `agents.md`（MCP 与 CLI 都写在 `agents.md` 里）。`lightcraft`/`photocraft` 没有 `agents.md`，`filmcraft` 没有 `mcp.md`。

刷新后要做三件事：

1. 核对 `app-matrix.md` 的**认证方式**——这是最容易变的一列。
2. 核对 `control-protocols.md` 的认证与方法表、`mcp-servers.md` 的工具与 root 语义。
3. 把各 references 顶部的**快照日期**改成今天，并把本次 SHA256 记进下面的快照历史。

## 快照历史

| 日期 | 变化 |
|---|---|
| 2026-10-14 | 初始快照（LightCraft 0.7.1 / FilmCraft 0.7.2 / PhotoCraft 0.8.2）。当时 FilmCraft 通道**无 token**。 |
| 2026-11-04 | 刷新到上游 main：上游文档显示 FilmCraft 改为**要求 `FILMCRAFT_CONTROL_TOKEN`，凭据放每个请求的顶层 `token` 字段**；补齐 LightCraft `import` 工具与 `render --opt/--settings` 等新 CLI 用法；补齐 PhotoCraft 进度/取消与 `doc_*` 工具语义。 |
| 2026-11-04（实测） | 三应用版本实测为 LightCraft 0.9.1 / FilmCraft 0.9.0 / PhotoCraft 0.18.0。**实测与上游文档有出入**：FilmCraft 0.9.0 二进制**不强制 token**（无 token、错 token 都正常返回），上游 main 文档描述的是更严格的未发布行为。文档领先于二进制是常态，行为以实测为准。 |
| 2026-11-11 | 再次刷新上游 main（6 份，校验值见下表）。主要变化：**PhotoCraft 控制通道新增 `auth.challenge` 挑战握手**（官方 bridge 用，token 不上线；脚本的 token 首帧仍接受）；PhotoCraft MCP 文档改写为「MCP conventions」，新增多 read root / 单 write root 授权语义、目录型 `.pcraft` 与显式 Save As、job-capable 命令后台化与取消语义；`engine.commands` / `command_list` 明确为**裸 JSON 数组**，元素含 `disabledReason` / `needsDocument` / `keywords`；后台作业 `wait:false` + `jobs.list` / `jobs.cancel`；bridge 55s 客户端超时与字面量 loopback 限制；LightCraft 新增持久图库 `--library`、`--compact`、slideshow 命令集、导出格式扩展与 Apple Photos；FilmCraft 新增 `effects.*` 回复语义、长导出 `etaSeconds` / `offlineMedia` / `warnings`、图像序列编号；三家 MCP `2026-07-28` 的 `ttlMs` / `cacheScope` 提示与 10 分钟目录缓存。 |

### 2026-11-11 拉取清单（可复核）

全部取自 `main` 分支，`shasum -a 256` 值：

| 文件 | 字节 | 行 | SHA256 |
|---|---:|---:|---|
| `filmcraft-agents.md` | 30874 | 455 | `3ce2af777b8edc8ce829621592874e18fcf41d1b1e5fe6c2bf9a5103178d387b` |
| `filmcraft-control-protocol.md` | 25198 | 245 | `d9cafe5f0c91daafb37fbc1e006fde6b49041fd90ab2f785487c1bda3b894edf` |
| `lightcraft-control-protocol.md` | 50219 | 421 | `f7fe449b95057553f83598ab2a47725e70bf593199d7522bfaccf2060ccb0f20` |
| `lightcraft-mcp.md` | 26707 | 369 | `36512f153122220ca637b2bbb9400bf3d6c2ed80ec0c8517adf311a363bae613` |
| `photocraft-control-protocol.md` | 131726 | 840 | `1d921cbff1b3d522a6d8df48b34d6a85c83b0cda4e1f00d276e9a21ad714121e` |
| `photocraft-mcp.md` | 14205 | 216 | `293f3b36dc806383d0cebad537d8496ce67dc29fb1d14b27e6bbd570681c4caa` |

原始文件留在本机备份目录 `~/.workbuddy/skill-audit-backup/20261111-2302/`，**不入库**：上游仓库未提供可访问的 LICENSE，且本项目自述就是「把官方公开协议整理成给 agent 用的操作手册」，按渐进披露只保留蒸馏快照，不整份搬运原文。

## 本机实测环境

2026-11-04 在本机（macOS / Apple M2）逐项验证：

| 项 | 结果 |
|---|---|
| LightCraft 0.9.1 无认证通道 | ✅ 连通；`ui.inspect` / `library.state` / `ui.screenshot {headless:true}` 均正常，截图 3200×1854 |
| PhotoCraft 0.18.0 auth 首帧 | ✅ token 文件自动创建（mode 0600）；认证帧回 `{"authenticated":true}`；不认证则回 `authentication required` |
| FilmCraft 0.9.0 token 字段 | ✅ 请求带/不带 token、token 错误，**三种情况都正常返回** → 该版本不强制 token |
| `photocraft-cli` 0.18.2 | 装在 `~/.local/bin`；`lightcraft-cli` / `filmcraft-cli` 未安装 |

**当前状态随时会变**——跑一次 `scripts/craft_env.py` 就知道此刻的事实，不用信这段文字。

## 维护约定

- 上游文档和本表冲突时，**先信上游**，然后改本表。
- 发现新坑写进 `known-pitfalls.md`，并注明验证方式（实测 / 上游文档）。
- `scripts/` 里的脚本尽量保持"只读、无副作用"，除非用户明确要求。
- 上游文档著作权归 storytold 所有。只蒸馏事实并注明来源，不整份复制原文；本仓库的 MIT 许可只覆盖本仓库自己写的内容。
