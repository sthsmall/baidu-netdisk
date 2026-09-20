# 百度网盘 Skill（MCP 优先 + 脚本回落）

百度网盘文件操作总入口。**先用 MCP 工具，MCP 做不到的才用本 skill 的脚本**。

两侧共用同一 access_token；本 skill 负责分流、参数拼装与结果汇总。

---

## 一、分流规则（每次触发都先执行）

### 第 1 步：判断操作类型

| 用户意图 | 走哪条路 | 具体用法 |
|---|---|---|
| 查看/列出文件、列文档/图片/视频 | **MCP** | `file_list`、`file_doc_list`、`file_image_list`、`file_video_list` |
| 搜索文件（关键词） | **MCP** | `file_keyword_search` |
| 搜索文件（自然语言描述） | **MCP** | `file_semantics_search` |
| 看某个文件详情 | **MCP** | `file_meta` |
| 新建文件夹 | **MCP** | `make_dir` |
| 复制 / 移动 / 重命名 / 删除 | **MCP** | `file_copy`、`file_move`、`file_rename`、`file_del` |
| 生成分享链接 | **MCP** | `file_sharelink_set` |
| 账号信息 / 容量 | **MCP** | `user_info`、`get_quota` |
| 从 URL 或文本上传到网盘 | **MCP** | `file_upload_by_url`、`file_upload_by_content` |
| **下载文件到本地** | **脚本** | `baidu_netdisk_download.py` |
| **下载整个目录到本地** | **脚本** | `baidu_netdisk_download.py`（目录自动递归） |
| **上传本地文件/目录** | **脚本** | `upload.py`（目录自动递归，`--flat` 可平铺） |
| 下载分享链接的内容 | **脚本** | `baidu_netdisk_download.py "<分享链接>"` |

### 第 2 步：MCP 优先，失败再回落

即使属于"脚本"那几项，也按下面顺序尝试：

1. **先查 MCP 有没有对应工具**（如本地上传：`baidu-netdisk-upload` 的 `upload_file` 可用就直接用）。
2. MCP 工具**不存在、未启用、或调用失败**（如 token 失效、服务不可达、能力缺失）→ 再执行本 skill 的脚本。
3. 回落时必须在回复里说明**为什么走了脚本**（例如"远程 MCP 无下载能力"或"MCP 报错 xxx"），不要静默切换。

### 第 3 步：MCP 明确没有的能力（直接用脚本，不必尝试 MCP）

- **下载到本地**：远程 SSE 不存在任何下载工具。
- **目录递归下载/上传**：MCP 工具均只处理单个文件。
- **分享链接下载**：远程 SSE 无此工具。

---

## 二、脚本用法

脚本位于本 skill 的 `scripts/` 目录，解释器需能 `import requests`（Python ≥ 3.9）：

```bash
python <SKILL_DIR>/scripts/baidu_netdisk_download.py <参数>
python <SKILL_DIR>/scripts/upload.py <参数>
```

> Windows 下若系统 Python 版本过低或缺少依赖：
> `python -m venv .venv && .venv\Scripts\pip install requests`

### 下载

```bash
python scripts/baidu_netdisk_download.py <网盘路径|分享链接> [本地路径] [-p 提取码] [--overwrite]
```

- 网盘路径以 `/` 开头，指向文件或目录。
- 本地路径省略时：文件落到当前目录同名文件；目录落到 `./<目录名>/`。
- 本地已存在同名文件默认跳过，`--overwrite` 覆盖。
- 目录**递归**下载并保持结构；单文件失败不中断整批，结束时汇总。

```bash
python scripts/baidu_netdisk_download.py "/apps/report.pdf" "./report.pdf"
python scripts/baidu_netdisk_download.py "/apps/photos" "./photos"
python scripts/baidu_netdisk_download.py "https://pan.baidu.com/s/1abcd?pwd=1234" "./out"
```

### 上传

```bash
python scripts/upload.py <本地路径> <网盘目录> [--flat] [--overwrite]
```

