# smartctrlv_tray.py
# -*- coding: utf-8 -*-
"""
SmartCtrlV 托盘前端（轻量版 - pystray + tkinter）
- 使用 pystray 实现系统托盘图标
- 使用 tkinter 实现设置窗口
- 后台逻辑直接在线程中运行 smartctrlv_main
"""

import smartctrlv_main
import os
import sys
import json
import threading
import locale
import traceback
from PIL import Image
import pystray
from pystray import MenuItem as item

# Windows 开机自启动
try:
    import winreg
except ImportError:
    winreg = None

APP_VERSION = "v1.1"
APP_NAME = "SmartCtrlV"
TRAY_APP_NAME = "SmartCtrlVTray"

IS_FROZEN = getattr(sys, "frozen", False)


def get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(relative_path: str) -> str:
    if hasattr(sys, "frozen"):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


SCRIPT_DIR = get_base_dir()
CONFIG_PATH = os.path.join(SCRIPT_DIR, "smartctrlv_config.json")
LOG_DIR = SCRIPT_DIR

# ===================== 多语言字典 =====================
I18N = {
    "zh": {
        "tray_tooltip": f"{APP_NAME} {APP_VERSION}",
        "menu_status": "状态 / 使用说明",
        "menu_enable_explorer": "启用 Explorer 增强",
        "menu_enable_menu": "启用多格式粘贴菜单",
        "menu_enable_whitelist": "菜单白名单生效",
        "menu_open_settings": "打开设置...",
        "menu_open_config": "打开配置文件",
        "menu_open_logs": "打开日志目录",
        "menu_autostart": "开机自启动",
        "menu_restart_core": "重启后台进程",
        "menu_quit": "退出",
        "menu_language": "语言",
        "menu_lang_auto": "自动（跟随系统）",
        "menu_lang_zh": "简体中文",
        "menu_lang_ja": "日本語",
        "menu_lang_en": "English",
        "status_title": f"{APP_NAME} 状态",
        "status_text": (
            "{app} {ver}\n\n"
            "配置文件：{config}\n\n"
            "当前功能状态：\n"
            "- Explorer 增强：{explorer}\n"
            "- 多格式粘贴菜单：{menu}\n"
            "- 菜单白名单：{whitelist}\n\n"
            "提示：\n"
            "- 在资源管理器里 Ctrl+V：智能处理命令 / 文件名 / 写入文本文件\n"
            "- Ctrl+Alt+V：打开多格式粘贴菜单（默认仅在白名单应用中）\n"
            "- Ctrl+Alt+Esc：紧急退出后台"
        ),
        "on": "开启",
        "off": "关闭",
        "settings_title": f"{APP_NAME} 设置",
        "settings_explorer_section": "Explorer 增强",
        "settings_explorer_enable": "启用 Explorer 增强",
        "settings_explorer_cmd": "剪贴板命令 -> CMD 执行",
        "settings_explorer_create": "按行创建空文件/文件夹",
        "settings_explorer_write": "选中文本文件时写入",
        "settings_explorer_hotkey": "Explorer Ctrl+V 热键:",
        "settings_menu_section": "多格式粘贴菜单",
        "settings_menu_enable": "启用多格式粘贴菜单",
        "settings_menu_whitelist": "启用白名单",
        "settings_menu_hotkey": "菜单热键:",
        "settings_menu_whitelist_label": "白名单进程 (每行一个 exe 名):",
        "settings_options_section": "菜单条目开关",
        "settings_opt_raw": "原样粘贴",
        "settings_opt_plain": "纯文本粘贴",
        "settings_opt_md": "Markdown 清理粘贴",
        "settings_opt_struct": "结构化格式化(JSON/XML/HTML/SQL)",
        "settings_opt_collapse": "去所有空行粘贴",
        "settings_opt_py": "Python 缩进整理粘贴",
        "settings_save": "保存并应用",
        "settings_cancel": "取消",
        "btn_ok": "确定",
    },
    "ja": {
        "tray_tooltip": f"{APP_NAME} {APP_VERSION}",
        "menu_status": "状態 / 使い方",
        "menu_enable_explorer": "Explorer 拡張を有効",
        "menu_enable_menu": "多機能ペーストメニューを有効",
        "menu_enable_whitelist": "ホワイトリストを有効",
        "menu_open_settings": "設定を開く...",
        "menu_open_config": "設定ファイルを開く",
        "menu_open_logs": "ログフォルダを開く",
        "menu_autostart": "Windows 起動時に自動起動",
        "menu_restart_core": "バックグラウンドを再起動",
        "menu_quit": "終了",
        "menu_language": "言語",
        "menu_lang_auto": "自動",
        "menu_lang_zh": "簡体字中国語",
        "menu_lang_ja": "日本語",
        "menu_lang_en": "English",
        "status_title": f"{APP_NAME} 状態",
        "status_text": (
            "{app} {ver}\n\n"
            "設定ファイル：{config}\n\n"
            "現在の機能状態：\n"
            "- Explorer 拡張：{explorer}\n"
            "- 多機能ペーストメニュー：{menu}\n"
            "- ホワイトリスト：{whitelist}\n\n"
            "ヒント：\n"
            "- Explorer で Ctrl+V：コマンド / ファイル名 / テキストファイルへの書き込みを自動判定\n"
            "- Ctrl+Alt+V：多機能ペーストメニューを開く\n"
            "- Ctrl+Alt+Esc：緊急終了"
        ),
        "on": "オン",
        "off": "オフ",
        "settings_title": f"{APP_NAME} 設定",
        "settings_explorer_section": "Explorer 拡張",
        "settings_explorer_enable": "Explorer 拡張を有効",
        "settings_explorer_cmd": "クリップボードのコマンドを CMD で実行",
        "settings_explorer_create": "行ごとに空ファイル/フォルダを作成",
        "settings_explorer_write": "選択中のテキストファイルに書き込む",
        "settings_explorer_hotkey": "Explorer Ctrl+V ショートカット:",
        "settings_menu_section": "多機能ペーストメニュー",
        "settings_menu_enable": "多機能ペーストメニューを有効",
        "settings_menu_whitelist": "ホワイトリストを有効",
        "settings_menu_hotkey": "メニューのホットキー:",
        "settings_menu_whitelist_label": "ホワイトリストのプロセス (1行に1つのexe名):",
        "settings_options_section": "メニュー項目の有効/無効",
        "settings_opt_raw": "そのまま貼り付け",
        "settings_opt_plain": "プレーンテキストで貼り付け",
        "settings_opt_md": "Markdown を整形して貼り付け",
        "settings_opt_struct": "構造化フォーマット(JSON/XML/HTML/SQL)",
        "settings_opt_collapse": "空行をすべて削除して貼り付け",
        "settings_opt_py": "Python インデントを整理して貼り付け",
        "settings_save": "保存して適用",
        "settings_cancel": "キャンセル",
        "btn_ok": "OK",
    },
    "en": {
        "tray_tooltip": f"{APP_NAME} {APP_VERSION}",
        "menu_status": "Status / Help",
        "menu_enable_explorer": "Enable Explorer enhancements",
        "menu_enable_menu": "Enable multi-format paste menu",
        "menu_enable_whitelist": "Enable menu whitelist",
        "menu_open_settings": "Open settings...",
        "menu_open_config": "Open config file",
        "menu_open_logs": "Open log directory",
        "menu_autostart": "Run at system startup",
        "menu_restart_core": "Restart backend",
        "menu_quit": "Quit",
        "menu_language": "Language",
        "menu_lang_auto": "Auto (follow system)",
        "menu_lang_zh": "Simplified Chinese",
        "menu_lang_ja": "Japanese",
        "menu_lang_en": "English",
        "status_title": f"{APP_NAME} Status",
        "status_text": (
            "{app} {ver}\n\n"
            "Config file: {config}\n\n"
            "Current feature status:\n"
            "- Explorer enhancements: {explorer}\n"
            "- Multi-format paste menu: {menu}\n"
            "- Menu whitelist: {whitelist}\n\n"
            "Tips:\n"
            "- In Explorer, Ctrl+V: smart handling of commands / file names / writing to text files\n"
            "- Ctrl+Alt+V: open multi-format paste menu\n"
            "- Ctrl+Alt+Esc: emergency exit"
        ),
        "on": "On",
        "off": "Off",
        "settings_title": f"{APP_NAME} Settings",
        "settings_explorer_section": "Explorer enhancements",
        "settings_explorer_enable": "Enable Explorer enhancements",
        "settings_explorer_cmd": "Clipboard commands -> CMD execution",
        "settings_explorer_create": "Create empty files/folders line by line",
        "settings_explorer_write": "Write clipboard text to selected file",
        "settings_explorer_hotkey": "Explorer Ctrl+V hotkey:",
        "settings_menu_section": "Multi-format paste menu",
        "settings_menu_enable": "Enable multi-format paste menu",
        "settings_menu_whitelist": "Enable whitelist",
        "settings_menu_hotkey": "Menu hotkey:",
        "settings_menu_whitelist_label": "Whitelist processes (one exe name per line):",
        "settings_options_section": "Menu item switches",
        "settings_opt_raw": "Raw paste",
        "settings_opt_plain": "Plain text paste",
        "settings_opt_md": "Markdown cleanup paste",
        "settings_opt_struct": "Structured format (JSON/XML/HTML/SQL)",
        "settings_opt_collapse": "Remove all blank lines",
        "settings_opt_py": "Python dedent paste",
        "settings_save": "Save & apply",
        "settings_cancel": "Cancel",
        "btn_ok": "OK",
    },
}


