# 上游来源与快照维护

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

```sh
mkdir -p /tmp/acdocs && cd /tmp/acdocs
for app in photocraft lightcraft filmcraft; do
  for doc in control-protocol agents mcp; do
    curl -sS -m 25 -o "$app-$doc.md" \
      "https://raw.githubusercontent.com/storytold/$app/main/docs/$doc.md"
  done
done
```

（`agents.md` 只有 filmcraft 有，另外两家是 404，忽略即可。）

刷新后要做三件事：

1. 核对 `app-matrix.md` 的**认证方式**——这是最容易变的一列。
2. 核对 `control-protocols.md` 的方法表增删。
3. 把各 references 顶部的**快照日期**改成今天。

## 快照历史

| 日期 | 变化 |
|---|---|
| 2026-10-14 | 初始快照（LightCraft 0.7.1 / FilmCraft 0.7.2 / PhotoCraft 0.8.2）。当时 FilmCraft 通道**无 token**。 |
| 2026-11-04 | 刷新到上游 main：上游文档显示 FilmCraft 改为**要求 `FILMCRAFT_CONTROL_TOKEN`，凭据放每个请求的顶层 `token` 字段**；补齐 LightCraft `import` 工具与 `render --opt/--settings` 等新 CLI 用法；补齐 PhotoCraft 进度/取消与 `doc_*` 工具语义。 |
| 2026-11-04（实测） | 三应用版本实测为 LightCraft 0.9.1 / FilmCraft 0.9.0 / PhotoCraft 0.18.0。**实测与上游文档有出入**：FilmCraft 0.9.0 二进制**不强制 token**（无 token、错 token 都正常返回），上游 main 文档描述的是更严格的未发布行为。文档领先于二进制是常态，行为以实测为准。 |

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
