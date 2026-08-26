@echo off
chcp 65001 >nul
REM ============================================================
REM  打包图形化面板 gui.py 为独立 exe（无控制台黑窗）
REM  入口: gui.py  依赖: mouse_to_key.py (后端) + mappings.json (配置)
REM  需先安装: pip install pynput pyinstaller
REM  生成的 exe 在 dist\ 目录，需与 mappings.json 放同一目录运行
REM ============================================================

where pyinstaller >nul 2>nul
if errorlevel 1 (
    echo [提示] 未检测到 PyInstaller，正在安装...
    pip install pynput pystray Pillow pyinstaller
)

echo [图标] 生成 icon.ico ...
python make_icon.py
if not exist icon.ico (
    echo [错误] icon.ico 生成失败，请检查 Pillow 是否安装
    pause
    exit /b 1
)

echo [打包中] 请稍候...
set PYTHONDONTWRITEBYTECODE=1
python -m PyInstaller --noconfirm --onefile --windowed --name mouse_to_key ^
    --icon=icon.ico ^
    --add-data "icon.ico;." ^
    --hidden-import=pynput.mouse._win32 ^
    --hidden-import=pynput.keyboard._win32 ^
    --hidden-import=pynput._util.xorg ^
    --hidden-import=pystray._win32 ^
    --exclude-module=numpy ^
    --exclude-module=scipy ^
    --collect-submodules pynput ^
    --collect-submodules pystray ^
    gui.py

echo.
echo [完成] exe 已生成在: dist\mouse_to_key.exe
echo [提示] 请把 dist\mouse_to_key.exe 复制到 mappings.json 同一目录运行
echo        双击 exe 即弹出图形化控制面板
echo.
pause
