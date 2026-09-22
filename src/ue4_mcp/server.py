"""Tool JSON Schemas and the UE4 editor bridge handlers for the MCP server."""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from .engine import run_in_editor
from .protocol import Resource, Tool


# ── schema building blocks ─────────────────────────────────────────────────────────

def _num(desc: str, default: Optional[float] = None) -> Dict[str, Any]:
    s: Dict[str, Any] = {"type": "number", "description": desc}
    if default is not None:
        s["default"] = default
    return s


def _int(desc: str, default: Optional[int] = None) -> Dict[str, Any]:
    s: Dict[str, Any] = {"type": "integer", "description": desc}
    if default is not None:
        s["default"] = default
    return s


# ── remote-execution bridge ──────────────────────────────────────────────────────

def _exec(code: str) -> str:
    """Run *code* inside the editor world and return its stdout."""
    from .engine import run_in_editor
    return run_in_editor(code)


# ── handler implementations (all return str for stdout) ──────────────────────────

def _run_python(code: str) -> str:
    return _exec("import unreal\n" + code)


def _console_command(command: str) -> str:
    code = (
        "import unreal\n"
        "w = unreal.EditorLevelLibrary.get_editor_world()\n"
        f"unreal.SystemLibrary.execute_console_command(w, {command!r})\n"
        "print('console_ok')\n"
    )
    return _exec(code)


def _get_project_info() -> str:
    return _exec(
        "import unreal\n"
        "print('name=' + unreal.SystemLibrary.get_game_name())\n"
        "print('engine=' + unreal.SystemLibrary.get_engine_version())\n"
        "n = unreal.EditorAssetLibrary.list_assets('/Game/', True, True)\n"
        "print('assets=' + str(len(n)))\n"
    )


def _get_map_info() -> str:
    return _exec(
        "import unreal\n"
        "ELL = unreal.EditorLevelLibrary\n"
        "w = ELL.get_editor_world()\n"
        "acts = ELL.get_all_level_actors()\n"
        "types = {}\n"
        "for a in acts:\n"
        "    c = a.get_class().get_name()\n"
        "    types[c] = types.get(c, 0) + 1\n"
        "print('map=' + w.get_name())\n"
        "print('actors=' + str(len(acts)))\n"
        "for k, v in sorted(types.items()):\n"
        "    print('  ' + k + '=' + str(v))\n"
    )


def _get_world_outliner(max_actors: int = 80, prefix: str = "") -> str:
    code = (
        "import unreal\n"
        "ELL = unreal.EditorLevelLibrary\n"
        "acts = ELL.get_all_level_actors()\n"
        "print('total=' + str(len(acts)))\n"
        f"limit = {max_actors}\n"
        "n = 0\n"
        "for a in acts:\n"
        f"    lbl = a.get_actor_label()\n"
        f"    if {prefix!r} and not lbl.startswith({prefix!r}):\n"
        "        continue\n"
        "    if n >= limit:\n"
        "        break\n"
        "    n += 1\n"
        "    loc = a.get_actor_location()\n"
        "    rot = a.get_actor_rotation()\n"
        "    sc = a.get_actor_scale3d()\n"
        "    print(lbl + '|' + a.get_class().get_name()\n"
        "        + '|%.1f,%.1f,%.1f' % (loc.x, loc.y, loc.z)\n"
        "        + '|%.1f,%.1f,%.1f' % (rot.pitch, rot.yaw, rot.roll)\n"
        "        + '|%.2f,%.2f,%.2f' % (sc.x, sc.y, sc.z))\n"
    )
    return _exec(code)


def _search_assets(search_term: str, asset_class: str = "") -> str:
    code = (
        "import unreal\n"
        f"assets = unreal.EditorAssetLibrary.list_assets('/Game/{search_term}*', True, True)\n"
        "seen = 0\n"
        "for a in assets:\n"
        f"    if {asset_class!r} and a.asset_class != {asset_class!r}:\n"
        "        continue\n"
        "    if seen >= 50:\n"
        "        break\n"
        "    seen += 1\n"
        "    print(a.package_name + '|' + a.asset_class)\n"
        "print('count=' + str(seen))\n"
    )
    return _exec(code)


