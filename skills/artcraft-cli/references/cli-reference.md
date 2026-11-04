# CLI 参考

> 快照日期：2026-11-04。来源：上游仓库 README 与 `docs/agents.md` / `docs/mcp.md`（main 分支）。
> CLI 子命令随版本增删。**用 `<cli> --help`、`<cli> commands` 复核**，别照抄本表。

## 获取与安装

CLI 是**独立二进制**，不在 `.app` 里，ArtCraft Launcher 也不安装它。从 GitHub Releases 下载对应平台资产：

| 应用 | macOS 资产 | 其他平台 |
|---|---|---|
| LightCraft | `lightcraft-cli-<ver>-macos-universal.zip`（signed + notarized） | Linux：与 AppImage 同页；Windows：便携 zip |
| PhotoCraft | `photocraft-cli-<ver>-macos-universal.zip`（与 app 同一 Developer ID，首次运行在线校验 notarization） | Windows：`.msi` 或 `-portable.zip`；Linux：AppImage/deb/rpm/tarball |
| FilmCraft | `filmcraft-cli-<version>-macos-<arch>.zip`（`.app` 里只有桌面应用） | Windows：MSI 安装目录内的 `filmcraft-cli.exe`（默认不在 PATH）；Linux deb/rpm：`/usr/bin/filmcraft-cli` |

macOS 校验 notarization：

```sh
ditto -x -k photocraft-cli-<ver>-macos-universal.zip . && \
  spctl --assess --type install -vv ./photocraft-cli     # 应回 accepted, source=Notarized Developer ID
```

解压后建议软链到 PATH：`ln -s "$PWD/lightcraft-cli" /usr/local/bin/lightcraft-cli`。

源码构建（三家同构）：`cargo build --release -p <app>-cli`，或 `cargo install --path apps/<app>-cli --locked`（装到 `$CARGO_HOME/bin`，`cargo clean` 后仍可用）。

**本机有没有 CLI，用 `craft_env.py` 查，别用 `ls` 猜。**

## 通用规则（三家一致）

- 选项位置任意；输出 JSON；**退出码 0=成功，1=命令失败，2=用法错误**；`help` / `--help` / `-h` 打印参考并成功退出。
- `key=value` 的值能解析为 JSON 就按 JSON（`3.5`、`true`、`[1,2]`），否则当字符串；点号键表示嵌套（`color.r=1`）。
- 一个不带 `=` 的词开始下一条命令；`'{…}'` 参数把一个 JSON 对象合并进 params。
- **zsh 把 `[...]` 当 glob**，含方括号的参数要加引号：`'ids=[3,4]'`。
- 输出流早退（`filmcraft-cli commands | head`）时 CLI 会丢弃剩余输出。
- 离线媒体渲染为占位符并在 stderr 列出（`item 8 a.mp4 (missing): /path`），写完后 exit 1；`--allow-offline` 接受占位（exit 0）。导出结果含 `offlineMedia:[{item,name,path,status,error}]`。

## LightCraft CLI

```sh
# 一条命令链跑完：导入 → 编辑 → 导出（每命令一行 JSON）
lightcraft-cli run --import in.dng develop.set control=light.exposure value=0.7 \
    develop.auto app.export path=/tmp/a.jpg shortEdge=1080 colorSpace=displayP3

# 持久库：编辑会保存，后续调用能看到
lightcraft-cli run --library ~/lc-lib --import ~/Pictures/shoot library.info
lightcraft-cli run --library ~/lc-lib library.select ids=[3] develop.get

# 驱动运行中的应用（同套命令 + ui.* 方法）
lightcraft-cli run --connect 127.0.0.1:7980 ui.set view=detail ui.screenshot path=/tmp/ui.png

# JSON lines 脚本：{"command": id, "params": {…}} 或 {"method": "ui.inspect"}
lightcraft-cli run --demo --script steps.jsonl --keep-going
```

子命令：

```sh
lightcraft-cli render in.dng -o out.tif --opt colorSpace=displayP3 --opt bitDepth=16 --opt percent=50
lightcraft-cli render in.dng -o out.jpg --set light.exposure=0.5 --set light.contrast=20 --size 2048
lightcraft-cli render in.jpg -o out.png --settings look.json --preset <presetId>
lightcraft-cli render in.dng -o out.jpg --opt addToPhotos=true --opt photosAlbum=Trip   # macOS：导入 Apple Photos
lightcraft-cli snapshot --demo -o grid.png --size 1600x1000 [--scale 2]
lightcraft-cli snapshot --library DIR --script tour.jsonl -o shot.png
lightcraft-cli commands [--json]    # 命令注册表
lightcraft-cli controls [--json]    # develop 滑块 id 与范围
lightcraft-cli calibrate --max 300 ~/Pictures/2026   # 相机色彩配置
lightcraft-cli mcp [--connect 127.0.0.1:7980] [LIBRARY_DIR]
```

- `run` 每命令输出一行 JSON（`{command, ok, result|error, ms}`），失败时退出码非零。
- `export.contactSheet` 出联系表 PDF（A4/Letter、行列、文件名题注；限 1000 张 / 100 页 / 256 MiB；CJK 题注需 craft-fonts）。

