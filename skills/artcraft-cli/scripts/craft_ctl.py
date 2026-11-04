#!/usr/bin/env python3
"""craft_ctl.py - ArtCraft 控制通道的通用 JSON-lines 客户端。

ArtCraft 套件（LightCraft / FilmCraft / PhotoCraft）在桌面上开一个仅 loopback 的
JSON-lines 控制通道：一行一个 JSON 请求，一行一个 JSON 回复，按序一一对应。

本脚本兼容三家通道的**认证差异**，这是通用化后的核心：
  light  无认证          —— 直接发请求
  film   顶层 token 字段  —— 每个请求都带 "token"
  photo  auth 首帧握手    —— 每个连接第一帧必须是 {"method":"auth",...}

用法：
  # 通用形式（推荐）：按应用名走，自动套用正确的认证方式
  craft_ctl.py --app light --port 7980 engine.commands
  craft_ctl.py --app film  --port 9876 --method engine.execute --params '{"command":"sequence.inspect"}'
  craft_ctl.py --app photo --port 7878 --token-file ~/photocraft-control.token '{"method":"ui.inspect"}'

  # 旧的纯端口写法仍然可用（未指定 --app 时凭据按 PhotoCraft 的首帧握手处理）
  craft_ctl.py 7980 engine.commands

  # 条件发现：打印命令注册表精简表（--filter 过滤，避免上千行刷屏）
  craft_ctl.py --app light --port 7980 --discover --filter develop

  # 脚本模式：stdin 每行一个请求，'#' 开头为注释
  echo '{"method":"engine.commands"}' | craft_ctl.py --app light --port 7980

退出码：全部回复 ok=true → 0；出现 ok=false → 1；用法/连接错误 → 2。
"""

import argparse
import json
import os
import socket
import sys
from pathlib import Path

MAX_LINE = 4 * 1024 * 1024  # 服务端拒绝超过 4 MiB 的行

# 每个应用的认证方式与凭据入口
APPS = {
    "light": {"auth": "none",  "token_env": None,
              "token_file_env": None},
    "film":  {"auth": "field", "token_env": "FILMCRAFT_CONTROL_TOKEN",
              "token_file_env": None},
    "photo": {"auth": "frame", "token_env": "PHOTOCRAFT_CONTROL_TOKEN",
              "token_file_env": "PHOTOCRAFT_CONTROL_TOKEN_FILE"},
}

# PhotoCraft 常见的 token 文件落位（只读取，不创建）
TOKEN_CANDIDATES = [
    "~/photocraft-control.token",
    "~/.photocraft/control.token",
    "~/Library/Application Support/ai.storyteller.photocraft/control.token",
]


def parse_args(argv):
    p = argparse.ArgumentParser(
        description="ArtCraft 控制通道 JSON-lines 客户端（LightCraft / FilmCraft / PhotoCraft）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("args", nargs="*",
                   help="位置参数：可选的端口（纯数字）+ JSON 请求对象或裸方法名")
    p.add_argument("--app", choices=sorted(APPS),
                   help="目标应用，决定认证方式与凭据来源：light=无认证 film=token 字段 photo=auth 首帧")
    p.add_argument("--port", dest="port_opt", type=int, metavar="PORT",
                   help="控制通道端口（与位置参数等价）")
    p.add_argument("--host", default="127.0.0.1",
                   help="默认 127.0.0.1（通道仅 loopback）")
    p.add_argument("--timeout", type=float, default=30.0,
                   help="单次请求超时秒数（默认 30；服务端回复上限 60，长任务请用 wait:false）")
    p.add_argument("--method", help="用 --params 构造单个请求的方法名")
    p.add_argument("--params", help='--method 的 JSON 参数，如 \'{"command":"library.next"}\'')
    p.add_argument("--token", help="bearer token（64 位十六进制）")
    p.add_argument("--token-file", help="存放 token 的文件路径")
    p.add_argument("--auth-mode", choices=["auto", "none", "frame", "field"],
                   default="auto", help="认证方式：auto=按 --app 推断（默认）")
    p.add_argument("--discover", action="store_true",
                   help="发送 engine.commands 并打印精简命令表")
    p.add_argument("--filter", help="配合 --discover 按 id/label 过滤")
    p.add_argument("--pretty", action="store_true", help="缩进输出回复")
    return p.parse_args(argv)


def split_args(args):
    """位置参数两种写法都支持：`7980 engine.commands` 与 `--port 7980 engine.commands`。"""
    items = list(args.args)
    if args.port_opt:
        return args.port_opt, items
    if items and items[0].isdigit():
        return int(items[0]), items[1:]
    return None, items


def resolve_token(args):
    """凭据来源优先级：--token > --token-file > 应用的环境变量 > 常见 token 文件落位。"""
    if args.token:
        return args.token.strip(), "--token"
    if args.token_file:
        path = Path(os.path.expanduser(args.token_file))
        if not path.is_file():
            raise SystemExit("error: token 文件不存在: %s" % path)
        return path.read_text(encoding="utf-8").strip(), str(path)
    if args.app:
        spec = APPS[args.app]
        if spec["token_file_env"] and os.environ.get(spec["token_file_env"]):
            path = Path(os.path.expanduser(os.environ[spec["token_file_env"]]))
            if path.is_file():
                return path.read_text(encoding="utf-8").strip(), str(path)
        if spec["token_env"] and os.environ.get(spec["token_env"]):
            return os.environ[spec["token_env"]].strip(), "环境变量 %s" % spec["token_env"]
        if spec["auth"] == "frame":
            for cand in TOKEN_CANDIDATES:
                path = Path(os.path.expanduser(cand))
                if path.is_file():
                    return path.read_text(encoding="utf-8").strip(), str(path)
    return None, None


