import os
import time
import json
import threading
import re
import textwrap
import tkinter as tk
import urllib.parse
import tkinter.messagebox as messagebox
import sys
import os
import keyboard
import pyperclip

import subprocess
import shutil  # 文件顶部如果还没 import 的话记得加上
import difflib
import locale

import win32gui
import win32process
import win32api
import win32con
import win32clipboard as wcb

import mouse  # 全局鼠标监听
import comtypes
import comtypes.client
import xml.dom.minidom as minidom

# ========= 配置相关 =========

def get_base_dir():
    # 如果是打包成 exe 运行，sys.frozen = True
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    # 普通 Python 运行
    return os.path.dirname(os.path.abspath(__file__))

SCRIPT_DIR = get_base_dir()
CONFIG_PATH = os.path.join(SCRIPT_DIR, "smartctrlv_config.json")

CONFIG_DEFAULT = {
    "explorer": {
        "enable_command_from_clipboard": True,       # 剪贴板命令 -> cmd 执行
        "enable_create_files_from_clipboard": True,  # 文本行 -> 创建空文件
        "enable_write_file_from_clipboard": True,    # 选中文件 -> 写入文件
        "text_ext_whitelist": [                      # 写入文件的“文本后缀白名单”
            ".txt", ".md", ".markdown",
            ".log",
            ".json", ".yaml", ".yml", ".ini", ".cfg",
            ".py", ".js", ".ts", ".java", ".c", ".cpp", ".cs",
        ],
    },
    "menu": {
        "whitelist_enabled": True,
        "whitelist_processes": [
            "notepad.exe",
            "chrome.exe",
            "msedge.exe",
            "firefox.exe",
            "code.exe",
            "winword.exe",
            "excel.exe",
            "powerpnt.exe",
            "wechat.exe",
            "qq.exe",
        ],
        "hotkey": "ctrl+alt+v",

        "options": {
            "raw": True,
            "plain": True,
            "markdown": True,
            "structured": True,
            "collapse_blank": True,
            "python_dedent": True,
        },
    },
    "hotkeys": {
        "explorer_ctrl_v": "ctrl+v",
    }
}

CONFIG = CONFIG_DEFAULT.copy()

# ========= hooks 运行状态（给托盘用） =========
# ========= hooks 运行状态 =========
HOOKS_STARTED = False
HOOK_HANDLES = []  # 保存 add_hotkey 返回值，方便统一卸载

def get_ui_lang():
    """
    根据 config['ui']['language'] 或系统语言，返回 'zh' / 'ja' / 'en'
    """
    # 允许托盘写的 ui.language
    ui_cfg = CONFIG.get("ui", {})
    lang = ui_cfg.get("language", "auto")
    if lang in ("zh", "ja", "en"):
        return lang

    # auto: 根据系统语言猜
    try:
        loc = (locale.getdefaultlocale()[0] or "").lower()
    except Exception:
        loc = ""

    if loc.startswith("zh"):
        return "zh"
    if loc.startswith("ja"):
        return "ja"
    return "en"

def emergency_exit():
    """
    紧急逃生：卸载所有 hotkey，然后强制退出进程。
    遇到任何奇怪情况，按 Ctrl+Alt+Esc 就能把本程序干掉。
    """
    global HOOKS_STARTED, HOOK_HANDLES

    try:
        for h in HOOK_HANDLES:
            try:
                keyboard.remove_hotkey(h)
            except Exception:
                pass
        HOOK_HANDLES = []
        HOOKS_STARTED = False

        # 兜底再清一次（可能也会影响别的用 keyboard 的脚本，但我们只有一个的话没关系）
        try:
            keyboard.clear_all_hotkeys()
        except Exception:
            pass
    except Exception:
        pass

    print("[SmartCtrlV] emergency_exit: 所有 hotkey 已卸载，进程将退出。")
    os._exit(0)  # 直接硬退出，保证钩子被清理



def deep_update_dict(base: dict, override: dict):
    """简单深度合并 dict，用用户配置覆盖默认配置"""
    for k, v in override.items():
        if (
            isinstance(v, dict)
            and k in base
            and isinstance(base[k], dict)
        ):
            deep_update_dict(base[k], v)
        else:
            base[k] = v


def load_config():
    global CONFIG
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
            cfg = json.loads(json.dumps(CONFIG_DEFAULT))  # 深拷贝一份默认
            deep_update_dict(cfg, user_cfg)
            CONFIG = cfg
            print(f"[SmartCtrlV] 已加载配置文件: {CONFIG_PATH}")
        else:
            print(f"[SmartCtrlV] 未找到配置文件，使用默认配置。")
    except Exception as e:
        print(f"[SmartCtrlV] 读取配置失败，使用默认配置。错误: {e}")
        CONFIG = CONFIG_DEFAULT

load_config
# ========= 全局状态 =========
def save_config():
    """把当前 CONFIG 写回 smartctrlv_config.json"""
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(CONFIG, f, indent=2, ensure_ascii=False)
        print(f"[SmartCtrlV] 配置已保存到 {CONFIG_PATH}")
    except Exception as e:
        print(f"[SmartCtrlV] 保存配置失败: {e}")

# 给 Explorer Ctrl+V 用的标记，避免递归
is_simulating = False

# 多格式菜单用的状态
last_foreground_hwnd = None
menu_window = None
root = None
menu_visible = False


# ========= Explorer 相关工具（Ctrl+V -> 创建文件） =========
ENABLE_EXPLORER_COMMAND = CONFIG["explorer"]["enable_command_from_clipboard"]
ENABLE_EXPLORER_CREATE_FILES = CONFIG["explorer"]["enable_create_files_from_clipboard"]
ENABLE_EXPLORER_WRITE_FILE = CONFIG["explorer"]["enable_write_file_from_clipboard"]

def get_foreground_exe_path_and_hwnd():
    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return None, None

    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    try:
        h_process = win32api.OpenProcess(
            win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ,
            False,
            pid,
        )
    except Exception:
        return None, hwnd

    try:
        exe_path = win32process.GetModuleFileNameEx(h_process, 0)
    except Exception:
        exe_path = None
    finally:
        win32api.CloseHandle(h_process)

    return exe_path, hwnd


def is_clipboard_file_drop():
    CF_HDROP = 15
    try:
        return bool(wcb.IsClipboardFormatAvailable(CF_HDROP))
    except Exception:
        return False


def _convert_location_url_to_path(url: str):
    if not url or not url.lower().startswith("file:///"):
        return None
    path_part = url[8:]
    path_part = urllib.parse.unquote(path_part)
    path_part = path_part.replace("/", "\\")
    return path_part


def get_explorer_folder_path(foreground_hwnd):
    """通过 Shell.Application 找到当前 Explorer 文件夹路径"""
    comtypes.CoInitialize()
    try:
        shell = comtypes.client.CreateObject("Shell.Application")
        for window in shell.Windows():
            try:
                if not window or window.HWND != foreground_hwnd:
                    continue

                # 1) Document.Folder.Self.Path
                try:
                    doc = getattr(window, "Document", None)
                    if doc is not None:
                        folder = getattr(doc, "Folder", None)
                        if folder is not None:
                            self_item = getattr(folder, "Self", None)
                            if self_item is not None:
                                path = getattr(self_item, "Path", None)
                                if path:
                                    return path
                except Exception:
                    pass

                # 2) LocationURL 兜底
                try:
                    loc = getattr(window, "LocationURL", None)
                    path2 = _convert_location_url_to_path(loc) if loc else None
                    if path2:
                        return path2
                except Exception:
                    pass

            except Exception:
                continue

        return None
    finally:
        comtypes.CoUninitialize()


def is_explorer_text_input_focused():
    """粗略判断当前焦点是不是 Edit 类控件（地址栏/搜索框/重命名）"""
    try:
        focus_hwnd = win32gui.GetFocus()
        if not focus_hwnd:
            return False
        class_name = win32gui.GetClassName(focus_hwnd)
        if "Edit" in class_name or "EDIT" in class_name:
            return True
    except Exception:
        pass
    return False


# ---------- 文件名 / 命令 判断 ----------

def looks_like_filename(line: str) -> bool:
    """
    判断一行是否“像文件名”：
    - 不能包含空格
    - 不能包含路径分隔符 /: 等
    - 不能包含 Windows 非法字符
    """
    line = line.strip()
    if not line:
        return False

    # 有空格就认为不是“干净文件名”（命令更可能）
    if " " in line:
        return False

    # 包含路径符号也认为不是单纯“文件名”
    if any(ch in line for ch in ['\\', '/', ':']):
        return False

    # Windows 非法字符
    invalid_chars = '<>:"/\\|?*'
    if any(ch in line for ch in invalid_chars):
        return False

    # 简单合法形式：名字[.扩展名]
    if re.fullmatch(r'[\w\-.]+(\.[\w\-.]+)?', line):
        return True

    return False


def looks_like_filename_list(text: str) -> bool:
    """
    判断整段文本是否像“文件名列表”：
    - 至少一行
    - 每一行都 looks_like_filename
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return False
    return all(looks_like_filename(l) for l in lines)

def normalize_code_block(block: str) -> str:
    """
    清洗从 AI 回答里截出来的“代码块”：
    - 去掉像 python / rust / 复制代码 这种按钮文字
    - 去掉 ```xxx 语言标记（如果有的话）
    - 去掉首尾多余空行
    """
    lines = block.splitlines()
    cleaned = []

    skip_markers = {
        "python", "rust", "cpp", "c++", "java", "go",
        "复制代码", "copy", "复制"
    }

    for line in lines:
        raw = line.rstrip("\r")
        stripped = raw.strip()

        # 全空行：保留为空行（有时候缩进/结构要用）
        if not stripped:
            cleaned.append("")
            continue

        # 去掉 ``` 开头的围栏
        if stripped.startswith("```"):
            continue

        # 去掉语言名 / “复制代码”按钮行
        if stripped.lower() in skip_markers:
            continue

        cleaned.append(raw)

    # 去掉首尾多余空行
    while cleaned and cleaned[0].strip() == "":
        cleaned.pop(0)
    while cleaned and cleaned[-1].strip() == "":
        cleaned.pop()

    return "\n".join(cleaned)


