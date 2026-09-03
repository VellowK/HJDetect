@echo off
setlocal EnableExtensions
chcp 65001 >nul
title 智鉴黄精 - 一键安装

rem ============================================================
rem  智鉴黄精 AI 品质检测系统 - Windows 一键安装脚本
rem  功能: 环境检查 / 拉取代码 / 虚拟环境 / 依赖安装 / 配置向导
rem ============================================================

rem ---- 取 ANSI 转义字符用于彩色输出 (Win10+) ----
set "ESC="
for /F %%a in ('echo prompt $E ^| cmd') do set "ESC=%%a"
set "G=%ESC%[92m"
set "Y=%ESC%[93m"
set "R=%ESC%[91m"
set "C=%ESC%[96m"
set "N=%ESC%[0m"

rem ---- 计算项目根目录 (scripts 的上一级) ----
for %%i in ("%~dp0..") do set "ROOT=%%~fi"
set "VENV=%ROOT%\venv"
set "VPY=%VENV%\Scripts\python.exe"
set "ENV_FILE=%ROOT%\.env"
set "REPO_URL=https://github.com/VellowK/HJDetect"

echo.
echo %C%==============================================%N%
echo %C%   智鉴黄精 - AI 黄精品质检测系统 安装向导   %N%
echo %C%==============================================%N%
echo.
echo 项目目录: %ROOT%
echo.

rem ============================================================
rem 步骤 1/6: 检查 Git
rem ============================================================
echo %C%[1/6]%N% 检查 Git ...
git --version >nul 2>&1
if errorlevel 1 (
    echo %R%  [错误] 未检测到 Git。%N%
    echo   请先安装 Git: https://git-scm.com/download/win
    echo   安装时全部默认选项即可, 安装完成后重新运行本脚本。
    goto :fail
)
for /f "tokens=3" %%v in ('git --version 2^>nul') do echo   [OK] Git %%v
echo.

rem ============================================================
rem 步骤 2/6: 获取或更新代码
rem ============================================================
echo %C%[2/6]%N% 获取 / 更新项目代码 ...
if exist "%ROOT%\.git" (
    git -C "%ROOT%" pull --ff-only >nul 2>&1
    if errorlevel 1 (
        echo %Y%  [警告] 代码更新失败, 将继续使用本地现有代码。%N%
        echo   可稍后手动执行: git pull
    ) else (
        echo   [OK] 代码已是最新。
    )
) else if exist "%ROOT%\app.py" (
    echo   [OK] 检测到本地项目代码, 跳过克隆。
) else (
    echo   未检测到项目代码, 正在从 GitHub 克隆 ...
    echo   %REPO_URL%
    set "TMP_CLONE=%TEMP%\HJDetect_clone_%RANDOM%"
    git clone --depth 1 "%REPO_URL%" "!TMP_CLONE!" >nul 2>&1
    if errorlevel 1 (
        echo %R%  [错误] 克隆失败。%N%
        echo   请检查网络连接后重试, 或手动执行:
        echo   git clone %REPO_URL% "%ROOT%"
        goto :fail
    )
    robocopy "!TMP_CLONE!" "%ROOT%" /E /MOVE /NFL /NDL /NJH /NJS >nul
    if exist "!TMP_CLONE!" rd /s /q "!TMP_CLONE!" 2>nul
    echo   [OK] 代码克隆完成。
)
echo.

rem ============================================================
rem 步骤 3/6: 检查 Python 3.8+
rem ============================================================
echo %C%[3/6]%N% 检查 Python 3.8+ ...
set "PY="
python --version >nul 2>&1
if not errorlevel 1 set "PY=python"
if not defined PY (
    py -3 --version >nul 2>&1
    if not errorlevel 1 set "PY=py -3"
)
if not defined PY (
    echo %R%  [错误] 未检测到 Python。%N%
    echo   请安装 Python 3.8 或更高版本: https://www.python.org/downloads/
    echo   安装时务必勾选 "Add Python to PATH"。
    goto :fail
)
for /f "tokens=2" %%v in ('%PY% --version 2^>nul') do set "PYVER=%%v"
for /f "tokens=1,2 delims=." %%a in ("%PYVER%") do (
    set "PYMAJOR=%%a"
    set "PYMINOR=%%b"
)
if %PYMAJOR% LSS 3 goto :py_too_old
if %PYMAJOR% EQU 3 if %PYMINOR% LSS 8 goto :py_too_old
echo   [OK] Python %PYVER%
echo.

rem ============================================================
rem 步骤 4/6: 创建虚拟环境
rem ============================================================
echo %C%[4/6]%N% 创建 Python 虚拟环境 ...
if exist "%VPY%" (
    echo   [OK] 虚拟环境已存在, 跳过创建。
) else (
    %PY% -m venv "%VENV%"
    if errorlevel 1 (
        echo %R%  [错误] 虚拟环境创建失败。%N%
        goto :fail
    )
    echo   [OK] 虚拟环境创建完成: %VENV%
)
echo.