def tr(lang: str, key: str, **kwargs) -> str:
    d = I18N.get(lang, I18N["en"])
    text = d.get(key, I18N["en"].get(key, key))
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text


# ===================== 默认配置 =====================
DEFAULT_CONFIG = {
    "ui": {"language": "auto"},
    "explorer": {
        "enabled": True,
        "enable_command_from_clipboard": True,
        "enable_create_files_from_clipboard": True,
        "enable_write_file_from_clipboard": True,
        "text_ext_whitelist": [
            ".txt", ".md", ".markdown", ".log", ".json", ".yaml", ".yml",
            ".ini", ".cfg", ".py", ".js", ".ts", ".java", ".c", ".cpp", ".cs",
        ],
    },
    "menu": {
        "enabled": True,
        "whitelist_enabled": True,
        "whitelist_processes": [
            "notepad.exe", "chrome.exe", "msedge.exe", "firefox.exe",
            "code.exe", "winword.exe", "excel.exe", "powerpnt.exe",
            "wechat.exe", "qq.exe",
        ],
        "hotkey": "ctrl+alt+v",
        "options": {
            "raw": True, "plain": True, "markdown": True,
            "structured": True, "collapse_blank": True, "python_dedent": True,
        },
    },
    "hotkeys": {"explorer_ctrl_v": "ctrl+v"},
}


