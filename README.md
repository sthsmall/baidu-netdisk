# baidu-netdisk

百度网盘 AI Agent 工具集合：**Skill（MCP 优先 + 脚本回落）**，内置于仓库的 MCP Server（远程 SSE + 本地 stdio 上传），两侧共用同一 access_token。

面向 [opencode](https://opencode.ai) / Claude Code / Cursor 等支持 Skill 与 MCP 的 Agent。

## 工作方式

Skill 是**总入口**，按「先 MCP、后脚本」分流：

```
用户请求
   │
   ├─ 列表 / 搜索 / 详情 / 建目录 / 复制 / 移动 / 重命名 / 删除 /
   │  分享 / 容量 / 用户信息 / URL 或文本上传   ──►  MCP 工具
   │
   └─ 下载到本地 / 目录递归 / 分享链接下载 / 本地文件上传
        ├─ 先看 MCP 有没有对应工具（如 upload_file）→ 有就用
        └─ MCP 做不到或失败 → 回落 skill 脚本
```

分流细节见 `skill/SKILL.md`。

## 目录结构

```
baidu-netdisk/
├── skill/                              # Agent Skill：下载/上传脚本
│   ├── SKILL.md                        # Skill 定义（Agent 行为规范）
│   └── scripts/
│       ├── baidu_netdisk_common.py     # 共享层：token 解析 / API 调用 / 进度条
│       ├── baidu_netdisk_download.py   # 下载（单文件 / 目录递归 / 分享链接）
│       ├── upload.py                   # 上传（单文件 / 目录递归）
│       └── netdisk-mcp-server-stdio/   # 上传能力依赖（MCP 服务模块，被 upload.py 复用）
└── mcp/                                # 本地 stdio MCP Server（本地上传）
    ├── fileupload_tool.py              # MCP 服务入口（tools: upload_file）
    ├── openapi_client/                 # 百度开放平台 Python SDK
    ├── pyproject.toml
    └── uv.lock
```

## 能力矩阵

| 能力 | 提供方 | 说明 |
|------|--------|------|
| 文件列表 / 文档 / 图片 / 视频列表 | MCP | `file_list`、`file_doc_list`、`file_image_list`、`file_video_list` |
| 关键词搜索 / 语义搜索 | MCP | `file_keyword_search`、`file_semantics_search` |
| 文件详情 | MCP | `file_meta` |
| 建目录 / 复制 / 移动 / 重命名 / 删除 | MCP | `make_dir`、`file_copy`、`file_move`、`file_rename`、`file_del` |
| 分享链接生成 | MCP | `file_sharelink_set` |
| 用户信息 / 容量 | MCP | `user_info`、`get_quota` |
| URL / 文本上传 | MCP | `file_upload_by_url`、`file_upload_by_content` |
| 本地上传（含 >4MB 分片） | MCP（stdio）/ 脚本 | MCP `upload_file`，或 `skill/scripts/upload.py` |
| **下载到本地** | **脚本** | `skill/scripts/baidu_netdisk_download.py` |
| **目录递归下载 / 上传** | **脚本** | 目录自动递归；上传可 `--flat` 平铺 |
| **分享链接下载** | **脚本** | 转存后下载 |

> 远程 SSE 没有「下载」能力，这是仓库内置下载脚本的主要原因。

## 安装

### 1. 获取 access_token

浏览器登录百度账号后打开并点击「授权」：

```
https://openapi.baidu.com/oauth/2.0/authorize?response_type=token&client_id=QHOuRXiepJBMjtk0esLhrPoNlQyYd0mF&redirect_uri=oob&scope=basic,netdisk
```

跳转后地址栏形如 `https://openapi.baidu.com/oauth/2.0/login_success#access_token=xxx&...`，取 `access_token=` 到 `&` 之间的值。

> Token 有效期 **30 天**，过期需重新授权。
> `client_id` 为百度开放平台个人体验用的公共 App Key，仅供测试，官方可能不定期变更。

### 2. 配置 token（三选一，脚本会自动按序回退）

```bash
# 方式 A：环境变量
export BAIDU_NETDISK_ACCESS_TOKEN="123.xxxx.yyyy-zzzz"

# 方式 B：凭证文件（推荐，脚本默认读取）
mkdir -p ~/.config/bdpan && echo "123.xxxx.yyyy-zzzz" > ~/.config/bdpan/access_token

# 方式 C：已配置 MCP 时，脚本会从 opencode.jsonc 里读取
```

Windows（PowerShell）：

```powershell
[Environment]::SetEnvironmentVariable("BAIDU_NETDISK_ACCESS_TOKEN", "123.xxxx.yyyy-zzzz", "User")
```

### 3. 安装 Skill

把 `skill/` 复制到 Agent 的 skills 目录：

```bash
# opencode
cp -r skill ~/.config/opencode/skills/baidu-netdisk

# Claude Code
cp -r skill ~/.claude/skills/baidu-netdisk
```

Python 依赖（仅需 `requests`）：

```bash
pip install requests        # 或用 uv / venv
```

### 4. 配置 MCP

`~/.config/opencode/opencode.jsonc`：

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    // 远程 SSE：查询 / 管理 / 分享 / 上传(URL、文本)
    "baidu-netdisk": {
      "type": "remote",
      "url": "https://mcp-pan.baidu.com/sse?access_token=<YOUR_ACCESS_TOKEN>",
      "enabled": true
    },
    // 本地 stdio：上传本地文件（含大文件分片）
    "baidu-netdisk-upload": {
      "type": "local",
      "command": [
        "uv",
        "--directory",
        "<本仓库>/mcp",
        "run",
        "fileupload_tool.py"
      ],
      "environment": {
        "BAIDU_NETDISK_ACCESS_TOKEN": "<YOUR_ACCESS_TOKEN>"
      },
      "enabled": true
    }
  }
}
```

本地 stdio 依赖安装（推荐 Python 3.12）：

```bash
cd mcp && uv sync
```

## 使用

Skill 由 Agent 自动触发，也可手动调用脚本：

```bash
# 下载单个文件
python skill/scripts/baidu_netdisk_download.py "/apps/report.pdf" "./report.pdf"