def is_probable_shell_command(text: str) -> bool:
    """
    根据整段文本判断更像“命令”还是“文件名列表/普通文本”。

    规则：
    - 如果整段像“文件名列表” -> False（交给创建文件逻辑）
    - 否则：
        * 多行：只有当某些行看起来像命令（前缀 / 操作符）才当命令
        * 单行：
            - 像纯文件名 => False
            - 含空格 / shell 操作符 / 常见命令前缀 => True
    """
    text = text.strip()
    if not text:
        return False

    # 整体是文件名列表 -> 绝不是命令
    if looks_like_filename_list(text):
        return False

    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return False

    shell_tokens = ["&&", "||", "|", ">", "<"]
    prefixes = [
        "cd ", "dir", "ls ", "git ", "pip ", "python", "py ",
        "conda ", "npm ", "yarn ", "cargo ", "mvn ", "gradle ",
        "clang", "gcc", "g++", "make ",
    ]

    # 多行：只要有一行明显像命令，就认为是命令脚本
    if len(lines) > 1:
        for ln in lines:
            low = ln.lower()
            if any(tok in ln for tok in shell_tokens):
                return True
            if any(low.startswith(p) for p in prefixes):
                return True
        # 多行且没有明显命令特征 -> 不当命令（比如几千行代码）
        return False

    # 单行情况
    line = lines[0]

    # 单行如果像文件名 -> 不是命令
    if looks_like_filename(line):
        return False

    # shell 特征：操作符
    if any(tok in line for tok in shell_tokens):
        return True

    low = line.lower()
    # 常见命令前缀
    if any(low.startswith(p) for p in prefixes):
        return True

    # 如果包含中文，就不要因为“有空格”而当成命令（大概率是自然语言）
    if re.search(r"[\u4e00-\u9fff]", line):
        return False

    # 对纯英文/符号的情况，保留“有空格大概率是命令”的经验规则
    if " " in line:
        return True

    return False




def fake_ai_analyze_clipboard(text: str):
    """
    假 AI 解析：
    - 尝试从“原来的写法是 ... 可以改成 ...”里抽出 old/new 代码块
    - 把明显的命令行抽出来
    - 把“创建 xxx 文件，输入 yyy”这种抽出来
    """
    plan = {
        "files": [],
        "commands": [],
        "code_blocks": [],
        "patches": [],
        "raw_text": text,
    }

    # -------- 1) 基于“原来的写法是 / 可以改成”切 old/new --------
    # 形如：
    #   原来的写法是：
    #   def foo():
    #       print("foo1")
    #   可以改成：
    #   python
    #   复制代码
    #   def foo():
    #       logger.info("foo1")
    #   rust
    #   复制代码
    m = re.search(
        r"原来的写法是[:：]\s*(.*?)(?:可以改成[:：]\s*(.*))?$",
        text,
        flags=re.S
    )
    if m:
        old_part = m.group(1) or ""
        new_part = m.group(2) or ""

        old_norm = normalize_code_block(old_part)
        new_norm = normalize_code_block(new_part)

        if old_norm:
            plan["code_blocks"].append(old_norm)
        if new_norm:
            plan["code_blocks"].append(new_norm)

        if old_norm and new_norm and old_norm.strip() != new_norm.strip():
            plan["patches"].append({
                "old": old_norm,
                "new": new_norm,
            })

    # -------- 2) 中文 “创建 xxx 文件，输入 yyy” 这种 --------
    m2 = re.search(
        r"创建\s*([\w\-.]+\.\w+)\s*文件[^，。,；;：:]*[，。,；;：:]*\s*(?:输入|写入|内容为)[:：]?\s*(.+)$",
        text,
        flags=re.S
    )
    if m2:
        filename = m2.group(1).strip()
        content_part = m2.group(2).strip()
        content = normalize_code_block(content_part)

        plan["files"].append({
            "name": filename,
            "content": content,
        })

    # -------- 3) 提取“明显像命令”的行 --------
    shell_tokens = ["&&", "||", "|", ">", "<"]
    prefixes = [
        "cd ", "dir", "ls ", "git ", "pip ", "python", "py ",
        "conda ", "npm ", "yarn ", "cargo ", "mvn ", "gradle ",
        "clang", "gcc", "g++", "make ",
    ]
    lang_words = {"python", "rust", "cpp", "c++", "java", "go"}

    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for ln in lines:
        low = ln.lower()

        # 如果全文包含“复制代码”，那单独的 "python" / "rust" 多半是按钮，不是命令
        if low in lang_words and "复制代码" in text:
            continue

        if any(tok in ln for tok in shell_tokens) or any(low.startswith(p) for p in prefixes):
            plan["commands"].append(ln)

    return plan




def run_shell_command_in_folder(folder: str, cmd_text: str):
    """
    在指定文件夹打开 cmd 并执行命令：
    - 支持多行：每一行当一条命令，用 && 串起来
    """
    try:
        lines = [l.strip() for l in cmd_text.splitlines() if l.strip()]
        if not lines:
            return

        combined = " && ".join(lines)
        print(f"[SmartCtrlV] 在 {folder} 打开 cmd 并执行: {combined}")

        subprocess.Popen(
            ["cmd.exe", "/K", combined],
            cwd=folder,
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
    except Exception as e:
        print(f"[SmartCtrlV] 打开 cmd 失败: {e}")


def create_empty_files_by_clipboard_text(folder_path, text):
    """
    从剪贴板文本按行创建文件或文件夹：
    - 只对 looks_like_filename 的行建文件/文件夹
    - 有后缀名的 -> 创建文件
    - 无后缀名且长度合理 -> 创建文件夹
    - 其他奇怪内容（例如代码）全部跳过
    """
    if not folder_path:
        return

    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]

    if not lines:
        return

    created_count = 0
    MAX_FOLDER_NAME_LEN = 100  # 文件夹名最大长度限制

    for name in lines:
        if not looks_like_filename(name):
            # 不像正常文件名的行直接跳过，避免几千行代码变几千个文件
            continue

        base, ext = os.path.splitext(name)

        # 无后缀名：创建文件夹（长度需合理）
        is_folder = not ext and len(name) <= MAX_FOLDER_NAME_LEN

        candidate = os.path.join(folder_path, base + ext)
        index = 1
        while os.path.exists(candidate):
            candidate_name = f"{base} ({index}){ext}"
            candidate = os.path.join(folder_path, candidate_name)
            index += 1

        try:
            if is_folder:
                os.makedirs(candidate)
                print(f"[SmartCtrlV] 已创建文件夹: {candidate}")
            else:
                with open(candidate, "w", encoding="utf-8"):
                    pass
                print(f"[SmartCtrlV] 已创建文件: {candidate}")
            created_count += 1
        except Exception as e:
            print(f"[SmartCtrlV] 创建失败 {candidate}: {e}")

    if created_count == 0:
        print("[SmartCtrlV] 文本中没有合法文件名，不进行创建。")


# ---------- 选中文件获取 + 追加写入 ----------

TEXT_EXT_WHITELIST = set(
    ext.lower() for ext in CONFIG["explorer"]["text_ext_whitelist"]
)


def get_explorer_selected_files(foreground_hwnd):
    """
    获取当前 Explorer 窗口选中的文件路径列表
    """
    comtypes.CoInitialize()
    try:
        shell = comtypes.client.CreateObject("Shell.Application")
        for window in shell.Windows():
            try:
                if not window or window.HWND != foreground_hwnd:
                    continue
                doc = getattr(window, "Document", None)
                if doc is None:
                    continue
                items = doc.SelectedItems()
                paths = []
                for i in range(items.Count):
                    item = items.Item(i)
                    path = getattr(item, "Path", None)
                    if path:
                        paths.append(path)
                return paths
            except Exception:
                continue
        return []
    finally:
        comtypes.CoUninitialize()

def confirm_write_to_file(hwnd, file_path: str, text_len: int):
    """
    弹出一个 Windows 对话框，询问如何写入：
    - 是(Yes)    -> 覆盖
    - 否(No)     -> 追加
    - 取消       -> 不写
    返回值: "overwrite" / "append" / None
    """
    msg = (
        f"检测到你选中了这个文件：\n\n"
        f"{file_path}\n\n"
        f"剪贴板文本长度：{text_len} 字符\n\n"
        f"是否将剪贴板内容写入该文件？\n\n"
        f"是 = 覆盖写入（会清空原内容）\n"
        f"否 = 追加到文件末尾\n"
        f"取消 = 不写入"
    )
    title = "SmartCtrlV - 写入文件"

    flags = win32con.MB_YESNOCANCEL | win32con.MB_ICONQUESTION
    res = win32api.MessageBox(hwnd, msg, title, flags)

    if res == win32con.IDYES:
        return "overwrite"
    elif res == win32con.IDNO:
        return "append"
    else:
        return None


def write_text_to_file(file_path: str, text: str, mode: str):
    """
    按模式写入文本：
    - mode == "overwrite": 覆盖写入
    - mode == "append":    追加写入（智能补一个换行）
    """
    try:
        if mode == "overwrite":
            with open(file_path, "w", encoding="utf-8", errors="ignore") as f:
                f.write(text)
            print(f"[SmartCtrlV] 覆盖写入 {len(text)} 字符到 {file_path}")
        else:
            # 追加逻辑 = 原来的 append_text_to_file
            needs_newline = False
            if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                with open(file_path, "rb") as f:
                    try:
                        f.seek(-1, os.SEEK_END)
                        last = f.read(1)
                        if last not in (b"\n", b"\r"):
                            needs_newline = True
                    except OSError:
                        pass

            with open(file_path, "a", encoding="utf-8", errors="ignore") as f:
                if needs_newline:
                    f.write("\n")
                f.write(text)

            print(f"[SmartCtrlV] 追加写入 {len(text)} 字符到 {file_path}")
    except Exception as e:
        print(f"[SmartCtrlV] 写入失败 {file_path}: {e}")


