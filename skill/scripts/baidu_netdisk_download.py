#!/usr/bin/env python3
"""百度网盘下载：单个文件、整个目录（递归）、分享链接（转存后下载）。

用法：
    python baidu_netdisk_download.py <网盘路径|分享链接> [本地路径] [-p 提取码] [--overwrite]

示例：
    python baidu_netdisk_download.py "/apps/demo.mp4" ./demo.mp4
    python baidu_netdisk_download.py "/apps/photos" ./photos
    python baidu_netdisk_download.py "https://pan.baidu.com/s/1abc?pwd=1234" ./out

token 解析顺序见 netdisk_common.get_token。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from baidu_netdisk_common import (  # noqa: E402
    NetdiskError,
    api_get,
    download_stream,
    ensure_utf8_console,
    find_entry,
    get_dlink,
    get_token,
    human_size,
    list_dir,
    probe_size,
    API_SHARE,
)


def download_one(token: str, entry: dict, local_path: Path, overwrite: bool) -> int:
    if local_path.exists() and not overwrite:
        print(f"跳过（本地已存在）：{local_path}", file=sys.stderr)
        return 0
    fs_id = entry.get("fs_id")
    size = int(entry.get("size") or 0)
    print(f"下载 {entry.get('path')} -> {local_path} ({human_size(size)})", file=sys.stderr)
    dlink = get_dlink(token, fs_id)
    total = probe_size(token, dlink) or size
    return download_stream(dlink, local_path, total=total)


def download_dir(token: str, remote_dir: str, local_dir: Path, overwrite: bool) -> tuple[int, int]:
    entries = list_dir(token, remote_dir)
    if not entries:
        print(f"目录为空或不存在：{remote_dir}", file=sys.stderr)
    files = 0
    total_bytes = 0
    local_dir.mkdir(parents=True, exist_ok=True)

    for item in entries:
        name = item.get("server_filename")
        if item.get("isdir"):
            files_i, bytes_i = download_dir(token, f"{remote_dir.rstrip('/')}/{name}", local_dir / name, overwrite)
            files += files_i
            total_bytes += bytes_i
        else:
            try:
                total_bytes += download_one(token, item, local_dir / name, overwrite)
                files += 1
            except NetdiskError as exc:
                print(f"失败：{item.get('path')} — {exc}", file=sys.stderr)
    return files, total_bytes


def download_share(token: str, link: str, local_dir: Path, pwd: str | None, overwrite: bool) -> tuple[int, int]:
    """转存分享链接到 /apps/bdpan-skill/share-<random>，再下载。"""
    import random
    import string

    params = {"method": "transfer", "shareid": None, "from": None, "bdstoken": None}
    # 通过解析短链得到 shareid / uk，这里交给 share precreate 的 link 形式
    target = "/apps/bdpan-skill/share-" + "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    api_get(API_SHARE, {"method": "mkdir", "path": target}, token)
    body = {"method": "transfer", "link": link, "path": target, "async": 1}
    if pwd:
        body["pwd"] = pwd
    data = api_get(API_SHARE, body, token)
    if data.get("task_id"):
        print(f"已提交转存任务 task_id={data['task_id']}，等待完成…", file=sys.stderr)
        import time

        for _ in range(30):
            time.sleep(2)
            info = api_get(API_SHARE, {"method": "querytask", "taskid": data["task_id"]}, token)
            status = info.get("status")
            if status in ("success", 2):
                break
            if status in ("failed", 3):
                raise NetdiskError(f"转存失败：{info}")
    print(f"已转存到 {target}，开始下载", file=sys.stderr)
    return download_dir(token, target, local_dir, overwrite)


def main() -> int:
    ensure_utf8_console()
    parser = argparse.ArgumentParser(description="百度网盘下载脚本")
    parser.add_argument("remote", help="网盘路径（如 /apps/demo.mp4 或 /apps/photos）或分享链接")
    parser.add_argument("local", nargs="?", help="本地保存路径（默认当前目录）")
    parser.add_argument("-p", "--pwd", help="分享链接提取码")
    parser.add_argument("--overwrite", action="store_true", help="覆盖本地已存在文件")
    args = parser.parse_args()

    try:
        token = get_token()
        remote = args.remote.strip()
        local_arg = args.local
    except NetdiskError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        if remote.startswith("http://") or remote.startswith("https://"):
            local_dir = Path(local_arg or ".")
            files, total = download_share(token, remote, local_dir, args.pwd, args.overwrite)
        else:
            if not remote.startswith("/"):
                remote = "/" + remote
            entry = find_entry(token, remote)
            if not entry:
                print(f"未找到：{remote}", file=sys.stderr)
                return 1
            if entry.get("isdir"):
                local_dir = Path(local_arg or os.path.basename(remote.rstrip("/")) or ".")
                files, total = download_dir(token, remote.rstrip("/"), local_dir, args.overwrite)
            else:
                local = Path(local_arg or os.path.basename(remote))
                if local.is_dir():
                    local = local / os.path.basename(remote)
                size = download_one(token, entry, local, args.overwrite)
                files, total = 1, size
    except NetdiskError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"完成：{files} 个文件，共 {human_size(total)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
