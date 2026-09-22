# 用 MCP 让 AI 助手直接控制 Unreal Engine 编辑器 —— 从零搭建 UE4 AI 工作流

> 本文介绍如何通过 Model Context Protocol (MCP) 将 UE4/5 编辑器接入 AI 助手，实现自然语言驱动的场景搭建、资产管理和关卡编辑。附完整代码和配置。

## 一、背景：为什么要把 AI 接入游戏引擎？

大语言模型（LLM）已经能写代码、做分析、生成文案，但它们一直缺少一个关键能力：**直接操控物理世界的工具**。对于游戏开发者来说，最有价值的"物理世界"就是 UE 编辑器。

想象一下这样的工作流：

- 你对 AI 说："在场景里创建一个穿山隧道，双向两车道，两侧每隔 5 米放一个反光锥"
- AI 直接在 UE 编辑器里生成所有 actor、材质、灯光
- 你目视确认效果，告诉 AI "灯光太暗了，隧道顶部加几盏灯"
- AI 追加修改

这不是科幻——通过 **Model Context Protocol (MCP)**，这已经在我们的项目中跑通了。

## 二、核心概念

### 什么是 MCP？

MCP（Model Context Protocol）是 Anthropic 推出的开放协议，定义了 AI 助手与外部工具之间的通信标准。你可以把它理解为：

```
AI 助手  ←→  MCP 协议  ←→  MCP Server（工具提供者）
```

每个 MCP Server 可以暴露多个 **工具（Tools）**，AI 助手根据用户的自然语言请求，自动选择合适的工具并传入参数执行。

### 什么是 UE4 Remote Execution？

UE4/5 的 Python Script Plugin 内置了一个 Remote Execution 模块：

1. 编辑器启动后监听 UDP 6766 端口
2. 客户端通过 UDP 广播发现编辑器端点
3. 通过 HTTP POST 发送 Python 代码到编辑器执行
4. 编辑器执行结果返回给客户端

这意味着：**只要网络可达，任何程序都可以远程操控 UE 编辑器。**

### 把两者结合起来

```
opencode / Claude Desktop / Cursor
        ↕ (MCP over stdio)
    ue4-mcp-server (Python)
        ↕ (UDP discovery + HTTP POST)
    UE4 Editor (Remote Execution Plugin)
```

AI 助手通过 MCP 协议调用 `ue4-mcp-server` 提供的工具，MCP Server 再通过 Remote Execution 把 Python 代码发送到 UE 编辑器执行。整个链路是：

**自然语言 → MCP 工具调用 → Python 代码 → UE 编辑器操作**

## 三、实现细节

### 3.1 UE4 端配置

只需一步——在项目的 `Config/DefaultEngine.ini` 中添加：

```ini
[PythonScriptPlugin]
bRemoteExecution=True
```

重启编辑器后，Remote Execution 插件就会监听 UDP 6766 端口，等待客户端连接。

### 3.2 MCP Server 实现

核心代码分为两层：

**Remote Execution 客户端**（发现 + 执行）：

```python
import socket, json

def discover_ue4(port=6766, timeout=3.0):
    """通过 UDP 广播发现 UE4 编辑器端点"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(timeout)
    msg = json.dumps({"Type": "icast", "Version": 1}).encode()
    sock.sendto(msg, ("<broadcast>", port))
    data, addr = sock.recvfrom(4096)
    resp = json.loads(data.decode())
    return resp["Addr"], resp["Port"], resp.get("Auth", "")

def run_python(addr, port, auth, code):
    """通过 HTTP POST 在 UE4 中执行 Python 代码"""
    from urllib.request import Request, urlopen
    body = json.dumps({
        "Type": 1, "Version": 1,
        "Magic": "ue_py",  # hex 编码
        "Results": -1, "Flags": 0,
        "Path": "", "Output": -1,
        "Exec": code
    }).encode()
    url = f"http://{addr}:{port}/remote/exec"
    req = Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if auth:
        req.add_header("Authorization", f"Bearer {auth}")
    with urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())["Output"]
```

**MCP 工具层**（使用 FastMCP）：

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ue4")

@mcp.tool()
def run_python(code: str) -> str:
    """在 UE4 编辑器中执行 Python 代码"""
    ep = discover_ue4()
    return run_python(ep[0], ep[1], ep[2], code)

@mcp.tool()
def create_actor(object_class: str, object_name: str,
                 x: float = 0, y: float = 0, z: float = 0) -> str:
    """在关卡中创建一个 actor"""
    code = f"""
import unreal
a = unreal.EditorLevelLibrary.spawn_actor_from_class(
    unreal.{object_class}, unreal.Vector({x},{y},{z}))
a.set_actor_label('{object_name}')
print('created=' + a.get_actor_label())
"""
    return run_python(...)
