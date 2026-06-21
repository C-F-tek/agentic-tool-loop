from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHON = REPO_ROOT / "venvs" / "labtools" / "Scripts" / "python.exe"
SERVER = Path(__file__).with_name("repo_code_mcp_server.py")
EXPECTED_TOOLS = {
    "aicarmine_repo_code_health",
    "aicarmine_repo_code_propose_edit",
    "aicarmine_repo_code_unidiff_validate",
    "aicarmine_repo_code_git_apply_check",
    "aicarmine_repo_code_apply_patch",
}


def _git(repo: Path, *args: str) -> None:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"git {' '.join(args)} failed: {completed.stderr.strip()}"
        )


def _first_illegal_json_control(data: bytes) -> tuple[int, int] | None:
    in_string = False
    escaped = False
    for offset, value in enumerate(data):
        if in_string:
            if escaped:
                if value < 0x20:
                    return offset, value
                escaped = False
                continue
            if value == 0x5C:
                escaped = True
                continue
            if value == 0x22:
                in_string = False
                continue
            if value < 0x20:
                return offset, value
        elif value == 0x22:
            in_string = True
    return None


def _fixture_text() -> tuple[str, str]:
    crlf = "\r\n"
    lines = [
        "$rawInput = [Console]::In.ReadToEnd()",
        "$root = $PSScriptRoot",
        chr(96) + " continued",
        "[ordered]@{",
        r"    path = \fixture\item",
        "    tab = \tvalue",
        "    unicode = caffè Ω 漢字",
        "    multiline = first",
        "        second",
        "    marker = VALUE=old",
        "}",
    ]
    lines.extend(
        f"# filler {index:04d} \\segment\tcaffè Ω 漢字"
        for index in range(900)
    )
    old_text = crlf.join(lines) + crlf
    new_text = old_text.replace("VALUE=old", "VALUE=new").replace(
        "# filler", "# changed"
    )
    return old_text, new_text