## PhotoCraft CLI

```sh
# headless：打开→编辑→保存（一个 --cmd 配一个 --params，顺序执行）
photocraft-cli run wave.psd \
  --cmd filter.sharpen.smartSharpen     --params '{"amount":80}' \
  --cmd layer.newAdjustmentLayer.curves --params '{"points":[[0,0],[64,48],[192,212],[255,255]]}' \
  --out wave-final.png

# 新建画布起点
photocraft-cli run --new '{"width":1080,"height":1440,"background":"#FFFFFF","name":"xxx"}' --cmd ... --out out.png

# 动作清单批处理整个目录
photocraft-cli batch --actions grade.json --in ./raw --out ./graded

photocraft-cli commands                 # 全部命令 id（--json 出机器格式）
photocraft-cli commands --filter sharp  # 过滤（注意：不加 --filter 时命令不过滤）
photocraft-cli mcp                      # MCP 服务器（headless）
photocraft-cli mcp --bridge 127.0.0.1:7878 --control-token-file /path/token
photocraft-cli droplet                  # macOS droplet 自动化（.command 包装器）
```

- 输出格式由 `--out` 扩展名决定（`.png/.jpg/.webp/.psd/.tif` 等）。
- `--cmd` / `--params` 作用于前一个命令；`run` 的输入可以是现有图片或 PSD。
- env `PHOTOCRAFT_CLI` 可覆盖 CLI 路径（应用内 droplet 用）。

## FilmCraft CLI

```sh
filmcraft-cli commands razor                     # 按关键词找命令 id（--json 机器输出）
filmcraft-cli describe timeline.razor            # 单命令：菜单、快捷键、参数、当前启用态
filmcraft-cli --demo inspect sequence            # 项目 / 序列 JSON
filmcraft-cli --project p.fcproj --save exec timeline.razor seconds=3.5
filmcraft-cli --project p.fcproj exec effects.apply '{"effect":"Gaussian Blur"}'
filmcraft-cli --project p.fcproj exec markers.exportCsv path=review.csv
filmcraft-cli --project p.fcproj --save import a.mov b.wav
filmcraft-cli --project p.fcproj export out.mp4                          # 格式由扩展名决定；等待作业
filmcraft-cli --project p.fcproj export out --preset "YouTube 1080p Full HD" --start 0 --end 10
filmcraft-cli export --list-presets prores                              # 内置 + 用户预设（--data-dir 换库）
filmcraft-cli --project p.fcproj exec export.queue.add preset="Apple ProRes 422 HQ" path=renders/ start=true wait=true
echo '{"id":"file.newBin","params":{"name":"Selects"}}' | filmcraft-cli --project p.fcproj --save run -
filmcraft-cli --bridge 127.0.0.1:9876 exec window.workspace.color        # 驱动运行中的应用
filmcraft-cli mcp --demo            # headless MCP
filmcraft-cli mcp --bridge 127.0.0.1:9876
```

- `--save` 写回 `--project`；`--save-as path` 写别处。
- 无窗口脚本：`filmcraft-cli run script.jsonl`（每行 `{"id":"…","params":{…}}`）。
- `markers.exportCsv {path}`：全部序列标记转 UTF-8 CSV（CRLF、表头；公式字符前加 `'`）；不改动项目、脏标记、undo。

## 三条发现命令 id 的路

| 路径 | 适合 |
|---|---|
| `filmcraft-cli commands <kw>` / `photocraft-cli commands --filter <kw>` / `lightcraft-cli commands` | 有 CLI 时最省事 |
| 通道 `engine.commands` | 只想知道**当前实例**能做什么（注册表随状态变化，`enabled` 会变） |
| MCP `command_list {filter?, enabled_only?}` | 已经接了 MCP 客户端 |

**优先用运行中实例的注册表**——它带 `enabled` / `disabledReason`，能直接告诉你这条命令现在为什么不能点。

## 没有 CLI 时的降级：直接跑 GUI 二进制

三个 `.app/Contents/MacOS/<App>` 二进制本身接受部分参数：

| 应用 | 可用参数 | 备注 |
|---|---|---|
| LightCraft | `--control PORT`、`--library DIR`、`--no-demo`、`--memory`（内存会话）、`--version`、`--help`；位置参数=要导入的文件/文件夹 | `--help` 完整可用 |
| FilmCraft | `--control <port>`、`--control-input-only`、`--demo`、`--empty`、`--recover`/`--no-recover`、`--data-dir DIR`、`--graphics MODE`、`--version`、`-h/--help`；位置参数=project.fcproj 或媒体文件 | `--help` 完整可用；**需 `FILMCRAFT_CONTROL_TOKEN`** |
| PhotoCraft | `--control <port>`、`--control-token`/`--control-token-file`、`--automation-read-root`/`--automation-write-root`、`--safe-gpu`、`--in-window-menus` | **没有 `--help`**：会把 `--help` 当文件路径尝试打开并启动 GUI。用 `strings <binary> \| grep -i control` 或通道 `methods` 发现 flag |
