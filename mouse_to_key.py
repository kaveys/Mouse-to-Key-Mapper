# -*- coding: utf-8 -*-
"""
鼠标按键 -> 键盘快捷键 映射程序

功能：
  - 通过 mappings.json 配置任意鼠标按键到键盘快捷键的映射
  - 支持组合键（如 alt+f、ctrl+shift+s、win+e）
  - 可用 PyInstaller 打包为独立 exe

依赖：pip install pynput
打包：见 build.bat
"""

import json
import os
import sys
import threading
from pynput import mouse, keyboard
from pynput.keyboard import Key, Controller, KeyCode


# 特殊键名 -> pynput Key 对象
SPECIAL_KEYS = {
    'alt': Key.alt_l,
    'alt_l': Key.alt_l,
    'alt_r': Key.alt_r,
    'altgr': Key.alt_r,
    'ctrl': Key.ctrl_l,
    'control': Key.ctrl_l,
    'ctrl_l': Key.ctrl_l,
    'ctrl_r': Key.ctrl_r,
    'shift': Key.shift_l,
    'shift_l': Key.shift_l,
    'shift_r': Key.shift_r,
    'win': Key.cmd_l,
    'cmd': Key.cmd_l,
    'meta': Key.cmd_l,
    'super': Key.cmd_l,
    'tab': Key.tab,
    'enter': Key.enter,
    'return': Key.enter,
    'esc': Key.esc,
    'escape': Key.esc,
    'space': Key.space,
    'backspace': Key.backspace,
    'delete': Key.delete,
    'del': Key.delete,
    'insert': Key.insert,
    'home': Key.home,
    'end': Key.end,
    'pageup': Key.page_up,
    'page_up': Key.page_up,
    'pgup': Key.page_up,
    'pagedown': Key.page_down,
    'page_down': Key.page_down,
    'pgdn': Key.page_down,
    'up': Key.up,
    'down': Key.down,
    'left': Key.left,
    'right': Key.right,
    'capslock': Key.caps_lock,
    'scrolllock': Key.scroll_lock,
    'printscreen': Key.print_screen,
    'pause': Key.pause,
}

# 功能键 F1..F13
for _i in range(1, 14):
    SPECIAL_KEYS[f'f{_i}'] = getattr(Key, f'f{_i}')

# 鼠标按键名映射
MOUSE_BUTTON_NAMES = {
    mouse.Button.left: 'left',
    mouse.Button.right: 'right',
    mouse.Button.middle: 'middle',
    mouse.Button.x1: 'x1',   # 鼠标侧键4（后退）
    mouse.Button.x2: 'x2',   # 鼠标侧键5（前进）
}


def get_key_object(name):
    """把键名转成 pynput 的 Key/KeyCode 对象，找不到返回 None。"""
    if name is None:
        return None
    key = name.lower()
    if key in SPECIAL_KEYS:
        return SPECIAL_KEYS[key]
    if len(key) == 1:
        return KeyCode.from_char(key)
    return None


class MouseToKeyMapper:
    def __init__(self, config_path, state_callback=None):
        self.config_path = config_path
        self.keyboard = Controller()
        self.mappings = {}        # mouse_button_name -> action string
        self.mouse_listener = None
        self.lock = threading.Lock()
        self.state_callback = state_callback  # GUI 状态回调（保留接口）
        self.load_config()

    def load_config(self):
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
        except FileNotFoundError:
            print(f'[错误] 配置文件不存在: {self.config_path}')
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f'[错误] 配置文件 JSON 格式有误: {e}')
            sys.exit(1)

        new_map = {}
        for item in cfg.get('mappings', []):
            btn = str(item.get('mouse_button', '')).lower()
            action = str(item.get('action', '')).lower()
            desc = item.get('description', '')
            if btn and action:
                new_map[btn] = action
                print(f'  {btn:<6} -> {action:<14} {desc}')

        with self.lock:
            self.mappings = new_map
        print(f'[配置] 已加载 {len(new_map)} 条映射: {self.config_path}')

    def execute_action(self, action):
        """在后台线程中执行键盘快捷键。"""
        parts = [p.strip() for p in action.split('+') if p.strip()]
        if not parts:
            return
        mods = parts[:-1]
        main_key = parts[-1]

        mod_objs = [get_key_object(m) for m in mods]
        key_obj = get_key_object(main_key)
        if key_obj is None:
            print(f'[警告] 无法识别按键: {main_key}')
            return

        try:
            for m in mod_objs:
                if m is not None:
                    self.keyboard.press(m)
            self.keyboard.press(key_obj)
            self.keyboard.release(key_obj)
            for m in reversed(mod_objs):
                if m is not None:
                    self.keyboard.release(m)
        except Exception as e:
            print(f'[警告] 执行 {action} 时出错: {e}')

    def button_to_name(self, button):
        return MOUSE_BUTTON_NAMES.get(button)

    def on_click(self, x, y, button, pressed):
        if not pressed:
            return
        name = self.button_to_name(button)
        if name is None:
            return
        with self.lock:
            action = self.mappings.get(name)
        if action:
            # 放到后台线程执行，避免阻塞鼠标 hook
            threading.Thread(
                target=self.execute_action,
                args=(action,),
                daemon=True,
            ).start()

    def start_in_background(self):
        """非阻塞启动监听器（立即返回），供 GUI 调用。仅监听鼠标。"""
        self.mouse_listener = mouse.Listener(on_click=self.on_click)
        self.mouse_listener.start()
        print('======================================')
        print(' 鼠标键盘映射服务已启动 (后台模式)')
        print('======================================')

    def start(self):
        self.start_in_background()
        print('======================================')
        print(' 鼠标键盘映射程序已启动')
        print('======================================')
        try:
            while self.mouse_listener.is_alive():
                self.mouse_listener.join(timeout=0.5)
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        if self.mouse_listener:
            self.mouse_listener.stop()


def get_base_dir():
    """exe 模式下返回 exe 所在目录，否则返回脚本目录。"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def main():
    base_dir = get_base_dir()
    config_path = os.path.join(base_dir, 'mappings.json')
    mapper = MouseToKeyMapper(config_path)
    mapper.start()


if __name__ == '__main__':
    main()
