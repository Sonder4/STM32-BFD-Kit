#!/usr/bin/env python3
"""BFD-Kit tool path configuration for cross-platform STM32 workflows."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import sys


WINDOWS_DEFAULT_CUBECLT_ROOTS = [
    r"D:\STM32CubeCLT",
    r"C:\ST\STM32CubeCLT",
]
LINUX_DEFAULT_CUBECLT_ROOTS = [
    "/opt/st/stm32cubeclt",
    "/opt/STM32CubeCLT",
]

TOOL_CANDIDATES = {
    "cmake": ["cmake"],
    "ninja": ["ninja"],
    "arm_none_eabi_gcc": ["arm-none-eabi-gcc"],
    "arm_none_eabi_gdb": ["arm-none-eabi-gdb"],
    "pyocd": ["pyocd"],
    "openocd": ["openocd"],
    "jlink_exe": ["JLinkExe", "JLink.exe"],
    "jlink_gdb_server": ["JLinkGDBServerCLExe", "JLinkGDBServerCL.exe"],
    "stm32cubeprogrammer_cli": ["STM32_Programmer_CLI", "STM32_Programmer_CLI.exe"],
    "stlink_gdb_server": ["ST-LINK_gdbserver", "ST-LINK_gdbserver.exe"],
    "keil_uv4": ["UV4", "UV4.exe"],
}


def detect_host_os() -> str:
    raw = platform.system().lower()
    if raw == "windows":
        return "windows"
    if raw == "darwin":
        return "macos"
    return "linux"


def global_config_path(*, home: str | Path | None = None) -> Path:
    home_path = Path(home).expanduser() if home is not None else Path.home()
    return home_path / ".config" / "bfd-kit" / "tool_config.json"


def workspace_config_path(workspace: str | Path | None = None) -> Path:
    root = Path(workspace or Path.cwd()).resolve()
    return root / ".codex" / "bfd" / "tool_config.json"


def _load_config(path: Path) -> dict:
    if not path.is_file():
        return {"tools": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"tools": {}}
    if not isinstance(payload, dict):
        return {"tools": {}}
    tools = payload.get("tools")
    if not isinstance(tools, dict):
        payload["tools"] = {}
    return payload


def _save_config(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def set_tool_path(
    tool: str,
    path: str,
    *,
    workspace: str | Path | None = None,
    home: str | Path | None = None,
    global_flag: bool = False,
) -> Path:
    config_path = global_config_path(home=home) if global_flag else workspace_config_path(workspace)
    payload = _load_config(config_path)
    payload.setdefault("tools", {})[tool] = str(Path(path).expanduser())
    payload["host_os"] = detect_host_os()
    return _save_config(config_path, payload)


def get_tool_path(
    tool: str,
    *,
    workspace: str | Path | None = None,
    home: str | Path | None = None,
) -> str | None:
    workspace_cfg = _load_config(workspace_config_path(workspace))
    workspace_tools = workspace_cfg.get("tools", {})
    if tool in workspace_tools:
        return str(workspace_tools[tool])
    global_cfg = _load_config(global_config_path(home=home))
    global_tools = global_cfg.get("tools", {})
    if tool in global_tools:
        return str(global_tools[tool])
    return None


def list_tools(
    *,
    workspace: str | Path | None = None,
    home: str | Path | None = None,
) -> dict[str, dict[str, str]]:
    merged: dict[str, dict[str, str]] = {}
    global_tools = _load_config(global_config_path(home=home)).get("tools", {})
    for name, path in global_tools.items():
        merged[name] = {"path": str(path), "source": "global"}
    workspace_tools = _load_config(workspace_config_path(workspace)).get("tools", {})
    for name, path in workspace_tools.items():
        merged[name] = {"path": str(path), "source": "workspace"}
    return merged


def remove_tool_path(
    tool: str,
    *,
    workspace: str | Path | None = None,
    home: str | Path | None = None,
    global_flag: bool = False,
) -> bool:
    config_path = global_config_path(home=home) if global_flag else workspace_config_path(workspace)
    payload = _load_config(config_path)
    tools = payload.get("tools", {})
    if tool not in tools:
        return False
    del tools[tool]
    _save_config(config_path, payload)
    return True


def _cubeclt_root_candidates(host_os: str) -> list[Path]:
    roots = WINDOWS_DEFAULT_CUBECLT_ROOTS if host_os == "windows" else LINUX_DEFAULT_CUBECLT_ROOTS
    env_root = os.environ.get("STM32CUBECLT_ROOT")
    if env_root:
        roots = [env_root, *roots]
    return [Path(item) for item in roots]


def detect_default_tools(*, host_os: str | None = None) -> dict[str, str]:
    normalized = host_os or detect_host_os()
    found: dict[str, str] = {}
    for tool_name, executables in TOOL_CANDIDATES.items():
        for executable in executables:
            resolved = shutil.which(executable)
            if resolved:
                found[tool_name] = resolved
                break
    for root in _cubeclt_root_candidates(normalized):
        if root.is_dir():
            found.setdefault("stm32cubeclt_root", str(root))
            programmer = root / "STM32CubeProgrammer" / "bin" / ("STM32_Programmer_CLI.exe" if normalized == "windows" else "STM32_Programmer_CLI")
            if programmer.is_file():
                found.setdefault("stm32cubeprogrammer_cli", str(programmer))
            stlink = root / "STLink-gdb-server" / "bin" / ("ST-LINK_gdbserver.exe" if normalized == "windows" else "ST-LINK_gdbserver")
            if stlink.is_file():
                found.setdefault("stlink_gdb_server", str(stlink))
            segger = root / "Segger"
            if segger.is_dir():
                jlink_exe = next(segger.rglob("JLink.exe" if normalized == "windows" else "JLinkExe"), None)
                if jlink_exe and jlink_exe.is_file():
                    found.setdefault("jlink_exe", str(jlink_exe))
                jlink_gdb = next(segger.rglob("JLinkGDBServerCL.exe" if normalized == "windows" else "JLinkGDBServerCLExe"), None)
                if jlink_gdb and jlink_gdb.is_file():
                    found.setdefault("jlink_gdb_server", str(jlink_gdb))
            break
    return found


def _cmd_set(args: argparse.Namespace) -> int:
    config_path = set_tool_path(
        args.tool,
        args.path,
        workspace=args.workspace,
        global_flag=args.global_flag,
    )
    print(config_path)
    return 0


def _cmd_get(args: argparse.Namespace) -> int:
    path = get_tool_path(args.tool, workspace=args.workspace)
    if path is None:
        return 1
    print(path)
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    print(json.dumps(list_tools(workspace=args.workspace), indent=2, ensure_ascii=False))
    return 0


def _cmd_remove(args: argparse.Namespace) -> int:
    removed = remove_tool_path(args.tool, workspace=args.workspace, global_flag=args.global_flag)
    return 0 if removed else 1


def _cmd_path(args: argparse.Namespace) -> int:
    payload = {
        "global_config": str(global_config_path()),
        "workspace_config": str(workspace_config_path(args.workspace)),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def _cmd_detect(args: argparse.Namespace) -> int:
    found = detect_default_tools(host_os=args.host_os)
    if args.write:
        for name, path in found.items():
            set_tool_path(name, path, workspace=args.workspace, global_flag=args.global_flag)
    print(json.dumps(found, indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="BFD-Kit tool path configuration")
    subparsers = parser.add_subparsers(dest="command")

    set_parser = subparsers.add_parser("set", help="Persist a tool path")
    set_parser.add_argument("tool")
    set_parser.add_argument("path")
    set_parser.add_argument("--workspace")
    set_parser.add_argument("--global", dest="global_flag", action="store_true")

    get_parser = subparsers.add_parser("get", help="Read a configured tool path")
    get_parser.add_argument("tool")
    get_parser.add_argument("--workspace")

    list_parser = subparsers.add_parser("list", help="List configured tools")
    list_parser.add_argument("--workspace")

    remove_parser = subparsers.add_parser("remove", help="Delete a configured tool path")
    remove_parser.add_argument("tool")
    remove_parser.add_argument("--workspace")
    remove_parser.add_argument("--global", dest="global_flag", action="store_true")

    path_parser = subparsers.add_parser("path", help="Show config file locations")
    path_parser.add_argument("--workspace")

    detect_parser = subparsers.add_parser("detect", help="Detect common tool paths from PATH and STM32CubeCLT")
    detect_parser.add_argument("--workspace")
    detect_parser.add_argument("--host-os", choices=["linux", "macos", "windows"])
    detect_parser.add_argument("--write", action="store_true")
    detect_parser.add_argument("--global", dest="global_flag", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 1
    dispatch = {
        "set": _cmd_set,
        "get": _cmd_get,
        "list": _cmd_list,
        "remove": _cmd_remove,
        "path": _cmd_path,
        "detect": _cmd_detect,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
