# -*- coding: utf-8 -*-
"""
鼠标按键映射键盘 - 图形化控制面板

功能：
  - 启动 / 停止映射服务
  - 可视化查看、添加、编辑、删除映射
  - 一键「捕获鼠标按键」自动填入按键名
  - 一键「捕获」按下组合键自动填入（如 Alt+F -> alt+f）
  - 修改后自动写入 mappings.json 并热重载运行中的服务
  - 关闭窗口时询问「最小化到托盘」或「彻底关闭」
  - 系统托盘图标：双击/菜单恢复窗口，菜单彻底退出

依赖：pip install pynput pystray Pillow
打包：python build.bat（生成无控制台 exe）
"""

import json
import os
import sys
import ctypes
import threading
import tkinter as tk
from tkinter import ttk, messagebox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mouse_to_key import (
    MouseToKeyMapper,
    MOUSE_BUTTON_NAMES,
    get_base_dir,
)
from pynput import mouse as pynput_mouse
from pynput import keyboard as pynput_keyboard
from pynput.keyboard import Key, KeyCode
from pystray import Icon as TrayIcon, Menu as TrayMenu, MenuItem as TrayMenuItem
from PIL import Image, ImageDraw, ImageFont


# 鼠标按键显示名 <-> 内部名
BUTTON_DISPLAY = {
    'left':   '左键 (按钮1)',
    'right':  '右键 (按钮2)',
    'middle': '中键/滚轮 (按钮3)',
    'x1':     '侧键4 - 后退',
    'x2':     '侧键5 - 前进',
}
DISPLAY_TO_KEY = {v: k for k, v in BUTTON_DISPLAY.items()}
KEY_TO_DISPLAY = {k: v for k, v in BUTTON_DISPLAY.items()}

# pynput Key 对象 -> 规范化名称（用于快捷键捕获）
KEY_NAME_MAP = {
    Key.alt_l: 'alt', Key.alt_r: 'alt',
    Key.ctrl_l: 'ctrl', Key.ctrl_r: 'ctrl',
    Key.shift_l: 'shift', Key.shift_r: 'shift',
    Key.cmd_l: 'win', Key.cmd_r: 'win',
    Key.tab: 'tab',
    Key.enter: 'enter',
    Key.esc: 'esc',
    Key.space: 'space',
    Key.backspace: 'backspace',
    Key.delete: 'delete',
    Key.insert: 'insert',
    Key.home: 'home',
    Key.end: 'end',
    Key.page_up: 'pageup',
    Key.page_down: 'pagedown',
    Key.up: 'up', Key.down: 'down', Key.left: 'left', Key.right: 'right',
    Key.caps_lock: 'capslock',
    Key.scroll_lock: 'scrolllock',
    Key.print_screen: 'printscreen',
    Key.pause: 'pause',
    Key.f1: 'f1', Key.f2: 'f2', Key.f3: 'f3', Key.f4: 'f4',
    Key.f5: 'f5', Key.f6: 'f6', Key.f7: 'f7', Key.f8: 'f8',
    Key.f9: 'f9', Key.f10: 'f10', Key.f11: 'f11', Key.f12: 'f12', Key.f13: 'f13',
}
MODIFIER_NAMES = {'alt', 'ctrl', 'shift', 'win'}

# ================= 配色（与 icon.ico 蓝色一致）=================
BG = '#F4F5F7'         # 应用底色
PANEL = '#FFFFFF'      # 白色面板
TEXT = '#1A1A1F'       # 主文本
DIM = '#6B7280'        # 次要文本
ACCENT = '#2878C8'     # 强调蓝（主操作）
ACCENT_HOVER = '#1F66B0'
SUCCESS = '#16A34A'    # 运行中
DANGER = '#DC2626'     # 停止 / 关闭
BORDER = '#E4E4E7'     # 分隔 / 描边
ROW_ALT = '#F8FAFC'    # 表格隔行底色
HEADER_BG = '#F1F3F5'  # 表头底色