def append_text_to_file(file_path: str, text: str):
    """
    安全地把文本追加写入到文件尾部：
    - 如果文件非空且最后一字节不是换行，就先补一个换行
    """
    try:
        needs_newline = False
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            with open(file_path, "rb") as f:
                try:
                    f.seek(-1, os.SEEK_END)
                    last = f.read(1)
                    if last not in (b"\n", b"\r"):
                        needs_newline = True
                except OSError:
                    # 很小的文件之类，忽略
                    pass

        with open(file_path, "a", encoding="utf-8", errors="ignore") as f:
            if needs_newline:
                f.write("\n")
            f.write(text)

        print(f"[SmartCtrlV] 已追加 {len(text)} 字符到 {file_path}")
    except Exception as e:
        print(f"[SmartCtrlV] 追加写入失败 {file_path}: {e}")



def _infer_substitution(old_block: str, new_block: str):
    """
    尝试从 old_block -> new_block 的差异中，推断出一个简单的“子串替换”模式：
        old_sub -> new_sub

    用的是“最长公共前缀 + 最长公共后缀”思路，
    只要中间那坨不同，就当它是要替换的子串。

    推断失败返回 (None, None)。
    """
    if old_block == new_block:
        return None, None

    # 去掉首尾空白，避免纯缩进变化影响判断
    ob = old_block
    nb = new_block

    # 最长公共前缀
    prefix_len = 0
    min_len = min(len(ob), len(nb))
    while prefix_len < min_len and ob[prefix_len] == nb[prefix_len]:
        prefix_len += 1

    # 最长公共后缀（从尾巴往前数）
    suffix_len = 0
    while (
        suffix_len < (len(ob) - prefix_len)
        and suffix_len < (len(nb) - prefix_len)
        and ob[-(suffix_len + 1)] == nb[-(suffix_len + 1)]
    ):
        suffix_len += 1

    old_mid = ob[prefix_len: len(ob) - suffix_len if suffix_len > 0 else len(ob)]
    new_mid = nb[prefix_len: len(nb) - suffix_len if suffix_len > 0 else len(nb)]

    old_mid = old_mid.strip()
    new_mid = new_mid.strip()

    if not old_mid or not new_mid or old_mid == new_mid:
        return None, None

    # 太长的替换片段就算了，避免一整段都被当成“子串”
    if len(old_mid) > 64 or len(new_mid) > 64:
        return None, None

    return old_mid, new_mid


def _infer_substitution(old_block: str, new_block: str):
    """
    尝试从 old_block -> new_block 的差异中，推断出一个简单的“子串替换”模式：
        old_sub -> new_sub
    用最长公共前缀 + 最长公共后缀的方式。
    推断失败返回 (None, None)。
    """
    if old_block == new_block:
        return None, None

    ob = old_block
    nb = new_block

    # 最长公共前缀
    prefix_len = 0
    min_len = min(len(ob), len(nb))
    while prefix_len < min_len and ob[prefix_len] == nb[prefix_len]:
        prefix_len += 1

    # 最长公共后缀
    suffix_len = 0
    while (
        suffix_len < (len(ob) - prefix_len)
        and suffix_len < (len(nb) - prefix_len)
        and ob[-(suffix_len + 1)] == nb[-(suffix_len + 1)]
    ):
        suffix_len += 1

    old_mid = ob[prefix_len: len(ob) - suffix_len if suffix_len > 0 else len(ob)]
    new_mid = nb[prefix_len: len(nb) - suffix_len if suffix_len > 0 else len(nb)]

    old_mid = old_mid.strip()
    new_mid = new_mid.strip()

    if not old_mid or not new_mid or old_mid == new_mid:
        return None, None

    # 片段太长就算了，避免一整段被当成“子串”
    if len(old_mid) > 64 or len(new_mid) > 64:
        return None, None

    return old_mid, new_mid


def apply_patch_to_file(file_path: str, old_block: str, new_block: str) -> bool:
    """
    在 file_path 里将 old_block 替换成 new_block，支持：
      - 一改一：旧块只出现一次 -> 换这一处
      - 多改多：旧块出现多次 -> 用户选择只改第一个 / 全部替换
      - 多改一：如果推断出“子串替换模式”（比如 print -> logger.info），
                可选择在整个文件中对子串做全局替换

    额外处理：
      - 自动对齐 Windows 文件的换行符(\r\n) 与 AI 文本中的(\n)，避免匹配不到。
      - 任何写入前都会先生成 .bak 备份。
    """
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception as e:
        print(f"[AI Patch] 读取文件失败: {file_path}, {e}")
        return False

    # ---------- 检测文件的换行风格，并对齐 old/new block ----------

    if "\r\n" in content:
        newline = "\r\n"
    elif "\n" in content:
        newline = "\n"
    else:
        newline = os.linesep  # 极少数奇怪文件，退回系统默认

    # 把 old_block/new_block 中的换行统一换成文件的换行风格
    ob_norm = old_block.replace("\r\n", "\n").replace("\n", newline)
    nb_norm = new_block.replace("\r\n", "\n").replace("\n", newline)

    # ---------- 先尝试推断“子串替换模式”（多改一） ----------

    old_sub, new_sub = _infer_substitution(old_block, new_block)
    use_substitution = False

    if old_sub and new_sub:
        sub_count = content.count(old_sub)
        if sub_count > 1:
            def _preview(s: str, max_len: int = 40):
                s = s.replace("\r", "\\r").replace("\n", "\\n")
                if len(s) > max_len:
                    return s[:max_len] + "..."
                return s

            msg = (
                "检测到这次修改很像“子串全局替换”：\n\n"
                f"  原子串: '{_preview(old_sub)}'\n"
                f"  新子串: '{_preview(new_sub)}'\n\n"
                f"该子串在整个文件中出现了 {sub_count} 次。\n\n"
                "是否要在整个文件中对这个子串进行全局替换？\n\n"
                "是(Y): 在整个文件中把所有原子串替换为新子串（多改一）\n"
                "否(N): 不做子串全局替换，只对旧代码块做补丁替换\n"
                "取消: 取消本次修改，不改动文件"
            )
            title = "SmartCtrlV - 子串替换模式（多改一）"

            res = win32api.MessageBox(
                0,
                msg,
                title,
                win32con.MB_YESNOCANCEL | win32con.MB_ICONQUESTION
            )

            if res == win32con.IDCANCEL:
                print("[AI Patch] 用户取消了子串替换/补丁操作。")
                return False
            elif res == win32con.IDYES:
                use_substitution = True
            else:
                use_substitution = False

    # ---------- 分支 A：用户选择“子串全局替换”（多改一） ----------

    if use_substitution and old_sub and new_sub:
        new_content = content.replace(old_sub, new_sub)
        print("[AI Patch] 按“多改一”模式，对整个文件做子串全局替换。")

    else:
        # ---------- 分支 B：按“代码块补丁”处理（一改一 / 多改多） ----------

        block_count = content.count(ob_norm)
        if block_count == 0:
            print("[AI Patch] 文件中没有找到要替换的旧代码块。（可能是缩进或内容不完全一致）")
            return False

        if block_count == 1:
            # 一改一：只出现一次，直接替换这一处
            new_content = content.replace(ob_norm, nb_norm, 1)
            print("[AI Patch] 旧代码块在文件中仅出现一次，按“一改一”模式替换。")
        else:
            # 多改多：旧块出现多次，让用户选择
            msg = (
                "检测到旧代码块在文件中出现了多次。\n\n"
                f"出现次数: {block_count}\n\n"
                "你想如何应用这次补丁？\n\n"
                "是(Y): 只替换第一个匹配（1 改 1）\n"
                f"否(N): 替换全部 {block_count} 处（多改多）\n"
                "取消: 不进行任何修改"
            )
            title = "SmartCtrlV - 代码块补丁（多改多）"

            res = win32api.MessageBox(
                0,
                msg,
                title,
                win32con.MB_YESNOCANCEL | win32con.MB_ICONQUESTION
            )

            if res == win32con.IDCANCEL:
                print("[AI Patch] 用户取消了多处补丁操作。")
                return False
            elif res == win32con.IDYES:
                new_content = content.replace(ob_norm, nb_norm, 1)
                print("[AI Patch] 用户选择“只改第一个”（1 改 1）。")
            else:
                new_content = content.replace(ob_norm, nb_norm)
                print(f"[AI Patch] 用户选择“全部替换”（多改多，{block_count} 处）。")

    # ---------- 写回文件（带备份） ----------

    backup_path = file_path + ".bak"
    try:
        shutil.copyfile(file_path, backup_path)
        print(f"[AI Patch] 已创建备份文件: {backup_path}")
    except Exception as e:
        print(f"[AI Patch] 创建备份失败: {e}，但仍尝试写入。")

    try:
        with open(file_path, "w", encoding="utf-8", errors="ignore") as f:
            f.write(new_content)
        print(f"[AI Patch] 已成功将补丁/替换应用到: {file_path}")
        return True
    except Exception as e:
        print(f"[AI Patch] 写入文件失败: {e}")
        return False



# ---------- Ctrl+V：Explorer 中的智能行为 ----------

def simulate_native_ctrl_v():
    keyboard.send("ctrl+v")