def deep_update(base: dict, override: dict):
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            deep_update(base[k], v)
        else:
            base[k] = v


def detect_system_lang() -> str:
    try:
        loc = locale.getdefaultlocale()[0] or ""
        loc = loc.lower()
        if loc.startswith("zh"):
            return "zh"
        if loc.startswith("ja"):
            return "ja"
    except Exception:
        pass
    return "en"


def get_effective_lang(config: dict) -> str:
    setting = config.get("ui", {}).get("language", "auto")
    if setting in ("zh", "ja", "en"):
        return setting
    return detect_system_lang()


# ===================== 配置管理 =====================
class ConfigManager:
    def __init__(self):
        self.config = self.load_or_create()

    def load_or_create(self) -> dict:
        cfg = json.loads(json.dumps(DEFAULT_CONFIG))
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    user_cfg = json.load(f)
                deep_update(cfg, user_cfg)
            except Exception as e:
                print("[Tray] 读取配置失败:", e)
        else:
            self.save(cfg)
        return cfg

    def save(self, cfg: dict = None):
        if cfg is None:
            cfg = self.config
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print("[Tray] 写入配置失败:", e)

    def reload(self):
        self.config = self.load_or_create()


# ===================== 设置窗口 (Tkinter) =====================
class SettingsWindow:
    def __init__(self, config_manager: ConfigManager, lang: str, on_save_callback):
        self.config_manager = config_manager
        self.lang = lang
        self.on_save = on_save_callback
        self.window = None

    def show(self):
        if self.window is not None:
            try:
                self.window.lift()
                self.window.focus_force()
                return
            except Exception:
                pass

        import tkinter as tk
        from tkinter import ttk

        cfg = self.config_manager.config
        self.window = tk.Tk()
        self.window.title(tr(self.lang, "settings_title"))
        self.window.geometry("500x600")
        self.window.resizable(True, True)

        # 主框架带滚动
        main_frame = ttk.Frame(self.window, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # === Explorer 区块 ===
        exp_frame = ttk.LabelFrame(main_frame, text=tr(self.lang, "settings_explorer_section"), padding=5)
        exp_frame.pack(fill=tk.X, pady=5)

        exp_cfg = cfg.get("explorer", {})
        self.var_explorer_enabled = tk.BooleanVar(value=exp_cfg.get("enabled", True))
        self.var_explorer_cmd = tk.BooleanVar(value=exp_cfg.get("enable_command_from_clipboard", True))
        self.var_explorer_create = tk.BooleanVar(value=exp_cfg.get("enable_create_files_from_clipboard", True))
        self.var_explorer_write = tk.BooleanVar(value=exp_cfg.get("enable_write_file_from_clipboard", True))

        ttk.Checkbutton(exp_frame, text=tr(self.lang, "settings_explorer_enable"), variable=self.var_explorer_enabled).pack(anchor=tk.W)
        ttk.Checkbutton(exp_frame, text=tr(self.lang, "settings_explorer_cmd"), variable=self.var_explorer_cmd).pack(anchor=tk.W)
        ttk.Checkbutton(exp_frame, text=tr(self.lang, "settings_explorer_create"), variable=self.var_explorer_create).pack(anchor=tk.W)
        ttk.Checkbutton(exp_frame, text=tr(self.lang, "settings_explorer_write"), variable=self.var_explorer_write).pack(anchor=tk.W)

        hotkey_frame = ttk.Frame(exp_frame)
        hotkey_frame.pack(fill=tk.X, pady=2)
        ttk.Label(hotkey_frame, text=tr(self.lang, "settings_explorer_hotkey")).pack(side=tk.LEFT)
        self.entry_explorer_hotkey = ttk.Entry(hotkey_frame, width=20)
        self.entry_explorer_hotkey.insert(0, cfg.get("hotkeys", {}).get("explorer_ctrl_v", "ctrl+v"))
        self.entry_explorer_hotkey.pack(side=tk.LEFT, padx=5)

        # === 菜单区块 ===
        menu_frame = ttk.LabelFrame(main_frame, text=tr(self.lang, "settings_menu_section"), padding=5)
        menu_frame.pack(fill=tk.X, pady=5)

        menu_cfg = cfg.get("menu", {})
        self.var_menu_enabled = tk.BooleanVar(value=menu_cfg.get("enabled", True))
        self.var_menu_whitelist = tk.BooleanVar(value=menu_cfg.get("whitelist_enabled", True))

        ttk.Checkbutton(menu_frame, text=tr(self.lang, "settings_menu_enable"), variable=self.var_menu_enabled).pack(anchor=tk.W)
        ttk.Checkbutton(menu_frame, text=tr(self.lang, "settings_menu_whitelist"), variable=self.var_menu_whitelist).pack(anchor=tk.W)

        hotkey_frame2 = ttk.Frame(menu_frame)
        hotkey_frame2.pack(fill=tk.X, pady=2)
        ttk.Label(hotkey_frame2, text=tr(self.lang, "settings_menu_hotkey")).pack(side=tk.LEFT)
        self.entry_menu_hotkey = ttk.Entry(hotkey_frame2, width=20)
        self.entry_menu_hotkey.insert(0, menu_cfg.get("hotkey", "ctrl+alt+v"))
        self.entry_menu_hotkey.pack(side=tk.LEFT, padx=5)

        # 白名单进程
        ttk.Label(menu_frame, text=tr(self.lang, "settings_menu_whitelist_label")).pack(anchor=tk.W, pady=(5, 0))
        self.text_whitelist = tk.Text(menu_frame, height=5, width=50)
        self.text_whitelist.insert("1.0", "\n".join(menu_cfg.get("whitelist_processes", [])))
        self.text_whitelist.pack(fill=tk.X, pady=2)

        # === 菜单选项区块 ===
        opts_frame = ttk.LabelFrame(main_frame, text=tr(self.lang, "settings_options_section"), padding=5)
        opts_frame.pack(fill=tk.X, pady=5)

        opts_cfg = menu_cfg.get("options", {})
        self.var_opt_raw = tk.BooleanVar(value=opts_cfg.get("raw", True))
        self.var_opt_plain = tk.BooleanVar(value=opts_cfg.get("plain", True))
        self.var_opt_md = tk.BooleanVar(value=opts_cfg.get("markdown", True))
        self.var_opt_struct = tk.BooleanVar(value=opts_cfg.get("structured", True))
        self.var_opt_collapse = tk.BooleanVar(value=opts_cfg.get("collapse_blank", True))
        self.var_opt_py = tk.BooleanVar(value=opts_cfg.get("python_dedent", True))

        ttk.Checkbutton(opts_frame, text=tr(self.lang, "settings_opt_raw"), variable=self.var_opt_raw).pack(anchor=tk.W)
        ttk.Checkbutton(opts_frame, text=tr(self.lang, "settings_opt_plain"), variable=self.var_opt_plain).pack(anchor=tk.W)
        ttk.Checkbutton(opts_frame, text=tr(self.lang, "settings_opt_md"), variable=self.var_opt_md).pack(anchor=tk.W)
        ttk.Checkbutton(opts_frame, text=tr(self.lang, "settings_opt_struct"), variable=self.var_opt_struct).pack(anchor=tk.W)
        ttk.Checkbutton(opts_frame, text=tr(self.lang, "settings_opt_collapse"), variable=self.var_opt_collapse).pack(anchor=tk.W)
        ttk.Checkbutton(opts_frame, text=tr(self.lang, "settings_opt_py"), variable=self.var_opt_py).pack(anchor=tk.W)

        # === 按钮 ===
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=10)
        ttk.Button(btn_frame, text=tr(self.lang, "settings_save"), command=self._on_save).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text=tr(self.lang, "settings_cancel"), command=self._on_cancel).pack(side=tk.RIGHT)

        self.window.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.window.mainloop()

    def _on_save(self):
        cfg = self.config_manager.config
        # Explorer
        cfg["explorer"]["enabled"] = self.var_explorer_enabled.get()
        cfg["explorer"]["enable_command_from_clipboard"] = self.var_explorer_cmd.get()
        cfg["explorer"]["enable_create_files_from_clipboard"] = self.var_explorer_create.get()
        cfg["explorer"]["enable_write_file_from_clipboard"] = self.var_explorer_write.get()
        cfg["hotkeys"]["explorer_ctrl_v"] = self.entry_explorer_hotkey.get().strip() or "ctrl+v"
        # Menu
        cfg["menu"]["enabled"] = self.var_menu_enabled.get()
        cfg["menu"]["whitelist_enabled"] = self.var_menu_whitelist.get()
        cfg["menu"]["hotkey"] = self.entry_menu_hotkey.get().strip() or "ctrl+alt+v"
        # Whitelist
        whitelist_text = self.text_whitelist.get("1.0", "end").strip()
        cfg["menu"]["whitelist_processes"] = [p.strip() for p in whitelist_text.splitlines() if p.strip()]
        # Options
        cfg["menu"]["options"]["raw"] = self.var_opt_raw.get()
        cfg["menu"]["options"]["plain"] = self.var_opt_plain.get()
        cfg["menu"]["options"]["markdown"] = self.var_opt_md.get()
        cfg["menu"]["options"]["structured"] = self.var_opt_struct.get()
        cfg["menu"]["options"]["collapse_blank"] = self.var_opt_collapse.get()
        cfg["menu"]["options"]["python_dedent"] = self.var_opt_py.get()

        self.config_manager.save()
        self.window.destroy()
        self.window = None
        if self.on_save:
            self.on_save()

    def _on_cancel(self):
        self.window.destroy()
        self.window = None