- 网盘目录**必须以 `/` 开头**，且是**目录**（文件落到该目录下，不再二次拼文件名）。
- 本地为目录时递归上传，默认在网盘重建相对目录结构；`--flat` 全部平铺到目标目录。
- `>4MB` 自动分片上传；失败自动重试。

```bash
python scripts/upload.py "./report.pdf" "/apps/docs"
python scripts/upload.py "./photos" "/apps/backup"
python scripts/upload.py "./photos" "/apps/backup" --flat
```

---

## 三、access_token 解析

脚本按序回退，任一命中即用（见 `scripts/baidu_netdisk_common.py`）：

1. 环境变量 `BAIDU_NETDISK_ACCESS_TOKEN`
2. 凭证文件 `~/.config/bdpan/access_token`（可用 `BDPAN_TOKEN_FILE` 覆盖）
3. `~/.config/opencode/opencode.jsonc` 中 `baidu-netdisk` / `baidu-netdisk-upload` 条目

MCP 侧使用它自己配置里的 token。**不要**打印或在回复中回显 token。

---

## 四、行为规范（Agent 必须遵守）

1. **先 MCP 后脚本**：按上面的分流表执行，不要跳过分流直接写脚本。
2. **确认目标**：下载/上传前用 MCP `file_list` 或 `file_meta` 确认远端路径存在。
3. **不猜路径**：路径或文件名有歧义时先向用户确认。
4. **列表必须翻页到空页**：MCP 的列表类工具（`file_list`、`file_doc_list`、`file_image_list`、`file_video_list`、`file_keyword_search`）**默认只返回一页约 10 条，且响应不含总数**。
   - 不传 `page` 时只拿到首屏 10 条，**不代表目录只有 10 项**；
   - 要完整枚举，必须传 `page` 逐页拉取（`page=1,2,3…`），**直到某一页返回空列表**才算到底；
   - 搜索类可配合 `num` 调大每页条数，但同样要翻页到空页；
   - 向用户汇报数量时，必须基于翻完的结果，**禁止**用单页条数当作总数；
   - 用户只要求"看看有什么"时，也应说明"共 N 项（已翻页确认）"，不要只报第一页。
5. **输出精简**：脚本把日志和进度条写到 stderr、统计写到 stdout；回复只汇总结果（文件名、大小、本地路径、成功/失败数），不要贴整条进度条。
6. **失败如实上报**：退出码 `0` 成功、`1` 业务失败、`2` 参数或 token 问题。保留原始错误原因。
7. **删除需确认**：删除走 MCP，且必须先列出待删对象、取得用户明确确认。
8. **大文件**：耗时可能超过命令超时，用后台方式执行并轮询，同时先告知预估耗时。

---

## 五、常见错误

| 现象 | 原因与处理 |
|------|-----------|
| 只看到 10 个文件，怀疑不完整 | 列表工具默认只回一页且无总数；必须传 `page` 翻页到空页（见行为规范第 4 条） |
| MCP 工具未出现在工具列表 | MCP 未启用；改用脚本，或提示用户在 `opencode.jsonc` 中启用 |
| MCP 返回 token 相关错误 | token 过期（30 天）；重新授权后同步更新 MCP 配置与凭证文件 |
| `未找到 access_token` | 三个来源都没有；引导重新授权并写入凭证文件 |
| `errno=111` / `-6` | access_token 无效或已过期，需重新授权 |
| `errno=-7` / `未找到：<路径>` | 网盘路径不存在；用 MCP `file_list` 核对 |
| `errno=31034` | 平台限流，稍后重试 |

---

## 六、授权（token 过期时）

引导用户打开并登录，点「授权」后把跳转地址发回：

```
https://openapi.baidu.com/oauth/2.0/authorize?response_type=token&client_id=QHOuRXiepJBMjtk0esLhrPoNlQyYd0mF&redirect_uri=oob&scope=basic,netdisk
```

跳转后形如 `https://openapi.baidu.com/oauth/2.0/login_success#access_token=xxx&...`，取 `access_token=` 到 `&` 之间的值，写入 `~/.config/bdpan/access_token`，并同步更新 MCP 配置中的 token。
