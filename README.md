# AviatrecMusic by ADigital

**AviatrecMusic** is a lightweight MUSIC client with a graphical user interface, developed specifically for working with the AviatrecMusic cloud storage. The application provides convenient access to files music on the server via the HTTPS protocol.

## Features

- **Client** — browse, upload, download music files (MP3, WAV, FLAC) up to 5 GB
- **Streaming** — progressive HTTP audio streaming with smooth rewind timeline
- **Like System** — interactive like button with real-time global counter synced via SQLite
- **Playlists** — create personal playlists and add tracks inside the application
- **Dark & Light Themes** — modern dark interface design in Yandex Music style with light mode toggle
- **Portable** — single EXE file, no installation required
- **Multi-User Support** — works with any Aviatrec account (login/registration with auto-login)

## Tech Stack

| Component | Technology |
|-----------|------------|
| GUI Framework | PyQt6 |
| HTTP Protocol | requests (built-in) |
| Database | SQLite3 (Server-side metadata & accounts) |
| Async Workers | QThread, threading (120 FPS responsive UI) |
| Build Tool | PyInstaller |
| Platform | Windows 10/11 (Architecture: x64) |

## Download

| Format | Link |
|--------|------|
|  RAR   | [Download from Aviatrec Cloud](http://94.190.58.137:5000/download_app)|
|  RAR   | [Download from github](https://github.com/FlowMore-lab/AviatrecMusic/releases/download/Aviatrack/AviatrecMusic.rar)       |

## System Requirements

- Windows 10 or 11
- Internet connection (HTTPS access to AviatrecMusic server)
- No additional dependencies required (portable version)

## Keyboard & Mouse Shortcuts

| Shortcut | Action |
|----------|--------|
| Left-click track | Stream and play track instantly |
| Left-click playlist | Open playlist tracks and show Back button |
| Left-click drag top bar | Drag frameless window seamlessly |

## Audio Player Controls

| Button | Action |
|--------|--------|
| ⚙️ Settings | Change language, theme, region or log in |
| ➕ Add | Create a new custom playlist |
| [ + ] Add to playlist | Add selected track to your active playlist |
| ❤ Like | Toggle track like status and update counter |
| ▶ Play / ⏸ Pause | Control audio playback |
| 📥 Download | Download the original file to local PC |