def _write_message(process: subprocess.Popen[bytes], message: dict[str, Any]) -> None:
    assert process.stdin is not None
    raw = json.dumps(
        message,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8") + b"\n"
    process.stdin.write(raw)
    process.stdin.flush()


def _read_response(
    process: subprocess.Popen[bytes],
    captured_stdout: list[bytes],
    decoded_frames: list[dict[str, Any]],
) -> tuple[dict[str, Any], Any]:
    assert process.stdout is not None
    raw_line = process.stdout.readline()
    if not raw_line:
        raise AssertionError("repo_code server closed stdout before responding")
    if not raw_line.endswith(b"\n"):
        raise AssertionError("repo_code JSONL frame is missing its LF delimiter")
    frame = raw_line[:-1]
    illegal = _first_illegal_json_control(frame)
    if illegal is not None:
        raise AssertionError(f"illegal outer JSON control byte: {illegal}")
    outer = json.loads(frame.decode("utf-8"))
    assert json.loads(
        json.dumps(outer, ensure_ascii=False, separators=(",", ":"))
    ) == outer
    captured_stdout.append(raw_line)
    decoded_frames.append(outer)

    result = outer.get("result", {})
    if "content" not in result:
        return outer, result
    text_value = result["content"][0]["text"]
    inner_bytes = text_value.encode("utf-8")
    illegal = _first_illegal_json_control(inner_bytes)
    if illegal is not None:
        raise AssertionError(f"illegal inner JSON control byte: {illegal}")
    payload = json.loads(text_value)
    assert json.loads(json.dumps(payload, ensure_ascii=False)) == payload
    return outer, payload


def _request(
    process: subprocess.Popen[bytes],
    captured_stdout: list[bytes],
    decoded_frames: list[dict[str, Any]],
    message: dict[str, Any],
) -> tuple[dict[str, Any], Any]:
    _write_message(process, message)
    return _read_response(process, captured_stdout, decoded_frames)


def _tool_call(
    process: subprocess.Popen[bytes],
    captured_stdout: list[bytes],
    decoded_frames: list[dict[str, Any]],
    message_id: int,
    name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    _, payload = _request(
        process,
        captured_stdout,
        decoded_frames,
        {
            "jsonrpc": "2.0",
            "id": message_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
    )
    assert isinstance(payload, dict)
    return payload


def _in_memory_round_trip(old_text: str) -> None:
    bridge_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(bridge_dir))
    import repo_mcp_common as common

    value = {
        "ok": True,
        "change_set_id": "a" * 64,
        "unified_diff": old_text,
    }
    tool_result = common.tool_content(value)
    response = common.ok(99, tool_result)
    encoded = json.dumps(response, ensure_ascii=False, separators=(",", ":"))
    decoded = json.loads(encoded)
    decoded_value = json.loads(decoded["result"]["content"][0]["text"])
    assert decoded_value == value


def main() -> int:
    old_text, new_text = _fixture_text()
    assert "$rawInput" in old_text
    assert "$PSScriptRoot" in old_text
    assert chr(96) + " continued" in old_text
    assert "[ordered]@{" in old_text
    assert "\\" in old_text
    assert "\r\n" in old_text
    assert "\t" in old_text
    assert "Ω 漢字" in old_text
    _in_memory_round_trip(old_text)

    with tempfile.TemporaryDirectory(prefix="aicarmine-rc1r-") as temp_dir:
        temp_repo = Path(temp_dir) / "repo"
        temp_repo.mkdir()
        _git(temp_repo, "init", "--quiet")
        _git(temp_repo, "config", "user.email", "rc1r@example.invalid")
        _git(temp_repo, "config", "user.name", "RC1R")
        _git(temp_repo, "config", "core.autocrlf", "false")
        fixture_path = temp_repo / "fixture.ps1"
        fixture_path.write_bytes(old_text.encode("utf-8"))
        _git(temp_repo, "add", "--", "fixture.ps1")
        _git(temp_repo, "commit", "--quiet", "-m", "fixture")

        env = os.environ.copy()
        env["AICARMINE_CODEX_MCP_REPO_ROOT"] = str(temp_repo)
        env["AICARMINE_LAB_REPO"] = str(temp_repo)
        env["AICARMINE_REPO_MCP_MAX_TEXT_CHARS"] = "24000"
        process = subprocess.Popen(
            [str(PYTHON), "-u", str(SERVER)],
            cwd=str(REPO_ROOT),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        captured_stdout: list[bytes] = []
        decoded_frames: list[dict[str, Any]] = []
        try:
            _, initialized = _request(
                process,
                captured_stdout,
                decoded_frames,
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {
                            "name": "repo-code-serialization-test",
                            "version": "1",
                        },
                    },
                },
            )
            assert initialized["protocolVersion"] == "2024-11-05"
            _write_message(
                process,
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                    "params": {},
                },
            )
            _, listed = _request(
                process,
                captured_stdout,
                decoded_frames,
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/list",
                    "params": {},
                },
            )
            names = {tool["name"] for tool in listed["tools"]}
            assert names == EXPECTED_TOOLS

            proposal = _tool_call(
                process,
                captured_stdout,
                decoded_frames,
                3,
                "aicarmine_repo_code_propose_edit",
                {
                    "edit_kind": "structured_edit",
                    "edits": [
                        {
                            "path": "fixture.ps1",
                            "operation": "replace_exact",
                            "old_text": old_text,
                            "new_text": new_text,
                            "expected_occurrences": 1,
                        }
                    ],
                    "rationale": "RC1R real stdio serialization regression",
                    "validation_commands": ["git diff --check"],
                },
            )
            assert proposal["ok"] is True
            change_set_id = proposal["change_set_id"]
            diff_sha256 = proposal["diff_sha256"]
            file_count = proposal["file_count"]
            proposed_stage = proposal["change_set_stage"]
            assert re.fullmatch(r"[0-9a-f]{64}", change_set_id)
            assert re.fullmatch(r"[0-9a-f]{64}", diff_sha256)
            assert file_count == 1
            assert proposed_stage == "proposed"
            assert len(proposal["unified_diff"]) > 24000

            validated = _tool_call(
                process,
                captured_stdout,
                decoded_frames,
                4,
                "aicarmine_repo_code_unidiff_validate",
                {"change_set_id": change_set_id},
            )
            checked = _tool_call(
                process,
                captured_stdout,
                decoded_frames,
                5,
                "aicarmine_repo_code_git_apply_check",
                {"change_set_id": change_set_id},
            )
            applied = _tool_call(
                process,
                captured_stdout,
                decoded_frames,
                6,
                "aicarmine_repo_code_apply_patch",
                {
                    "change_set_id": change_set_id,
                    "allow_source_write": True,
                },
            )
            assert validated["ok"] is True
            assert checked["ok"] is True
            assert applied["ok"] is True
            assert applied["change_set_stage"] == "applied"
            assert fixture_path.read_bytes() == new_text.encode("utf-8")

            assert process.stdin is not None
            process.stdin.close()
            assert process.stdout is not None
            remaining_stdout = process.stdout.read()
            assert process.stderr is not None
            stderr = process.stderr.read()
            exit_code = process.wait(timeout=30)
            assert exit_code == 0
            assert remaining_stdout == b""
            assert stderr == b""

            raw_stdout = b"".join(captured_stdout)
            assert raw_stdout
            assert len(decoded_frames) == 6
            for raw_frame in captured_stdout:
                assert _first_illegal_json_control(raw_frame[:-1]) is None

            summary = {
                "ok": proposal["ok"],
                "change_set_id": change_set_id,
                "diff_sha256": diff_sha256,
                "file_count": file_count,
                "change_set_stage": proposed_stage,
                "validate_ok": validated["ok"],
                "git_apply_check_ok": checked["ok"],
                "apply_ok": applied["ok"],
                "decoded_frames": len(decoded_frames),
                "stdout_bytes": len(raw_stdout),
                "stderr_bytes": len(stderr),
                "illegal_json_control_bytes": 0,
            }
            print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
            print("ALL AICARMINE REPO CODE SERIALIZATION TESTS PASSED")
            return 0
        finally:
            if process.poll() is None:
                if process.stdin is not None and not process.stdin.closed:
                    process.stdin.close()
                process.kill()
                process.wait(timeout=10)


if __name__ == "__main__":
    raise SystemExit(main())