# 递归下载目录
python skill/scripts/baidu_netdisk_download.py "/apps/photos" "./photos"

# 下载分享链接（转存后下载）
python skill/scripts/baidu_netdisk_download.py "https://pan.baidu.com/s/1abcd?pwd=1234" "./out"

# 上传文件 / 目录
python skill/scripts/upload.py "./report.pdf" "/apps/docs"
python skill/scripts/upload.py "./photos" "/apps/backup"
python skill/scripts/upload.py "./photos" "/apps/backup" --flat
```

对 Agent 说自然语言即可：`把 /apps/photos 下载到本地`、`上传 ./report.pdf 到网盘的 /apps/docs`。

## 安全说明

- 仓库内**不含任何 token**，请通过环境变量或本地凭证文件注入；`.env` / `access_token` 已在 `.gitignore` 中忽略。
- Token 权限为**全盘**（非沙箱），请自行评估风险；泄露后在 [授权管理](https://passport.baidu.com/v6/appAuthority) 解除关联。
- 本工具处于 BETA，建议对重要数据先行备份，并人工审核 Agent 执行的每条命令。

## 致谢 / 来源

- 远程 SSE MCP 接口与本地 stdio 上传服务：[baidu-netdisk/mcp](https://github.com/baidu-netdisk/mcp)（Apache-2.0）
- 下载脚本的初始思路：[bbinwang/baidu-netdisk](https://github.com/bbinwang/baidu-netdisk)（MIT）

本仓库在其基础上做了整合与增强：共享 token 解析层、自动分页、目录递归下载/上传、断点续传、错误码释义、Windows 适配等。

## License

MIT
