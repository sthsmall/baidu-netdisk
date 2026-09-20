#!/usr/bin/env python3
"""共享工具：access_token 读取、网盘 API 调用、进度条。

token 采用三级回退，任一命中即用：
1. 环境变量 BAIDU_NETDISK_ACCESS_TOKEN
2. 凭证文件（默认 ~/.config/bdpan/access_token，可用 BDPAN_TOKEN_FILE 覆盖）
3. MCP 配置 ~/.config/opencode/opencode.jsonc 中的 baidu-netdisk 条目
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

import requests

API_FILE = "https://pan.baidu.com/rest/2.0/xpan/file"
API_MULTIMEDIA = "https://pan.baidu.com/rest/2.0/xpan/multimedia"
API_NAS = "https://pan.baidu.com/rest/2.0/xpan/nas"
API_SHARE = "https://pan.baidu.com/rest/2.0/xpan/share"

ERRNO_HINT = {
    0: "成功",
    -6: "身份验证失败，access_token 无效或已过期",
    -7: "文件或目录不存在",
    2: "参数错误",
    111: "access_token 无效或已过期，请重新授权",
    31034: "命中平台限流，请稍后重试",
    31066: "该目录不存在",
    42211: "该分享链接不存在或已失效",
    42214: "分享提取码错误",
}

DEFAULT_TOKEN_FILE = Path.home() / ".config" / "bdpan" / "access_token"
MCP_CONFIG = Path.home() / ".config" / "opencode" / "opencode.jsonc"


class NetdiskError(RuntimeError):
    pass


def _from_env() -> str | None:
    return (os.environ.get("BAIDU_NETDISK_ACCESS_TOKEN") or "").strip() or None


def _from_token_file() -> str | None:
    path = Path(os.environ.get("BDPAN_TOKEN_FILE") or DEFAULT_TOKEN_FILE)
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        return line
    return None


def _from_mcp_config() -> str | None:
    if not MCP_CONFIG.is_file():
        return None
    text = MCP_CONFIG.read_text(encoding="utf-8")
    text = re.sub(r"^\s*//.*$", "", text, flags=re.M)
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    try:
        conf = json.loads(text)
    except json.JSONDecodeError:
        return None
    mcp = conf.get("mcp", {}) or {}
    for name, entry in mcp.items():
        if not isinstance(entry, dict):
            continue
        if name == "baidu-netdisk":
            m = re.search(r"access_token=([^&\s\"]+)", entry.get("url", "") or "")
            if m:
                return m.group(1).strip()
        if name == "baidu-netdisk-upload":
            tok = (entry.get("environment", {}) or {}).get("BAIDU_NETDISK_ACCESS_TOKEN")
            if tok:
                return str(tok).strip()
    return None


def get_token(required: bool = True) -> str | None:
    for source in (_from_env, _from_token_file, _from_mcp_config):
        tok = source()
        if tok:
            return tok
    if required:
        raise NetdiskError(
            "未找到 access_token。请设置环境变量 BAIDU_NETDISK_ACCESS_TOKEN，"
            f"或把 token 写入 {DEFAULT_TOKEN_FILE}"
        )
    return None


def api_get(url: str, params: dict, token: str, timeout: int = 30) -> dict:
    params = dict(params)
    params["access_token"] = token
    try:
        resp = requests.get(url, params=params, timeout=timeout)
    except requests.RequestException as exc:
        raise NetdiskError(f"请求失败：{exc}") from exc
    if resp.status_code != 200:
        raise NetdiskError(f"HTTP {resp.status_code}：{resp.text[:300]}")
    try:
        data = resp.json()
    except ValueError as exc:
        raise NetdiskError(f"响应不是合法 JSON：{resp.text[:300]}") from exc
    errno = data.get("errno")
    if errno not in (0, None):
        hint = ERRNO_HINT.get(errno, data.get("errmsg") or data.get("err_msg") or "未知错误")
        raise NetdiskError(f"网盘接口 errno={errno}：{hint}")
    return data


def list_dir(token: str, remote_dir: str, page_size: int = 1000) -> list[dict]:
    """列出目录全部条目（自动分页）。remote_dir 需以 / 开头。"""
    if not remote_dir.startswith("/"):
        remote_dir = "/" + remote_dir
    items: list[dict] = []
    start = 0
    while True:
        data = api_get(
            API_FILE,
            {"method": "list", "dir": remote_dir, "order": "name", "start": start, "limit": page_size},
            token,
        )
        batch = data.get("list") or []
        items.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size
    return items


def find_entry(token: str, remote_path: str) -> dict | None:
    """按完整路径查找单条目，返回 list 元素。"""
    remote_path = remote_path.rstrip("/") or "/"
    parent = "/" + "/".join(remote_path.split("/")[1:-1])
    name = remote_path.rsplit("/", 1)[-1]
    for item in list_dir(token, parent or "/"):
        if item.get("server_filename") == name or item.get("path") == remote_path:
            return item
    return None


def get_dlink(token: str, fs_id: int | str) -> str:
    data = api_get(
        API_MULTIMEDIA,
        {"method": "filemetas", "fsids": json.dumps([int(fs_id)]), "dlink": 1},
        token,
    )
    entries = data.get("list") or []
    if not entries or not entries[0].get("dlink"):
        raise NetdiskError(f"无法获取下载直链（fs_id={fs_id}）")
    return entries[0]["dlink"] + "&access_token=" + token


def probe_size(token: str, dlink: str) -> int:
    try:
        resp = requests.head(dlink, headers={"User-Agent": "pan.baidu.com"}, timeout=20, allow_redirects=True)
        return int(resp.headers.get("Content-Length") or 0)
    except (requests.RequestException, ValueError):
        return 0


def download_stream(dlink: str, local_path: Path, total: int = 0, retries: int = 3) -> int:
    """流式下载到文件，返回字节数。先写 .part 再改名，支持重试续传。"""
    local_path.parent.mkdir(parents=True, exist_ok=True)
    part = local_path.with_name(local_path.name + ".part")
    done = part.stat().st_size if part.exists() else 0
    if total and done >= total:
        part.replace(local_path)
        return done

    for attempt in range(1, retries + 1):
        headers = {"User-Agent": "pan.baidu.com"}
        if done:
            headers["Range"] = f"bytes={done}-"
        try:
            resp = requests.get(dlink, headers=headers, stream=True, timeout=60)
            if resp.status_code not in (200, 206):
                raise NetdiskError(f"下载失败：HTTP {resp.status_code}")
            if not total:
                total = done + int(resp.headers.get("Content-Length") or 0)
            mode = "ab" if done and resp.status_code == 206 else "wb"
            if mode == "wb":
                done = 0
            last = time.monotonic()
            with open(part, mode) as fh:
                for chunk in resp.iter_content(1024 * 256):
                    if not chunk:
                        continue
                    fh.write(chunk)
                    done += len(chunk)
                    now = time.monotonic()
                    if now - last >= 0.5:
                        _render_progress(done, total)
                        last = now
            _render_progress(done, total, final=True)
            if total and done < total:
                raise NetdiskError(f"传输中断：{done}/{total} 字节")
            part.replace(local_path)
            return done
        except (requests.RequestException, NetdiskError) as exc:
            if attempt >= retries:
                raise NetdiskError(f"下载失败（重试 {retries} 次后）：{exc}") from exc
            time.sleep(2 * attempt)
            done = part.stat().st_size if part.exists() else 0
    return done


def _render_progress(done: int, total: int, final: bool = False) -> None:
    if total:
        pct = done / total * 100
        bar_len = 24
        filled = int(bar_len * pct / 100)
        bar = "#" * filled + "-" * (bar_len - filled)
        text = f"\r  [{bar}] {pct:5.1f}% {done / 1048576:.1f}/{total / 1048576:.1f} MB"
    else:
        text = f"\r  已下载 {done / 1048576:.1f} MB"
    stream = sys.stderr
    try:
        stream.write(text)
        stream.flush()
    except Exception:
        pass
    if final:
        try:
            stream.write("\n")
            stream.flush()
        except Exception:
            pass


def human_size(num: int | float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num) < 1024 or unit == "TB":
            return f"{num:.1f}{unit}" if unit != "B" else f"{int(num)}B"
        num /= 1024
    return f"{num:.1f}TB"


def ensure_utf8_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