def on_ctrl_v_explorer():
    """
    在资源管理器里的 Ctrl+V 智能行为：
    1) 如果选中单个文本文件 & 剪贴板是普通文本：
         -> 弹确认框：覆盖 / 追加 / 取消
    2) 否则：
         -> 如果文本像命令：在当前目录打开 cmd 执行
         -> 如果文本像文件名列表：按行创建文件
         -> 其他情况：忽略（防止几千行代码乱搞）
    """
    global is_simulating
    if not CONFIG.get("explorer", {}).get("enabled", True):
        # 不接管，直接让系统原生 Ctrl+V 生效
        is_simulating = True
        simulate_native_ctrl_v()
        is_simulating = False
        return
    if is_simulating:
        return

    # Alt + Ctrl + V：强制原生粘贴（逃生键）
    if keyboard.is_pressed("alt"):
        is_simulating = True
        simulate_native_ctrl_v()
        is_simulating = False
        return

    exe_path, hwnd = get_foreground_exe_path_and_hwnd()
    if not exe_path or not hwnd:
        is_simulating = True
        simulate_native_ctrl_v()
        is_simulating = False
        return

    exe_lower = exe_path.lower()

    # 非 explorer：直接原生粘贴
    if "explorer.exe" not in exe_lower:
        is_simulating = True
        simulate_native_ctrl_v()
        is_simulating = False
        return

    # Explorer 中的输入框（重命名 / 地址栏 / 搜索框）：不接管
    if is_explorer_text_input_focused():
        is_simulating = True
        simulate_native_ctrl_v()
        is_simulating = False
        return

    # 剪贴板是文件（复制文件/文件夹）：不接管
    if is_clipboard_file_drop():
        is_simulating = True
        simulate_native_ctrl_v()
        is_simulating = False
        return

    # 先拿剪贴板文本
    try:
        text = pyperclip.paste()
    except Exception:
        text = ""

    text = (text or "").strip()
    if not text:
        # 没文本就退回原生行为
        is_simulating = True
        simulate_native_ctrl_v()
        is_simulating = False
        return

    # ========= ① 优先检查：是否选中了单个“文本文件” =========
    selected = get_explorer_selected_files(hwnd) or []
    if ENABLE_EXPLORER_WRITE_FILE and len(selected) == 1:
        file_path = selected[0]
        if os.path.isfile(file_path):
            _, ext = os.path.splitext(file_path)
            ext = ext.lower()

            if ext in TEXT_EXT_WHITELIST:
                # 选中文本文件时，无论内容长什么样，都按“写入文件”处理（由用户确认）
                mode = confirm_write_to_file(hwnd, file_path, len(text))
                if mode is None:
                    # 用户点取消 -> 什么都不做（最安全）
                    return
                write_text_to_file(file_path, text, mode)
                return

    # ========= ② 没有合适的“选中文本文件”，走原来的逻辑 =========

    # 获取当前文件夹
    folder = get_explorer_folder_path(hwnd)
    if not folder:
        is_simulating = True
        simulate_native_ctrl_v()
        is_simulating = False
        return

    # 像命令 -> 在该目录开 cmd 执行
    if ENABLE_EXPLORER_COMMAND and is_probable_shell_command(text):
        run_shell_command_in_folder(folder, text)
        return

    # 像文件名列表 -> 创建空文件（只有“像文件名”的行才会建）
    if ENABLE_EXPLORER_CREATE_FILES and looks_like_filename_list(text):
        print(f"[SmartCtrlV] 在 {folder} 用剪贴板文本创建文件...")
        create_empty_files_by_clipboard_text(folder, text)
        return

    # 其他情况（例如几千行代码）：为了安全，什么都不做
    print("[SmartCtrlV] 剪贴板文本既不像命令，也不像文件名列表，忽略。")
    # 如果你希望这里退回“原生 Ctrl+V”，可以改成：
    # is_simulating = True
    # simulate_native_ctrl_v()
    # is_simulating = False


def on_ai_smart_paste():
    """
    AI 智能粘贴（安全精简版）：

    1）在资源管理器里：
        - 如果选中了文件/文件夹：不做任何 AI 特殊处理，直接当普通 Ctrl+V 用
          （也就是说：不再尝试自动 patch / 自动写入现有文件）
        - 如果没选中任何东西（只是当前文件夹空白处）：
            * plan.files 有内容：在当前目录创建对应文件并写入内容
            * plan.commands 有内容：在当前目录打开 cmd 并执行这些命令
            * 否则：退回 on_ctrl_v_explorer（你原来的“命令 / 文件名列表 / 忽略”逻辑）

    2）在终端里（cmd / powershell / Windows Terminal）：
        - 如果识别出了 commands，只把 commands 粘进去
        - 否则正常 Ctrl+V

    3）在代码编辑器里（VS Code / PyCharm / notepad 等）：
        - 如果识别到了 code_blocks，只粘最后一个代码块（一般是“新代码”）
        - 否则正常 Ctrl+V

    4）其他应用：普通 Ctrl+V
    """
    # 1. 读剪贴板
    try:
        raw = pyperclip.paste()
    except Exception:
        raw = ""

    raw = (raw or "").strip()
    if not raw:
        keyboard.send("ctrl+v")
        return

    # 2. 当前前台进程
    exe_path, hwnd = get_foreground_exe_path_and_hwnd()
    if not exe_path or not hwnd:
        keyboard.send("ctrl+v")
        return

    exe_lower = exe_path.lower()
    exe_name = os.path.basename(exe_lower)

    # 3. 统一跑一遍“假 AI 解析”
    plan = fake_ai_analyze_clipboard(raw)
    files = plan.get("files") or []
    commands = plan.get("commands") or []
    code_blocks = plan.get("code_blocks") or []

    print("[AI Paste] plan:", plan)

    # ========= 场景 A：终端（一键只粘命令） =========
    terminal_exes = ["cmd.exe", "powershell.exe", "wt.exe", "windowsterminal.exe"]
    if exe_name in terminal_exes:
        if commands:
            cmd_text = "\n".join(commands)
            pyperclip.copy(cmd_text)
            keyboard.send("ctrl+v")
            return
        else:
            keyboard.send("ctrl+v")
            return

    # ========= 场景 B：代码编辑器（一键只粘代码） =========
    editor_exes = [
        "code.exe",         # VS Code
        "notepad.exe",
        "notepad++.exe",
        "pycharm64.exe",
        "pycharm.exe",
        "idea64.exe",
    ]
    if exe_name in editor_exes:
        if code_blocks:
            # 一般最后一个 code block 是“改完之后”的版本
            pyperclip.copy(code_blocks[-1])
            keyboard.send("ctrl+v")
            return
        else:
            keyboard.send("ctrl+v")
            return

    # ========= 场景 C：资源管理器 =========
    if "explorer.exe" in exe_lower:
        # 输入框内（重命名/搜索/地址栏）：别抢
        if is_explorer_text_input_focused():
            keyboard.send("ctrl+v")
            return

        # 剪贴板是文件（复制文件/文件夹）：别抢
        if is_clipboard_file_drop():
            keyboard.send("ctrl+v")
            return

        folder = get_explorer_folder_path(hwnd)
        if not folder:
            # 拿不到当前目录，就退回原有智能 Ctrl+V
            on_ctrl_v_explorer()
            return

        selected = get_explorer_selected_files(hwnd) or []

        # 1）如果有选中的文件/文件夹：不做 AI 特殊操作，直接退回你原本的 Ctrl+V 逻辑
        if selected:
            on_ctrl_v_explorer()
            return

        # 2）没有选中任何条目：可以认为是在“空白处”AI 粘贴
        #   - 创建文件并写入内容
        if files:
            for f in files:
                name = (f.get("name") or "").strip()
                content = f.get("content") or ""
                if not name or not looks_like_filename(name):
                    continue

                base, ext = os.path.splitext(name)
                candidate = os.path.join(folder, base + ext)
                index = 1
                while os.path.exists(candidate):
                    candidate_name = f"{base} ({index}){ext}"
                    candidate = os.path.join(folder, candidate_name)
                    index += 1

                # 这里直接覆盖写入，因为是“新创建”的文件
                write_text_to_file(candidate, content, mode="overwrite")

            return

        #   - 没有 files，但有命令：在该目录开 cmd 执行
        if commands:
            cmd_text = "\n".join(commands)
            run_shell_command_in_folder(folder, cmd_text)
            return

        #   - 既不是创建文件，也不是命令：退回你原来的智能 Ctrl+V 行为
        on_ctrl_v_explorer()
        return

    # ========= 场景 D：其他应用 =========
    keyboard.send("ctrl+v")


    # ========== 场景 2：目录模式 ==========

    # 2-1 有 files：在当前目录创建这些文件并写入内容
    if ENABLE_EXPLORER_CREATE_FILES and files:
        for f in files:
            name = (f.get("name") or "").strip()
            content = f.get("content") or ""
            if not name or not looks_like_filename(name):
                continue

            base, ext = os.path.splitext(name)
            candidate = os.path.join(folder, base + ext)
            index = 1
            while os.path.exists(candidate):
                candidate_name = f"{base} ({index}){ext}"
                candidate = os.path.join(folder, candidate_name)
                index += 1

            write_text_to_file(candidate, content, mode="overwrite")

        return

    # 2-2 有 commands：在当前目录开 cmd 执行
    if ENABLE_EXPLORER_COMMAND and commands:
        cmd_text = "\n".join(commands)
        run_shell_command_in_folder(folder, cmd_text)
        return

    # 2-3 兜底：退回你原来的 Explorer 智能逻辑（命令/文件名列表判断）
    on_ctrl_v_explorer()





