#!/usr/bin/env python3
"""craft_env.py - 探测 ArtCraft 套件在本机的安装、版本与运行状态。

用途：任何自动化动作之前先跑一次，把"我以为的版本/路径"换成"机器上的事实"。
脚本不猜测、不修改系统，只读。无法探测的项返回 null 并给出说明，而不是编造。

用法：
  craft_env.py                     # JSON（默认）
  craft_env.py --table             # 人读表格
  craft_env.py --snapshot          # Markdown 快照（可粘贴进 references/verified-environments.md）
  craft_env.py --app photo         # 只看某一个应用
  craft_env.py --app-dir /custom   # 追加应用搜索目录（可重复）

环境变量：
  ARTCRAFT_APP_DIRS   冒号分隔的额外应用搜索目录，优先于内置默认值
"""

import argparse
import json
import os
import plistlib
import shutil
import subprocess
import sys
import stat
from pathlib import Path

# --------------------------------------------------------------------------
# 应用注册表：认证方式与凭据入口随版本演进，这里给出"当前已知"的一档，
# 实际使用前仍应以运行中实例的 methods/engine.commands 为准。
# --------------------------------------------------------------------------
APPS = {
    "light": {
        "name": "LightCraft",
        "role": "RAW 修图 / 照片管理",
        "cli": "lightcraft-cli",
        "bundle_id": "ai.storyteller.lightcraft",
        "port_env": "LIGHTCRAFT_CONTROL_PORT",
        "token_env": None,
        "token_file_env": None,
        "auth": "none",
    },
    "film": {
        "name": "FilmCraft",
        "role": "非线性视频剪辑",
        "cli": "filmcraft-cli",
        "bundle_id": "ai.storyteller.filmcraft",
        "port_env": "FILMCRAFT_CONTROL_PORT",
        "token_env": "FILMCRAFT_CONTROL_TOKEN",
        "token_file_env": None,
        "auth": "field",
    },
    "photo": {
        "name": "PhotoCraft",
        "role": "位图编辑",
        "cli": "photocraft-cli",
        "bundle_id": "ai.storyteller.photocraft",
        "port_env": "PHOTOCRAFT_CONTROL_PORT",
        "token_env": "PHOTOCRAFT_CONTROL_TOKEN",
        "token_file_env": "PHOTOCRAFT_CONTROL_TOKEN_FILE",
        "auth": "frame",
    },
}

# 常见的 token 文件落位（PhotoCraft 系）。只报告存在的，不创建。
TOKEN_CANDIDATES = {
    "photo": [
        "~/photocraft-control.token",
        "~/.photocraft/control.token",
        "~/Library/Application Support/ai.storyteller.photocraft/control.token",
        "~/.config/photocraft/control.token",
    ],
    "film": [
        "~/filmcraft-control.token",
        "~/.filmcraft/control.token",
    ],
    "light": [],
}

CLI_EXTRA_DIRS = [
    "/usr/local/bin",
    "/opt/homebrew/bin",
    "~/.local/bin",
    "~/bin",
    "/usr/bin",
]


def default_app_dirs():
    if sys.platform == "darwin":
        dirs = ["/Applications", str(Path.home() / "Applications")]
    elif os.name == "nt":
        dirs = []
        for var in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            base = os.environ.get(var)
            if base:
                dirs.append(str(Path(base) / "ArtCraft"))
                dirs.append(base)
    else:
        dirs = ["/opt", "/usr/share", "/usr/local/share", "/usr/local/bin"]
    return dirs


def app_search_dirs(extra):
    dirs = list(extra)
    env = os.environ.get("ARTCRAFT_APP_DIRS")
    if env:
        dirs.extend(p for p in env.split(os.pathsep) if p)
    dirs.extend(default_app_dirs())
    seen, out = set(), []
    for d in dirs:
        p = os.path.expanduser(d)
        if p and p not in seen and Path(p).is_dir():
            seen.add(p)
            out.append(p)
    return out


def read_bundle_plist(app_path):
    """macOS .app -> Info.plist；Linux/Windows 目录找不到就返回 None。"""
    candidates = [
        Path(app_path) / "Contents" / "Info.plist",
        Path(app_path) / "Info.plist",
    ]
    for cand in candidates:
        if cand.is_file():
            try:
                with open(cand, "rb") as fh:
                    return plistlib.load(fh)
            except Exception:
                return None
    return None


