@echo off
setlocal EnableExtensions
chcp 65001 >nul
title 智鉴黄精 - 启动

rem ============================================================
rem  智鉴黄精 AI 品质检测系统 - Windows 启动脚本
rem ============================================================

set "ESC="
for /F %%a in ('echo prompt $E ^| cmd') do set "ESC=%%a"
set "G=%ESC%[92m"
set "Y=%ESC%[93m"
set "R=%ESC%[91m"
set "C=%ESC%[96m"
set "N=%ESC%[0m"

for %%i in ("%~dp0..") do set "ROOT=%%~fi"
set "VPY=%ROOT%\venv\Scripts\python.exe"

echo.
echo %C%==============================================%N%
echo %C%     智鉴黄精 - AI 黄精品质检测系统 启动     %N%
echo %C%==============================================%N%
echo.

if not exist "%VPY%" (
    echo %R%[错误] 未找到虚拟环境。%N%
    echo   请先双击运行 scripts\install.bat 完成安装。
    echo.
    pause
    exit /b 1
)

if not exist "%ROOT%\app.py" (
    echo %R%[错误] 未找到项目入口 app.py。%N%
    echo   请确认项目代码完整, 必要时重新运行 scripts\install.bat。
    echo.
    pause
    exit /b 1
)

if not exist "%ROOT%\.env" (
    echo %Y%[提示] 未找到配置文件 .env, 请先运行 scripts\install.bat 完成配置。%N%
    echo.
)

echo %G%正在启动 Streamlit 应用 ...%N%
echo %G%启动后请在浏览器访问 http://localhost:8501 (如修改过端口请使用实际端口)%N%
echo %G%按 Ctrl+C 可停止应用。%N%
echo.
cd /d "%ROOT%"
call "%ROOT%\venv\Scripts\activate.bat"
"%VPY%" -m streamlit run app.py --server.address 0.0.0.0 --server.port 8501
set "EXITCODE=%errorlevel%"

echo.
if not "%EXITCODE%"=="0" (
    echo %R%应用异常退出 (退出码 %EXITCODE%)。%N%
    echo   常见原因: 端口被占用、依赖缺失、.env 配置错误。
) else (
    echo %G%应用已停止。%N%
)
echo.
pause
exit /b %EXITCODE%