class MapperApp:
    def __init__(self, root, scale=1.0):
        self.root = root
        self._scale = float(scale) or 1.0
        self.root.title('鼠标按键映射键盘 - 控制面板')
        # 高 DPI：按缩放系数放大窗口尺寸，使文字以原生像素清晰渲染且整体不显小
        try:
            self.root.tk.call('tk', 'scaling', self._scale * 96.0 / 72.0)
        except Exception:
            pass
        sc = self._scale
        self.root.geometry(f'{int(round(980 * sc))}x{int(round(500 * sc))}')
        self.root.minsize(int(round(840 * sc)), int(round(460 * sc)))

        self.config_path = os.path.join(get_base_dir(), 'mappings.json')
        self.mapper = None
        self.capture_listener = None       # 鼠标按键捕获监听器
        self.action_capture_listener = None  # 快捷键捕获监听器
        self.held_mods = []                # 捕获时记录已按下的修饰键（有序）
        self.tray_icon = None              # 系统托盘图标
        self.quitting = False              # 是否正在彻底退出（区分托盘恢复与真退出）
        self.editing_index = None   # None=新增, int=编辑

        self._build_ui()
        self._set_window_icon()
        self.refresh_table()
        self._update_service_status()
        # 关闭窗口时清理
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)

    # ================= UI 构建 =================
    def _setup_style(self):
        """统一 ttk 主题：克制配色 + 单一强调蓝 + 分级按钮。"""
        s = ttk.Style(self.root)
        try:
            s.theme_use('clam')
        except Exception:
            pass
        self.root.configure(background=BG)
        # 关闭点击焦点时的黑色高亮框（修复“点击后四周黑条纹”）
        self.root.option_add('*highlightThickness', 0)

        # 全局默认 / 容器
        s.configure('.', background=BG, foreground=TEXT,
                    font=('Segoe UI', 10), borderwidth=0)
        s.configure('TFrame', background=BG)
        s.configure('Panel.TFrame', background=PANEL)

        # 文本标签
        s.configure('TLabel', background=BG, foreground=TEXT, font=('Segoe UI', 10))
        s.configure('Dim.TLabel', background=BG, foreground=DIM, font=('Segoe UI', 9))
        s.configure('Panel.TLabel', background=PANEL, foreground=TEXT, font=('Segoe UI', 10))
        s.configure('PanelDim.TLabel', background=PANEL, foreground=DIM, font=('Segoe UI', 9))
        s.configure('Section.TLabel', background=BG, foreground=TEXT, font=('Segoe UI', 10, 'bold'))
        s.configure('AppTitle.TLabel', background=BG, foreground=TEXT, font=('Segoe UI', 14, 'bold'))
        s.configure('Status.TLabel', background=BG, foreground=TEXT, font=('Segoe UI', 11, 'bold'))

        # 按钮：三级（主操作蓝 / 危险红描边 / 中性白描边）
        s.configure('TButton', font=('Segoe UI', 10), padding=(14, 7),
                    background=PANEL, foreground=TEXT, borderwidth=1,
                    bordercolor=BORDER, relief='flat', focusthickness=0,
                    highlightthickness=0, highlightcolor=BG,
                    highlightbackground=BG)
        s.map('TButton',
              background=[('active', HEADER_BG), ('pressed', HEADER_BG),
                          ('disabled', BG)],
              bordercolor=[('focus', ACCENT), ('hover', DIM)],
              foreground=[('disabled', '#9CA3AF')])

        s.configure('Accent.TButton', font=('Segoe UI', 10, 'bold'),
                    padding=(16, 8), background=ACCENT, foreground='#FFFFFF',
                    borderwidth=0, relief='flat', focusthickness=0)
        s.map('Accent.TButton',
              background=[('active', ACCENT_HOVER), ('pressed', ACCENT_HOVER),
                          ('disabled', '#A8C4E0')],
              foreground=[('disabled', '#FFFFFF')])

        s.configure('Danger.TButton', font=('Segoe UI', 10), padding=(14, 7),
                    background=PANEL, foreground=DANGER, borderwidth=1,
                    bordercolor=DANGER, relief='flat', focusthickness=0)
        s.map('Danger.TButton',
              background=[('active', '#FEE2E2'), ('pressed', '#FEE2E2'),
                          ('disabled', BG)],
              bordercolor=[('focus', DANGER), ('disabled', BORDER)],
              foreground=[('disabled', '#FCA5A5')])

        s.configure('Ghost.TButton', font=('Segoe UI', 9), padding=(6, 4),
                    background=BG, foreground=DIM, borderwidth=0,
                    relief='flat', focusthickness=0)
        s.map('Ghost.TButton',
              background=[('active', HEADER_BG), ('pressed', HEADER_BG)],
              foreground=[('active', TEXT)])

        # 输入控件
        s.configure('TEntry', fieldbackground=PANEL, foreground=TEXT,
                    bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                    borderwidth=1, padding=6)
        s.map('TEntry',
              bordercolor=[('focus', ACCENT)],
              lightcolor=[('focus', ACCENT)], darkcolor=[('focus', ACCENT)])
        s.configure('TCombobox', fieldbackground=PANEL, foreground=TEXT,
                    background=PANEL, bordercolor=BORDER, lightcolor=BORDER,
                    darkcolor=BORDER, borderwidth=1, padding=6, arrowcolor=DIM)
        s.map('TCombobox',
              fieldbackground=[('readonly', PANEL)],
              bordercolor=[('focus', ACCENT)],
              lightcolor=[('focus', ACCENT)], darkcolor=[('focus', ACCENT)])

        # 滚动条
        s.configure('Vertical.TScrollbar', background=PANEL, troughcolor=PANEL,
                    bordercolor=PANEL, arrowcolor=DIM, gripcount=0, arrowsize=14)
        s.map('Vertical.TScrollbar', background=[('active', BORDER)])

        # 表格
        s.configure('Treeview', background=PANEL, foreground=TEXT,
                    fieldbackground=PANEL, borderwidth=0,
                    rowheight=int(round(30 * self._scale)),
                    font=('Segoe UI', 10))
        s.configure('Treeview.Heading', background=HEADER_BG, foreground=DIM,
                    font=('Segoe UI', 10, 'bold'), borderwidth=0,
                    relief='flat', padding=(10, 8))
        s.map('Treeview.Heading', background=[('active', BORDER)])
        s.map('Treeview',
              background=[('selected', ACCENT)],
              foreground=[('selected', '#FFFFFF')])

        # 分隔线
        s.configure('TSeparator', background=BORDER)

    def _build_ui(self):
        self._setup_style()
        wrap = ttk.Frame(self.root, style='TFrame')
        wrap.pack(fill='both', expand=True, padx=20, pady=18)

        # ---- 顶栏：品牌 + 状态（横跨全宽）----
        header = ttk.Frame(wrap, style='TFrame'); header.pack(fill='x')
        ttk.Label(header, text='鼠标按键映射键盘', style='AppTitle.TLabel').pack(side='left')
        status_box = ttk.Frame(header, style='TFrame'); status_box.pack(side='right')
        self.status_dot = ttk.Label(status_box, text='●', font=('Segoe UI', 13),
                                    foreground=DIM, background=BG)
        self.status_dot.pack(side='left', padx=(0, 6))
        self.status_var = tk.StringVar(value='未运行')
        self.status_label = ttk.Label(status_box, textvariable=self.status_var,
                                      style='Status.TLabel')
        self.status_label.pack(side='left')
        ttk.Separator(wrap).pack(fill='x', pady=(12, 14))

        # ---- 主体：左右两栏（grid 布局，左列拉伸，右列固定）----
        body = ttk.Frame(wrap, style='TFrame')
        body.pack(fill='both', expand=True)
        body.columnconfigure(0, weight=1)   # 左列占满剩余宽度
        body.columnconfigure(1, weight=0)   # 右列自然宽度
        body.rowconfigure(0, weight=1)

        # 右栏：选中行操作 + 添加 / 编辑表单（固定宽度，靠右）
        right = ttk.Frame(body, style='TFrame')
        right.grid(row=0, column=1, sticky='ns', padx=(20, 0))
        ttk.Label(right, text='选中行', style='Section.TLabel').pack(anchor='w')
        sel_btns = ttk.Frame(right, style='TFrame'); sel_btns.pack(fill='x', pady=(8, 8))
        ttk.Button(sel_btns, text='编辑选中', command=self.edit_selected).pack(side='left', padx=(0, 8))
        ttk.Button(sel_btns, text='删除选中', command=self.delete_selected).pack(side='left')
        ttk.Separator(right).pack(fill='x', pady=(0, 12))
        ttk.Label(right, text='添加 / 编辑映射', style='Section.TLabel').pack(anchor='w')

        f1 = ttk.Frame(right, style='TFrame'); f1.pack(fill='x', pady=(8, 8))
        ttk.Label(f1, text='鼠标按键', style='Dim.TLabel', width=9).pack(side='left')
        self.btn_var = tk.StringVar()
        self.btn_combo = ttk.Combobox(f1, textvariable=self.btn_var,
                                      values=list(BUTTON_DISPLAY.values()),
                                      state='readonly', width=16)
        self.btn_combo.pack(side='left', padx=(8, 6))
        self.capture_btn = ttk.Button(f1, text='捕获', command=self.start_capture)
        self.capture_btn.pack(side='left', padx=6)
        self.capture_hint = ttk.Label(f1, text='', style='Dim.TLabel')
        self.capture_hint.pack(side='left', padx=8)

        f2 = ttk.Frame(right, style='TFrame'); f2.pack(fill='x', pady=(0, 8))
        ttk.Label(f2, text='快捷键', style='Dim.TLabel', width=9).pack(side='left')
        self.action_var = tk.StringVar()
        self.action_entry = ttk.Entry(f2, textvariable=self.action_var, width=16)
        self.action_entry.pack(side='left', padx=(8, 6))
        self.action_capture_btn = ttk.Button(f2, text='捕获',
                                             command=self.toggle_action_capture)
        self.action_capture_btn.pack(side='left', padx=6)
        self.action_hint = ttk.Label(right, text='如 alt+f / ctrl+shift+s / f5',
                                    style='Dim.TLabel')
        self.action_hint.pack(anchor='w', pady=(2, 0))

        f3 = ttk.Frame(right, style='TFrame'); f3.pack(fill='x', pady=(0, 8))
        ttk.Label(f3, text='说明', style='Dim.TLabel', width=9).pack(side='left')
        self.desc_var = tk.StringVar()
        ttk.Entry(f3, textvariable=self.desc_var, width=24).pack(side='left', padx=(8, 6))

        f4 = ttk.Frame(right, style='TFrame'); f4.pack(fill='x', pady=(6, 8))
        self.save_btn = ttk.Button(f4, text='添加映射', style='Accent.TButton',
                                   command=self.save_mapping)
        self.save_btn.pack(side='left')
        ttk.Button(f4, text='清空表单', command=self.clear_form).pack(side='left', padx=8)
        self.form_hint = ttk.Label(right, text='', style='Dim.TLabel')
        self.form_hint.pack(anchor='w', pady=(2, 0))

        # 左栏：服务 + 映射列表（占满剩余宽度）
        left = ttk.Frame(body, style='TFrame')
        left.grid(row=0, column=0, sticky='nsew')

        # 服务（标题与按钮同行）
        svc = ttk.Frame(left, style='TFrame'); svc.pack(fill='x')
        ttk.Label(svc, text='服务', style='Section.TLabel').pack(side='left')
        svc_btns = ttk.Frame(svc, style='TFrame'); svc_btns.pack(side='right')
        self.start_btn = ttk.Button(svc_btns, text='启动服务', style='Accent.TButton',
                                    command=self.start_service)
        self.start_btn.pack(side='left')
        self.stop_btn = ttk.Button(svc_btns, text='停止服务', style='Danger.TButton',
                                   command=self.stop_service, state='disabled')
        self.stop_btn.pack(side='left', padx=8)
        self.reload_btn = ttk.Button(svc_btns, text='热重载',
                                     command=self.reload_config, state='disabled')
        self.reload_btn.pack(side='left')
        ttk.Separator(left).pack(fill='x', pady=(10, 10))

        # 映射列表
        list_head = ttk.Frame(left, style='TFrame'); list_head.pack(fill='x')
        ttk.Label(list_head, text='当前映射', style='Section.TLabel').pack(side='left')
        ttk.Button(list_head, text='刷新', style='Ghost.TButton',
                   command=self.refresh_table).pack(side='right')

        panel = ttk.Frame(left, style='Panel.TFrame')
        panel.pack(fill='both', expand=True, pady=(8, 0))
        cols = ('btn', 'action', 'desc')
        self.tree = ttk.Treeview(panel, columns=cols, show='headings', height=8)
        self.tree.heading('btn', text='鼠标按键')
        self.tree.heading('action', text='快捷键')
        self.tree.heading('desc', text='说明')
        self.tree.column('btn', width=140, anchor='w', stretch=False)
        self.tree.column('action', width=140, anchor='w', stretch=False)
        self.tree.column('desc', width=200, anchor='w', stretch=True)
        self.tree.tag_configure('odd', background=PANEL)
        self.tree.tag_configure('even', background=ROW_ALT)
        self.tree.pack(side='left', fill='both', expand=True, padx=1, pady=1)
        sb = ttk.Scrollbar(panel, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y', padx=(0, 1), pady=1)

        # 页脚（横跨全宽）
        ttk.Separator(wrap).pack(fill='x', pady=14)
        ttk.Label(wrap, text='保存映射即自动应用  ·  关闭窗口可最小化到托盘',
                  style='Dim.TLabel').pack(anchor='w')

    # ================= 配置读写 =================
    def _read_config(self):
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _write_config(self, cfg):
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)

    def refresh_table(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        try:
            cfg = self._read_config()
        except Exception as e:
            messagebox.showerror('错误', f'读取配置失败:\n{e}')
            return
        for i, m in enumerate(cfg.get('mappings', [])):
            btn = str(m.get('mouse_button', '')).lower()
            disp = KEY_TO_DISPLAY.get(btn, btn)
            self.tree.insert('', 'end',
                             values=(disp, m.get('action', ''), m.get('description', '')),
                             tags=('even' if i % 2 == 0 else 'odd',))

    # ================= 服务控制 =================
    def start_service(self):
        if self.mapper is not None:
            return
        try:
            self.mapper = MouseToKeyMapper(self.config_path,
                                           state_callback=self._on_mapper_state)
            self.mapper.start_in_background()
        except Exception as e:
            messagebox.showerror('启动失败', str(e))
            self.mapper = None
            return
        self._update_service_status()

    def stop_service(self):
        if self.mapper:
            self.mapper.stop()
            self.mapper = None
        self._update_service_status()

    def reload_config(self):
        if self.mapper:
            self.mapper.load_config()
            self.refresh_table()

    def _on_mapper_state(self, state):
        """被 mapper 的工作线程调用，需切回主线程更新 UI。"""
        self.root.after(0, lambda: self._handle_mapper_state(state))

    def _handle_mapper_state(self, state):
        if state == 'reloaded':
            self.refresh_table()
            self.form_hint.config(text='配置已热重载', foreground=SUCCESS)
        elif state == 'quit':
            self.mapper = None
            self._update_service_status()

    def _update_service_status(self):
        if self.mapper is not None:
            self.status_var.set('运行中')
            self.status_dot.config(foreground=SUCCESS)
            self.status_label.config(foreground=SUCCESS)
            self.start_btn.config(state='disabled')
            self.stop_btn.config(state='normal')
            self.reload_btn.config(state='normal')
        else:
            self.status_var.set('未运行')
            self.status_dot.config(foreground=DIM)
            self.status_label.config(foreground=DIM)
            self.start_btn.config(state='normal')
            self.stop_btn.config(state='disabled')
            self.reload_btn.config(state='disabled')

    # ================= 添加 / 编辑 / 删除 =================
    def edit_selected(self):
        sel = self.tree.selection()
        if not sel:
            self.form_hint.config(text='请先选中一行', foreground=DANGER)
            return
        idx = self.tree.index(sel[0])
        cfg = self._read_config()
        mappings = cfg.get('mappings', [])
        if idx >= len(mappings):
            return
        m = mappings[idx]
        self.editing_index = idx
        btn = str(m.get('mouse_button', '')).lower()
        self.btn_var.set(KEY_TO_DISPLAY.get(btn, btn))
        self.action_var.set(m.get('action', ''))
        self.desc_var.set(m.get('description', ''))
        self.save_btn.config(text='保存修改')
        self.form_hint.config(text=f'正在编辑第 {idx + 1} 条', foreground=DIM)

    def delete_selected(self):
        sel = self.tree.selection()
        if not sel:
            self.form_hint.config(text='请先选中一行', foreground=DANGER)
            return
        idx = self.tree.index(sel[0])
        cfg = self._read_config()
        mappings = cfg.get('mappings', [])
        if idx < len(mappings):
            del mappings[idx]
            cfg['mappings'] = mappings
            self._write_config(cfg)
            if self.mapper:
                self.mapper.load_config()
            self.refresh_table()
            self.clear_form()
            self.form_hint.config(text='已删除', foreground=SUCCESS)

    def save_mapping(self):
        disp = self.btn_var.get().strip()
        action = self.action_var.get().strip().lower()
        desc = self.desc_var.get().strip()
        if not disp or not action:
            self.form_hint.config(text='请选择鼠标按键并填写快捷键', foreground=DANGER)
            return
        btn = DISPLAY_TO_KEY.get(disp, disp.lower())
        cfg = self._read_config()
        mappings = cfg.get('mappings', [])
        entry = {'mouse_button': btn, 'action': action, 'description': desc}
        if self.editing_index is not None and self.editing_index < len(mappings):
            mappings[self.editing_index] = entry
        else:
            mappings.append(entry)
        cfg['mappings'] = mappings
        try:
            self._write_config(cfg)
        except Exception as e:
            messagebox.showerror('保存失败', str(e))
            return
        if self.mapper:
            self.mapper.load_config()
        self.refresh_table()
        self.clear_form()
        self.form_hint.config(text='已保存并应用', foreground=SUCCESS)

    def clear_form(self):
        self.btn_var.set('')
        self.action_var.set('')
        self.desc_var.set('')
        self.editing_index = None
        self.save_btn.config(text='添加映射')
        self.capture_hint.config(text='', foreground=DIM)
        self.action_capture_btn.config(text='捕获', state='normal')
        self.action_hint.config(text='如 alt+f / ctrl+shift+s / f5', foreground=DIM)

    # ================= 鼠标按键捕获 =================
    def start_capture(self):
        if self.capture_listener is not None:
            return
        self.capture_hint.config(text='请按下任意鼠标按键…', foreground=DANGER)
        self.capture_btn.config(state='disabled')
        self.capture_listener = pynput_mouse.Listener(on_click=self._on_capture_click)
        self.capture_listener.start()

    def _on_capture_click(self, x, y, button, pressed):
        # 在监听线程中调用，只处理按下事件
        if not pressed:
            return
        name = None
        for b, n in MOUSE_BUTTON_NAMES.items():
            if b == button:
                name = n
                break
        if name and self.capture_listener:
            self.capture_listener.stop()
            self.capture_listener = None
            self.root.after(0, lambda: self._set_captured(name))

    def _set_captured(self, name):
        self.btn_var.set(KEY_TO_DISPLAY.get(name, name))
        self.capture_hint.config(text=f'已捕获: {name}', foreground=SUCCESS)
        self.capture_btn.config(state='normal')

    # ================= 快捷键捕获 =================
    def toggle_action_capture(self):
        """按钮可切换：未捕获时开始捕获，捕获中点击则取消。"""
        if self.action_capture_listener is not None:
            self._stop_action_capture()
            self.action_hint.config(text='已取消捕获', foreground=DIM)
            return
        self.start_action_capture()

    def start_action_capture(self):
        self.held_mods = []
        self.action_hint.config(text='请按下快捷键组合（如 Alt+F），Esc 取消…',
                                 foreground=DANGER)
        self.action_capture_btn.config(text='取消捕获')
        self.action_capture_listener = pynput_keyboard.Listener(
            on_press=self._on_action_key_press,
            on_release=self._on_action_key_release,
        )
        self.action_capture_listener.start()

    def _stop_action_capture(self):
        listener = self.action_capture_listener
        self.action_capture_listener = None
        self.held_mods = []
        if listener:
            listener.stop()
        self.action_capture_btn.config(text='捕获')

    def _key_to_name(self, key):
        """把 pynput 按键对象转换为规范化的名称字符串。"""
        if key in KEY_NAME_MAP:
            return KEY_NAME_MAP[key]
        if isinstance(key, KeyCode):
            if key.char:
                return key.char.lower()
            # 修饰键按住时某些字符键 char 为 None，用 vk 兜底映射数字/符号
            if key.vk is not None:
                try:
                    return chr(key.vk).lower()
                except (ValueError, OverflowError):
                    return None
        return None

    def _on_action_key_press(self, key):
        # 在监听线程中调用
        name = self._key_to_name(key)
        if name is None:
            return
        # Esc 取消捕获
        if name == 'esc' and not self.held_mods:
            listener = self.action_capture_listener
            self.action_capture_listener = None
            self.held_mods = []
            if listener:
                listener.stop()
            self.root.after(0, lambda: self._cancel_action_capture())
            return
        # 修饰键：记下（保持顺序，去重）
        if name in MODIFIER_NAMES:
            if name not in self.held_mods:
                self.held_mods.append(name)
            return
        # 主键：组合完成
        combo_parts = list(self.held_mods) + [name]
        combo = '+'.join(combo_parts)
        listener = self.action_capture_listener
        self.action_capture_listener = None
        self.held_mods = []
        if listener:
            listener.stop()
        self.root.after(0, lambda: self._set_action_captured(combo))

    def _on_action_key_release(self, key):
        name = self._key_to_name(key)
        if name in MODIFIER_NAMES and name in self.held_mods:
            self.held_mods.remove(name)

    def _set_action_captured(self, combo):
        self.action_var.set(combo)
        self.action_hint.config(text=f'已捕获: {combo}', foreground=SUCCESS)
        self.action_capture_btn.config(text='捕获')

    def _cancel_action_capture(self):
        self.action_capture_btn.config(text='捕获')
        self.action_hint.config(text='已取消捕获', foreground=DIM)

    # ================= 关闭询问 / 系统托盘 =================
    def _on_close(self):
        """窗口关闭按钮：询问 最小化到托盘 / 彻底关闭 / 取消。"""
        choice = self._ask_close_action()
        if choice == 'tray':
            self._minimize_to_tray()
        elif choice == 'close':
            self._fully_quit()
        # else None -> 取消，什么都不做

    def _ask_close_action(self):
        """弹出询问窗。返回 'tray' / 'close' / None。"""
        dialog = tk.Toplevel(self.root)
        dialog.title('关闭程序')
        dialog.configure(background=BG)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)

        result = {'value': None}

        def choose(val):
            result['value'] = val
            dialog.destroy()

        box = ttk.Frame(dialog, style='TFrame')
        box.pack(fill='both', expand=True, padx=26, pady=24)
        ttk.Label(box, text='您要如何关闭程序？', style='AppTitle.TLabel').pack(anchor='w')
        ttk.Label(box, text='最小化到托盘将保持程序与服务后台运行。',
                  style='Dim.TLabel').pack(anchor='w', pady=(6, 20))

        bf = ttk.Frame(box, style='TFrame'); bf.pack(fill='x')
        ttk.Button(bf, text='最小化到托盘', style='Accent.TButton',
                   command=lambda: choose('tray')).pack(side='left')
        ttk.Button(bf, text='彻底关闭', style='Danger.TButton',
                   command=lambda: choose('close')).pack(side='left', padx=10)
        ttk.Button(bf, text='取消', command=dialog.destroy).pack(side='left')

        # 自适应大小并居中于主窗口
        dialog.update_idletasks()
        w = max(dialog.winfo_reqwidth(), 380)
        h = max(dialog.winfo_reqheight(), 170)
        self.root.update_idletasks()
        rx = self.root.winfo_x(); ry = self.root.winfo_y()
        rw = self.root.winfo_width(); rh = self.root.winfo_height()
        dialog.geometry(f'{w}x{h}+{rx + (rw - w) // 2}+{ry + (rh - h) // 2}')

        dialog.protocol('WM_DELETE_WINDOW', dialog.destroy)
        self.root.wait_window(dialog)
        return result['value']

    def _minimize_to_tray(self):
        """隐藏窗口并显示托盘图标，程序继续运行。"""
        self.root.withdraw()
        if self.tray_icon is None:
            self._create_tray_icon()

    def _icon_path(self):
        """icon.ico 路径：打包后从 _MEIPASS 取，源码运行从项目目录取。"""
        base = getattr(sys, '_MEIPASS', None) or os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base, 'icon.ico')

    def _set_window_icon(self):
        """设置窗口标题栏/任务栏图标，与 exe 文件图标一致。"""
        try:
            self.root.iconbitmap(self._icon_path())
        except Exception:
            pass  # 找不到 icon.ico 时用默认图标

    def _load_icon_image(self):
        """加载 icon.ico 为托盘用的 PIL Image；失败则现场绘制兜底。"""
        try:
            img = Image.open(self._icon_path())
            return img.convert('RGBA').resize((64, 64), Image.LANCZOS)
        except Exception:
            return self._make_tray_image()

    def _create_tray_icon(self):
        img = self._load_icon_image()
        menu = TrayMenu(
            TrayMenuItem('显示窗口', self._tray_show, default=True),
            TrayMenuItem('彻底退出', self._tray_quit),
        )
        self.tray_icon = TrayIcon('mouse_to_key', img, '鼠标按键映射键盘', menu)
        self.tray_icon.run_detached()

    def _make_tray_image(self):
        """兜底图标（icon.ico 缺失时用），与 make_icon.py 保持一致样式。"""
        img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        try:
            d.rounded_rectangle([3, 3, 61, 61], radius=14, fill=(40, 120, 200))
        except Exception:
            d.rectangle([3, 3, 61, 61], fill=(40, 120, 200))
        try:
            font = ImageFont.truetype('arial.ttf', 30)
        except Exception:
            font = ImageFont.load_default()
        text = 'MK'
        try:
            bbox = d.textbbox((0, 0), text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            d.text(((64 - tw) / 2, (64 - th) / 2 - bbox[1]), text, fill='white', font=font)
        except Exception:
            d.text((18, 16), text, fill='white', font=font)
        return img

    def _tray_show(self, icon=None, item=None):
        """托盘菜单：显示窗口（在托盘线程中触发，切回主线程）。"""
        self.root.after(0, self._show_window)

    def _tray_quit(self, icon=None, item=None):
        """托盘菜单：彻底退出。"""
        self.root.after(0, self._fully_quit)

    def _show_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _fully_quit(self):
        """彻底关闭：停止所有服务/监听/托盘，销毁窗口。"""
        if self.quitting:
            return
        self.quitting = True
        if self.mapper:
            self.mapper.stop()
            self.mapper = None
        if self.capture_listener:
            self.capture_listener.stop()
            self.capture_listener = None
        if self.action_capture_listener:
            self.action_capture_listener.stop()
            self.action_capture_listener = None
        if self.tray_icon is not None:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
            self.tray_icon = None
        self.root.destroy()


def _setup_dpi():
    """启用高 DPI 感知并返回 (dpi, scale)。必须在创建 Tk 之前调用。"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    try:
        dpi = int(ctypes.windll.user32.GetDpiForSystem()) or 96
    except Exception:
        dpi = 96
    return dpi, dpi / 96.0


def main():
    _dpi, scale = _setup_dpi()
    root = tk.Tk()
    MapperApp(root, scale=scale)
    root.mainloop()


if __name__ == '__main__':
    main()