def find_app(key, search_dirs):
    spec = APPS[key]
    name = spec["name"]
    found = {
        "key": key,
        "name": name,
        "role": spec["role"],
        "installed": False,
        "path": None,
        "version": None,
        "build": None,
        "bundle_id": None,
        "binary": None,
        "note": None,
    }
    for d in search_dirs:
        for cand in (Path(d) / f"{name}.app", Path(d) / name):
            if not cand.exists():
                continue
            found["installed"] = True
            found["path"] = str(cand)
            plist = read_bundle_plist(cand)
            if plist:
                found["version"] = plist.get("CFBundleShortVersionString")
                found["build"] = plist.get("CFBundleVersion")
                found["bundle_id"] = plist.get("CFBundleIdentifier")
            if sys.platform == "darwin" and cand.suffix == ".app":
                exe = cand / "Contents" / "MacOS" / name
                if exe.is_file():
                    found["binary"] = str(exe)
            elif cand.is_dir():
                for exe in cand.glob("*" + name.lower() + "*"):
                    if exe.is_file() and exe.suffix in ("", ".exe"):
                        found["binary"] = str(exe)
                        break
            return found
    found["note"] = "未在 %s 中找到 %s" % (", ".join(search_dirs), name)
    return found


def find_cli(key):
    spec = APPS[key]
    cli = spec["cli"]
    path = shutil.which(cli)
    if path:
        return {"name": cli, "installed": True, "path": path, "source": "PATH"}
    for d in CLI_EXTRA_DIRS:
        cand = Path(os.path.expanduser(d)) / cli
        if cand.is_file() and os.access(cand, os.X_OK):
            return {"name": cli, "installed": True, "path": str(cand), "source": d}
    return {"name": cli, "installed": False, "path": None, "source": None,
            "note": "CLI 是独立 release 资产，Launcher 不安装；见 references/cli-reference.md"}


def running_channels():
    """找出正在跑、且开了 --control 的实例：pid、端口、命令行里的凭据路径。"""
    out = []
    try:
        if sys.platform == "darwin":
            proc = subprocess.run(["ps", "-Ao", "pid=,args="], capture_output=True,
                                  text=True, timeout=10)
        else:
            proc = subprocess.run(["ps", "-eo", "pid=,args="], capture_output=True,
                                  text=True, timeout=10)
    except Exception:
        return out
    if proc.returncode != 0:
        return out
    names = {spec["name"] for spec in APPS.values()}
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        matched = next((n for n in names if n in line), None)
        if not matched or "--control" not in line:
            continue
        parts = line.split()
        port = None
        token_file = None
        for i, tok in enumerate(parts):
            if tok == "--control" and i + 1 < len(parts):
                port = parts[i + 1]
            if tok == "--control-token-file" and i + 1 < len(parts):
                token_file = parts[i + 1]
        try:
            pid = int(parts[0])
        except ValueError:
            pid = None
        out.append({
            "app": matched,
            "pid": pid,
            "port": port,
            "token_file": token_file,
            "cmdline": line[:300],
        })
    return out


def token_state(key):
    spec = APPS[key]
    info = {
        "auth": spec["auth"],
        "token_env": spec["token_env"],
        "token_env_set": bool(spec["token_env"] and os.environ.get(spec["token_env"])),
        "token_file_env": spec["token_file_env"],
        "token_file_env_path": os.environ.get(spec["token_file_env"]) if spec["token_file_env"] else None,
        "files": [],
    }
    cands = list(TOKEN_CANDIDATES.get(key, []))
    if spec["token_file_env"] and os.environ.get(spec["token_file_env"]):
        cands.insert(0, os.environ[spec["token_file_env"]])
    for cand in cands:
        p = Path(os.path.expanduser(cand))
        if not p.is_file():
            continue
        try:
            mode = stat.S_IMODE(p.stat().st_mode)
        except OSError:
            mode = None
        info["files"].append({
            "path": str(p),
            "mode": oct(mode) if mode is not None else None,
            "mode_ok": (mode is not None and mode & 0o077 == 0),
            "size": p.stat().st_size,
        })
    if spec["auth"] == "none":
        info["note"] = "该应用控制通道无认证：任何本机进程都能驱动，用完即关"
    elif spec["auth"] == "field":
        info["note"] = "凭据放在每个请求的顶层 token 字段（不是独立 auth 帧）"
    else:
        info["note"] = "每个连接首帧必须是 auth 请求"
    return info