```

### 3.3 AI 助手配置

以 opencode 为例，在 `~/.config/opencode/opencode.jsonc` 中：

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

## 四、实战案例：用 AI 创建穿山隧道

以下是我们在实际项目中使用的工作流：

### 第一轮对话

> **用户：** 在 UE4 里创建一个穿山隧道，双向两车道，每车道 3.75 米，隧道两侧每隔 5 米放一个 0.95 米高的反光锥。

AI 调用 `run_python` 工具，生成了以下操作：
1. 创建混凝土双面材质（隧道壁、顶、底）
2. 创建沥青路面材质、黄/白车道线材质
3. 用 Cube 搭建隧道壳（左右墙、顶板、底板）
4. 用 Plane 铺设路面、车道线
5. 用 Sphere 堆建山体
6. 放置 CARLA 交通锥模型（缩放到 0.95m）
7. 添加平行光、天光、点光源

### 第二轮对话

> **用户：** 新建一个关卡，隧道长度改成 1000 米，保存成 CARLA 场景。

AI 完成了：
1. 创建新关卡 `/Game/Carla/Maps/Tunnel1000m`
2. 创建匹配的 OpenDRIVE 文件 `Tunnel1000m.xodr`
3. 1000 米隧道全部重建（对齐 xodr 坐标系）
4. 放置 400 根 1 米反光柱
5. 放置 OpenDriveActor（CARLA 路网生成器）
6. 保存关卡

**整个过程 AI 自主完成了约 500 个 actor 的创建，无需手动操作编辑器。**

## 五、UE 4.26 兼容性注意事项

我们在 UE 4.26（CARLA 自定义构建）上测试时发现了一些兼容性问题：

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| `AssetData.asset_class_path` 不存在 | UE4.26 没有 AssetClassPath | 改用 `asset.asset_class` |
| `EditorAssetLibrary.list_assets("/Game/")` 返回空 | UE4.26 需要尾斜杠 | 用 `"/Game/"` |
| `Box.get_size()` 不存在 | UE4.26 Box 没有 get_size | 用 `max - min` 手动计算 |
| `set_editor_property` 不触发 PostEditChangeProperty | UE4.26 Python 绑定的已知限制 | 需要手动在编辑器 UI 中操作 |
| ProceduralMeshComponent 无法注册 | UE4.26 Python 没有 register_component | 改用 StaticMeshActor |

## 六、项目结构

```
ue4-mcp-server/
├── pyproject.toml          # 包配置
├── README.md               # 文档
├── LICENSE                 # MIT
└── src/ue4_mcp/
    ├── __init__.py
    ├── __main__.py         # 入口点
    ├── remote_execution.py # UE4 Remote Execution 客户端
    └── server.py           # MCP Server（13 个工具）
```

## 七、安装和使用

```bash
# 安装
pip install ue4-mcp-server

# 或从源码
git clone https://github.com/lusilong/ue4-mcp-server.git
cd ue4-mcp-server
pip install -e .

# 配置 UE4
# 在 Config/DefaultEngine.ini 添加:
# [PythonScriptPlugin]
# bRemoteExecution=True

# 配置 AI 助手（以 opencode 为例）
# 编辑 ~/.config/opencode/opencode.jsonc
```

然后打开 UE 编辑器，在 AI 助手中直接对话即可。

## 八、提供的 MCP 工具一览

| 工具 | 功能 | 示例调用 |
|------|------|---------|
| `run_python` | 执行任意 Python | 创建材质、修改属性 |
| `console_command` | 控制台命令 | `stat fps` |
| `get_project_info` | 项目信息 | 引擎版本、资产数 |
| `get_map_info` | 关卡信息 | actor 数量、类型 |
| `get_world_outliner` | 世界大纲 | 所有 actor 列表 |
| `search_assets` | 搜索资产 | 按名称/类型 |
| `create_actor` | 创建 actor | 灯光、网格体 |
| `delete_actor` | 删除 actor | 按名称 |
| `update_actor` | 更新 actor | 位移、旋转、缩放 |
| `take_screenshot` | 截图 | 保存到文件 |
| `move_camera` | 移动相机 | 定位视口 |
| `get_asset_references` | 资产引用 | 依赖分析 |

## 九、总结

通过 MCP + UE4 Remote Execution，我们实现了：

1. **零代码场景搭建** —— 用自然语言描述，AI 自动在编辑器中创建
2. **跨工具集成** —— opencode、Claude Desktop、Cursor 等任何 MCP 兼容客户端都能用
3. **实时反馈** —— AI 可以截图查看效果，根据视觉反馈调整
4. **项目级操作** —— 资产搜索、引用分析、批量修改

这不是要取代关卡设计师，而是把重复性的 actor 放置、材质赋值、参数调整等工作交给 AI，让人专注于创意决策。

---

**项目地址：** https://github.com/lusilong/ue4-mcp-server

**相关资源：**
- [MCP 官方文档](https://modelcontextprotocol.io)
- [UE4 Python Script Plugin](https://docs.unrealengine.com/5.0/en-US/Python-Scripting-in-UE4/)
- [UE4 Remote Execution 源码](Engine/Plugins/Experimental/PythonScriptPlugin/Content/Python/remote_execution.py)
