@echo off
chcp 65001 >nul
cd /d %~dp0
rem ===== 2026-09-17 修复 =====
rem 原实现写死 MIAO_PYTHON=C:\Users\<用户名>\...\Doubao\sandbox_runtime\...\python.exe，
rem 换一台机器该路径不存在，主进程 spawn 直接失败，猫在但不会说话。
rem 现在：只有「随包自带了便携解释器」时才设 MIAO_PYTHON，其余情况交给主进程自动探测
rem       （探测顺序：MIAO_PYTHON > 随包 > .venv > PATH > 常见安装位置，且会校验 tkinter 可用）。
if exist "%~dp0python\python.exe" set "MIAO_PYTHON=%~dp0python\python.exe"
rem Electron 不应继承外部 NODE_OPTIONS（会被注入 shim，导致主进程 require('electron') 失败）
set NODE_OPTIONS=
set ELECTRON_RUN_AS_NODE=
echo ==========================================
echo   找工作喵 · Electron 版启动中…
echo   猫窗在右下角，对话框左上，右键出菜单
echo ==========================================
node_modules\electron\dist\electron.exe .
pause
