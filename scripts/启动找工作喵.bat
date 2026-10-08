@echo off
rem ============================================================
rem  JobHunterCat launcher
rem  IMPORTANT: keep this file PURE ASCII, and do NOT add chcp.
rem  cmd.exe + chcp 65001 + non-ASCII content is unreliable: it
rem  eats bytes at line starts, so rem/echo prefixes get lost and
rem  the whole script derails (2026-10-08: launcher stopped working).
rem ============================================================
setlocal
set "ROOT=%~dp0"
set "APPDIR=%ROOT:~0,-1%"
set "EXE=%ROOT%node_modules\electron\dist\electron.exe"

rem This launcher ships in two places (desktop\ = the real app,
rem scripts\ = a copy). Resolve relative to where THIS file is;
rem if that has no node_modules, fall back to ..\desktop.
if exist "%EXE%" goto :launch
set "ROOT=%~dp0..\desktop\"
set "APPDIR=%ROOT:~0,-1%"
set "EXE=%ROOT%node_modules\electron\dist\electron.exe"
if exist "%EXE%" goto :launch

echo [ERROR] Electron not found. Looked in:
echo   %~dp0node_modules\electron\dist\electron.exe
echo   %~dp0..\desktop\node_modules\electron\dist\electron.exe
echo Run "npm install" inside the desktop folder, or re-extract the package.
pause
exit /b 1

:launch
rem Only set MIAO_PYTHON when a portable interpreter ships with the package.
rem Otherwise the main process auto-detects (MIAO_PYTHON > bundled > .venv >
rem PATH > common install dirs, and it verifies tkinter is importable).
if exist "%ROOT%python\python.exe" set "MIAO_PYTHON=%ROOT%python\python.exe"

rem Electron must not inherit an external NODE_OPTIONS (a shim would make
rem the main process fail on require('electron')).
set "NODE_OPTIONS="
set "ELECTRON_RUN_AS_NODE="

echo ==========================================
echo   JobHunterCat launcher 2026-10-08-ascii
echo   pet window: bottom-right ^| chat: top-left ^| right-click = menu
echo ==========================================

rem Best effort: do not rely on cd succeeding (see header note).
cd /d "%ROOT%" 2>nul

"%EXE%" "%APPDIR%"
pause
