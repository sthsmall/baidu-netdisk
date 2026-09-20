## 简介
fileupload_tool.py为Python语言的开发者提供，可以帮助您快速通过stdio模式调用网盘开放平台提供的文件上传MCP Server。

## 准备开发环境

我们推荐通过`uv`构建虚拟环境来运行MCP Server，关于`uv`你可以在 [这里](https://docs.astral.sh/uv/getting-started/features/) 找到一些说明。
按照 [官方流程](https://modelcontextprotocol.io/quickstart/server) ，你会安装`Python`包管理工具`uv`。除此之外，你也可以尝试其他方法（如`Anaconda`）来创建你的`Python`虚拟环境。

**`Windows 建议使用 pip 或者 anaconda 来准备运行环境，将 uv run 命令替换为 python。`**

### 1. UV安装
安装之后可通过 **`uv help`** 命令检查是否安装成功
```
1. On macOS and Linux.
   curl -LsSf https://astral.sh/uv/install.sh | sh
2. On Windows.
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
3. With pip.
   pip install uv
```

> <img src="https://bce.bdstatic.com/doc/xpan-open-platform/doc/586ceddb7e10c32c6c7cb84fdae58344_586cedd.jpg" width="500" height="300" alt="图片描述">


### 2. 通过uv添加mcp依赖
执行以下命令安装MCP
```
uv add "mcp[cli]"
```
执行如下命令，验证mcp依赖是否安装成功
```
uv run mcp
```
当出现下图时代表安装成功


> <img src="https://bce.bdstatic.com/doc/xpan-open-platform/doc/9e1ea997c959383324ac51ea41e2bf9c_9e1ea99.png" width="500" height="240" alt="图片描述">

### 3. 运行环境
```
执行uv run ./netdisk.py命令会读取当前目录下的 pyproject.toml。
执行后会自动创建虚拟环境和安装依赖，同时在这个环境中运行代码。
你可以验证netdisk.py是否可运行，若无报错则环境依赖均配置完成。
```
* 推荐运行环境：Python 3.12
* 运行环境要求：python >= 3.12
* 需要依赖的库：见pyproject.toml

**运行示例：**

* 依赖环境安装中：

> ![67c7480d78ab7b2c3dd98fd3a2741f3a.png](https://bce.bdstatic.com/doc/xpan-open-platform/doc/67c7480d78ab7b2c3dd98fd3a2741f3a_67c7480.png)

* 依赖环境安装完成

> ![0dc446ae37cbb06846fb80d71de82dcf.png](https://bce.bdstatic.com/doc/xpan-open-platform/doc/0dc446ae37cbb06846fb80d71de82dcf_0dc446a.png)

## 使用上传工具
在支持mcp的host中配置如下内容，然后发起上传交互即可。
```
{
  "mcpServers": {
    "netdisk-fileupload": {
        "command": "<您的uv绝对路径>",
        "args": [
            "--directory",
            "<您的fileupload_tool.py所在父目录绝对路径>",
            "run",
            "fileupload_tool.py"
        ],
        "env": {
          "BAIDU_NETDISK_ACCESS_TOKEN": "<您的AccessToken>"
        }
    }
  }
}
```