def on_ctrl_shift_v_explorer():
    """
    Ctrl+Shift+V：
    - 在 Explorer 且选中单个文本文件时：
        把剪贴板文本“追加写入”该文件
    - 否则：退回原生 Ctrl+V
    """
    global is_simulating

    exe_path, hwnd = get_foreground_exe_path_and_hwnd()
    if not exe_path or not hwnd:
        is_simulating = True
        simulate_native_ctrl_v()
        is_simulating = False
        return

    exe_lower = exe_path.lower()
    if "explorer.exe" not in exe_lower:
        # 非资源管理器：走原生 Ctrl+V
        is_simulating = True
        simulate_native_ctrl_v()
        is_simulating = False
        return

    # 取选中文件列表
    selected = get_explorer_selected_files(hwnd) or []
    if len(selected) != 1:
        is_simulating = True
        simulate_native_ctrl_v()
        is_simulating = False
        return

    file_path = selected[0]

    # 选中的是文件夹？那就别乱动
    if os.path.isdir(file_path):
        is_simulating = True
        simulate_native_ctrl_v()
        is_simulating = False
        return

    _, ext = os.path.splitext(file_path)
    ext = ext.lower()

    # 扩展名不在文本白名单 -> 不乱写
    if ext not in TEXT_EXT_WHITELIST:
        print(f"[SmartCtrlV] {file_path} 扩展名 {ext} 不在文本白名单，退回原生粘贴。")
        is_simulating = True
        simulate_native_ctrl_v()
        is_simulating = False
        return

    # 获取剪贴板文本
    try:
        text = pyperclip.paste()
    except Exception:
        text = ""

    if not text:
        print("[SmartCtrlV] 剪贴板为空或不是文本，退回原生粘贴。")
        is_simulating = True
        simulate_native_ctrl_v()
        is_simulating = False
        return

    # 真正追加写入
    append_text_to_file(file_path, text)
    # 不执行原生 Ctrl+V



# ========= 多格式粘贴 菜单（Ctrl+Alt+V） =========

# 白名单：哪些进程可以弹菜单
WHITELIST_ENABLED = CONFIG["menu"]["whitelist_enabled"]
WHITELIST_PROCESSES = [
    p.lower() for p in CONFIG["menu"]["whitelist_processes"]
]

def get_foreground_exe_name():
    """获取当前前台窗口的 exe 文件名（小写），失败返回 None"""
    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return None, None

    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        h_process = win32api.OpenProcess(
            win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ,
            False,
            pid,
        )
    except Exception:
        return None, hwnd

    try:
        exe_path = win32process.GetModuleFileNameEx(h_process, 0)
    except Exception:
        exe_path = None
    finally:
        win32api.CloseHandle(h_process)

    if not exe_path:
        return None, hwnd

    exe_name = os.path.basename(exe_path).lower()
    return exe_name, hwnd


def close_menu():
    """关闭菜单窗口"""
    global menu_window, root, menu_visible
    if menu_window is not None:
        try:
            menu_window.destroy()
        except Exception:
            pass
        menu_window = None
    if root is not None:
        try:
            root.quit()
        except Exception:
            pass
    menu_visible = False


def raw_paste_menu():
    global last_foreground_hwnd
    print("[MultiPaste] 模式：原样粘贴")
    close_menu()
    focus_window(last_foreground_hwnd)
    keyboard.send("ctrl+v")


def plain_text_paste():
    global last_foreground_hwnd
    print("[MultiPaste] 模式：纯文本粘贴")
    text = pyperclip.paste()
    if text is None:
        text = ""
    pyperclip.copy(text)
    close_menu()
    focus_window(last_foreground_hwnd)
    keyboard.send("ctrl+v")


# ---- 结构化格式化 ----

def try_format_json(text: str):
    try:
        data = json.loads(text)
        return json.dumps(data, indent=2, ensure_ascii=False)
    except Exception:
        return None


def try_format_xml_or_html(text: str):
    t = text.strip()
    if not (t.startswith("<") and t.endswith(">")):
        return None
    try:
        dom = minidom.parseString(text)
        pretty = dom.toprettyxml(indent="  ")
        return pretty
    except Exception:
        return None


def try_format_sql(text: str):
    lower = text.lower()
    if "select" not in lower:
        return None

    keywords = [
        "select", "from", "where", "group by", "order by", "having",
        "join", "left join", "right join", "inner join", "outer join",
        "limit", "offset"
    ]

    formatted = " " + text
    for kw in keywords:
        pattern = r"(?i)\s(" + re.escape(kw) + r")\b"
        formatted = re.sub(pattern, r"\n\1", formatted)

    return formatted.strip()


def structured_format_paste():
    global last_foreground_hwnd
    print("[MultiPaste] 模式：结构化格式化粘贴")
    text = pyperclip.paste()
    if not text:
        close_menu()
        focus_window(last_foreground_hwnd)
        keyboard.send("ctrl+v")
        return

    formatted = try_format_json(text)
    if formatted is None:
        formatted = try_format_xml_or_html(text)
    if formatted is None:
        formatted = try_format_sql(text)

    if formatted is not None:
        pyperclip.copy(formatted)
    else:
        print("[MultiPaste] 结构化格式化：无法识别类型，保持原样")

    close_menu()
    focus_window(last_foreground_hwnd)
    keyboard.send("ctrl+v")


# ---- 去空行 ----

def collapse_blank_lines(text: str) -> str:
    lines = text.splitlines()
    new_lines = [line for line in lines if line.strip() != ""]
    return "\n".join(new_lines)

def cleanup_markdown(text: str) -> str:
    """
    简单 Markdown 清理：
    - 去掉标题前缀 #, ##, ...
    - 去掉列表前缀 -, *, +, 1. 2. ...
    - 去掉引用前缀 >
    - 去掉 ``` 这类代码块围栏，但保留代码内容
    """
    lines = text.splitlines()
    new_lines = []
    in_code_block = False

    for line in lines:
        stripped = line.lstrip()

        # 代码块围栏 ```xxx
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            # 代码块的围栏本身丢掉，不加入 new_lines
            continue

        if in_code_block:
            # 代码块内部原样保留
            new_lines.append(line)
            continue

        # 引用前缀 >
        if stripped.startswith(">"):
            stripped = stripped[1:].lstrip()

        # 标题 #, ##, ### ...
        if re.match(r"^#{1,6}\s+", stripped):
            stripped = re.sub(r"^#{1,6}\s+", "", stripped)

        # 无序列表 -, *, +
        if re.match(r"^[-*+]\s+", stripped):
            stripped = re.sub(r"^[-*+]\s+", "", stripped)

        # 有序列表 1. 2. 3.
        if re.match(r"^\d+\.\s+", stripped):
            stripped = re.sub(r"^\d+\.\s+", "", stripped)

        new_lines.append(stripped)

    return "\n".join(new_lines)


def markdown_cleanup_paste():
    """
    Markdown 清理后粘贴：
    - 适合从 AI 聊天窗口复制整段回答，再贴到笔记/Word/代码注释里
    """
    global last_foreground_hwnd

    print("[MultiPaste] 模式：Markdown 清理粘贴")
    text = pyperclip.paste()
    if not text:
        close_menu()
        focus_window(last_foreground_hwnd)
        keyboard.send("ctrl+v")
        return

    cleaned = cleanup_markdown(text)
    pyperclip.copy(cleaned)

    close_menu()
    focus_window(last_foreground_hwnd)
    keyboard.send("ctrl+v")


def collapse_blank_paste():
    global last_foreground_hwnd
    print("[MultiPaste] 模式：去所有空行粘贴")
    text = pyperclip.paste()
    if not text:
        close_menu()
        focus_window(last_foreground_hwnd)
        keyboard.send("ctrl+v")
        return
    cleaned = collapse_blank_lines(text)
    pyperclip.copy(cleaned)
    close_menu()
    focus_window(last_foreground_hwnd)
    keyboard.send("ctrl+v")


# ---- Python 缩进整理 ----

def python_dedent_paste():
    global last_foreground_hwnd
    print("[MultiPaste] 模式：Python 缩进整理粘贴")
    text = pyperclip.paste()
    if not text:
        close_menu()
        focus_window(last_foreground_hwnd)
        keyboard.send("ctrl+v")
        return
    dedented = textwrap.dedent(text)
    pyperclip.copy(dedented)
    close_menu()
    focus_window(last_foreground_hwnd)
    keyboard.send("ctrl+v")


# ---- 鼠标点击监控 ----

def is_descendant(child_hwnd, parent_hwnd):
    if not child_hwnd or not parent_hwnd:
        return False
    h = child_hwnd
    while h:
        if h == parent_hwnd:
            return True
        h = win32gui.GetParent(h)
    return False


def mouse_click_watcher():
    global menu_visible, menu_window

    while True:
        mouse.wait(button="left", target_types=("down",))
        if not menu_visible or menu_window is None:
            return

        x, y = win32api.GetCursorPos()
        clicked_hwnd = win32gui.WindowFromPoint((x, y))

        try:
            menu_hwnd = menu_window.winfo_id()
        except Exception:
            return

        if is_descendant(clicked_hwnd, menu_hwnd):
            continue

        close_menu()
        return


def focus_window(hwnd):
    try:
        if hwnd and win32gui.IsWindow(hwnd):
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.05)
    except Exception:
        pass


