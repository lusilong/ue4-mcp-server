# ue4-mcp-server

[![MCP](https://img.shields.io/badge/MCP-Compatible-brightgreen)](https://modelcontextprotocol.io)
[![Python](https://img.shields.io/badge/Python-3.8+-blue)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**让 AI 助手直接控制 Unreal Engine 编辑器。**

通过 [Model Context Protocol (MCP)](https://modelcontextprotocol.io) 把 UE4/5 的编辑器能力暴露给 AI 助手（opencode、Claude Desktop、Cursor 等），实现自然语言驱动的场景搭建、资产管理和关卡编辑。

## 架构

```
┌──────────────┐     stdio/MCP      ┌────────────────┐     UDP+HTTP     ┌──────────────┐
│  AI 助手      │ ◄──────────────── │  ue4-mcp-server │ ◄──────────────► │  UE4 Editor  │
│  (opencode /  │                    │  (Python MCP)   │   Remote Exec   │  (Python     │
│   Claude等)   │                    └────────────────┘                   │   Plugin)    │
└──────────────┘                                                        └──────────────┘
```

**工作原理：**
1. UE4 编辑器启用 Remote Execution 插件（监听 UDP 6766 端口）
2. MCP Server 通过 UDP 广播发现编辑器端点
3. 通过 HTTP POST 发送 Python 代码到编辑器执行
4. 编辑器执行结果返回给 AI 助手

## 快速开始

### 1. 安装

```bash
pip install ue4-mcp-server
```

或从源码安装：

```bash
git clone https://github.com/lusilong/ue4-mcp-server.git
cd ue4-mcp-server
pip install -e .
```

### 2. 配置 UE4 编辑器

在你的项目 `Config/DefaultEngine.ini` 中添加：

```ini
[PythonScriptPlugin]
bRemoteExecution=True
```

重启编辑器，Remote Execution 插件会监听 UDP 6766 端口。

### 3. 配置 AI 助手

#### opencode (`~/.config/opencode/opencode.jsonc`)

```jsonc
{
  "mcp": {
    "ue4": {
      "type": "local",
      "command": ["ue4-mcp"]
    }
  }
}
```

#### Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "ue4": {
      "command": "ue4-mcp",
      "args": []
    }
  }
}
```

#### Cursor (`.cursor/mcp.json`)

```json
{
  "mcpServers": {
    "ue4": {
      "command": "ue4-mcp"
    }
  }
}
```

### 4. 启动

1. 打开 UE4/5 编辑器（确保 Remote Execution 已启用）
2. 在 AI 助手中对话，AI 会自动连接编辑器

## 提供的工具

| 工具 | 说明 |
|------|------|
| `run_python` | 在编辑器中执行任意 Python 代码 |
| `console_command` | 执行 UE4 控制台命令 |
| `get_project_info` | 获取项目名称、引擎版本、资产数量 |
| `get_map_info` | 获取当前关卡信息（actor 数量、类型分布） |
| `get_world_outliner` | 列出所有 actor 及其位置、旋转、缩放 |
| `search_assets` | 按名称搜索项目资产 |
| `create_actor` | 在关卡中创建 actor（StaticMesh、Light 等） |
| `delete_actor` | 按名称删除 actor |
| `update_actor` | 更新 actor 的变换或标签 |
| `take_screenshot` | 截取编辑器视口截图 |
| `move_camera` | 移动编辑器视口相机 |
| `get_asset_references` | 查看资产的引用关系 |

## 使用示例

连接后，你可以用自然语言对 AI 说：

- "在原点创建一个 10 米高的柱子"
- "把场景里所有 PointLight 的强度改成 5000"
- "截一张图看看当前场景"
- "列出场景里所有的 StaticMeshActor"
- "创建一个蓝色的平面当水面"
- "把相机移到 (1000, 500, 300) 看看效果"

AI 会自动调用对应的 MCP 工具，通过 Remote Execution 在编辑器中执行操作。

## UE 版本兼容性

| UE 版本 | 状态 |
|---------|------|
| UE 4.26 | ✅ 完全支持（已验证） |
| UE 4.27 | ✅ 应该支持 |
| UE 5.0+ | ✅ 应该支持（未测试） |

> **UE 4.26 注意事项：** `set_editor_property` 不触发 `PostEditChangeProperty` 回调，因此依赖此回调的功能（如 OpenDriveActor 的路网生成）需要在编辑器 UI 中手动操作。

## 故障排除

**连接超时：**
- 确认编辑器正在运行
- 确认 `DefaultEngine.ini` 中 `bRemoteExecution=True`
- 检查防火墙是否阻止了 UDP 6766 端口

**执行错误：**
- Python 代码必须以 `import unreal` 开头
- 某些 API 在打包版本中不可用，仅限编辑器内使用

## License

MIT

---

**Publish status (2026-09-22):** live on GitHub → https://github.com/lusilong/ue4-mcp-server
CSDN walkthrough: see docs/csdn_post.md (translated copy on the Desktop).
