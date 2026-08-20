import asyncio
import json
import os
import sys
import traceback

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> int:
    if len(sys.argv) < 3:
        print(
            "Uso: test_mcp.py <server.py> <tool_da_invocare>",
            file=sys.stderr,
        )
        return 2

    server_script = os.path.abspath(sys.argv[1])
    tool_to_call = sys.argv[2]

    python_exe = r"C:\Users\carmi\AI\venvs\labtools\Scripts\python.exe"

    env = os.environ.copy()
    env.update(
        {
            "AICARMINE_CODEX_MCP_REPO_ROOT": r"C:\Users\carmi\AI",
            "AICARMINE_LAB_REPO": r"C:\Users\carmi\AI",
            "AICARMINE_USEFUL_TOOLS_ROOT": r"C:\Users\carmi\AI\services\useful_tools",
            "AICARMINE_REPO_MCP_MAX_TEXT_CHARS": "24000",
        }
    )

    params = StdioServerParameters(
        command=python_exe,
        args=["-u", server_script],
        cwd=r"C:\Users\carmi\AI",
        env=env,
    )

    print(f"SERVER : {server_script}")
    print(f"PYTHON : {python_exe}")
    print(f"TOOL   : {tool_to_call}")
    print()

    try:
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                print("[1] initialize")
                init_result = await session.initialize()

                print("[OK] initialize completato")
                print(
                    json.dumps(
                        {
                            "protocolVersion": getattr(
                                init_result,
                                "protocolVersion",
                                None,
                            ),
                            "serverInfo": str(
                                getattr(init_result, "serverInfo", None)
                            ),
                            "capabilities": str(
                                getattr(init_result, "capabilities", None)
                            ),
                        },
                        indent=2,
                        ensure_ascii=False,
                    )
                )

                print()
                print("[2] tools/list")
                tools_result = await session.list_tools()
                tool_names = [tool.name for tool in tools_result.tools]

                print(f"[OK] tools/list: {len(tool_names)} tool")
                for name in tool_names:
                    print(f"  - {name}")

                if tool_to_call not in tool_names:
                    print()
                    print(
                        f"[ERRORE] Tool non trovato: {tool_to_call}",
                        file=sys.stderr,
                    )
                    return 3

                print()
                print(f"[3] tools/call: {tool_to_call}")
                call_result = await session.call_tool(
                    tool_to_call,
                    arguments={},
                )

                print("[OK] tools/call completato")
                print(call_result)

                return 0

    except Exception:
        print()
        print("[ERRORE MCP]", file=sys.stderr)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