def create_menu_window():
    """在鼠标旁边创建菜单窗口（带屏幕边缘避让 + 根据配置/语言生成菜单）"""
    global menu_window, root, menu_visible

    close_menu()

    # 鼠标位置
    x, y = win32api.GetCursorPos()

    root = tk.Tk()
    root.withdraw()
    win = tk.Toplevel(root)
    menu_window = win
    menu_visible = True

    # 外层背景稍微深一点，当假“阴影”
    win.overrideredirect(True)
    win.attributes("-topmost", True)
    win.configure(bg="#111111")

    # 内层主容器，圆角做不了，只能靠 padding+颜色假装一下…
    container = tk.Frame(win, bg="#252525", bd=1, relief="solid")
    container.pack(fill="both", expand=True, padx=2, pady=2)

    # ===== 1. 多语言标签 =====
    lang = get_ui_lang()
    labels_table = {
        "zh": {
            "title": "SmartCtrlV 多格式粘贴",
            "subtitle": "选择一种粘贴方式：",
            "raw": "🧷 原样粘贴",
            "plain": "📄 纯文本粘贴",
            "markdown": "🧹 Markdown 清理粘贴",
            "structured": "🧩 结构化格式化 (JSON/XML/HTML/SQL)",
            "collapse_blank": "📏 去所有空行粘贴",
            "python_dedent": "🐍 Python 缩进整理粘贴",
        },
        "ja": {
            "title": "SmartCtrlV マルチペースト",
            "subtitle": "貼り付けモードを選択：",
            "raw": "🧷 そのまま貼り付け",
            "plain": "📄 プレーンテキストで貼り付け",
            "markdown": "🧹 Markdown 整形貼り付け",
            "structured": "🧩 構造化フォーマット (JSON/XML/HTML/SQL)",
            "collapse_blank": "📏 空行をすべて削除して貼り付け",
            "python_dedent": "🐍 Python インデント整理貼り付け",
        },
        "en": {
            "title": "SmartCtrlV Multi-Paste",
            "subtitle": "Choose how to paste:",
            "raw": "🧷 Raw paste",
            "plain": "📄 Plain text paste",
            "markdown": "🧹 Markdown cleanup paste",
            "structured": "🧩 Structured format (JSON/XML/HTML/SQL)",
            "collapse_blank": "📏 Remove all blank lines",
            "python_dedent": "🐍 Python dedent paste",
        },
    }
    labels = labels_table.get(lang, labels_table["en"])

    # ===== 顶部标题区域 =====
    title_label = tk.Label(
        container,
        text=labels["title"],
        bg="#252525",
        fg="#ffffff",
        anchor="w",
        font=("Segoe UI", 10, "bold"),
        pady=3,
    )
    title_label.pack(fill="x", padx=10, pady=(6, 0))

    subtitle_label = tk.Label(
        container,
        text=labels["subtitle"],
        bg="#252525",
        fg="#bbbbbb",
        anchor="w",
        font=("Segoe UI", 8),
        pady=2,
    )
    subtitle_label.pack(fill="x", padx=10, pady=(0, 4))

    # 分隔线
    sep = tk.Frame(container, height=1, bg="#3a3a3a")
    sep.pack(fill="x", padx=6, pady=(0, 4))

    # ===== 2. 从配置里读菜单项开关 =====
    menu_cfg = CONFIG.get("menu", {})
    opts = menu_cfg.get("options", {})

    # 按钮统一样式
    def add_button(text, command):
        btn = tk.Button(
            container,
            text=text,
            command=command,
            relief="flat",
            bg="#333333",
            fg="#ffffff",
            activebackground="#555555",
            activeforeground="#ffffff",
            padx=12,
            pady=4,
            anchor="w",
            bd=0,
            font=("Segoe UI", 9),
        )
        btn.pack(fill="x", padx=6, pady=2)

        # hover 效果
        def on_enter(e):
            btn.configure(bg="#444444")

        def on_leave(e):
            btn.configure(bg="#333333")

        btn.bind("<Enter>", on_enter)
        btn.bind("<Leave>", on_leave)

    # 根据 options 决定是否添加按钮（默认都 True，这样旧配置也能用）
    if opts.get("raw", True):
        add_button(labels["raw"], raw_paste_menu)
    if opts.get("plain", True):
        add_button(labels["plain"], plain_text_paste)
    if opts.get("markdown", True):
        add_button(labels["markdown"], markdown_cleanup_paste)
    if opts.get("structured", True):
        add_button(labels["structured"], structured_format_paste)
    if opts.get("collapse_blank", True):
        add_button(labels["collapse_blank"], collapse_blank_paste)
    if opts.get("python_dedent", True):
        add_button(labels["python_dedent"], python_dedent_paste)

    def on_escape(event):
        close_menu()

    win.bind("<Escape>", on_escape)

    win.update_idletasks()
    width = win.winfo_width()
    height = win.winfo_height()

    # 屏幕尺寸
    screen_width = win32api.GetSystemMetrics(0)
    screen_height = win32api.GetSystemMetrics(1)

    # 默认右下
    pos_x = x + 10
    pos_y = y + 10

    # 右边缘
    if pos_x + width > screen_width:
        pos_x = x - width - 10

    # 下边缘
    if pos_y + height > screen_height:
        pos_y = y - height - 10

    if pos_x < 0:
        pos_x = 0
    if pos_y < 0:
        pos_y = 0

    win.geometry(f"{width}x{height}+{pos_x}+{pos_y}")

    t = threading.Thread(target=mouse_click_watcher, daemon=True)
    t.start()

    root.mainloop()


def on_hotkey_menu():
    """Ctrl+Alt+V 菜单入口"""
    """Ctrl+Alt+V 菜单入口"""
    global last_foreground_hwnd

    # ⭐ 每次打开菜单前重新加载配置，让 options 的修改立即生效
    load_config()
    _apply_config_from_dict(CONFIG)

    print("[MultiPaste] on_hotkey_menu TRIGGERED")  # 调试用
    exe_name, hwnd = get_foreground_exe_name()
    last_foreground_hwnd = hwnd

    # 总开关：配置里可以关掉整个多格式菜单
    if not CONFIG.get("menu", {}).get("enabled", True):
        # 直接当普通 Ctrl+V 用
        keyboard.send("ctrl+v")
        return

    # 白名单逻辑
    if WHITELIST_ENABLED:
        if not exe_name or exe_name not in WHITELIST_PROCESSES:
            # 不在白名单里 -> 退回普通粘贴
            focus_window(last_foreground_hwnd)
            keyboard.send("ctrl+v")
            return

    # 通过线程启动 Tk 窗口，避免卡主当前线程
    t = threading.Thread(target=create_menu_window, daemon=True)
    t.start()


# ========= main =========

# ========= 从这里开始替换原来的 main / start_hooks / stop_hooks 等 =========

def _apply_config_from_dict(new_cfg: dict):
    """
    把配置 dict 应用到当前模块的 CONFIG 上，
    并同步更新一些用作“开关”的全局变量（包括白名单）。
    """
    global CONFIG
    # 先从默认配置深拷贝一份，再叠加新的，防止缺项 KeyError
    cfg = json.loads(json.dumps(CONFIG_DEFAULT))
    deep_update_dict(cfg, new_cfg)
    CONFIG = cfg

    # 同步 explorer 开关
    global ENABLE_EXPLORER_COMMAND, ENABLE_EXPLORER_CREATE_FILES, ENABLE_EXPLORER_WRITE_FILE
    ENABLE_EXPLORER_COMMAND = CONFIG["explorer"]["enable_command_from_clipboard"]
    ENABLE_EXPLORER_CREATE_FILES = CONFIG["explorer"]["enable_create_files_from_clipboard"]
    ENABLE_EXPLORER_WRITE_FILE = CONFIG["explorer"]["enable_write_file_from_clipboard"]

    # 同步多格式菜单白名单相关
    global WHITELIST_ENABLED, WHITELIST_PROCESSES
    WHITELIST_ENABLED = CONFIG["menu"]["whitelist_enabled"]
    WHITELIST_PROCESSES = [p.lower() for p in CONFIG["menu"]["whitelist_processes"]]

