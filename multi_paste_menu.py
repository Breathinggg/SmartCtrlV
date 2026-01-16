import time
import json
import threading
import os
import re
import textwrap
import tkinter as tk

import keyboard
import pyperclip

import win32api
import win32gui
import win32process
import win32con
import mouse  # 全局鼠标监听
import xml.dom.minidom as minidom


# ========= 白名单配置 =========

WHITELIST_ENABLED = True

WHITELIST_PROCESSES = [
    "notepad.exe",
    "chrome.exe",
    "msedge.exe",
    "firefox.exe",
    "code.exe",        # VS Code
    "winword.exe",     # Word
    "excel.exe",
    "powerpnt.exe",
    "wechat.exe",
    "qq.exe",
]


# ========= 全局状态 =========

last_foreground_hwnd = None
menu_window = None
root = None
menu_visible = False


# ========= 前台窗口 & 进程工具 =========

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


def focus_window(hwnd):
    """把焦点切回原来的窗口"""
    try:
        if hwnd and win32gui.IsWindow(hwnd):
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.05)
    except Exception:
        pass


# ========= 菜单关闭 / 基础操作 =========

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


def raw_paste():
    """原样粘贴：不改剪贴板，直接 Ctrl+V"""
    global last_foreground_hwnd
    print("[MultiPaste] 模式：原样粘贴")
    close_menu()
    focus_window(last_foreground_hwnd)
    keyboard.send("ctrl+v")


def plain_text_paste():
    """纯文本粘贴：只保留文本，不做额外清洗（以后可以增强）"""
    global last_foreground_hwnd

    print("[MultiPaste] 模式：纯文本粘贴")
    text = pyperclip.paste()
    if text is None:
        text = ""
    pyperclip.copy(text)

    close_menu()
    focus_window(last_foreground_hwnd)
    keyboard.send("ctrl+v")


# ========= 结构化内容格式化（JSON / XML / HTML / SQL） =========

def try_format_json(text: str):
    try:
        data = json.loads(text)
        return json.dumps(data, indent=2, ensure_ascii=False)
    except Exception:
        return None


def try_format_xml_or_html(text: str):
    # 简单判断一下是否像 XML/HTML
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
    # 非严格 SQL 识别，非常粗糙，只用于提升可读性
    lower = text.lower()
    if "select" not in lower:
        return None

    # 简单格式化：在关键字前面加换行
    keywords = [
        "select", "from", "where", "group by", "order by", "having",
        "join", "left join", "right join", "inner join", "outer join",
        "limit", "offset"
    ]

    formatted = " " + text  # 前面加一个空格方便处理
    for kw in keywords:
        # 用正则在关键词前面加换行，忽略大小写
        pattern = r"(?i)\s(" + re.escape(kw) + r")\b"
        formatted = re.sub(pattern, r"\n\1", formatted)

    return formatted.strip()


def structured_format_paste():
    """JSON / XML / HTML / SQL 智能格式化后粘贴"""
    global last_foreground_hwnd

    print("[MultiPaste] 模式：结构化格式化粘贴")
    text = pyperclip.paste()
    if not text:
        close_menu()
        focus_window(last_foreground_hwnd)
        keyboard.send("ctrl+v")
        return

    formatted = None

    # 1. 先试 JSON
    formatted = try_format_json(text)
    if formatted is None:
        # 2. 再试 XML/HTML
        formatted = try_format_xml_or_html(text)
    if formatted is None:
        # 3. 再试 SQL（非常粗糙）
        formatted = try_format_sql(text)

    if formatted is not None:
        pyperclip.copy(formatted)
    else:
        print("[MultiPaste] 结构化格式化：无法识别类型，保持原样")

    close_menu()
    focus_window(last_foreground_hwnd)
    keyboard.send("ctrl+v")


# ========= 去空行 =========

def collapse_blank_lines(text: str) -> str:
    """
    删除所有空行：
    - 只包含空格/制表符/全角空格的行统统干掉
    """
    lines = text.splitlines()
    new_lines = [line for line in lines if line.strip() != ""]
    return "\n".join(new_lines)


def collapse_blank_paste():
    """去除所有空行后粘贴"""
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


# ========= Python 缩进整理 =========

def python_dedent_paste():
    """
    用 textwrap.dedent 去掉公共前导缩进：
    - 适用于：你粘贴代码到一个已经有缩进的块里时，
      避免每行都多一个 tab / 多几个空格。
    """
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


