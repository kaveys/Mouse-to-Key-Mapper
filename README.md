# 鼠标按键映射键盘 (Mouse to Key Mapper)

一个 Windows 桌面小工具：把鼠标按键（侧键、中键等）映射为任意键盘快捷键，支持图形化面板配置与托盘后台运行。

## 功能

- **鼠标 → 键盘映射**：点击鼠标按键时自动触发配置的键盘快捷键
- **图形化配置面板**：可视化增删改映射，无需手动编辑 JSON
- **一键捕获**：点「捕获」按钮后按一下鼠标/按键，自动填入
- **热重载**：保存配置后自动生效，无需重启服务
- **系统托盘**：可最小化到托盘后台运行，双击托盘图标恢复窗口
- **高 DPI 支持**：自动检测系统缩放，文字与图标原生像素渲染不发糊
- **零全局快捷键**：程序本身不占用任何全局键盘快捷键

## 支持的鼠标按键

| 配置名 | 实际按键 |
|--------|----------|
| `left` | 左键 |
| `right` | 右键 |
| `middle` | 中键 / 滚轮键 |
| `x1` | 侧键 4（后退） |
| `x2` | 侧键 5（前进） |

## 支持的快捷键写法

用 `+` 连接，修饰键在前、主键在最后：

```
alt+f              单主键
ctrl+shift+s       双修饰键
win+e              Windows 键组合
f5                 功能键
ctrl+alt+delete    三键组合
```

修饰键支持：`alt`、`ctrl`、`shift`、`win`（或 `cmd`/`super`）
功能键支持：`f1` ~ `f13`
特殊键支持：`tab`、`enter`、`esc`、`space`、`backspace`、`delete`、`home`、`end`、`pageup`、`pagedown`、`up`、`down`、`left`、`right`、`printscreen` 等

## 快速开始

### 方式一：直接运行 Python

```bash
# 安装依赖
pip install pynput pystray Pillow

# 启动图形化面板
python gui.py
```

### 方式二：运行打包好的 exe

双击 `dist\mouse_to_key.exe` 即可，无需安装 Python 环境。

> **注意**：exe 需与 `mappings.json` 放在同一目录运行。

### 方式三：仅运行后端（无界面）

```bash
python mouse_to_key.py
```

适合用 `AutoHotkey` 等工具配合，或在命令行下使用。

## 使用步骤

1. 启动程序，弹出图形化控制面板
2. 点击「启动服务」——程序开始监听鼠标
3. 在右栏「添加 / 编辑映射」区域：
   - 选择或捕获鼠标按键
   - 输入或捕获快捷键
   - 填写说明（可选）
   - 点击「添加映射」
4. 保存后自动生效，按鼠标按键即触发对应快捷键
5. 关闭窗口时可选择「最小化到托盘」后台运行

## 配置文件 `mappings.json`

程序通过 `mappings.json` 管理所有映射。GUI 会自动读写，也可手动编辑：

```json
{
  "mappings": [
    {
      "mouse_button": "x2",
      "action": "alt+f",
      "description": "侧键5 -> Alt+F"
    },
    {
      "mouse_button": "x1",
      "action": "ctrl+w",
      "description": "侧键4 -> Ctrl+W"
    }
  ]
}
```

字段说明：

| 字段 | 类型 | 说明 |
|------|------|------|
| `mouse_button` | string | 鼠标按键名（见上方对照表） |
| `action` | string | 键盘快捷键（`+` 连接，修饰键在前） |
| `description` | string | 可选，描述信息 |

## 项目结构

```
123/
├── gui.py              # 图形化控制面板（入口）
├── mouse_to_key.py     # 后端映射引擎（鼠标监听 + 键盘触发）
├── mappings.json       # 映射配置文件
├── make_icon.py        # 图标生成脚本
├── icon.ico            # 应用图标（exe / 窗口 / 托盘共用）
├── build.bat           # 一键打包脚本
└── dist/
    └── mouse_to_key.exe  # 打包产物
```

## 从源码打包 exe

```bash
# 方式一：一键打包
build.bat

# 方式二：手动
pip install pynput pystray Pillow pyinstaller
python make_icon.py
python -m PyInstaller --noconfirm --onefile --windowed ^
    --icon=icon.ico --add-data "icon.ico;." ^
    --hidden-import=pynput.mouse._win32 ^
    --hidden-import=pynput.keyboard._win32 ^
    --hidden-import=pystray._win32 ^
    --collect-submodules pynput ^
    --collect-submodules pystray ^
    gui.py
```

打包产物在 `dist\mouse_to_key.exe`，需与 `mappings.json` 放同一目录运行。

## 依赖

- [pynput](https://github.com/moses-palmer/pynput) — 鼠标监听与键盘模拟
- [pystray](https://github.com/jronallo/pystray) — 系统托盘
- [Pillow](https://github.com/python-pillow/Pillow) — 图标生成
- tkinter — GUI（Python 标准库）
- [PyInstaller](https://pyinstaller.org/) — 打包为 exe

## 常见问题

**Q: 侧键在浏览器里仍会触发前进/后退？**

A: 是的。pynput 的鼠标监听是"观察"而非"拦截"，所以原始事件仍会传递。若想去掉浏览器原生行为，可在浏览器设置中禁用侧键导航，或改用 `intercept` 模式（需以管理员权限运行）。

**Q: 打包后 exe 很大？**

A: 约 16 MB。可通过 `--exclude-module` 进一步排除不需要的模块。

**Q: 支持多显示器 / 高 DPI？**

A: 支持。程序自动调用 Windows `SetProcessDpiAwareness`，文字按原生像素渲染。

**Q: 能否开机自启？**

A: 可以。把 exe 的快捷方式放到 `shell:startup` 目录即可。

## 许可证

本项目仅供个人学习与使用。
