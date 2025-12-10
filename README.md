<p align="center">
  <img src="https://github.com/Breathinggg/SmartCtrlV/blob/main/icon.ico" width="120" alt="SmartCtrlV Icon"/>
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

### 🌟 1. Enhanced Ctrl+V in File Explorer
SmartCtrlV detects clipboard content intelligently and performs smart actions:

- Create files from clipboard text (one filename per line)
- Write or append clipboard content to selected text files
- Detect and execute shell-like commands in the current folder  
- Fully safe: no destructive behavior without confirmation

### 📋 2. Multi-Format Paste Menu (`Ctrl + Alt + V`)
A quick popup menu near your cursor with multiple paste modes:

- **Raw Paste** — normal paste  
- **Plain Text Paste** — remove formatting  
- **Markdown Cleanup** — clean headings, lists, quotes, fences  
- **Structured Formatting** — auto-format JSON / XML / HTML / SQL  
- **Remove Blank Lines**  
- **Python Dedent** — auto-fix indentation  

Menu items are fully configurable.

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




