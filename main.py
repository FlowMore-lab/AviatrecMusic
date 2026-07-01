import os
import sys
import json
import requests
import ctypes
from requests_toolbelt.multipart.encoder import MultipartEncoder, MultipartEncoderMonitor
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QListWidget, QPushButton, QLabel, QSlider, QLineEdit,
                             QFileDialog, QMessageBox, QDialog, QProgressBar,
                             QGraphicsOpacityEffect, QComboBox, QInputDialog)
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtCore import QUrl, Qt, QTime, QPropertyAnimation, QEasingCurve, QThread, pyqtSignal

# СТРОГИЙ СИСТЕМНЫЙ ФИКС ДЛЯ ОТОБРАЖЕНИЯ ИКОНКИ В ПАНЕЛИ ЗАДАЧ WINDOWS
if sys.platform == "win32":
    try:
        my_app_id = "ru.hamus.yandexmusic.player.1.0"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(my_app_id)
    except Exception:
        pass


def resource_path(relative_path):
    """Абсолютный путь к ресурсам, работает для обычного запуска и для PyInstaller .exe"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else os.getcwd()
    return os.path.join(base_path, relative_path)


# Глобальные константы путей и сессий
ICON_PATH = resource_path("app_icon.ico")
SERVERS = {
    "Россия": "http://94.190.58.137:5000",
    "Германия": "http://94.190.58.137:5001",
    "Нидерланды": "http://94.190.58.137:5002"
}
SERVER_URL = SERVERS["Россия"]
USER_SESSION = {"user_id": None, "username": None}

LANGUAGES = {
    "Русский": {
        "title": "Aviatrec от ADigital", "tracks_pl": "Треки / Плейлисты",
        "upload": "Загрузить трек", "select": "Выберите трек", "download": "Скачать",
        "settings": "Настройки", "profile": "Профиль пользователя:", "guest": "Вы вошли как: Гость",
        "user_logged": "Вы вошли как: ", "auth_btn": "Вход / Регистрация", "region": "Регион сервера:",
        "lang_label": "Язык интерфейса:", "theme_label": "Тема оформления:", "apply": "Применить",
        "dark": "Темная (Яндекс)", "light": "Светлая", "new_pl_title": "Новый плейлист",
        "new_pl_prompt": "Введите название плейлиста:"
    },
    "English": {
        "title": "Aviatrec by ADigital", "tracks_pl": "Tracks / Playlists",
        "upload": "Upload Track", "select": "Select a track", "download": "Download",
        "settings": "Settings", "profile": "User Profile:", "guest": "Logged in as: Guest",
        "user_logged": "Logged in as: ", "auth_btn": "Login / Registration", "region": "Server Region:",
        "lang_label": "Interface Language:", "theme_label": "Interface Theme:", "apply": "Apply",
        "dark": "Dark (Yandex)", "light": "Light", "new_pl_title": "New Playlist",
        "new_pl_prompt": "Enter playlist name:"
    }
}
CUR_LANG = "English"


# --- 1. АСИНХРОННЫЕ ПОТОКИ С ИЗОЛИРОВАННОЙ ПАМЯТЬЮ (ФИКС КРАШЕЙ 0xC0000409) ---
class NetworkRequestThread(QThread):
    json_signal = pyqtSignal(str)
    bytes_signal = pyqtSignal(bytes)
    error_signal = pyqtSignal(str)

    def __init__(self, url, params=None, is_bytes=False):
        super().__init__()
        self.url = url
        self.params = params
        self.is_bytes = is_bytes

    def run(self):
        try:
            res = requests.get(self.url, params=self.params, timeout=5)
            if res.status_code == 200:
                if self.is_bytes:
                    self.bytes_signal.emit(res.content)
                else:
                    self.json_signal.emit(res.text)
            else:
                self.error_signal.emit(f"HTTP {res.status_code}")
        except Exception as e:
            self.error_signal.emit(str(e))


class DownloadThread(QThread):
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, track_name, save_path, current_server_url):
        super().__init__()
        self.track_name = track_name
        self.save_path = save_path
        self.server_url = current_server_url

    def run(self):
        try:
            audio_url = f"{self.server_url}/api/tracks/{self.track_name}/audio"
            response = requests.get(audio_url, stream=True, timeout=60)
            if response.status_code == 200:
                with open(self.save_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=4096):
                        if chunk: f.write(chunk)
                self.finished_signal.emit(True, "Файл успешно сохранен на диск!")
            else:
                self.finished_signal.emit(False, f"Ошибка скачивания: HTTP {response.status_code}")
        except Exception as e:
            self.finished_signal.emit(False, str(e))


class UploadThread(QThread):
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, folder, title, artist, audio_path, png_path):
        super().__init__()
        self.folder = folder
        self.title = title
        self.artist = artist
        self.audio_path = audio_path
        self.png_path = png_path

    def on_upload_progress(self, monitor):
        if monitor.len > 0:
            percentage = int((monitor.bytes_read / monitor.len) * 100)
            self.progress_signal.emit(percentage)

    def run(self):
        try:
            with open(self.audio_path, 'rb') as audio_f, open(self.png_path, 'rb') as png_f:
                _, ext = os.path.splitext(self.audio_path.lower())
                mime_type = 'audio/x-flac' if ext == '.flac' else ('audio/x-wav' if ext == '.wav' else 'audio/mpeg')
                encoder = MultipartEncoder(fields={
                    'folder': self.folder, 'title': self.title, 'artist': self.artist,
                    'audio': (os.path.basename(self.audio_path), audio_f, mime_type),
                    'cover': (os.path.basename(self.png_path), png_f, 'image/png')
                })
                monitor = MultipartEncoderMonitor(encoder, self.on_upload_progress)
                response = requests.post(f"{SERVER_URL}/api/upload", data=monitor,
                                         headers={'Content-Type': monitor.content_type}, timeout=600)
                if response.status_code == 200:
                    self.finished_signal.emit(True, "Трек успешно загружен на сервер!")
                else:
                    self.finished_signal.emit(False, f"Сервер отклонил запрос:\n{response.text}")
        except Exception as e:
            self.finished_signal.emit(False, str(e))


# --- 2. ГРАФИЧЕСКИЕ ДИАЛОГОВЫЕ ОКНА (НАСТРОЕК, ВХОДА, ЗАГРУЗКИ) ---
class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        t = LANGUAGES[CUR_LANG]
        self.setWindowTitle(t["settings"])
        self.setFixedSize(380, 420)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        layout.addWidget(QLabel(f"<b>{t['profile']}</b>"))
        self.auth_status = QLabel(
            t["guest"] if not USER_SESSION["user_id"] else f"{t['user_logged']}{USER_SESSION['username']}")
        layout.addWidget(self.auth_status)

        self.login_btn = QPushButton(t["auth_btn"])
        self.login_btn.clicked.connect(self.open_auth)
        layout.addWidget(self.login_btn)

        layout.addWidget(QLabel(f"<b>{t['region']}</b>"))
        self.server_box = QComboBox()
        self.server_box.addItems(list(SERVERS.keys()))
        for name, url in SERVERS.items():
            if url == SERVER_URL: self.server_box.setCurrentText(name)
        layout.addWidget(self.server_box)

        layout.addWidget(QLabel(f"<b>{t['lang_label']}</b>"))
        self.lang_box = QComboBox()
        self.lang_box.addItems(["Русский", "English"])
        self.lang_box.setCurrentText(CUR_LANG)
        layout.addWidget(self.lang_box)

        layout.addWidget(QLabel(f"<b>{t['theme_label']}</b>"))
        self.theme_box = QComboBox()
        self.theme_box.addItems([t["dark"], t["light"]])
        layout.addWidget(self.theme_box)

        layout.addStretch()
        apply_btn = QPushButton(t["apply"])
        apply_btn.setObjectName("play_btn")
        apply_btn.clicked.connect(self.apply_changes)
        layout.addWidget(apply_btn)

    def open_auth(self):
        dialog = AuthDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            t = LANGUAGES[CUR_LANG]
            self.auth_status.setText(f"{t['user_logged']}{USER_SESSION['username']}")

    def apply_changes(self):
        global SERVER_URL, CUR_LANG
        SERVER_URL = SERVERS[self.server_box.currentText()]
        CUR_LANG = self.lang_box.currentText()

        if self.theme_box.currentIndex() == 1:
            LIGHT_STYLE = """
                QWidget { background-color: #F6F6F6; color: #121214; font-family: 'Segoe UI', Arial; font-size: 14px; }
                QWidget#title_bar { background-color: #EAEAEA; border-top-left-radius: 12px; border-top-right-radius: 12px; }
                QWidget#content_widget { background-color: #F6F6F6; border-bottom-left-radius: 12px; border-bottom-right-radius: 12px; }
                QLabel { background-color: transparent; color: #121214; }
                QPushButton#sys_btn { color: #121214 !important; background: transparent; }
                QPushButton#sys_btn:hover { background-color: #DCDCDC; }
                QPushButton#close_btn { color: #121214 !important; background: transparent; }
                QPushButton#close_btn:hover { background-color: #E81123; color: white !important; }
                QListWidget { background-color: #FFFFFF; border: 1px solid #E0E0E0; border-radius: 12px; padding: 5px; }
                QListWidget::item { color: #121214; }
                QListWidget::item:hover { background-color: #F0F0F0; }
                QListWidget::item:selected { background-color: #E0E0E0; color: #000000; font-weight: bold; }
                QPushButton { background-color: #EAEAEA; color: #121214; border-radius: 16px; padding: 8px; font-weight: 600; border: none; }
                QPushButton:hover { background-color: #DFDFDF; }
                QPushButton#play_btn { background-color: #FFF200; color: #121214; font-weight: bold; }
                QPushButton#add_pl_plus { background-color: #EAEAEA; color: #121214; border-radius: 4px; }
                QSlider::groove:horizontal { border: none; height: 4px; background: #E0E0E0; border-radius: 2px; }
                QSlider::sub-page:horizontal { background: #FFF200; border-radius: 2px; }
                QSlider::handle:horizontal { background: #121214; border: 1px solid #FFFFFF; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }
                QComboBox, QLineEdit { background-color: #FFFFFF; color: #121214; padding: 6px; border-radius: 8px; border: 1px solid #E0E0E0; }
                QLabel#cover_label { background-color: #EAEAEA; border-radius: 16px; }
                QLabel#likes_count_label { color: #6E6E73; font-size: 13px; font-weight: bold; }
                QPushButton#track_like_btn { background-color: transparent; color: #CCCCCC; font-size: 20px; border: none; }
                QPushButton#track_like_btn:checked { color: #FF3366; }
            """
            QApplication.instance().setStyleSheet(LIGHT_STYLE)
        else:
            QApplication.instance().setStyleSheet(YANDEX_STYLE)
        self.accept()


class AuthDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("HaMus Account")
        self.setFixedSize(320, 240)
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Вход / Регистрация в облаке"))
        self.username_in = QLineEdit()
        self.username_in.setPlaceholderText("Логин")
        self.password_in = QLineEdit()
        self.password_in.setPlaceholderText("Пароль")
        self.password_in.setEchoMode(QLineEdit.EchoMode.Password)

        layout.addWidget(self.username_in)
        layout.addWidget(self.password_in)

        btns = QHBoxLayout()
        login_sub = QPushButton("Войти")
        login_sub.setObjectName("play_btn")
        login_sub.clicked.connect(self.handle_login)

        reg_sub = QPushButton("Регистрация")
        reg_sub.clicked.connect(self.handle_register)

        btns.addWidget(login_sub)
        btns.addWidget(reg_sub)
        layout.addLayout(btns)

    def handle_login(self):
        try:
            u, p = self.username_in.text().strip(), self.password_in.text().strip()
            res = requests.post(f"{SERVER_URL}/api/login", json={"username": u, "password": p}, timeout=7)
            if res.status_code == 200:
                USER_SESSION["user_id"] = res.json()["user_id"]
                USER_SESSION["username"] = res.json()["username"]
                with open("session.json", "w", encoding="utf-8") as f:
                    json.dump({"username": u, "password": p}, f)
                QMessageBox.information(self, "Успех", "Авторизация успешна!")
                self.accept()
            else:
                QMessageBox.critical(self, "Ошибка", res.text)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка сети", str(e))

    def handle_register(self):
        try:
            u, p = self.username_in.text().strip(), self.password_in.text().strip()
            res = requests.post(f"{SERVER_URL}/api/register", json={"username": u, "password": p}, timeout=7)
            if res.status_code == 200:
                QMessageBox.information(self, "Успех", "Регистрация успешна! Теперь нажмите 'Войти'.")
            else:
                QMessageBox.critical(self, "Ошибка", res.text)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка сети", str(e))


class UploadDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Загрузка трека")
        self.setFixedSize(450, 420)
        self.audio_path, self.png_path = "", ""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        layout.addWidget(QLabel("Параметры трека на сервере:"))
        self.folder_input = QLineEdit()
        self.folder_input.setPlaceholderText("Имя папки трека (кириллица разрешена)")
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Название песни")
        self.artist_input = QLineEdit()
        self.artist_input.setPlaceholderText("Исполнитель")
        layout.addWidget(self.folder_input)
        layout.addWidget(self.title_input)
        layout.addWidget(self.artist_input)

        self.audio_btn = QPushButton("Выбрать файл (MP3, WAV, FLAC)")
        self.audio_btn.clicked.connect(self.choose_audio)
        self.audio_label = QLabel("Файл не выбран")
        self.audio_label.setStyleSheet("color: #8E8E93; font-size: 11px;")

        self.png_btn = QPushButton("Выбрать обложку (Только PNG)")
        self.png_btn.clicked.connect(self.choose_png)
        self.png_label = QLabel("Файл не выбран")
        self.png_label.setStyleSheet("color: #8E8E93; font-size: 11px;")

        layout.addWidget(self.audio_btn)
        layout.addWidget(self.audio_label)
        layout.addWidget(self.png_btn)
        layout.addWidget(self.png_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        self.submit_btn = QPushButton("Начать загрузку (До 5 ГБ)")
        self.submit_btn.setObjectName("play_btn")
        self.submit_btn.clicked.connect(self.start_upload)
        layout.addWidget(self.submit_btn)

    def choose_audio(self):
        file, _ = QFileDialog.getOpenFileName(self, "Аудио", "", "Музыка (*.mp3 *.wav *.flac)")
        if file: self.audio_path = file; self.audio_label.setText(os.path.basename(file))

    def choose_png(self):
        file, _ = QFileDialog.getOpenFileName(self, "Обложка", "", "Картинка (*.png)")
        if file: self.png_path = file; self.png_label.setText(os.path.basename(file))

    def start_upload(self):
        f, t, a = self.folder_input.text().strip(), self.title_input.text().strip(), self.artist_input.text().strip()
        if not all([f, t, a, self.audio_path, self.png_path]):
            QMessageBox.warning(self, "Ошибка", "Заполните абсолютно все поля!")
            return
        self.submit_btn.setEnabled(False)
        self.progress_bar.show()
        self.thread = UploadThread(f, t, a, self.audio_path, self.png_path)
        self.thread.progress_signal.connect(self.progress_bar.setValue)
        self.thread.finished_signal.connect(self.upload_done)
        self.thread.start()

    def upload_done(self, success, msg):
        self.submit_btn.setEnabled(True)
        self.progress_bar.hide()
        if success:
            QMessageBox.information(self, "Успех", msg)
            self.accept()
        else:
            QMessageBox.critical(self, "Ошибка", msg)


# --- 3. ГЛАВНЫЙ ИНТЕРФЕЙСНЫЙ КЛАСС (ПАТЧ ШАПКИ И ОТСТУПОВ) ---
class MusicPlayerApp(QWidget):
    def __init__(self):
        super().__init__()
        self.current_track = None
        self.is_slider_moving = False
        self.current_track_likes = 0
        self.playlist_thread = None
        self.meta_thread = None
        self.cover_thread = None
        self.likes_thread = None

        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
        self.init_ui()
        self.init_player()
        self.init_animation()
        self.auto_login()
        self.load_track_list()

    def init_ui(self):
        t = LANGUAGES[CUR_LANG]
        self.setFixedSize(720, 500)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ШАПКА ПК ОКНА
        self.title_bar = QWidget()
        self.title_bar.setObjectName("title_bar")
        title_layout = QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(15, 5, 10, 5)

        title_with_icon = QHBoxLayout()
        title_with_icon.setSpacing(8)
        icon_label = QLabel()
        icon_pixmap = QPixmap(ICON_PATH)
        if not icon_pixmap.isNull():
            icon_label.setPixmap(icon_pixmap.scaled(18, 18, Qt.AspectRatioMode.KeepAspectRatio,
                                                    Qt.TransformationMode.SmoothTransformation))
        title_with_icon.addWidget(icon_label)

        self.app_title_label = QLabel(t["title"])
        self.app_title_label.setStyleSheet("font-weight: bold; background: transparent;")
        title_with_icon.addWidget(self.app_title_label)
        title_layout.addLayout(title_with_icon)
        title_layout.addStretch()

        self.btn_settings = QPushButton("⚙️")
        self.btn_settings.setObjectName("sys_btn")
        self.btn_settings.setFixedSize(36, 28)
        self.btn_settings.setStyleSheet("background: transparent; font-size: 18px; padding: 0px;")
        self.btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_settings.clicked.connect(self.open_settings)
        title_layout.addWidget(self.btn_settings)

        self.btn_minimize = QPushButton("—")
        self.btn_minimize.setObjectName("sys_btn")
        self.btn_minimize.setFixedSize(32, 28)
        self.btn_minimize.setStyleSheet("background: transparent; font-weight: bold; font-size: 16px; padding: 0px;")
        self.btn_minimize.clicked.connect(self.showMinimized)
        title_layout.addWidget(self.btn_minimize)

        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("close_btn")
        self.btn_close.setFixedSize(32, 28)
        self.btn_close.setStyleSheet("background: transparent; font-size: 14px; padding: 0px;")
        self.btn_close.clicked.connect(self.close)
        title_layout.addWidget(self.btn_close)

        root_layout.addWidget(self.title_bar)

        # КОНТЕНТ ПЛЕЕРА
        content_widget = QWidget()
        content_widget.setObjectName("content_widget")
        main_layout = QHBoxLayout(content_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        left_layout = QVBoxLayout()
        library_bar = QHBoxLayout()
        self.tracks_pl_label = QLabel(t["tracks_pl"])
        library_bar.addWidget(self.tracks_pl_label)

        btn_add_playlist = QPushButton("+")
        btn_add_playlist.setObjectName("add_pl_plus")
        btn_add_playlist.setFixedSize(25, 25)
        btn_add_playlist.setStyleSheet("font-weight: bold; font-size: 14px; padding: 0px;")
        btn_add_playlist.clicked.connect(self.add_new_playlist)
        library_bar.addWidget(btn_add_playlist)
        left_layout.addLayout(library_bar)

        self.track_list = QListWidget()
        self.track_list.setObjectName("track_list")
        self.track_list.itemClicked.connect(self.on_track_selected)
        left_layout.addWidget(self.track_list)

        self.upload_btn = QPushButton(t["upload"])
        self.upload_btn.setObjectName("upload_btn")
        self.upload_btn.clicked.connect(self.open_upload_dialog)
        left_layout.addWidget(self.upload_btn)

        main_layout.addLayout(left_layout, stretch=1)

        right_layout = QVBoxLayout()
        self.cover_label = QLabel()
        self.cover_label.setObjectName("cover_label")
        self.cover_label.setFixedSize(220, 220)
        self.cover_label.setScaledContents(True)
        right_layout.addWidget(self.cover_label, alignment=Qt.AlignmentFlag.AlignCenter)

        info_row = QHBoxLayout()
        info_row.setContentsMargins(10, 0, 10, 0)
        info_row.setSpacing(8)

        self.info_label = QLabel(t["select"])
        self.info_label.setObjectName("info_label")
        self.info_label.setWordWrap(True)
        info_row.addWidget(self.info_label, stretch=1)

        self.likes_count_label = QLabel("")
        self.likes_count_label.setObjectName("likes_count_label")
        info_row.addWidget(self.likes_count_label)

        self.like_btn = QPushButton("❤")
        self.like_btn.setObjectName("track_like_btn")
        self.like_btn.setFixedSize(32, 32)
        self.like_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.like_btn.setCheckable(True)
        self.like_btn.clicked.connect(self.toggle_track_like)
        self.like_btn.hide()
        info_row.addWidget(self.like_btn, alignment=Qt.AlignmentFlag.AlignVCenter)

        right_layout.addLayout(info_row)

        self.add_to_pl_btn = QPushButton("[ + ] Добавить в плейлист")
        self.add_to_pl_btn.setObjectName("add_to_pl_btn")
        self.add_to_pl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_to_pl_btn.clicked.connect(self.add_track_to_playlist)
        self.add_to_pl_btn.hide()
        right_layout.addWidget(self.add_to_pl_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        time_layout = QHBoxLayout()
        self.time_current = QLabel("00:00")
        self.time_current.setObjectName("time_lbl")
        self.time_total = QLabel("00:00")
        self.time_total.setObjectName("time_lbl")

        self.timeline = QSlider(Qt.Orientation.Horizontal)
        self.timeline.setObjectName("timeline")
        self.timeline.sliderPressed.connect(self.on_slider_pressed)
        self.timeline.sliderReleased.connect(self.on_slider_released)

        time_layout.addWidget(self.time_current)
        time_layout.addWidget(self.timeline)
        time_layout.addWidget(self.time_total)
        right_layout.addLayout(time_layout)

        btn_layout = QHBoxLayout()
        self.play_btn = QPushButton("Play")
        self.play_btn.setObjectName("play_btn")
        self.play_btn.clicked.connect(self.play_music)

        self.pause_btn = QPushButton("Pause")
        self.pause_btn.setObjectName("pause_btn")
        self.pause_btn.clicked.connect(self.pause_music)

        self.download_btn = QPushButton(t["download"])
        self.download_btn.setObjectName("download_btn")
        self.download_btn.clicked.connect(self.download_track)

        btn_layout.addWidget(self.play_btn)
        btn_layout.addWidget(self.pause_btn)
        btn_layout.addWidget(self.download_btn)
        right_layout.addLayout(btn_layout)

        main_layout.addLayout(right_layout, stretch=2)
        root_layout.addWidget(content_widget)

    def init_player(self):
        from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.player.positionChanged.connect(self.on_position_changed)
        self.player.durationChanged.connect(self.on_duration_changed)

    def init_animation(self):
        self.opacity_effect = QGraphicsOpacityEffect(self.cover_label)
        self.cover_label.setGraphicsEffect(self.opacity_effect)
        self.fade_animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_animation.setDuration(400)
        self.fade_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)

    def auto_login(self):
        if not os.path.exists("session.json"):
            return
        try:
            with open("session.json", "r", encoding="utf-8") as f:
                credentials = json.load(f)
            u, p = credentials.get("username"), credentials.get("password")
            if u and p:
                res = requests.post(f"{SERVER_URL}/api/login", json={"username": u, "password": p}, timeout=4)
                if res.status_code == 200:
                    USER_SESSION["user_id"] = res.json()["user_id"]
                    USER_SESSION["username"] = res.json()["username"]
                else:
                    os.remove("session.json")
        except Exception:
            pass

    def load_track_list(self):
        try:
            res = requests.get(f"{SERVER_URL}/api/tracks", timeout=3)
            if res.status_code == 200:
                self.track_list.clear()
                self.track_list.addItems(res.json())
                self.load_playlists()
        except Exception:
            self.info_label.setText("Сервер оффлайн!")

    def load_playlists(self):
        if not USER_SESSION["user_id"]:
            return
        try:
            res = requests.get(f"{SERVER_URL}/api/playlists", params={"user_id": USER_SESSION["user_id"]}, timeout=3)
            if res.status_code == 200:
                for pl in res.json():
                    self.track_list.addItem(f"📂 Плейлист: {pl['name']} (ID: {pl['id']})")
        except Exception:
            pass

    def add_new_playlist(self):
        t = LANGUAGES[CUR_LANG]
        if not USER_SESSION["user_id"]:
            QMessageBox.warning(self, "Внимание", "Создание плейлистов доступно только после входа в аккаунт!")
            return
        name, ok = QInputDialog.getText(self, t["new_pl_title"], t["new_pl_prompt"])
        if ok and name.strip():
            try:
                res = requests.post(f"{SERVER_URL}/api/playlists",
                                    json={"user_id": USER_SESSION["user_id"], "name": name.strip()}, timeout=5)
                if res.status_code == 200:
                    self.load_track_list()
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", str(e))

    def on_track_selected(self, item):
        text = item.text()
        if text == "⬅️ Назад к общему списку":
            self.load_track_list()
            return

        if text.startswith("📂 Плейлист:"):
            if self.playlist_thread and self.playlist_thread.isRunning():
                self.playlist_thread.quit()
                self.playlist_thread.wait()
            try:
                parts = text.split("(ID: ")
                if len(parts) > 1:
                    pl_id = parts[1].replace(")", "").strip()
                    self.info_label.setText("Открытие плейлиста...")
                    self.playlist_thread = NetworkRequestThread(f"{SERVER_URL}/api/playlists/{pl_id}/tracks")
                    self.playlist_thread.json_signal.connect(self._on_playlist_loaded)
                    self.playlist_thread.error_signal.connect(lambda err: self.info_label.setText(f"Ошибка: {err}"))
                    self.playlist_thread.start()
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", str(e))
            return

        if self.meta_thread and self.meta_thread.isRunning():
            self.meta_thread.quit()
            self.meta_thread.wait()
        if self.cover_thread and self.cover_thread.isRunning():
            self.cover_thread.quit()
            self.cover_thread.wait()
        if self.likes_thread and self.likes_thread.isRunning():
            self.likes_thread.quit()
            self.likes_thread.wait()

        self.current_track = text
        self.opacity_effect.setOpacity(0.0)
        self.add_to_pl_btn.show()
        self.like_btn.show()
        self.likes_count_label.show()
        self.likes_count_label.setText("...")
        self.info_label.setText("Загрузка...")

        self.player.setSource(QUrl(f"{SERVER_URL}/api/tracks/{self.current_track}/audio"))
        self.player.play()

        self.meta_thread = NetworkRequestThread(f"{SERVER_URL}/api/tracks/{self.current_track}/meta")
        self.meta_thread.json_signal.connect(self._on_meta_loaded)
        self.meta_thread.start()

        self.cover_thread = NetworkRequestThread(f"{SERVER_URL}/api/tracks/{self.current_track}/cover", is_bytes=True)
        self.cover_thread.bytes_signal.connect(self._on_cover_loaded)
        self.cover_thread.error_signal.connect(lambda err: self.cover_label.setText("Нет обложки"))
        self.cover_thread.start()

        p_dict = {"track_name": self.current_track}
        if USER_SESSION["user_id"]:
            p_dict["user_id"] = USER_SESSION["user_id"]
        self.likes_thread = NetworkRequestThread(f"{SERVER_URL}/api/likes", params=p_dict)
        self.likes_thread.json_signal.connect(self._on_likes_data_loaded)
        self.likes_thread.start()

    def _on_playlist_loaded(self, json_text):
        try:
            tracks = json.loads(json_text)
            self.track_list.clear()
            self.track_list.addItem("⬅️ Назад к общему списку")
            if tracks:
                for t_item in tracks:
                    name = t_item if isinstance(t_item, list) else t_item
                    self.track_list.addItem(name)
            else:
                self.track_list.addItem("Плейлист пуст.")
        except Exception:
            pass

    def _on_meta_loaded(self, json_text):
        try:
            m = json.loads(json_text)
            self.info_label.setText(f"{m.get('title', self.current_track)} - {m.get('artist', 'Неизвестен')}")
        except Exception:
            self.info_label.setText(f"{self.current_track}")

    def _on_likes_data_loaded(self, json_text):
        try:
            data = json.loads(json_text)
            is_liked = data.get("is_liked", False)
            self.current_track_likes = data.get("total_likes", 0)
            self.like_btn.setChecked(is_liked)
            self.likes_count_label.setText(str(self.current_track_likes) if self.current_track_likes > 0 else "")
        except Exception:
            self.likes_count_label.setText("")

    def _on_cover_loaded(self, byte_data):
        p = QPixmap()
        if p.loadFromData(byte_data):
            self.cover_label.setPixmap(p)
            self.fade_animation.setStartValue(0.0)
            self.fade_animation.setEndValue(1.0)
            self.fade_animation.start()

    def add_track_to_playlist(self):
        if not USER_SESSION["user_id"]:
            QMessageBox.warning(self, "Внимание", "Войдите в аккаунт через настройки!")
            return
        try:
            res = requests.get(f"{SERVER_URL}/api/playlists", params={"user_id": USER_SESSION["user_id"]}, timeout=3)
            if res.status_code == 200 and res.json():
                playlists = res.json()
                items = [pl['name'] for pl in playlists]
                pl_name, ok = QInputDialog.getItem(self, "Выбор плейлиста", "Добавить в плейлист:", items, 0, False)
                if ok and pl_name:
                    pl_id = next(pl['id'] for pl in playlists if pl['name'] == pl_name)
                    add_res = requests.post(f"{SERVER_URL}/api/playlists/{pl_id}/tracks",
                                            json={"track_name": self.current_track}, timeout=5)
                    if add_res.status_code == 200:
                        QMessageBox.information(self, "Успех", f"Добавлено в '{pl_name}'!")
                    else:
                        QMessageBox.warning(self, "Внимание", "Создайте сначала плейлист на кнопку '+'")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка сети", str(e))

    def toggle_track_like(self):
        if not USER_SESSION["user_id"]:
            QMessageBox.warning(self, "Внимание", "Войдите в аккаунт через настройки!")
            self.like_btn.setChecked(not self.like_btn.isChecked())
            return

        is_liked = self.like_btn.isChecked()
        payload = {"user_id": USER_SESSION["user_id"], "track_name": self.current_track}

        if is_liked:
            self.current_track_likes += 1
            self.likes_count_label.setText(str(self.current_track_likes))
            import threading
            def bg_post():
                try:
                    requests.post(f"{SERVER_URL}/api/likes", json=payload, timeout=4)
                except Exception:
                    pass

            threading.Thread(target=bg_post, daemon=True).start()
        else:
            self.current_track_likes = max(0, self.current_track_likes - 1)
            self.likes_count_label.setText(str(self.current_track_likes) if self.current_track_likes > 0 else "")
            import threading
            def bg_delete():
                try:
                    requests.delete(f"{SERVER_URL}/api/likes", json=payload, timeout=4)
                except Exception:
                    pass

            threading.Thread(target=bg_delete, daemon=True).start()

    def on_position_changed(self, pos):
        if not self.is_slider_moving:
            self.timeline.setValue(pos)
            self.time_current.setText(self.format_time(pos))

    def on_duration_changed(self, dur):
        self.timeline.setRange(0, dur)
        self.time_total.setText(self.format_time(dur))

    def on_slider_pressed(self):
        self.is_slider_moving = True

    def on_slider_released(self):
        self.is_slider_moving = False
        self.player.setPosition(self.timeline.value())

    def format_time(self, ms):
        return QTime(0, 0, 0).addMSecs(ms).toString("mm:ss")

    def play_music(self):
        self.player.play()

    def pause_music(self):
        self.player.pause()

    def download_track(self):
        if not self.current_track:
            return
        t = LANGUAGES[CUR_LANG]
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить трек", f"{self.current_track}.mp3",
                                              "Аудио (*.mp3 *.wav *.flac)")
        if path:
            self.download_btn.setEnabled(False)
            self.download_btn.setText("...")
            self.dl = DownloadThread(self.current_track, path, SERVER_URL)
            self.dl.finished_signal.connect(self.on_dl_finished)
            self.dl.start()

    def on_dl_finished(self, success, message):
        t = LANGUAGES[CUR_LANG]
        self.download_btn.setEnabled(True)
        self.download_btn.setText(t["download"])
        if success:
            QMessageBox.information(self, "Скачивание", message)
        else:
            QMessageBox.critical(self, "Ошибка", message)

    def open_settings(self):
        SettingsDialog(self).exec()
        t = LANGUAGES[CUR_LANG]
        self.app_title_label.setText(t["title"])
        self.tracks_pl_label.setText(t["tracks_pl"])
        self.upload_btn.setText(t["upload"])
        self.download_btn.setText(t["download"])
        if not self.current_track:
            self.info_label.setText(t["select"])
        self.load_track_list()

    def open_upload_dialog(self):
        if UploadDialog(self).exec() == QDialog.DialogCode.Accepted:
            self.load_track_list()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.title_bar.underMouse():
            self.drag_position = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            e.accept()

    def mouseMoveEvent(self, e):
        if hasattr(self, 'drag_position') and e.buttons() == Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self.drag_position)
            e.accept()

    def mouseReleaseEvent(self, e):
        if hasattr(self, 'drag_position'):
            del self.drag_position
        e.accept()


# Дизайн стилей Яндекс Музыки
YANDEX_STYLE = """
QWidget { background-color: #121214; color: #FFFFFF; font-family: 'Segoe UI', Arial, sans-serif; font-size: 14px; }
QWidget#title_bar { background-color: #1A1A1F; border-top-left-radius: 12px; border-top-right-radius: 12px; }
QWidget#content_widget { background-color: #121214; border-bottom-left-radius: 12px; border-bottom-right-radius: 12px; }
QListWidget { background-color: #1A1A1F; border: none; border-radius: 12px; padding: 5px; }
QListWidget::item { padding: 12px; color: #E5E5EA; border-radius: 8px; margin-bottom: 2px; }
QListWidget::item:hover { background-color: #2C2C35; }
QListWidget::item:selected { background-color: #25252A; color: #FFF200; font-weight: bold; }
QLabel { background-color: transparent; color: #FFFFFF; }
QLabel#info_label { font-size: 15px; font-weight: 500; }
QLabel#likes_count_label { color: #8E8E93; font-size: 13px; font-weight: bold; padding-right: 2px; }
QPushButton { background-color: #2C2C35; color: #FFFFFF; border: none; border-radius: 16px; padding: 8px 18px; font-weight: 600; min-height: 20px; }
QPushButton:hover { background-color: #3A3A45; }
QPushButton#play_btn { background-color: #FFF200; color: #121214; font-weight: bold; }
QPushButton#play_btn:hover { background-color: #E6DA00; }
QPushButton#add_to_pl_btn { background-color: transparent; color: #FFF200; border: 1px solid #FFF200; border-radius: 12px; padding: 4px; font-size: 12px; }
QPushButton#add_to_pl_btn:hover { background-color: #FFF200; color: #121214; }
QPushButton#track_like_btn { background-color: transparent; color: #6E6E73; font-size: 20px; border: none; padding: 0px; }
QPushButton#track_like_btn:hover { color: #FF3366; }
QPushButton#track_like_btn:checked { color: #FF3366; }
QSlider::groove:horizontal { border: none; height: 4px; background: #2C2C35; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #FFF200; border-radius: 2px; }
QSlider::handle:horizontal { background: #FFFFFF; border: 1px solid #121214; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }
QSlider::handle:horizontal:hover { background: #FFF200; width: 16px; height: 16px; margin: -6px 0; border-radius: 8px; }
QComboBox, QLineEdit { background-color: #1A1A1F; color: white; padding: 6px; border-radius: 8px; border: 1px solid #2C2C35; }
QProgressBar { border: 1px solid #2C2C35; border-radius: 6px; text-align: center; background-color: #1A1A1F; }
QProgressBar::chunk { background-color: #FFF200; border-radius: 5px; }
"""

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(YANDEX_STYLE)
    window = MusicPlayerApp()
    window.show()
    sys.exit(app.exec())