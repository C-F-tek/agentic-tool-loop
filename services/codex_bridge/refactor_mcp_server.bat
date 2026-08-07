@echo off
REM Wrapper script for refactor-mcp server
cd /d "C:\Users\carmi\AI"
call "venvs\labtools\Scripts\activate.bat" 2>nul || set "PYTHON=python"
"%PYTHON%" -u "services\codex_bridge\refactor_mcp_server.py"