def open_global_settings_window():
    """
    全局设置窗口：
      - 修改 Explorer 增强 Ctrl+V 热键 (CONFIG['hotkeys']['explorer_ctrl_v'])
      - 修改 多格式菜单 热键 (CONFIG['menu']['hotkey'])
    由托盘右键菜单调用即可。
    """
    # 用一个独立的 Tk root，避免和菜单那个 root 搞混
    settings_root = tk.Tk()
    settings_root.title("SmartCtrlV 设置")
    settings_root.attributes("-topmost", True)
    settings_root.configure(bg="#202020")

    # 读取当前配置
    explorer_hotkey_current = CONFIG.get("hotkeys", {}).get("explorer_ctrl_v", "ctrl+v")
    menu_hotkey_current = CONFIG.get("menu", {}).get("hotkey", "ctrl+alt+v")

    explorer_var = tk.StringVar(value=explorer_hotkey_current)
    menu_var = tk.StringVar(value=menu_hotkey_current)

    # 简单的状态 -> 文本映射
    lang_ui = get_ui_lang()
    texts = {
        "zh": {
            "title": "SmartCtrlV 设置",
            "explorer_label": "资源管理器增强粘贴快捷键（默认 Ctrl+V）：",
            "menu_label": "多格式粘贴菜单快捷键（默认 Ctrl+Alt+V）：",
            "current": "当前：",
            "change": "更改...",
            "capture_tip": "请按下新的快捷键组合，例如：Ctrl+Alt+P",
            "save": "保存并生效",
            "cancel": "取消",
            "conflict_title": "快捷键冲突",
            "conflict_msg": "两个功能不能使用同一个快捷键，请修改其中一个。",
        },
        "ja": {
            "title": "SmartCtrlV 設定",
            "explorer_label": "エクスプローラー拡張貼り付けショートカット（デフォルト Ctrl+V）：",
            "menu_label": "マルチペーストメニューショートカット（デフォルト Ctrl+Alt+V）：",
            "current": "現在：",
            "change": "変更...",
            "capture_tip": "新しいショートカットを押してください（例：Ctrl+Alt+P）",
            "save": "保存して反映",
            "cancel": "キャンセル",
            "conflict_title": "ショートカットの衝突",
            "conflict_msg": "2つの機能に同じショートカットは使用できません。",
        },
        "en": {
            "title": "SmartCtrlV Settings",
            "explorer_label": "Explorer enhanced paste hotkey (default Ctrl+V):",
            "menu_label": "Multi-paste menu hotkey (default Ctrl+Alt+V):",
            "current": "Current: ",
            "change": "Change...",
            "capture_tip": "Press the new hotkey combination, e.g. Ctrl+Alt+P",
            "save": "Save & apply",
            "cancel": "Cancel",
            "conflict_title": "Hotkey conflict",
            "conflict_msg": "The two features cannot use the same hotkey.",
        },
    }
    t = texts.get(lang_ui, texts["en"])
    settings_root.title(t["title"])

    # ==== 布局 ====
    main_frame = tk.Frame(settings_root, bg="#202020", padx=12, pady=12)
    main_frame.pack(fill="both", expand=True)

    def make_hotkey_row(parent, label_text, var):
        frame = tk.Frame(parent, bg="#202020")
        frame.pack(fill="x", pady=6)

        lbl = tk.Label(frame, text=label_text, bg="#202020", fg="#ffffff", anchor="w", justify="left", wraplength=420)
        lbl.pack(fill="x", side="top", anchor="w")

        sub = tk.Frame(frame, bg="#202020")
        sub.pack(fill="x", pady=(2, 0))

        cur_lbl = tk.Label(sub, text=f"{t['current']}{var.get()}", bg="#202020", fg="#aaaaaa")
        cur_lbl.pack(side="left")

        def capture_hotkey():
            cap = tk.Toplevel(settings_root)
            cap.title(label_text)
            cap.attributes("-topmost", True)
            cap.configure(bg="#202020")
            cap.grab_set()  # 模态

            info = tk.Label(cap, text=t["capture_tip"], bg="#202020", fg="#ffffff", wraplength=360, pady=10)
            info.pack(fill="x", padx=12, pady=(10, 0))

            show = tk.Label(cap, text="", bg="#202020", fg="#00ff99", font=("Segoe UI", 10, "bold"))
            show.pack(fill="x", padx=12, pady=(5, 12))

            pressed = {"ctrl": False, "shift": False, "alt": False}

            def on_key(event):
                # 记录修饰键状态
                ks = event.keysym.lower()
                if ks in ("control_l", "control_r", "control"):
                    pressed["ctrl"] = True
                    show.configure(text="Ctrl + ...")
                    return
                if ks in ("shift_l", "shift_r", "shift"):
                    pressed["shift"] = True
                    show.configure(text="Shift + ...")
                    return
                if ks in ("alt_l", "alt_r", "alt", "meta_l", "meta_r"):
                    pressed["alt"] = True
                    show.configure(text="Alt + ...")
                    return

                # 非纯修饰键：真正的快捷键键位
                mods = []
                if pressed["ctrl"] or (event.state & 0x4):
                    mods.append("ctrl")
                if pressed["shift"] or (event.state & 0x1):
                    mods.append("shift")
                # Alt 在 Tk 的 state 里不太统一，用上面 pressed 标志兜底
                if pressed["alt"]:
                    mods.append("alt")

                key = ks
                # 常规字母统一小写
                if len(key) == 1:
                    key = key.lower()

                # 防止只按一个字母，没有任何修饰键的情况也允许（比如 F8）
                combo = "+".join(mods + [key]) if mods else key

                var.set(combo)
                cur_lbl.configure(text=f"{t['current']}{var.get()}")
                cap.destroy()

            cap.bind("<KeyPress>", on_key)

            cap.update_idletasks()
            w = cap.winfo_width()
            h = cap.winfo_height()
            # 居中到父窗口
            px = settings_root.winfo_rootx() + (settings_root.winfo_width() - w) // 2
            py = settings_root.winfo_rooty() + (settings_root.winfo_height() - h) // 2
            cap.geometry(f"+{px}+{py}")

        btn = tk.Button(
            sub,
            text=t["change"],
            command=capture_hotkey,
            relief="flat",
            bg="#4caf50",
            fg="#ffffff",
            activebackground="#66bb6a",
            activeforeground="#ffffff",
            padx=8,
            pady=2,
        )
        btn.pack(side="right")

    # 两行：Explorer 热键 & 菜单热键
    make_hotkey_row(main_frame, t["explorer_label"], explorer_var)
    make_hotkey_row(main_frame, t["menu_label"], menu_var)

    # 底部按钮
    btn_frame = tk.Frame(main_frame, bg="#202020")
    btn_frame.pack(fill="x", pady=(12, 0))

    def on_save():
        hk_explorer = explorer_var.get().strip().lower() or "ctrl+v"
        hk_menu = menu_var.get().strip().lower() or "ctrl+alt+v"

        # 不能一样
        if hk_explorer == hk_menu:
            messagebox.showerror(t["conflict_title"], t["conflict_msg"])
            return

        # 写入 CONFIG
        CONFIG.setdefault("hotkeys", {})["explorer_ctrl_v"] = hk_explorer
        CONFIG.setdefault("menu", {})["hotkey"] = hk_menu

        # 保存到文件
        save_config()

        # 应用到当前进程 & 重新注册热键
        _apply_config_from_dict(CONFIG)
        stop_hooks()
        register_hotkeys_safe()

        settings_root.destroy()

    def on_cancel():
        settings_root.destroy()

    btn_ok = tk.Button(
        btn_frame,
        text=t["save"],
        command=on_save,
        relief="flat",
        bg="#4caf50",
        fg="#ffffff",
        activebackground="#66bb6a",
        activeforeground="#ffffff",
        padx=10,
        pady=4,
    )
    btn_ok.pack(side="left")

    btn_cancel = tk.Button(
        btn_frame,
        text=t["cancel"],
        command=on_cancel,
        relief="flat",
        bg="#555555",
        fg="#ffffff",
        activebackground="#777777",
        activeforeground="#ffffff",
        padx=10,
        pady=4,
    )
    btn_cancel.pack(side="left", padx=(8, 0))

    settings_root.update_idletasks()
    w = settings_root.winfo_width()
    h = settings_root.winfo_height()
    # 居中
    screen_w = settings_root.winfo_screenwidth()
    screen_h = settings_root.winfo_screenheight()
    px = (screen_w - w) // 2
    py = (screen_h - h) // 2
    settings_root.geometry(f"{w}x{h}+{px}+{py}")

    settings_root.mainloop()

