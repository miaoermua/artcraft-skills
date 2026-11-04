# 已知坑位与排障

> 收录的是**实测踩过**的坑，不含纯推测。每条都标了适用应用和出现条件。
> 遇到新坑补在这里，并注明验证方式。

## 通用

### 1. GUI 进程随启动 shell 退出被回收

`binary --control PORT &` 起的应用会跟着启动它的 shell 一起消失，之后连接一律 `Connection refused`——即使用了 `nohup ... & disown`，跨工具调用仍可能被杀。

- 处理：用 `nohup ... & disown`，或把「启动 → sleep → 操控 → 退出」写在**同一条命令**里。
- 确认已监听：日志里应出现 `control server listening on 127.0.0.1:PORT`。

### 2. 命令 id 会变

各版本注册表不同，命令可能被改名、删除或换参数。**硬编码 id 是最常见的失败原因。**

- 处理：先查 `engine.commands` / `<cli> commands` / MCP `command_list`；用 `craft_ctl.py --discover --filter <关键词>` 拿精简表，别把整个注册表打进上下文。

### 3. 窗口不绘制帧 → 请求超时

应用被最小化、被其他窗口遮挡、显示器睡眠时不产生帧，请求会卡到超时（LightCraft 会明确回 `the app drew no frame for 5 s`）。

- 处理：改用 headless 截图（LightCraft：`ui.screenshot {headless:true}`；CLI：`snapshot`），或先把窗口置前。

### 4. 首行不合法 → 连接被直接关闭

服务端只接受含字符串 `method` 的 JSON 对象。非 JSON、数组、数字、缺 `method`、非法 UTF-8、超 4 MiB 的行 → 回一条错误后**关闭连接**，同一连接上后续请求全部不执行。

- 处理：注意 zsh 会把 `[...]` 当 glob，数组参数要加引号：`'ids=[3,4]'`。

### 5. 已派发的命令超时 ≠ 没执行

请求超时后命令可能仍在跑。直接重试会造成重复编辑或重复导出。

- 处理：重试前先查状态（`photo.inspect` / `sequence.inspect` / `document.inspect` / `jobs.list`）。

## 认证相关

### 6. FilmCraft 的 token：文档比二进制更严

上游 `main` 文档说控制通道**必须**带 `FILMCRAFT_CONTROL_TOKEN`，缺失就不监听端口。但 2026-11-04 实测 **0.9.0 二进制并不强制**——不带 token 字段、甚至带错误 token，`engine.commands` 都正常返回。

- 处理：**照样带上凭据**（`craft_ctl.py --app film` 会自动从环境变量取并塞进每个请求），别依赖"服务端会拦"这件事；同时别在排查连接问题时把时间浪费在"token 是不是错了"上——先确认端口有没有监听。
- 客户端不因缺 token 直接失败：让服务端判定，把它的错误原样读出来。

### 7. PhotoCraft 首帧必须 auth

每个 TCP 连接第一帧必须是 `{"method":"auth","params":{"token":...}}`。忘了认证 → 连接被关。

- 处理：`craft_ctl.py --app photo --token-file <路径>`，脚本会自动握手。token 文件由应用首次启动时创建（Unix mode 0600）。

### 8. PhotoCraft：flag 与环境变量同时给会报用法错误

同时给了 `--control-token` 和 `--control-token-file`，或给了 `--control` 又配了凭据，是 usage error（退出码 2）。空环境变量视为未设。

### 9. LightCraft 通道无认证

任何本机进程都能驱动它。**按需开启，用完关闭**；自动化时用 `LIGHTCRAFT_CONFIG_DIR` 隔离配置目录。

## PhotoCraft 专属

### 10. 没有 `--help`

`photocraft --help` 会把 `--help` 当文件路径尝试打开，然后**正常启动 GUI**（还可能弹窗）。

- 处理：发现它的 flag 用 `strings <binary> | grep -i control`，或走通道的 `methods` 方法。

### 11. 导出是原子保存，受保护目录会被系统策略拦截

先写 `.<name>.png.<pid>-0.pcsave.tmp` 再改名。在 `~/Documents` 等受保护目录里，最后的改名/清理可能被系统安全策略拦截 → **CLI 返回非零退出码，但成品其实是完整的**（留在隐藏临时文件里）。

