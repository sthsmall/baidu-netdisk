# 百度网盘下载/上传 Skill

补足 MCP 缺失的**下载到本地**能力，并提供脚本化上传。与 `baidu-netdisk`（remote SSE）和 `baidu-netdisk-upload`（local stdio）两个 MCP server 并存，共用同一个 access_token。

## 能力边界（重要）

| 能做 | 不能做 |
|------|--------|
| 下载单个文件到本地 | 断点续传（仅支持失败自动重试 + `.part` 续传） |
| 递归下载整个目录并保持目录结构 | — |
| 上传单个文件 | — |
| 递归上传目录（`--flat` 可平铺） | — |
| 转存分享链接后下载（实验性） | — |
| 覆盖本地已存在文件（`--overwrite`） | — |

**以下操作不要用本 skill，改用 MCP 工具**：`file_list`、`file_keyword_search`、`file_semantics_search`、`file_meta`、`make_dir`、`file_copy`、`file_move`、`file_rename`、`file_sharelink_set`、`get_quota`、`user_info`。

## 调用方式

脚本位于本 skill 的 `scripts/` 目录，解释器需能 `import requests`（Python ≥ 3.9）：

```bash
python <SKILL_DIR>/scripts/baidu_netdisk_download.py <参数>
python <SKILL_DIR>/scripts/upload.py <参数>
```

> Windows 下若系统 Python 版本过低或缺少依赖，可先创建虚拟环境：
> `python -m venv .venv && .venv\Scripts\pip install requests`

## access_token 解析顺序

脚本按以下顺序自动查找，任一命中即用（见 `scripts/baidu_netdisk_common.py`）：

1. 环境变量 `BAIDU_NETDISK_ACCESS_TOKEN`
2. 凭证文件 `~/.config/bdpan/access_token`（可用 `BDPAN_TOKEN_FILE` 覆盖）
3. 仓库/本机的 `~/.config/opencode/opencode.jsonc` 中 `baidu-netdisk` / `baidu-netdisk-upload` 条目

**不要**把 token 打印出来，也不要在回复里回显。

## 下载

```bash
python scripts/baidu_netdisk_download.py <网盘路径|分享链接> [本地路径] [-p 提取码] [--overwrite]
```

- 网盘路径以 `/` 开头，指向文件或目录。
- 本地路径省略时：文件下载到当前目录同名文件；目录下载到 `./<目录名>/`。
- 本地已存在同名文件时默认跳过，需要覆盖请加 `--overwrite`。
- 目录为**递归**下载并保持目录结构；单文件失败不会中断整批，结束时汇总。

示例：

```bash
python scripts/baidu_netdisk_download.py "/apps/report.pdf" "./report.pdf"
python scripts/baidu_netdisk_download.py "/apps/photos" "./photos"
python scripts/baidu_netdisk_download.py "https://pan.baidu.com/s/1abcd?pwd=1234" "./out"
```

## 上传

```bash
python scripts/upload.py <本地路径> <网盘目录> [--flat] [--overwrite]
```

- 网盘目录**必须以 `/` 开头**，且是**目录**（文件会落到该目录下，不会再拼一次文件名）。
- 本地路径为目录时递归上传；默认在网盘上重建相对目录结构，`--flat` 则全部平铺进目标目录。
- `>4MB` 的文件自动分片上传；失败自动重试。
- 冲突处理由网盘侧决定（默认自动重命名），`--overwrite` 会请求覆盖。

示例：

```bash
python scripts/upload.py "./report.pdf" "/apps/docs"
python scripts/upload.py "./photos" "/apps/backup"
python scripts/upload.py "./photos" "/apps/backup" --flat
```

## 行为规范（Agent 必须遵守）

1. **先确认目标**：下载前用 MCP `file_list` 或 `file_meta` 确认网盘路径存在；上传前确认远端目录与本地路径。
2. **不要猜测路径**：路径或文件名有歧义时先向用户确认。
3. **大幅输出用 stderr**：脚本把逐文件日志和进度条写到 stderr，最终统计写到 stdout。回复用户时只汇报结果摘要（文件名、大小、本地路径、成功/失败数），不要把整个进度条贴给用户。
4. **失败要如实上报**：退出码 `0` 成功、`1` 业务失败、`2` 参数或 token 问题。失败时保留脚本给出的原因，不要改成"已完成"。
5. **大文件**：单个大文件下载耗时可能超过命令超时，请用后台方式执行并轮询进度，同时先告知用户预估耗时。
6. **不要用本 skill 做删除/移动等写操作**，那些交给 MCP 工具，且删除必须有用户明确确认。

## 常见错误

| 现象 | 原因与处理 |
|------|-----------|
| `未找到 access_token` | 三个来源都没有；引导用户重新授权并写入凭证文件 |
| `errno=111` / `-6` | access_token 无效或已过期（有效期 30 天），需重新授权 |
| `errno=-7` / `未找到：<路径>` | 网盘路径不存在；用 MCP `file_list` 核对 |
| `errno=31034` | 平台限流，稍后重试 |
| 本地中文/emoji 显示乱码 | 仅影响控制台显示，文件内容与文件名不受影响 |

## 授权（token 过期时）

引导用户打开并登录，点「授权」后把跳转地址发回：

```
https://openapi.baidu.com/oauth/2.0/authorize?response_type=token&client_id=QHOuRXiepJBMjtk0esLhrPoNlQyYd0mF&redirect_uri=oob&scope=basic,netdisk
```

跳转后 URL 形如 `https://openapi.baidu.com/oauth/2.0/login_success#access_token=xxx&...`，取 `access_token=` 到 `&` 之间的值，写入凭证文件 `~/.config/bdpan/access_token`，并同步更新 MCP 配置中的 token。
