#!/usr/bin/env python3
"""百度网盘上传（CLI 友好）：单文件或整个目录（递归）。

用法：
    python upload.py <本地路径> <网盘目录> [--flat] [--overwrite]

示例：
    python upload.py ./report.pdf /apps/docs
    python upload.py ./photos /apps/backup          # 递归，保持目录结构
    python upload.py ./photos /apps/backup --flat   # 递归，全部平铺到目标目录

token 解析顺序（见 baidu_netdisk_common.py）：
    BAIDU_NETDISK_ACCESS_TOKEN 环境变量
    -> ~/.config/bdpan/access_token 凭证文件
    -> opencode.jsonc 中的 MCP 配置
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from baidu_netdisk_common import ensure_utf8_console, get_token, human_size  # noqa: E402

NETDISK_DIR = Path(__file__).resolve().parent / "netdisk-mcp-server-stdio"
sys.path.insert(0, str(NETDISK_DIR))


def _load_uploader():
    """延迟导入 netdisk.py（MCP 服务模块），并把 token 注入其中。"""
    token = get_token()
    # netdisk.py 在 import 时读取环境变量作为模块级 access_token，
    # 这里先把解析到的 token 写入环境变量，保证 import 后拿到的是它。
    os.environ["BAIDU_NETDISK_ACCESS_TOKEN"] = token
    import netdisk  # type: ignore

    def upload(local: str, remote_dir: str) -> dict:
        netdisk.access_token = token
        return netdisk.upload_file(local, remote_dir.rstrip("/") + "/")

    return upload


def iter_files(local: Path, flat: bool):
    if local.is_file():
        yield local, local.name
        return
    for root, _dirs, files in os.walk(local):
        for name in files:
            path = Path(root) / name
            if flat:
                yield path, name
            else:
                yield path, path.relative_to(local).as_posix()


def main() -> int:
    ensure_utf8_console()
    parser = argparse.ArgumentParser(description="百度网盘上传脚本")
    parser.add_argument("local", help="本地文件或目录")
    parser.add_argument("remote_dir", help="网盘目录（必须以 / 开头）")
    parser.add_argument("--flat", action="store_true", help="递归上传时全部平铺到目标目录")
    parser.add_argument("--overwrite", action="store_true", help="冲突时覆盖（默认由网盘自动重命名）")
    args = parser.parse_args()

    local = Path(args.local).expanduser()
    if not local.exists():
        print(f"error: 本地路径不存在：{local}", file=sys.stderr)
        return 2

    remote_dir = args.remote_dir
    if not remote_dir.startswith("/"):
        print("error: 网盘目录必须以 / 开头", file=sys.stderr)
        return 2
    remote_dir = remote_dir.rstrip("/")

    upload = _load_uploader()
    files = list(iter_files(local, args.flat))
    if not files:
        print("没有可上传的文件", file=sys.stderr)
        return 1

    ok = 0
    failed: list[str] = []
    for path, rel in files:
        target_dir = remote_dir if args.flat else f"{remote_dir}/{Path(rel).parent.as_posix()}".rstrip("/.")
        target_dir = target_dir or remote_dir
        result = upload(str(path), target_dir)
        if result.get("status") == "success":
            ok += 1
            size = human_size(os.path.getsize(path))
            print(f"[{ok}/{len(files)}] 已上传 {path} ({size}) -> {result.get('remote_path')}")
        else:
            failed.append(str(path))
            print(f"失败：{path} — {result.get('message')}", file=sys.stderr)

    print(f"完成：成功 {ok}/{len(files)}")
    if failed:
        print("失败列表：", file=sys.stderr)
        for item in failed:
            print(f"  - {item}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
