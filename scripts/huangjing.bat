@echo off
rem 智鉴黄精 CLI wrapper (Windows)

setlocal
set "SCRIPT_DIR=%~dp0"
for %%i in ("%SCRIPT_DIR%..") do set "ROOT_DIR=%%~fi"
set "VENV_PYTHON=%ROOT_DIR%\venv\Scripts\python.exe"

if not exist "%VENV_PYTHON%" (
    echo 错误: 虚拟环境不存在，请先运行 scripts\install.bat
    exit /b 1
)

"%VENV_PYTHON%" "%SCRIPT_DIR%\huangjing_cli.py" %*