def resolve_auth_mode(args, token):
    if args.auth_mode != "auto":
        return args.auth_mode
    if args.app:
        return APPS[args.app]["auth"]
    return "frame" if token else "none"


def collect_requests(args, positional):
    reqs = []
    if args.method:
        params = json.loads(args.params) if args.params else None
        reqs.append({"method": args.method, "params": params})
    for r in positional:
        r = r.strip()
        if not r:
            continue
        reqs.append(json.loads(r) if r.startswith("{") else {"method": r})
    if args.discover:
        reqs.append({"method": "engine.commands"})
    if not reqs and not sys.stdin.isatty():
        for line in sys.stdin:
            line = line.strip()
            if line and not line.startswith("#"):
                reqs.append(json.loads(line))
    return reqs


def roundtrip(fh, req, timeout):
    line = json.dumps(req, ensure_ascii=False) + "\n"
    if len(line.encode("utf-8")) > MAX_LINE:
        raise SystemExit("error: 请求行超过 4 MiB 上限")
    fh.write(line.encode("utf-8"))
    fh.flush()
    raw = fh.readline()
    if not raw:
        raise SystemExit(
            "error: 连接被应用关闭（首行不是合法请求？凭据缺失或错误？"
            "非 JSON / 数组 / 缺 method / 超 4 MiB 的行都会导致对端直接断开）")
    return json.loads(raw.decode("utf-8", "replace"))


def print_reply(reply, pretty):
    print(json.dumps(reply, ensure_ascii=False, indent=2 if pretty else None))


def print_registry(result, flt):
    """把 engine.commands 的返回压成一张可读的表。"""
    items = result if isinstance(result, list) else []
    if isinstance(result, dict) and isinstance(result.get("commands"), list):
        items = result["commands"]
    rows = []
    for c in items:
        if not isinstance(c, dict):
            continue
        cid = str(c.get("id", ""))
        label = str(c.get("label", "") or "")
        menu = str(c.get("menu", "") or "")
        hay = " ".join([cid, label, menu]).lower()
        if flt and flt.lower() not in hay:
            continue
        enabled = c.get("enabled")
        flag = "" if enabled is None else ("+" if enabled else "-")
        rows.append((cid, label, menu, flag))
    if not rows:
        print("(命令注册表为空，或过滤条件无匹配)")
        return
    w_id = max(len(r[0]) for r in rows)
    w_lb = max(min(len(r[1]), 48) for r in rows)
    print("%-*s  %-*s  %-28s %s" % (w_id, "id", w_lb, "label", "menu", "en"))
    print("-" * (w_id + w_lb + 40))
    for cid, label, menu, flag in rows:
        print("%-*s  %-*s  %-28s %s" % (w_id, cid, w_lb, label[:48], menu[:28], flag))
    print("(+ = enabled, - = disabled；共 %d 条)" % len(rows))


def main(argv):
    args = parse_args(argv)
    port, positional = split_args(args)
    if not port:
        print("error: 缺少端口。用 --port 或位置参数给出应用的 --control 端口，"
              "或先用 craft_env.py 找出正在运行的通道。", file=sys.stderr)
        return 2

    token, token_src = resolve_token(args)
    auth_mode = resolve_auth_mode(args, token)

    if auth_mode == "field" and not token:
        print("note: 未找到 token，按无凭据方式发送。新版 FilmCraft 会要求每个请求带 "
              "顶层 token 字段并因此拒绝；旧版（如 0.9.0）不强制。", file=sys.stderr)
    if auth_mode == "frame" and not token:
        print("warning: 未找到 token，跳过 auth 首帧。PhotoCraft 会回复 "
              "'authentication required'（用 --token-file 指定应用启动时的 token 文件）。",
              file=sys.stderr)

    reqs = collect_requests(args, positional)
    if not reqs:
        print("error: 没有要发的请求（给方法名、JSON 对象，或用 --discover，或从 stdin 管道输入）",
              file=sys.stderr)
        return 2

    try:
        sock = socket.create_connection((args.host, port), timeout=args.timeout)
    except OSError as exc:
        print("error: 连不上 %s:%s（%s）" % (args.host, port, exc), file=sys.stderr)
        print("hint: 先用 --control <port> 启动对应应用；"
              "裸 '&' 启动的 GUI 会随 shell 退出被回收，用 nohup ... & disown，"
              "或把「启动→操控」写在同一条命令里。", file=sys.stderr)
        return 2

    sock.settimeout(args.timeout)
    fh = sock.makefile("rwb")
    ok = True
    try:
        if auth_mode == "frame":
            reply = roundtrip(fh, {"id": "auth", "method": "auth",
                                   "params": {"token": token}}, args.timeout)
            print_reply(reply, args.pretty)
            if not reply.get("ok"):
                return 1

        next_id = 1
        for req in reqs:
            req = dict(req)
            req.setdefault("id", next_id)
            next_id += 1
            if auth_mode == "field":
                req["token"] = token
            reply = roundtrip(fh, req, args.timeout)
            if args.discover and req.get("method") == "engine.commands" and reply.get("ok"):
                print_registry(reply.get("result"), args.filter)
            else:
                print_reply(reply, args.pretty)
            if not reply.get("ok"):
                ok = False
    except (socket.timeout, TimeoutError):
        print("error: 请求超时（%ss）。窗口没有绘制帧时（最小化/被遮挡/睡眠）会这样；"
              "改用 headless 截图或让长任务带 wait:false 后轮询状态。" % args.timeout,
              file=sys.stderr)
        return 2
    except OSError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    finally:
        try:
            fh.close()
            sock.close()
        except OSError:
            pass
    if token_src and auth_mode != "none":
        print("note: 凭据来源 %s（%s）" % (token_src, auth_mode), file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