def open_tray_settings_window():
    """
    托盘“设置”窗口：
      - 修改 Explorer 增强 Ctrl+V 热键 (CONFIG['hotkeys']['explorer_ctrl_v'])
      - 修改 多格式粘贴菜单热键 (CONFIG['menu']['hotkey'])
      - 切换 menu.enabled / menu.whitelist_enabled
      - 两个热键用“按键捕获”，不能相同
    """
    # 独立 root，避免跟别的 Tk 冲突
    root = tk.Tk()
    root.attributes("-topmost", True)
    root.configure(bg="#202020")

    lang_ui = get_ui_lang()
    texts = {
        "zh": {
            "title": "SmartCtrlV 设置",
            "explorer_label": "Explorer Ctrl+V 热键（资源管理器增强粘贴）：",
            "menu_group": "多格式粘贴菜单：",
            "menu_enable": "启用多格式粘贴菜单 (menu.enabled)",
            "menu_whitelist": "启用白名单 (menu.whitelist_enabled)",
            "menu_label": "菜单热键：",
            "current": "当前：",
            "change": "更改...",
            "capture_tip": "请按下新的快捷键组合，例如：Ctrl+Alt+P",
            "save": "保存并生效",
            "cancel": "取消",
            "conflict_title": "快捷键冲突",
            "conflict_msg": "两个功能不能使用同一个快捷键，请修改其中一个。",
        },
        "ja": {
            "title": "SmartCtrlV 設定",
            "explorer_label": "Explorer Ctrl+V ショートカット（エクスプローラー拡張貼り付け）：",
            "menu_group": "マルチペーストメニュー：",
            "menu_enable": "マルチペーストメニューを有効にする (menu.enabled)",
            "menu_whitelist": "ホワイトリストを有効にする (menu.whitelist_enabled)",
            "menu_label": "メニューショートカット：",
            "current": "現在：",
            "change": "変更...",
            "capture_tip": "新しいショートカットを押してください（例：Ctrl+Alt+P）",
            "save": "保存して反映",
            "cancel": "キャンセル",
            "conflict_title": "ショートカットの衝突",
            "conflict_msg": "2つの機能に同じショートカットは使用できません。",
        },
        "en": {
            "title": "SmartCtrlV Settings",
            "explorer_label": "Explorer Ctrl+V hotkey (enhanced paste in Explorer):",
            "menu_group": "Multi-paste menu:",
            "menu_enable": "Enable multi-paste menu (menu.enabled)",
            "menu_whitelist": "Enable whitelist (menu.whitelist_enabled)",
            "menu_label": "Menu hotkey:",
            "current": "Current: ",
            "change": "Change...",
            "capture_tip": "Press the new hotkey combination, e.g. Ctrl+Alt+P",
            "save": "Save & apply",
            "cancel": "Cancel",
            "conflict_title": "Hotkey conflict",
            "conflict_msg": "The two features cannot use the same hotkey.",
        },
    }
    t = texts.get(lang_ui, texts["en"])
    root.title(t["title"])

    # 当前配置
    explorer_hotkey_current = CONFIG.get("hotkeys", {}).get("explorer_ctrl_v", "ctrl+v")
    menu_hotkey_current = CONFIG.get("menu", {}).get("hotkey", "ctrl+alt+v")
    menu_enabled_current = CONFIG.get("menu", {}).get("enabled", True)
    menu_whitelist_current = CONFIG.get("menu", {}).get("whitelist_enabled", True)

    explorer_var = tk.StringVar(value=explorer_hotkey_current)
    menu_var = tk.StringVar(value=menu_hotkey_current)
    menu_enabled_var = tk.BooleanVar(value=menu_enabled_current)
    menu_whitelist_var = tk.BooleanVar(value=menu_whitelist_current)

    main = tk.Frame(root, bg="#202020", padx=12, pady=12)
    main.pack(fill="both", expand=True)

    # ---- 通用：一行“当前 + 更改” ----
    def make_hotkey_row(parent, label_text, var: tk.StringVar):
        frame = tk.Frame(parent, bg="#202020")
        frame.pack(fill="x", pady=6)

        lbl = tk.Label(
            frame,
            text=label_text,
            bg="#202020",
            fg="#ffffff",
            anchor="w",
            justify="left",
            wraplength=430,
        )
        lbl.pack(fill="x", side="top", anchor="w")

        sub = tk.Frame(frame, bg="#202020")
        sub.pack(fill="x", pady=(2, 0))

        cur_lbl = tk.Label(
            sub,
            text=f"{t['current']}{var.get()}",
            bg="#202020",
            fg="#aaaaaa",
        )
        cur_lbl.pack(side="left")

        def capture_hotkey():
            cap = tk.Toplevel(root)
            cap.title(label_text)
            cap.attributes("-topmost", True)
            cap.configure(bg="#202020")
            cap.grab_set()  # 模态

            info = tk.Label(
                cap,
                text=t["capture_tip"],
                bg="#202020",
                fg="#ffffff",
                wraplength=360,
                pady=10,
            )
            info.pack(fill="x", padx=12, pady=(10, 0))

            show = tk.Label(
                cap,
                text="",
                bg="#202020",
                fg="#00ff99",
                font=("Segoe UI", 10, "bold"),
            )
            show.pack(fill="x", padx=12, pady=(5, 12))

            pressed = {"ctrl": False, "shift": False, "alt": False}

            def on_key(event):
                ks = event.keysym.lower()

                # 记录修饰键
                if ks in ("control_l", "control_r", "control"):
                    pressed["ctrl"] = True
                    show.configure(text="Ctrl + ...")
                    return
                if ks in ("shift_l", "shift_r", "shift"):
                    pressed["shift"] = True
                    show.configure(text="Shift + ...")
                    return
                if ks in ("alt_l", "alt_r", "alt", "meta_l", "meta_r"):
                    pressed["alt"] = True
                    show.configure(text="Alt + ...")
                    return

                mods = []
                # Tk 的 state 里 0x4 基本是 Ctrl，0x1 是 Shift，Alt 比较混乱，用 pressed 兜底
                if pressed["ctrl"] or (event.state & 0x4):
                    mods.append("ctrl")
                if pressed["shift"] or (event.state & 0x1):
                    mods.append("shift")
                if pressed["alt"]:
                    mods.append("alt")

                key = ks
                if len(key) == 1:
                    key = key.lower()

                combo = "+".join(mods + [key]) if mods else key
                var.set(combo)
                cur_lbl.configure(text=f"{t['current']}{var.get()}")
                cap.destroy()

            cap.bind("<KeyPress>", on_key)

            cap.update_idletasks()
            w = cap.winfo_width()
            h = cap.winfo_height()
            px = root.winfo_rootx() + (root.winfo_width() - w) // 2
            py = root.winfo_rooty() + (root.winfo_height() - h) // 2
            cap.geometry(f"+{px}+{py}")

        btn = tk.Button(
            sub,
            text=t["change"],
            command=capture_hotkey,
            relief="flat",
            bg="#4caf50",
            fg="#ffffff",
            activebackground="#66bb6a",
            activeforeground="#ffffff",
            padx=8,
            pady=2,
        )
        btn.pack(side="right")

    # ---- Explorer Ctrl+V 行 ----
    make_hotkey_row(main, t["explorer_label"], explorer_var)

    # ---- 多格式菜单开关 ----
    group = tk.LabelFrame(
        main,
        text=t["menu_group"],
        bg="#202020",
        fg="#ffffff",
        padx=8,
        pady=6,
        labelanchor="n",
    )
    group.pack(fill="x", pady=(10, 4))

    chk1 = tk.Checkbutton(
        group,
        text=t["menu_enable"],
        variable=menu_enabled_var,
        bg="#202020",
        fg="#ffffff",
        selectcolor="#202020",
        activebackground="#202020",
        activeforeground="#ffffff",
    )
    chk1.pack(anchor="w", pady=2)

    chk2 = tk.Checkbutton(
        group,
        text=t["menu_whitelist"],
        variable=menu_whitelist_var,
        bg="#202020",
        fg="#ffffff",
        selectcolor="#202020",
        activebackground="#202020",
        activeforeground="#ffffff",
    )
    chk2.pack(anchor="w", pady=2)

    # ---- 菜单热键行 ----
    make_hotkey_row(main, t["menu_label"], menu_var)

    # ---- 底部按钮 ----
    btn_frame = tk.Frame(main, bg="#202020")
    btn_frame.pack(fill="x", pady=(14, 0))

    def on_save():
        hk_explorer = explorer_var.get().strip().lower() or "ctrl+v"
        hk_menu = menu_var.get().strip().lower() or "ctrl+alt+v"

        if hk_explorer == hk_menu:
            messagebox.showerror(t["conflict_title"], t["conflict_msg"])
            return

        # 写入 CONFIG
        CONFIG.setdefault("hotkeys", {})["explorer_ctrl_v"] = hk_explorer
        CONFIG.setdefault("menu", {})["hotkey"] = hk_menu
        CONFIG.setdefault("menu", {})["enabled"] = bool(menu_enabled_var.get())
        CONFIG.setdefault("menu", {})["whitelist_enabled"] = bool(menu_whitelist_var.get())

        # 保存到文件
        save_config()

        # 应用配置并重注册热键
        _apply_config_from_dict(CONFIG)
        stop_hooks()
        register_hotkeys_safe()

        root.destroy()

    def on_cancel():
        root.destroy()

    btn_ok = tk.Button(
        btn_frame,
        text=t["save"],
        command=on_save,
        relief="flat",
        bg="#4caf50",
        fg="#ffffff",
        activebackground="#66bb6a",
        activeforeground="#ffffff",
        padx=10,
        pady=4,
    )
    btn_ok.pack(side="left")

    btn_cancel = tk.Button(
        btn_frame,
        text=t["cancel"],
        command=on_cancel,
        relief="flat",
        bg="#555555",
        fg="#ffffff",
        activebackground="#777777",
        activeforeground="#ffffff",
        padx=10,
        pady=4,
    )
    btn_cancel.pack(side="left", padx=(8, 0))

    root.update_idletasks()
    w = root.winfo_width()
    h = root.winfo_height()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    px = (sw - w) // 2
    py = (sh - h) // 2
    root.geometry(f"{w}x{h}+{px}+{py}")

    root.mainloop()



def register_hotkeys_safe():
    global HOOKS_STARTED, HOOK_HANDLES

    if HOOKS_STARTED:
        return

    print("SmartCtrlV hooks 启动（安全模式 suppress=False）：")
    print("  - Explorer Ctrl+V 增强")
    print("  - Ctrl+Shift+V -> AI 智能粘贴")
    print("  - Ctrl+Alt+V -> 多格式粘贴菜单")
    print("  - Ctrl+Alt+Esc -> 紧急退出")

    h1 = keyboard.add_hotkey(
        CONFIG["hotkeys"].get("explorer_ctrl_v", "ctrl+v"),
        lambda: threading.Thread(target=on_ctrl_v_explorer, daemon=True).start(),
        suppress=True,
    )

    menu_hotkey = CONFIG.get("menu", {}).get("hotkey", "ctrl+alt+v")
    print(f"[SmartCtrlV] 多格式菜单热键: {menu_hotkey}")
    h2 = keyboard.add_hotkey(
        menu_hotkey,
        on_hotkey_menu,
        suppress=False,
    )

    # h4 = keyboard.add_hotkey(
    #    "ctrl+shift+v",
    #    lambda: threading.Thread(target=on_ai_smart_paste, daemon=True).start(),
    #    suppress=False,
    #)

    h_escape = keyboard.add_hotkey(
        "ctrl+alt+esc",
        emergency_exit,
        suppress=False,
    )

    # 🔍 调试热键：只打印一句话，确认 keyboard 是否正常收到按键
    h_debug = keyboard.add_hotkey(
        "ctrl+alt+9",
        lambda: print("[DEBUG] ctrl+alt+9 TRIGGERED"),
        suppress=False,
    )

    HOOK_HANDLES = [h1, h2, h4, h_escape, h_debug]
    HOOKS_STARTED = True
    print("[SmartCtrlV] 热键已注册。")


def start_hooks(config, suppress=False):
    """
    给托盘用的入口：
    - 如果托盘传 config 进来，就用它覆盖默认配置；
    - 否则自己从 JSON 里 load_config。
    - 然后统一调用 register_hotkeys_safe() 注册所有全局热键。
    """
    global HOOKS_STARTED

    if HOOKS_STARTED:
        return

    if config is None:
        load_config()
        _apply_config_from_dict(CONFIG)
    else:
        _apply_config_from_dict(config)

    register_hotkeys_safe()


def stop_hooks() -> None:
    """
    给托盘用的退出入口：
    - 取消所有已经注册的热键
    """
    global HOOKS_STARTED, HOOK_HANDLES

    if not HOOKS_STARTED:
        return

    try:
        for h in HOOK_HANDLES:
            try:
                keyboard.remove_hotkey(h)
            except Exception:
                pass
    except Exception:
        # 万一上面失败，兜底清掉所有热键（注意可能会把别的 keyboard 热键也清了）
        try:
            keyboard.clear_all_hotkeys()
        except Exception:
            pass

    HOOK_HANDLES = []
    HOOKS_STARTED = False
    print("SmartCtrlV hooks 已停止。")


# ========= main =========

def main():
    """
    直接命令行运行时的入口（不经过托盘）：
    - 读取 JSON 配置
    - 应用到全局开关（WHITELIST_ENABLED 等）
    - 注册全局热键
    - 用 while True 挂起进程
    """
    load_config()
    _apply_config_from_dict(CONFIG)

    print("SmartCtrlV Main 运行中（安全模式）：")
    print("  - 在资源管理器里 Ctrl+V：文本按行创建文件 / 写入文件 / 命令执行等")
    print("  - Ctrl+Alt+V：在白名单应用中打开多格式粘贴菜单")
    print("  - Ctrl+Shift+V：AI 智能粘贴")
    print("  - Ctrl+Alt+Esc：紧急退出本程序")
    print("按 Ctrl+C 或 Ctrl+Alt+Esc 退出。\n")

    register_hotkeys_safe()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        # Ctrl+C 的正常退出
        stop_hooks()
        print("SmartCtrlV 退出。")


if __name__ == "__main__":
    main()
