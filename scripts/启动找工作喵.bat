@echo off
chcp 65001 >nul
rem ===== 统一入口（转发） =====
rem 真正的启动逻辑在 desktop\ 下（Electron 的 node_modules 装在 desktop\ 里）。
rem 本文件只做转发，避免「scripts\node_modules 不存在导致启动失败」的旧坑。
rem 目录结构若被改过，请以 desktop\启动找工作喵.bat 为唯一准。
if exist "%~dp0desktop\启动找工作喵.bat" (
    call "%~dp0desktop\启动找工作喵.bat"
) else (
    echo 未找到 desktop\启动找工作喵.bat，请确认仓库目录完整。
    pause
)