# ===================== 状态窗口 =====================
def show_status_window(config: dict, lang: str):
    import tkinter as tk
    from tkinter import ttk

    win = tk.Tk()
    win.title(tr(lang, "status_title"))
    win.geometry("450x350")
    win.resizable(False, False)

    exp_on = tr(lang, "on") if config.get("explorer", {}).get("enabled", True) else tr(lang, "off")
    menu_on = tr(lang, "on") if config.get("menu", {}).get("enabled", True) else tr(lang, "off")
    wl_on = tr(lang, "on") if config.get("menu", {}).get("whitelist_enabled", True) else tr(lang, "off")

    text = tr(lang, "status_text", app=APP_NAME, ver=APP_VERSION, config=CONFIG_PATH,
              explorer=exp_on, menu=menu_on, whitelist=wl_on)

    frame = ttk.Frame(win, padding=15)
    frame.pack(fill=tk.BOTH, expand=True)

    lbl = ttk.Label(frame, text=text, wraplength=420, justify=tk.LEFT)
    lbl.pack(fill=tk.BOTH, expand=True)

    btn = ttk.Button(frame, text=tr(lang, "btn_ok"), command=win.destroy)
    btn.pack(pady=10)

    win.mainloop()


# ===================== 开机自启动 =====================
def is_autostart_enabled() -> bool:
    if winreg is None or os.name != "nt":
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Run",
                            0, winreg.KEY_READ) as key:
            try:
                value, _ = winreg.QueryValueEx(key, TRAY_APP_NAME)
                return True
            except FileNotFoundError:
                return False
    except Exception:
        return False


