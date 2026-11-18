"""Использование уже существующего профиля браузера пользователя для YouTube.
Не создаёт отдельный профиль и не запрашивает повторный вход в Google.
"""
from pathlib import Path
import json, os, shutil, subprocess, webbrowser

BROWSERS = {
    'edge': ('Microsoft/Edge/User Data', 'Microsoft/Edge/Application/msedge.exe'),
    'chrome': ('Google/Chrome/User Data', 'Google/Chrome/Application/chrome.exe'),
    'brave': ('BraveSoftware/Brave-Browser/User Data', 'BraveSoftware/Brave-Browser/Application/brave.exe'),
}

def _local_appdata():
    return Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local'))

def _browser_root(browser='edge'):
    rel = BROWSERS.get(browser, BROWSERS['edge'])[0]
    return _local_appdata() / rel

def _last_used_profile(root: Path):
    """Возвращает имя профиля, который браузер использовал последним."""
    try:
        state = json.loads((root / 'Local State').read_text(encoding='utf-8'))
        profile = state.get('profile', {})
        name = profile.get('last_used') or 'Default'
        cache = profile.get('info_cache', {})
        return name if name in cache or (root / name).is_dir() else 'Default'
    except Exception:
        return 'Default'

def detect_browser():
    # Текущий пользовательский браузер — Edge (по установленному браузеру системы).
    # Если Edge отсутствует, используем первый установленный поддерживаемый профиль.
    for name in ('edge', 'chrome', 'brave'):
        root = _browser_root(name)
        if (root / 'Local State').is_file():
            return name
    return 'edge'

def profile_name():
    browser = detect_browser()
    return _last_used_profile(_browser_root(browser))

def profile_dir():
    return _browser_root(detect_browser()) / profile_name()

def launch_login():
    """Открывает YouTube в основном браузере — существующая Google-сессия сохраняется."""
    url = 'https://www.youtube.com/'
    webbrowser.open(url, new=2)
    browser = detect_browser()
    profile = profile_name()
    return {'browser': browser, 'profile': profile, 'path': str(profile_dir())}

def profile_ready():
    root = _browser_root(detect_browser())
    p = root / profile_name()
    return (p / 'Network' / 'Cookies').is_file() or (p / 'Cookies').is_file()

def yt_dlp_cookie_tuple():
    return (detect_browser(), profile_name(), None, None)

def status_message():
    browser = detect_browser()
    profile = profile_name()
    if profile_ready():
        return f'Используется существующий профиль {browser} · {profile}. Повторный вход не требуется.'
    return f'Профиль {browser} не найден. Открой браузер и войди в YouTube.'
