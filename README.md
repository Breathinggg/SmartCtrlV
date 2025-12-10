SmartCtrlV – Enhanced Clipboard & Explorer Paste Tool for Windows

SmartCtrlV is a lightweight and powerful clipboard enhancement tool for Windows.
It improves the default Ctrl+V behavior in File Explorer and provides a multi-format paste menu for applications such as browsers, editors, IDEs, and terminals.

SmartCtrlV runs quietly in the system tray (Snipaste-style UI), supports configurable hotkeys, and includes multilingual UI (English / Chinese / Japanese).

🔗 Download & Installation

Download the following files from the Release page:

SmartCtrlV.exe
smartctrlv_config.json


Place them in the same folder and double-click SmartCtrlV.exe.

No installation required.
No admin privileges required.

A tray icon will appear in the Windows taskbar.

🚀 Features Overview
1️⃣ Enhanced Ctrl+V in File Explorer

When pressing Ctrl+V inside Explorer:

Clipboard Content	Explorer Behavior
File name list	Create multiple empty files (auto-rename on conflicts)
Text that looks like a command	Open cmd in the current folder and execute it
General text	Create file(s) or process text intelligently
When a text file is selected	Prompt: Overwrite / Append / Cancel

Supports newline-safe appending and extension whitelist.

2️⃣ Multi-Format Paste Menu (Ctrl+Alt+V)

Press Ctrl+Alt+V in whitelisted applications to show a small popup menu next to the mouse cursor:

Paste as-is

Paste as plain text

Paste with Markdown cleanup

Paste after structured formatting (JSON / XML / HTML / SQL)

Paste with blank lines removed

Paste with Python indentation normalization

Each menu option can be enabled or disabled in the configuration.

3️⃣ System Tray Application (Snipaste-Style)

Right-click the tray icon to access quick actions:

Enable / Disable Explorer enhancements

Enable / Disable multi-format paste menu

Toggle whitelist

Edit configuration file

Open log folder

Auto-start on boot

Exit

Double-click the tray icon to view an “About / Status” dialog.

⚙ Configuration File (smartctrlv_config.json)

The configuration file is automatically created in the executable directory on first run.

Example:

{
  "explorer": {
    "enable_command_from_clipboard": true,
    "enable_create_files_from_clipboard": true,
    "enable_write_file_from_clipboard": true,
    "text_ext_whitelist": [".txt", ".md", ".json", ".py"]
  },
  "menu": {
    "enabled": true,
    "whitelist_enabled": true,
    "whitelist_processes": ["chrome.exe", "notepad.exe", "code.exe"],
    "hotkey": "ctrl+alt+v",
    "options": {
      "raw": true,
      "plain": true,
      "markdown": true,
      "structured": true,
      "collapse_blank": true,
      "python_dedent": true
    }
  },
  "hotkeys": {
    "explorer_ctrl_v": "ctrl+v"
  },
  "ui": {
    "language": "auto"
  }
}

⌨ Default Hotkeys
Feature	Hotkey	Configurable
Explorer enhanced paste	Ctrl+V	✔ Yes
Multi-format paste menu	Ctrl+Alt+V	✔ Yes
Emergency exit	Ctrl+Alt+Esc	No

Hotkeys can be modified through the tray UI (press keys directly inside the hotkey field).

🌐 Language Support

English

简体中文

日本語

Language is automatically chosen based on system locale, or can be forced via config.

🛠 Technical Stack

Python 3.10

PySide6 (Qt6)

Tkinter (lightweight popup menu)

keyboard / mouse global hooks

pywin32 / comtypes for Explorer integration

PyInstaller (one-file executable)

❓ FAQ
Why is the executable 30–40 MB?

Because it bundles:

Python interpreter

Qt6 runtime

Tkinter

win32 dependencies

This is normal for a Python-based GUI tool.

Does it interfere with normal Ctrl+V?

No.

Enhanced Ctrl+V only activates in Explorer

In file rename dialogs / address bar, it falls back to native behavior

In other applications, Ctrl+V remains unchanged

How to exit the program?
Ctrl + Alt + Esc


or right-click the tray icon → Exit.

📜 License

MIT License

✔ Multi-language READMEs

If you want, I can generate:

README.zh-CN.md（简体中文）

README.ja.md（日本語版）

And add language toggle like:

English | [中文](README.zh-CN.md) | [日本語](README.ja.md)