# ========= 鼠标点击监控 =========

def is_descendant(child_hwnd, parent_hwnd):
    """判断 child_hwnd 是否是 parent_hwnd 的子孙窗口"""
    if not child_hwnd or not parent_hwnd:
        return False
    h = child_hwnd
    while h:
        if h == parent_hwnd:
            return True
        h = win32gui.GetParent(h)
    return False


def mouse_click_watcher():
    """
    监听鼠标左键点击：
    - 如果点击在菜单窗口内部：忽略，让按钮自己处理
    - 如果点击在菜单窗口外部：关闭菜单
    """
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
            # 点击在菜单内部，交给按钮命令处理
            continue

        close_menu()
        return


# ========= 菜单 UI =========

def create_menu_window():
    """在鼠标旁边创建菜单窗口"""
    global menu_window, root, menu_visible

    close_menu()

    # 取鼠标坐标
    x, y = win32api.GetCursorPos()

    root = tk.Tk()
    root.withdraw()
    win = tk.Toplevel(root)
    menu_window = win
    menu_visible = True

    win.overrideredirect(True)
    win.attributes("-topmost", True)
    win.configure(bg="#202020")

    def add_button(text, command):
        btn = tk.Button(
            win, text=text,
            command=command,
            relief="flat",
            bg="#303030",
            fg="#ffffff",
            activebackground="#505050",
            activeforeground="#ffffff",
            padx=10,
            pady=5
        )
        btn.pack(fill="x")

    add_button("原样粘贴", raw_paste)
    add_button("纯文本粘贴", plain_text_paste)
    add_button("结构化格式化粘贴(JSON/XML/HTML/SQL)", structured_format_paste)
    add_button("去所有空行粘贴", collapse_blank_paste)
    add_button("Python 缩进整理粘贴", python_dedent_paste)

    def on_escape(event):
        close_menu()

    win.bind("<Escape>", on_escape)

    # 计算窗口尺寸
    win.update_idletasks()
    width = win.winfo_width()
    height = win.winfo_height()

    # 获取屏幕大小
    screen_width = win32api.GetSystemMetrics(0)
    screen_height = win32api.GetSystemMetrics(1)

    # 默认偏移（右下角）
    pos_x = x + 10
    pos_y = y + 10

    # 如果超出右边界 → 向左弹
    if pos_x + width > screen_width:
        pos_x = x - width - 10

    # 如果超出下边界 → 向上弹
    if pos_y + height > screen_height:
        pos_y = y - height - 10

    # 如果超出左边界（极少出现）→ 贴左
    if pos_x < 0:
        pos_x = 0

    # 如果超出上边界（极少出现）→ 贴顶
    if pos_y < 0:
        pos_y = 0

    # 最终定位
    win.geometry(f"{width}x{height}+{pos_x}+{pos_y}")

    t = threading.Thread(target=mouse_click_watcher, daemon=True)
    t.start()

    root.mainloop()


# ========= 热键回调 =========

def on_hotkey():
    """热键回调：记录前台窗口 + 白名单判断 + 弹出菜单"""
    global last_foreground_hwnd

    exe_name, hwnd = get_foreground_exe_name()
    last_foreground_hwnd = hwnd

    if WHITELIST_ENABLED:
        if not exe_name or exe_name not in WHITELIST_PROCESSES:
            focus_window(last_foreground_hwnd)
            keyboard.send("ctrl+v")
            return

    t = threading.Thread(target=create_menu_window, daemon=True)
    t.start()


def main():
    print("多格式粘贴菜单运行中。")
    print("  - Ctrl + Alt + V 在鼠标旁弹出菜单（或按白名单逻辑直接粘贴）")
    print("  - 菜单项：")
    print("      * 原样粘贴")
    print("      * 纯文本粘贴")
    print("      * 结构化格式化粘贴 (JSON/XML/HTML/SQL)")
    print("      * 去所有空行粘贴")
    print("      * Python 缩进整理粘贴")
    print("  - 点菜单内部：执行对应粘贴（终端会打印当前模式）")
    print("  - 点菜单外部 或 Esc：关闭菜单")
    print("  - 白名单开关 WHITELIST_ENABLED =", WHITELIST_ENABLED)
    print("Ctrl+C 退出。\n")

    keyboard.add_hotkey("ctrl+alt+v", on_hotkey, suppress=True)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("退出。")


if __name__ == "__main__":
    main()