def _create_actor(object_class: str, object_name: str,
                  x: float = 0, y: float = 0, z: float = 0,
                  pitch: float = 0, yaw: float = 0, roll: float = 0,
                  scale_x: float = 1, scale_y: float = 1, scale_z: float = 1) -> str:
    code = (
        "import unreal\n"
        "ELL = unreal.EditorLevelLibrary\n"
        f"cls = unreal.{object_class}\n"
        f"loc = unreal.Vector({x}, {y}, {z})\n"
        f"rot = unreal.Rotator({pitch}, {yaw}, {roll})\n"
        f"a = ELL.spawn_actor_from_class(cls, loc, rot)\n"
        f"a.set_actor_label({object_name!r})\n"
        f"a.set_actor_scale3d(unreal.Vector({scale_x}, {scale_y}, {scale_z}))\n"
        "print('created=' + a.get_actor_label() + ' class=' + a.get_class().get_name())\n"
    )
    return _exec(code)


def _delete_actor(actor_names: str) -> str:
    names = [n.strip() for n in actor_names.split(",")]
    code = (
        "import unreal\n"
        "ELL = unreal.EditorLevelLibrary\n"
        "for a in ELL.get_all_level_actors():\n"
        f"    if a.get_actor_label() in {names!r}:\n"
        "        ELL.destroy_actor(a)\n"
        "        print('deleted=' + a.get_actor_label())\n"
    )
    return _exec(code)


def _update_actor(actor_name: str,
                  x: Optional[float] = None, y: Optional[float] = None, z: Optional[float] = None,
                  pitch: Optional[float] = None, yaw: Optional[float] = None, roll: Optional[float] = None,
                  scale_x: Optional[float] = None, scale_y: Optional[float] = None, scale_z: Optional[float] = None,
                  new_name: Optional[str] = None) -> str:
    lines = ["import unreal", "ELL = unreal.EditorLevelLibrary",
             "for a in ELL.get_all_level_actors():",
             f"    if a.get_actor_label() == {actor_name!r}:"]
    if x is not None and y is not None and z is not None:
        lines.append(f"        a.set_actor_location(unreal.Vector({x}, {y}, {z}))")
    if pitch is not None and yaw is not None and roll is not None:
        lines.append(f"        a.set_actor_rotation(unreal.Rotator({pitch}, {yaw}, {roll}))")
    if scale_x is not None and scale_y is not None and scale_z is not None:
        lines.append(f"        a.set_actor_scale3d(unreal.Vector({scale_x}, {scale_y}, {scale_z}))")
    if new_name:
        lines.append(f"        a.set_actor_label({new_name!r})")
    lines.append("        print('updated=' + a.get_actor_label())")
    lines.append("        break")
    return _exec("\n".join(lines))


def _take_screenshot(path: str = "/tmp/ue4_screenshot.png",
                     width: int = 1920, height: int = 1080) -> str:
    code = (
        "import unreal, time\n"
        f"unreal.AutomationLibrary.take_high_res_screenshot({width}, {height}, {path!r})\n"
        "time.sleep(3)\n"
        f"print('saved={' + repr(path) + '}')\n"
    )
    return _exec(code)


def _move_camera(x: float, y: float, z: float,
                 pitch: float = -30, yaw: float = 0, roll: float = 0) -> str:
    code = (
        "import unreal\n"
        f"unreal.EditorLevelLibrary.set_level_viewport_camera_info(\n"
        f"    unreal.Vector({x}, {y}, {z}),\n"
        f"    unreal.Rotator({pitch}, {yaw}, {roll}), 1.0, 0)\n"
        "print('camera_ok')\n"
    )
    return _exec(code)


# ── resources ──────────────────────────────────────────────────────────────────────

RESOURCES = [
    Resource("ue4://project", "Current UE4 project overview", "application/json",
             lambda: _get_project_info()),
    Resource("ue4://map", "Currently loaded level and its actors", "application/json",
             lambda: _get_map_info()),
]


