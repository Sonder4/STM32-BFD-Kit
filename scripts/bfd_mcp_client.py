#!/usr/bin/env python3
"""Minimal MCP stdio client for MathWorks Matlab and Simulink servers."""

from __future__ import annotations

import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import time
from typing import Any, Optional


class McpError(RuntimeError):
    """Raised when MCP communication or tool execution fails."""


def _is_executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def find_mcp_server(explicit: Optional[str] = None) -> Optional[str]:
    candidates: list[Optional[str]] = [
        explicit,
        os.environ.get("MATLAB_MCP_SERVER"),
        shutil.which("matlab-mcp-core-server"),
        str(Path.home() / ".local" / "bin" / "matlab-mcp-core-server"),
        str(Path.home() / "Tools" / "matlab-mcp-core-server" / "matlab-mcp-core-server"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if _is_executable(path):
            return str(path.resolve())
    return None


def _json_default(value: Any) -> str:
    return str(value)


class McpStdioClient:
    def __init__(self, command: list[str], *, timeout_s: float = 120.0) -> None:
        self.command = command
        self.timeout_s = timeout_s
        self.proc: subprocess.Popen[bytes] | None = None
        self._next_id = 1
        self._buffer = b""

    def __enter__(self) -> "McpStdioClient":
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def start(self) -> None:
        if self.proc is not None:
            return
        self.proc = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def close(self) -> None:
        if self.proc is None:
            return
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=2)
        self.proc = None

    def initialize(self) -> dict[str, Any]:
        result = self.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "bfd-kit", "version": "0.1"},
            },
        )
        self.notify("notifications/initialized", {})
        return result

    def list_tools(self) -> list[dict[str, Any]]:
        result = self.request("tools/list", {})
        tools = result.get("tools", [])
        if not isinstance(tools, list):
            raise McpError("MCP tools/list returned an invalid payload")
        return tools

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self.request("tools/call", {"name": name, "arguments": arguments})

    def notify(self, method: str, params: dict[str, Any]) -> None:
        self._write_message({"jsonrpc": "2.0", "method": method, "params": params})

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        self._write_message({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + self.timeout_s
        while True:
            message = self._read_message(deadline)
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise McpError(f"MCP request {method} failed: {message['error']}")
            result = message.get("result", {})
            if not isinstance(result, dict):
                raise McpError(f"MCP request {method} returned an invalid result")
            return result

    def _write_message(self, payload: dict[str, Any]) -> None:
        if self.proc is None or self.proc.stdin is None:
            raise McpError("MCP process is not started")
        body = json.dumps(payload, ensure_ascii=False, default=_json_default).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        self.proc.stdin.write(header + body)
        self.proc.stdin.flush()

    def _read_message(self, deadline: float) -> dict[str, Any]:
        header_end = b"\r\n\r\n"
        while header_end not in self._buffer:
            self._read_available(deadline)
        header, self._buffer = self._buffer.split(header_end, 1)
        length = None
        for line in header.decode("ascii", errors="replace").split("\r\n"):
            if line.lower().startswith("content-length:"):
                length = int(line.split(":", 1)[1].strip())
                break
        if length is None:
            raise McpError("MCP frame missing Content-Length header")
        while len(self._buffer) < length:
            self._read_available(deadline)
        body = self._buffer[:length]
        self._buffer = self._buffer[length:]
        parsed = json.loads(body.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise McpError("MCP frame is not a JSON object")
        return parsed

    def _read_available(self, deadline: float) -> None:
        if self.proc is None or self.proc.stdout is None:
            raise McpError("MCP process is not started")
        if self.proc.poll() is not None:
            stderr = ""
            if self.proc.stderr is not None:
                stderr = self.proc.stderr.read().decode("utf-8", errors="replace")
            raise McpError(f"MCP process exited with {self.proc.returncode}: {stderr.strip()}")
        remaining = max(0.0, deadline - time.monotonic())
        if remaining == 0:
            raise McpError("MCP response timed out")
        readable, _, _ = select.select([self.proc.stdout], [], [], remaining)
        if not readable:
            raise McpError("MCP response timed out")
        chunk = os.read(self.proc.stdout.fileno(), 65536)
        if not chunk:
            raise McpError("MCP process closed stdout")
        self._buffer += chunk


def _tool_by_name(tools: list[dict[str, Any]], name: str) -> Optional[dict[str, Any]]:
    for tool in tools:
        if tool.get("name") == name:
            return tool
    return None


def _schema_properties(tool: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not tool:
        return {}
    schema = tool.get("inputSchema", {})
    if not isinstance(schema, dict):
        return {}
    props = schema.get("properties", {})
    return props if isinstance(props, dict) else {}


def _pick_arg_name(tool: Optional[dict[str, Any]], candidates: list[str], fallback: str) -> str:
    props = _schema_properties(tool)
    for candidate in candidates:
        if candidate in props:
            return candidate
    return fallback


def _tool_text(result: dict[str, Any]) -> str:
    content = result.get("content", [])
    if not isinstance(content, list):
        return json.dumps(result, ensure_ascii=False, indent=2, default=_json_default)
    chunks: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if "text" in item:
            chunks.append(str(item["text"]))
        elif "data" in item:
            chunks.append(json.dumps(item["data"], ensure_ascii=False, default=_json_default))
    return "\n".join(chunks).strip()


def _call_code_tool(client: McpStdioClient, tool: dict[str, Any], code: str) -> dict[str, Any]:
    arg_name = _pick_arg_name(tool, ["code", "matlab_code", "script", "command"], "code")
    return client.call_tool(str(tool["name"]), {arg_name: code})


def _call_file_tool(client: McpStdioClient, tool: dict[str, Any], script_path: Path) -> dict[str, Any]:
    arg_name = _pick_arg_name(tool, ["file_path", "path", "file", "filename", "script_path"], "file_path")
    return client.call_tool(str(tool["name"]), {arg_name: str(script_path.resolve())})


def _run_expr(script_path: Path) -> str:
    escaped = str(script_path.resolve()).replace("'", "''")
    return f"run('{escaped}')"


def run_matlab_script_via_mcp(
    *,
    server: str,
    server_args: list[str],
    script_path: Path,
    satk_root: Optional[str] = None,
    timeout_s: float = 180.0,
) -> dict[str, Any]:
    command = [server, *server_args]
    with McpStdioClient(command, timeout_s=timeout_s) as client:
        initialize_result = client.initialize()
        tools = client.list_tools()
        tool_names = [str(tool.get("name", "")) for tool in tools]

        result: dict[str, Any] = {
            "backend": "mcp",
            "command": command,
            "initialize_result": initialize_result,
            "tool_names": tool_names,
            "toolbox_result": None,
            "check_result": None,
            "satk_result": None,
            "run_result": None,
        }

        toolbox_tool = _tool_by_name(tools, "detect_matlab_toolboxes")
        if toolbox_tool:
            result["toolbox_result"] = client.call_tool("detect_matlab_toolboxes", {})

        evaluate_tool = _tool_by_name(tools, "evaluate_matlab_code")
        if satk_root and evaluate_tool:
            escaped = str(Path(satk_root).expanduser().resolve()).replace("'", "''")
            code = (
                f"addpath(genpath('{escaped}')); "
                "if exist('satk_initialize','file') == 2, satk_initialize; end; "
                "disp('SATK initialization check complete');"
            )
            result["satk_result"] = _call_code_tool(client, evaluate_tool, code)

        check_tool = _tool_by_name(tools, "check_matlab_code")
        if check_tool:
            props = _schema_properties(check_tool)
            if any(name in props for name in ["file_path", "path", "file", "filename", "script_path"]):
                result["check_result"] = _call_file_tool(client, check_tool, script_path)
            else:
                result["check_result"] = _call_code_tool(client, check_tool, script_path.read_text(encoding="utf-8"))

        run_file_tool = _tool_by_name(tools, "run_matlab_file")
        if run_file_tool:
            result["run_result"] = _call_file_tool(client, run_file_tool, script_path)
        elif evaluate_tool:
            result["run_result"] = _call_code_tool(client, evaluate_tool, _run_expr(script_path))
        else:
            raise McpError("MCP server exposes neither run_matlab_file nor evaluate_matlab_code")

        result["log_text"] = "\n\n".join(
            text
            for text in [
                _tool_text(result["toolbox_result"]) if result["toolbox_result"] else "",
                _tool_text(result["check_result"]) if result["check_result"] else "",
                _tool_text(result["satk_result"]) if result["satk_result"] else "",
                _tool_text(result["run_result"]) if result["run_result"] else "",
            ]
            if text
        )
        return result
