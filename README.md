<p align="center">
  <img src="https://github.com/Breathinggg/SmartCtrlV/blob/main/icon.png" width="120" alt="SmartCtrlV Icon"/>
</p>

<h1 align="center">SmartCtrlV</h1>
<p align="center">
  A powerful Windows paste enhancement tool with customizable hotkeys, a multi-format paste menu, and Explorer clipboard automation.
</p>

<p align="center">
  <a href="https://github.com/Breathinggg/SmartCtrlV/releases/tag/v1.0.0">
    <img src="https://img.shields.io/github/v/release/Breathinggg/SmartCtrlV?style=for-the-badge" />
  </a>
  <img src="https://img.shields.io/badge/Platform-Windows-00a8ff?style=for-the-badge" />
  <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" />
</p>

---

## 📥 Download

👉 **Download the latest release:**  
https://github.com/Breathinggg/SmartCtrlV/releases/tag/v1.0.0  

No installation required — just run **SmartCtrlV.exe**.

---

## ✨ Features


## 🌟 1. Enhanced Ctrl+V in File Explorer
SmartCtrlV intelligently analyzes clipboard text and automatically performs the most appropriate action when you press Ctrl + V inside Windows Explorer.

### 🔧 ① Create files from clipboard text
Paste lines like:
```
todo.txt
notes.md
script.py
```
SmartCtrlV will create:
```
todo.txt
notes.md
script.py
```
If a file already exists, it automatically creates:
```
script (1).py
script (2).py
```
---

### 🔧 ② Write or append text into selected files
If you select a text file in Explorer (e.g., log.txt) and press Ctrl + V, SmartCtrlV asks:

- Overwrite file  
- Append to file  
- Cancel  

Example clipboard:

2025-02-10: System started.

→ Will be appended/overwritten safely into log.txt.

---

### 🔧 ③ Execute shell-like commands in the folder
If the clipboard looks like a command:
```
pip install requests
```
or:
```
git init && git add .
```
SmartCtrlV opens cmd inside the current folder and runs it.

Useful for:

- Running commands copied from StackOverflow  
- Quickly creating projects  
- Executing git/pip/npm commands in-place  

---

### 🛡️ ④ Safe by design
- No destructive action happens without confirmation  
- AI output / long text will NOT be misinterpreted as commands  
- Long text is ignored to avoid accidental file spam  

---

## 📋 2. Multi-Format Paste Menu (Ctrl + Alt + V)
Pressing Ctrl + Alt + V opens a floating menu near your cursor where you choose how to paste the clipboard content.

### ✨ Available Paste Modes

### ✔ Raw Paste — normal paste
Pastes text exactly as-is.

---

### ✔ Plain Text Paste — remove formatting
Clipboard:
```
**Hello** _World_ [Link]
```
→ Becomes:
```
Hello World Link
```
---

### ✔ Markdown Cleanup
Input:
```
## Title  
- item  
- item 2  
> quote  
```
→ Output:
```
Title  
item  
item 2  
quote  
```
---

### ✔ Structured Formatting (JSON / XML / HTML / SQL)
If you paste:
```
{"a":1,"b":2,"c":[3,4,5]}
```
→ Becomes formatted pretty JSON.

Also formats XML / HTML / SQL.

---

### ✔ Remove Blank Lines

Input:
```
Line 1  

Line 2  

Line 3  
```
→ Output:
```
Line 1  
Line 2  
Line 3  
```
---

### ✔ Python Dedent
Fixes indentation for Python code:
```
        def test():
            print("hi")
```
→ Output:
```
def test():
    print("hi")
```
---

### ✔ Fully Configurable
Each menu item can be enabled/disabled in tray settings.


### ⚙️ 3. Customizable Hotkeys
All major hotkeys are user-configurable through the tray menu:

- Explorer Paste Hotkey (default: `Ctrl + V`)
- Multi-Format Menu Hotkey (default: `Ctrl + Alt + V`)

SmartCtrlV ensures:
- Hotkeys cannot conflict  
- Hotkeys can be assigned by pressing the desired key combo directly  

### 🖥️ 4. Tray UI & Settings Panel
The tray menu allows you to:

- Enable/disable each paste mode  
- Change hotkeys  
- Reload configuration  
- Exit or restart SmartCtrlV  

User preferences are stored in `smartctrlv_config.json`.

### 🌏 5. Auto Language Detection
UI automatically switches between:

- English  
- 简体中文  
- 日本語  

Or you may force a language in the config.

---

## 📄 Configuration File

Automatically generated on first run:
`smartctrlv_config.json`

Contains:

- Hotkey bindings  
- Paste menu options  
- Whitelist for which apps allow the popup menu  

Users may edit the file manually if desired.

---

## 🔧 Build Instructions (for developers)

### Requirements
- Python 3.10  
- PyInstaller  
- PySide6  
- pywin32  
- keyboard / mouse  

### Build
pyinstaller smartctrlv_tray.spec


## 🧪 Roadmap / Planned Features

UI theme customization
Optional AI-powered paste helpers
Plugin-based formatting system
Cloud-sync settings (optional)

## ❤️ Acknowledgements

SmartCtrlV is inspired by the idea that copy/paste should be smarter.
Thanks to all open-source libraries that made this possible.

## 📜 License

MIT License — free for personal and commercial use.