# ── exported registry ──────────────────────────────────────────────────────────────

TOOLS = [
    Tool("run_python",
         "Execute arbitrary Python code inside the UE4 editor.",
         {"type": "object",
          "properties": {"code": {"type": "string",
                                  "description": "Python to run. GuiLib helper imports: "
                                                 "'import unreal' is added automatically."}},
          "required": ["code"]},
         _run_python),

    Tool("console_command",
         "Execute a UE4 console command (e.g. 'stat fps' or a commandlet).",
         {"type": "object",
          "properties": {"command": {"type": "string"}},
          "required": ["command"]},
         _console_command),

    Tool("get_project_info",
         "Project name, engine version, total asset count.",
         {"type": "object", "properties": {}},
         _get_project_info),

    Tool("get_map_info",
         "Currently open level: name, actor count, actor classes.",
         {"type": "object", "properties": {}},
         _get_map_info),

    Tool("get_world_outliner",
         "List actors in the level (label, class, location, rotation, scale).",
         {"type": "object",
          "properties": {
              "max_actors": _int("Maximum number of actors to list", 80),
              "prefix": {"type": "string",
                         "description": "Only list actors whose label starts with this prefix"}}},
         _get_world_outliner),

    Tool("search_assets",
         "Search project assets by name under /Game, optionally filtered by class.",
         {"type": "object",
          "properties": {
              "search_term": {"type": "string"},
              "asset_class": {"type": "string",
                              "description": "e.g. StaticMesh, Material, Blueprint"}},
          "required": ["search_term"]},
         _search_assets),

    Tool("create_actor",
         "Spawn an actor in the level. object_class examples: StaticMeshActor, "
         "PointLight, DirectionalLight, SkyLight, Plane.",
         {"type": "object",
          "properties": {
              "object_class": {"type": "string"},
              "object_name": {"type": "string"},
              "x": _num("World X (cm)"), "y": _num("World Y (cm)"), "z": _num("World Z (cm)"),
              "pitch": _num("Pitch (deg)"), "yaw": _num("Yaw (deg)"), "roll": _num("Roll (deg)"),
              "scale_x": _num("Scale X", 1), "scale_y": _num("Scale Y", 1), "scale_z": _num("Scale Z", 1)},
          "required": ["object_class", "object_name"]},
         _create_actor),

    Tool("delete_actor",
         "Delete one or more actors by label (comma-separated).",
         {"type": "object",
          "properties": {"actor_names": {"type": "string"}},
          "required": ["actor_names"]},
         _delete_actor),

    Tool("update_actor",
         "Update an actor's transform / label by label. Pass only values to change.",
         {"type": "object",
          "properties": {
              "actor_name": {"type": "string"},
              "x": _num("new X (cm)"), "y": _num("new Y (cm)"), "z": _num("new Z (cm)"),
              "pitch": _num("new pitch"), "yaw": _num("new yaw"), "roll": _num("new roll"),
              "scale_x": _num("new scale x", 1), "scale_y": _num("new scale y", 1), "scale_z": _num("new scale z", 1),
              "new_name": {"type": "string", "description": "optional new label"}},
          "required": ["actor_name"]},
         _update_actor),

    Tool("take_screenshot",
         "Capture the current editor viewport to a PNG file.",
         {"type": "object",
          "properties": {
              "path": {"type": "string", "description": "Absolute output image path", "default": "/tmp/ue4_screenshot.png"},
              "width": _int("Image width px", 1920), "height": _int("Image height px", 1080)}},
         _take_screenshot),

    Tool("move_camera",
         "Move the editor viewport camera to a world location.",
         {"type": "object",
          "properties": {
              "x": _num("X (cm)"), "y": _num("Y (cm)"), "z": _num("Z (cm)"),
              "pitch": _num("degrees", -30), "yaw": _num("degrees", 0), "roll": _num("degrees", 0)},
          "required": ["x", "y", "z"]},
         _move_camera),
]