rem ============================================================
rem 步骤 5/6: 安装依赖
rem ============================================================
echo %C%[5/6]%N% 安装项目依赖 ...
if not exist "%ROOT%\requirements.txt" (
    echo %Y%  [警告] 未找到 requirements.txt, 跳过依赖安装。%N%
    goto :wizard
)
set "USE_MIRROR=n"
set /p USE_MIRROR=  是否使用清华镜像源加速下载? (y/n, 回车默认 n): 
if /i "%USE_MIRROR%"=="y" (
    echo   正在升级 pip (使用镜像) ...
    "%VPY%" -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1
    echo   正在安装依赖, 可能需要几分钟, 请耐心等待 ...
    "%VPY%" -m pip install -r "%ROOT%\requirements.txt" -i https://pypi.tuna.tsinghua.edu.cn/simple
) else (
    echo   正在升级 pip ...
    "%VPY%" -m pip install --upgrade pip >nul 2>&1
    echo   正在安装依赖, 可能需要几分钟, 请耐心等待 ...
    "%VPY%" -m pip install -r "%ROOT%\requirements.txt"
)
if errorlevel 1 (
    echo %R%  [错误] 依赖安装失败。%N%
    echo   请检查网络连接后重新运行本脚本。
    goto :fail
)
echo   [OK] 依赖安装完成。
echo.

rem ============================================================
rem 步骤 6/6: 交互式配置向导
rem ============================================================
:wizard
echo %C%[6/6]%N% 配置向导 ...
if exist "%ENV_FILE%" (
    echo   检测到已有配置文件 .env
    set "RECONF=n"
    set /p RECONF=  是否重新配置? (y/n, 回车默认 n): 
    if /i not "%RECONF%"=="y" goto :done
)

echo.
echo   请回答以下问题, 直接回车使用 [方括号] 中的默认值。
echo.

rem ---- 运行模式 ----
set "APP_MODE=online"
echo   运行模式:
echo     1. online - 在线模式, 调用豆包视觉模型真实检测
echo     2. demo   - 演示模式, 使用预置结果 (演示容灾用)
set /p MODE_CHOICE=  请选择 (1/2, 回车默认 1): 
if "%MODE_CHOICE%"=="2" set "APP_MODE=demo"
echo   运行模式: %APP_MODE%
echo.

rem ---- API Key (隐藏输入) ----
set "ARK_API_KEY="
if "%APP_MODE%"=="demo" goto :ask_base_url
:ask_key
echo   请输入火山方舟 ARK API Key (输入内容不会显示):
powershell -NoProfile -Command "$s = Read-Host '  API Key' -AsSecureString; [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s))" > "%TEMP%\hk_key.txt" 2>nul
set /p ARK_API_KEY=<"%TEMP%\hk_key.txt"
del "%TEMP%\hk_key.txt" 2>nul
if not defined ARK_API_KEY (
    echo %Y%  [提示] API Key 不能为空, 在线模式必须有 Key 才能检测。%N%
    goto :ask_key
)
echo   [OK] API Key 已记录。
echo.

:ask_base_url
set "ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3"
set /p ARK_BASE_URL=  API 地址 (回车默认 https://ark.cn-beijing.volces.com/api/v3): 
if not defined ARK_BASE_URL set "ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3"
echo   API 地址: %ARK_BASE_URL%
echo.

set "ARK_MODEL=doubao-seed-2-0-lite"
set /p ARK_MODEL=  模型名称 (回车默认 doubao-seed-2-0-lite): 
if not defined ARK_MODEL set "ARK_MODEL=doubao-seed-2-0-lite"
echo   模型名称: %ARK_MODEL%
echo.

set "HOST=0.0.0.0"
set /p HOST=  服务监听地址 (回车默认 0.0.0.0, 本机使用可选 127.0.0.1): 
if not defined HOST set "HOST=0.0.0.0"

set "PORT=8501"
set /p PORT=  服务端口 (回车默认 8501): 
if not defined PORT set "PORT=8501"
echo   服务地址: http://localhost:%PORT%
echo.

rem ---- 写入 .env (重定向在前, 避免值以数字结尾时被解析为句柄) ----
> "%ENV_FILE%" echo # 智鉴黄精 AI 品质检测系统配置
>> "%ENV_FILE%" echo # 本文件包含敏感信息, 请勿提交到 Git 或分享给他人
>> "%ENV_FILE%" echo ARK_API_KEY=%ARK_API_KEY%
>> "%ENV_FILE%" echo ARK_BASE_URL=%ARK_BASE_URL%
>> "%ENV_FILE%" echo ARK_MODEL=%ARK_MODEL%
>> "%ENV_FILE%" echo APP_MODE=%APP_MODE%
>> "%ENV_FILE%" echo HOST=%HOST%
>> "%ENV_FILE%" echo PORT=%PORT%
echo   [OK] 配置已写入 .env
echo.

:done
echo %G%==============================================%N%
echo %G%   安装完成!%N%
echo %G%==============================================%N%
echo.
echo   启动应用:   双击运行 scripts\run.bat
echo   环境检查:   双击运行 scripts\check.bat
echo   启动后访问: http://localhost:%PORT%
echo.
echo %Y%   提醒: .env 中包含 API Key, 请注意保密。%N%
echo.
pause
exit /b 0

:py_too_old
echo %R%  [错误] 检测到 Python %PYVER%, 本项目需要 Python 3.8 或更高版本。%N%
goto :fail

:fail
echo.
echo %R%安装未完成, 请根据上方提示处理后重新运行本脚本。%N%
echo.
pause
exit /b 1