- 处理：稳妥做法是渲染到 `/tmp` 暂存目录，再用 `shutil.copy2` 复制进目标目录。

### 12. `edit.transform` 的 `quad` 是相对图层原点

图层原点 = `file.placeEmbedded` 的 `center` − (pw/2, ph/2)。要把内容放到画布绝对坐标 (L,T)-(R,B)，须传：

```
quad = [[L-ox,T-oy],[R-ox,T-oy],[R-ox,B-oy],[L-ox,B-oy]]
```

`rect` 是图层内容坐标系的源框（通常 `[0,0,pw,ph]`）。直接把画布绝对坐标当 quad 用，内容会整体偏移一个图层原点。

### 13. `file.placeEmbedded` 默认会缩放

`scale` 缺省是"比画布大时按 fit 缩小"。要 1:1 放置必须显式传 `"scale":100`，否则后续 rect/quad 的尺寸假设全错。

### 14. 旋转后再变换

横屏图先 `edit.transform.rotate90Cw`（绕图层中心旋转，图层原点随之变化），再 `edit.transform` 映射到目标框。

### 15. `photocraft-cli commands <filter>` 不过滤

必须写 `photocraft-cli commands --filter <text>`。同理，`describe` 子命令是 `filmcraft-cli` 独有的，PhotoCraft 没有。

## FilmCraft 专属

### 16. 时间基是 ticks

1 秒 = 254016000000 ticks。命令也接受 `seconds` / `frame` / `timecode`，但返回值常是 ticks——换算别用浮点。

### 17. 依赖选区的命令在无选择时禁用

除非在命令文档规定的键里点名目标（`clips`/`clip`、`items`/`item`），如 `clip.replaceFromBin {"clips":[12],"item":4}`。

### 18. 元素 id 来自上一帧

布局变化后元素会短暂缺失，应用会在后续帧重试。点击失败时先 `ui.elements` 重新取 id。

### 19. 离线媒体渲染成占位符

离线素材渲染为占位符并在 stderr 列出（`item 8 a.mp4 (missing): /path`），写完后 exit 1；`--allow-offline` 接受占位（exit 0）。导出结果里看 `offlineMedia` 字段。

### 20. 上游文档描述的是 `main` 分支，不是你手上那个二进制

ArtCraft 应用在仓库 `main` 上持续开发，文档经常**领先于已发布版本**。实测例子：上游文档说 FilmCraft 通道强制 token、缺 token 不监听端口，而已发布的 0.9.0 完全不强制。

- 处理：文档用来**理解设计**（知道将来会变），行为用**实测**确认（`craft_ctl.py` 直连、`<cli> --help`、通道 `methods`）。两者冲突时，以你机器上的实际表现为准，并回头更新本表。

## 排障速查表

| 症状 | 原因 | 处理 |
|---|---|---|
| Connection refused | 应用没起，或随启动 shell 被回收 | `nohup ... & disown`；检查日志的 `control server listening` |
| 连接建上但立刻被关 | PhotoCraft 忘了 auth | 用 `craft_ctl.py --app <app>` 让它按应用套认证 |
| `unknown method` | 方法名拼错或跨应用套用 | 先查注册表：`engine.commands` / `methods` / `<cli> commands` |
| `unknown command` | 命令 id 不存在或已改名 | 同上，按 label/menu 找 |
| 请求超时 | 窗口不在绘制帧；或命令真的很久 | 置前窗口或改 headless；长任务用 `wait:false` 再轮询 |
| PhotoCraft 回 `authentication required` | 没做 auth 首帧 | `--token-file` |
| `photocraft --help` 开了窗口 | 它不认 `--help` | 用 `strings` 或通道 `methods` |
| 导出返回非零但文件存在 | 原子保存的改名被系统策略拦截 | 从 `/tmp` 暂存再复制 |
| 命令执行了但状态没变 | 编辑进了 undo 栈但对象不同 | 重读状态：`photo.inspect` / `sequence.inspect` / `document.inspect` |
| MCP 客户端报找不到可执行文件 | 用了 `~` 或相对路径 | JSON 里写绝对路径 |

## 崩溃排查

- macOS 崩溃报告：`~/Library/Logs/DiagnosticReports/<App>-*.ips`
- 应用日志：`~/Library/Application Support/<App>/logs/`