def set_autostart_enabled(enabled: bool):
    if winreg is None or os.name != "nt":
        return
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Run",
                            0, winreg.KEY_ALL_ACCESS) as key:
            if enabled:
                if getattr(sys, 'frozen', False):
                    exe_path = sys.executable
                else:
                    exe_path = f'"{sys.executable}" "{os.path.abspath(sys.argv[0])}"'
                winreg.SetValueEx(key, TRAY_APP_NAME, 0, winreg.REG_SZ, exe_path)
            else:
                try:
                    winreg.DeleteValue(key, TRAY_APP_NAME)
                except FileNotFoundError:
                    pass
    except Exception as e:
        print("[Tray] 设置开机自启动失败:", e)


# ===================== 托盘应用 =====================
class TrayApp:
    def __init__(self):
        self.config_manager = ConfigManager()
        self.lang = get_effective_lang(self.config_manager.config)
        self.icon = None
        self.settings_window = None
        self.backend_running = False

    def create_image(self):
        icon_path = resource_path("smartctrlv.ico")
        if os.path.exists(icon_path):
            return Image.open(icon_path)
        # 创建一个简单的默认图标
        img = Image.new('RGB', (64, 64), color=(52, 152, 219))
        return img

    def get_menu(self):
        cfg = self.config_manager.config

        def toggle_explorer(icon, item):
            cfg["explorer"]["enabled"] = not cfg["explorer"]["enabled"]
            self.config_manager.save()
            self.restart_backend()
            self.update_menu()

        def toggle_menu(icon, item):
            cfg["menu"]["enabled"] = not cfg["menu"]["enabled"]
            self.config_manager.save()
            self.restart_backend()
            self.update_menu()

        def toggle_whitelist(icon, item):
            cfg["menu"]["whitelist_enabled"] = not cfg["menu"]["whitelist_enabled"]
            self.config_manager.save()
            self.restart_backend()
            self.update_menu()

        def toggle_autostart(icon, item):
            current = is_autostart_enabled()
            set_autostart_enabled(not current)
            self.update_menu()

        def set_lang(lang_code):
            def _set(icon, item):
                cfg["ui"]["language"] = lang_code
                self.config_manager.save()
                self.lang = get_effective_lang(cfg)
                self.update_menu()
            return _set

        def open_settings(icon, item):
            threading.Thread(target=self._open_settings, daemon=True).start()

        def open_config(icon, item):
            if os.path.exists(CONFIG_PATH):
                os.startfile(CONFIG_PATH)

        def open_logs(icon, item):
            if os.path.isdir(LOG_DIR):
                os.startfile(LOG_DIR)

        def show_status(icon, item):
            threading.Thread(target=lambda: show_status_window(cfg, self.lang), daemon=True).start()

        def restart_core(icon, item):
            self.restart_backend()

        def quit_app(icon, item):
            self.stop_backend()
            icon.stop()

        lang_setting = cfg.get("ui", {}).get("language", "auto")

        return pystray.Menu(
            item(tr(self.lang, "menu_status"), show_status),
            pystray.Menu.SEPARATOR,
            item(tr(self.lang, "menu_enable_explorer"), toggle_explorer,
                 checked=lambda item: cfg.get("explorer", {}).get("enabled", True)),
            item(tr(self.lang, "menu_enable_menu"), toggle_menu,
                 checked=lambda item: cfg.get("menu", {}).get("enabled", True)),
            item(tr(self.lang, "menu_enable_whitelist"), toggle_whitelist,
                 checked=lambda item: cfg.get("menu", {}).get("whitelist_enabled", True)),
            pystray.Menu.SEPARATOR,
            item(tr(self.lang, "menu_open_settings"), open_settings),
            item(tr(self.lang, "menu_open_config"), open_config),
            item(tr(self.lang, "menu_open_logs"), open_logs),
            pystray.Menu.SEPARATOR,
            item(tr(self.lang, "menu_language"), pystray.Menu(
                item(tr(self.lang, "menu_lang_auto"), set_lang("auto"),
                     checked=lambda item: lang_setting == "auto"),
                item(tr(self.lang, "menu_lang_zh"), set_lang("zh"),
                     checked=lambda item: lang_setting == "zh"),
                item(tr(self.lang, "menu_lang_ja"), set_lang("ja"),
                     checked=lambda item: lang_setting == "ja"),
                item(tr(self.lang, "menu_lang_en"), set_lang("en"),
                     checked=lambda item: lang_setting == "en"),
            )),
            pystray.Menu.SEPARATOR,
            item(tr(self.lang, "menu_autostart"), toggle_autostart,
                 checked=lambda item: is_autostart_enabled()),
            pystray.Menu.SEPARATOR,
            item(tr(self.lang, "menu_restart_core"), restart_core),
            item(tr(self.lang, "menu_quit"), quit_app),
        )

    def update_menu(self):
        self.config_manager.reload()
        self.lang = get_effective_lang(self.config_manager.config)
        if self.icon:
            self.icon.menu = self.get_menu()
            self.icon.update_menu()

    def _open_settings(self):
        def on_save():
            self.config_manager.reload()
            self.restart_backend()
            self.update_menu()

        self.settings_window = SettingsWindow(self.config_manager, self.lang, on_save)
        self.settings_window.show()

    def start_backend(self):
        if self.backend_running:
            return
        self.backend_running = True
        threading.Thread(target=smartctrlv_main.main, daemon=True).start()
        print("[Tray] 后台已启动")

    def stop_backend(self):
        if not self.backend_running:
            return
        try:
            smartctrlv_main.stop_hooks()
        except Exception:
            pass
        self.backend_running = False
        print("[Tray] 后台已停止")

    def restart_backend(self):
        try:
            smartctrlv_main.stop_hooks()
        except Exception:
            pass
        try:
            smartctrlv_main.start_hooks()
        except Exception:
            pass
        print("[Tray] 后台已重启")

    def run(self):
        self.start_backend()
        self.icon = pystray.Icon(
            APP_NAME,
            self.create_image(),
            tr(self.lang, "tray_tooltip"),
            self.get_menu()
        )
        self.icon.run()


def main():
    app = TrayApp()
    app.run()


if __name__ == "__main__":
    main()