def collect(only=None):
    keys = [only] if only in APPS else list(APPS)
    search = app_search_dirs([])
    data = {
        "platform": sys.platform,
        "python": sys.version.split()[0],
        "home": str(Path.home()),
        "app_search_dirs": search,
        "apps": {},
        "clis": {},
        "channels": running_channels(),
        "tokens": {},
    }
    for key in keys:
        data["apps"][key] = find_app(key, search)
        data["clis"][key] = find_cli(key)
        data["tokens"][key] = token_state(key)
    return data


def render_table(d):
    lines = []
    lines.append("ArtCraft 环境自检")
    lines.append("=" * 60)
    lines.append("平台: %s   应用搜索目录: %s" % (d["platform"], ", ".join(d["app_search_dirs"]) or "(无)"))
    lines.append("")
    lines.append("应用")
    lines.append("-" * 60)
    for key, a in d["apps"].items():
        if a["installed"]:
            lines.append("  %-11s %-9s %s" % (a["name"], a["version"] or "?", a["path"]))
        else:
            lines.append("  %-11s 未安装" % a["name"])
    lines.append("")
    lines.append("CLI")
    lines.append("-" * 60)
    for key, c in d["clis"].items():
        if c["installed"]:
            lines.append("  %-16s %s" % (c["name"], c["path"]))
        else:
            lines.append("  %-16s 未安装" % c["name"])
    lines.append("")
    lines.append("正在运行的控制通道")
    lines.append("-" * 60)
    if d["channels"]:
        for c in d["channels"]:
            lines.append("  %-11s pid=%-7s port=%-6s %s" % (
                c["app"], c["pid"], c["port"], c["cmdline"][:70]))
    else:
        lines.append("  （无）")
    lines.append("")
    lines.append("凭据")
    lines.append("-" * 60)
    for key, t in d["tokens"].items():
        head = "  %-11s auth=%-6s" % (APPS[key]["name"], t["auth"])
        if t["token_env_set"]:
            head += " %s 已设置" % t["token_env"]
        lines.append(head)
        for f in t["files"]:
            lines.append("      %s  mode=%s%s" % (
                f["path"], f["mode"], "" if f["mode_ok"] else "  <- 权限过宽"))
        if t["note"]:
            lines.append("      %s" % t["note"])
    return "\n".join(lines)


def render_snapshot(d):
    lines = ["## 环境快照", ""]
    lines.append("由 `scripts/craft_env.py --snapshot` 生成，自动更新，**不是权威来源**。")
    lines.append("")
    lines.append("- 平台: %s / Python %s" % (d["platform"], d["python"]))
    lines.append("")
    lines.append("| 应用 | 版本 | 安装路径 | CLI | 通道认证 |")
    lines.append("|---|---|---|---|---|")
    for key, a in d["apps"].items():
        c = d["clis"][key]
        lines.append("| %s | %s | %s | %s | %s |" % (
            a["name"], a["version"] or "-",
            "`%s`" % a["path"] if a["path"] else "未安装",
            "`%s`" % c["path"] if c["installed"] else "未安装",
            d["tokens"][key]["auth"]))
    lines.append("")
    if d["channels"]:
        lines.append("正在运行的通道: " + ", ".join(
            "%s pid=%s port=%s" % (c["app"], c["pid"], c["port"]) for c in d["channels"]))
    else:
        lines.append("正在运行的通道: 无")
    return "\n".join(lines)


def main(argv):
    p = argparse.ArgumentParser(description="探测 ArtCraft 套件的本机安装与运行状态")
    p.add_argument("--app", choices=sorted(APPS), help="只看某一个应用 (light|film|photo)")
    p.add_argument("--app-dir", action="append", default=[], help="追加应用搜索目录，可重复")
    p.add_argument("--table", action="store_true", help="人读表格输出")
    p.add_argument("--snapshot", action="store_true", help="Markdown 快照输出")
    args = p.parse_args(argv)

    data = collect(args.app)
    if args.table:
        print(render_table(data))
    elif args.snapshot:
        print(render_snapshot(data))
    else:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
