@echo off
setlocal EnableExtensions
chcp 65001 >nul
title 智鉴黄精 - 环境检查

rem ============================================================
rem  智鉴黄精 AI 品质检测系统 - Windows 环境检查脚本
rem ============================================================

set "ESC="
for /F %%a in ('echo prompt $E ^| cmd') do set "ESC=%%a"
set "G=%ESC%[92m"
set "Y=%ESC%[93m"
set "R=%ESC%[91m"
set "C=%ESC%[96m"
set "N=%ESC%[0m"

set "FAILS=0"
for %%i in ("%~dp0..") do set "ROOT=%%~fi"
set "VPY=%ROOT%\venv\Scripts\python.exe"
set "VPIP=%ROOT%\venv\Scripts\pip.exe"

echo.
echo %C%==============================================%N%
echo %C%     智鉴黄精 - 运行环境检查                 %N%
echo %C%==============================================%N%
echo 项目目录: %ROOT%
echo.

echo %C%[1/5] Python (系统)%N%
set "SYS_PY="
python --version >nul 2>&1
if not errorlevel 1 set "SYS_PY=python"
if not defined SYS_PY (
    py -3 --version >nul 2>&1
    if not errorlevel 1 set "SYS_PY=py -3"
)
if defined SYS_PY (
    for /f "tokens=2" %%v in ('%SYS_PY% --version 2^>nul') do set "PYVER=%%v"
    echo   %G%[OK]%N% Python %PYVER%
) else (
    echo   %R%[失败]%N% 未检测到 Python, 请安装 Python 3.8+ 并勾选 Add to PATH
    set /a FAILS+=1
)
echo.

echo %C%[2/5] pip%N%
set "HAS_PIP=0"
if defined SYS_PY (
    %SYS_PY% -m pip --version >nul 2>&1
    if not errorlevel 1 set "HAS_PIP=1"
)
if "%HAS_PIP%"=="1" (
    echo   %G%[OK]%N% pip 可用
) else (
    echo   %R%[失败]%N% pip 不可用
    set /a FAILS+=1
)
echo.

echo %C%[3/5] 虚拟环境%N%
if exist "%VPY%" (
    echo   %G%[OK]%N% 虚拟环境存在: %ROOT%\venv
    "%VPY%" --version >nul 2>&1
    if errorlevel 1 (
        echo   %R%[失败]%N% 虚拟环境中的 Python 无法运行, 建议删除 venv 后重新安装
        set /a FAILS+=1
    )
) else (
    echo   %R%[失败]%N% 虚拟环境不存在, 请先运行 scripts\install.bat
    set /a FAILS+=1
)
echo.

echo %C%[4/5] 依赖包%N%
if exist "%VPY%" (
    if exist "%ROOT%\requirements.txt" (
        "%VPY%" -m pip install --quiet --dry-run -r "%ROOT%\requirements.txt" >nul 2>&1
        if errorlevel 1 (
            echo   %Y%[警告]%N% 依赖可能不完整或有新版本可用
            echo     重新运行 scripts\install.bat 可修复
        ) else (
            echo   %G%[OK]%N% requirements.txt 中的依赖均已安装
        )
        "%VPY%" -m pip show streamlit >nul 2>&1
        if errorlevel 1 (
            echo   %R%[失败]%N% 核心依赖 streamlit 未安装
            set /a FAILS+=1
        ) else (
            for /f "tokens=2" %%v in ('"%VPIP%" show streamlit 2^>nul ^| findstr /i "^Version:"') do echo   %G%[OK]%N% streamlit %%v
        )
    ) else (
        echo   %Y%[警告]%N% 未找到 requirements.txt, 跳过依赖检查
    )
) else (
    echo   %R%[跳过]%N% 虚拟环境不存在, 无法检查依赖
)
echo.

echo %C%[5/5] 配置文件 .env%N%
if not exist "%ROOT%\.env" (
    echo   %R%[失败]%N% 未找到 .env 配置文件, 请运行 scripts\install.bat 完成配置
    set /a FAILS+=1
    goto :summary
)
echo   %G%[OK]%N% .env 文件存在

findstr /r /c:"^ARK_API_KEY=..*" "%ROOT%\.env" >nul 2>&1
if errorlevel 1 (
    echo   %R%[失败]%N% ARK_API_KEY 未配置 (在线模式无法检测)
    set /a FAILS+=1
) else (
    echo   %G%[OK]%N% ARK_API_KEY 已配置 (内容不显示)
)
for /f "tokens=1,* delims==" %%a in ('findstr /b "ARK_BASE_URL= ARK_MODEL= APP_MODE= PORT=" "%ROOT%\.env"') do (
    echo   [..] %%a = %%b
)
echo.

:summary
echo %C%==============================================%N%
if %FAILS% EQU 0 (
    echo %G%  检查完成: 全部通过, 可以运行 scripts\run.bat 启动%N%
) else (
    echo %R%  检查完成: 发现 %FAILS% 项问题, 请根据上方提示修复%N%
)
echo %C%==============================================%N%
echo.
pause
if %FAILS% GTR 0 exit /b 1
exit /b 0
