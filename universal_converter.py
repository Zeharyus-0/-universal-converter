#!/usr/bin/env python3
"""
UNIVERSAL CONVERTER by zeharyus
Drag images, videos or audio files (or folders) onto the window and convert them.

Reads everything Pillow can open (PNG, JPEG, WebP, AVIF, GIF, BMP, TIFF, ICO, TGA,
PSD, DDS, PCX, PPM, QOI, ...). Writes PNG, JPEG, WebP, AVIF, GIF, BMP, TIFF, ICO, TGA, PDF.

Themes live in the "themes" folder next to the app (see themes/README.txt to make your own).
Built in: Frontier (default), Medieval, Elden-style dark fantasy, Pixel, Custom wallpaper.

Needs:  Python 3.10+   and   pip install PySide6 Pillow imageio-ffmpeg
Run:    python universal_converter.py          (or pass files/folders as arguments)

Fonts: .ttf/.otf files in a "fonts" folder next to the script/.exe are loaded at start.
Settings and the wallpaper copy live in "universal_converter_data" next to the script/.exe
(falls back to the user's app-data folder if that isn't writable).
"""
from __future__ import annotations

import colorsys
import datetime as _dt
import hashlib
import io
import json
import math
import os
import base64
import random
import re
import shutil
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

try:
    from PIL import Image, ImageCms, ImageOps, ImageSequence, features
    from PySide6.QtCore import (QByteArray, QElapsedTimer, QEasingCurve, QEvent, QObject, QPoint, QPointF,
                                QPropertyAnimation, QRect, QRectF, QStandardPaths, Qt, QTimer, QUrl,
                                QVariantAnimation, Signal)
    from PySide6.QtGui import (QColor, QDesktopServices, QFont, QFontDatabase, QIcon, QPainter,
                               QImage, QLinearGradient, QMovie, QPainterPath, QPen, QPixmap, QRadialGradient,
                               QRegion, QTransform, QWindow)
    from PySide6.QtWidgets import (QApplication, QCheckBox, QColorDialog, QComboBox, QFileDialog,
                                   QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel,
                                   QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
                                   QButtonGroup, QDialog, QDialogButtonBox, QGraphicsOpacityEffect, QMenu,
                                   QProgressBar, QPushButton, QSlider,
                                   QToolButton, QVBoxLayout, QWidget)
except ImportError as exc:  # friendly message instead of a traceback
    print(f"Missing dependency ({exc.name}). Install with:\n    pip install PySide6 Pillow")
    sys.exit(1)

APP_TITLE = "UNIVERSAL CONVERTER"
APP_CREDIT = "by zeharyus"                                  # every theme except Socialab
SOCIALAB_CREDIT = "Socialab Edition by IT zeharyus"         # Socialab theme only
APP_NAME = f"{APP_TITLE} {APP_CREDIT}"

# ----------------------------------------------------------------------------- paths


def base_dir() -> Path:
    """Folder of the script or the .exe (where user data and extra fonts live)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def res_dir() -> Path:
    """Folder of bundled resources (inside the .exe when frozen)."""
    return Path(getattr(sys, "_MEIPASS", base_dir()))


# ---- hidden themes
# A locked theme stays out of the theme list until its code is typed while the window is active.
# Once typed, an unlock file is written to the "pins" folder next to the app, so it's never asked again.
# Codes are stored scrambled (salted SHA-256). This keeps themes out of casual view; it is not real security.
LOCKS = {
    "socialab": dict(salt=b"uc-socialab|", hash="bc1156020e5e5e8ca225929b00b7005d318aff66dc574be88ef7c944b2f2b57d",
                     length=6, file="socialab.pin", name="Socialab"),
    "frontier": dict(salt=b"uc-frontier|", hash="b131a0504950c02ebb05756f38d53ba40190f85e8b2cbd0846d4bcf121d908fa",
                     length=13, file="frontier.pin", name="Frontier"),
}
# The seal: typing this code makes every holiday theme selectable and stops them taking over.
SEAL = dict(salt=b"uc-seal|", hash="311f11da946164bf1cba2c51fcf3e9d01e67d399f2caf0df320306bc3b54e6f8",
            length=50, file="seal.pin")
_TYPED_MAX = max([v["length"] for v in LOCKS.values()] + [SEAL["length"]])


def _seal_ok(candidate: str) -> bool:
    return hashlib.sha256(SEAL["salt"] + candidate.encode()).hexdigest() == SEAL["hash"]


# ---- holidays: on these dates the matching theme takes over the app (until the seal is broken)
HOLIDAY_KEYS = ["halloween", "christmas", "newyear", "easter", "aprilfools"]


def _easter_western(y: int) -> _dt.date:
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return _dt.date(y, month, day)


def _easter_orthodox(y: int) -> _dt.date:
    a, b, c = y % 4, y % 7, y % 19
    d = (19 * c + 15) % 30
    e = (2 * a + 4 * b - d + 34) % 7
    month = (d + e + 114) // 31
    day = (d + e + 114) % 31 + 1
    return _dt.date(y, month, day) + _dt.timedelta(days=13)      # Julian -> Gregorian (1900-2099)


def today() -> _dt.date:
    fake = os.environ.get("UC_TEST_DATE")                         # for testing: UC_TEST_DATE=2026-10-31
    if fake:
        try:
            return _dt.date.fromisoformat(fake)
        except ValueError:
            pass
    return _dt.date.today()


def forced_holiday(d: _dt.date) -> tuple[str | None, _dt.date | None]:
    """(theme, first day it's free again) if today is a holiday, else (None, None)."""
    if (d.month, d.day) == (4, 1):
        return "aprilfools", _dt.date(d.year, 4, 2)
    if (d.month, d.day) == (10, 31):
        return "halloween", _dt.date(d.year, 11, 1)
    if d.month == 12 and 20 <= d.day <= 30:
        return "christmas", _dt.date(d.year, 12, 31)
    if (d.month, d.day) == (12, 31):
        return "newyear", _dt.date(d.year + 1, 1, 2)
    if (d.month, d.day) == (1, 1):
        return "newyear", _dt.date(d.year, 1, 2)
    for easter in (_easter_western(d.year), _easter_orthodox(d.year)):
        if easter - _dt.timedelta(days=2) <= d <= easter + _dt.timedelta(days=1):    # Good Friday .. Easter Monday
            return "easter", easter + _dt.timedelta(days=2)
    return None, None


def seal_open() -> bool:
    for d in pin_dirs():
        try:
            if (d / SEAL["file"]).read_text(encoding="utf-8").strip() == SEAL["hash"]:
                return True
        except OSError:
            pass
    return False


def save_seal() -> bool:
    for d in pin_dirs():
        try:
            d.mkdir(parents=True, exist_ok=True)
            (d / SEAL["file"]).write_text(SEAL["hash"] + "\n", encoding="utf-8")
            return True
        except OSError:
            continue
    return False


SEALED_MESSAGES = {
    "halloween": ("SEALED", "Something in the dark sealed the themes tonight.\nThe seal breaks on {until}."),
    "christmas": ("Wrapped up!", "The themes are wrapped like presents.\nNo unwrapping until {until}."),
    "newyear": ("Party lock!", "The themes are out celebrating.\nThey'll be back on {until}."),
    "easter": ("Hidden!", "The themes are hidden like eggs.\nThey'll turn up on {until}."),
    "aprilfools": ("Nice try 🦆", "The themes are on vacation until {until}.\nProbably."),
}

UPSIDE_DOWN = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "∀ᗺƆᗡƎℲ⅁HIſʞ˥WNOԀΌᴚS⊥∩ΛMX⅄Z")


def upside_down(text: str) -> str:
    return text.upper().translate(UPSIDE_DOWN)[::-1]


APRIL_HINTS = ["Drop your images here (they don't bite)", "Images go here. Ducks go everywhere else.",
               "Drop it like it's hot. Then drop some images.", "Feed me images. Nom nom.",
               "Drop images here. Or don't. I'm a sign, not a cop."]
APRIL_HINTS_MEDIA = ["Drop videos here (popcorn not included)", "Videos and audio go here. Quack.",
                     "Feed me videos. Nom nom.", "Drop your audio here. I'll pretend to dance."]
APRIL_QUIPS = ["Every pixel survived.", "No ducks were harmed.", "Quack-tastic.", "Suspiciously smooth.",
               "Converted with 100% organic bytes."]
APRIL_LABELS = ["Duck", "Also duck", "Definitely not a duck", "Duck (premium)", "Duck 2: The Duckening",
                "Goose (it's a duck)", "Duck", "Duck again", "Classic duck", "Duck", "Duck"]


def _code_ok(theme: str, candidate: str) -> bool:
    lk = LOCKS[theme]
    return hashlib.sha256(lk["salt"] + candidate.encode()).hexdigest() == lk["hash"]


def pin_dirs() -> list[Path]:
    """Where the unlock file may live: 'pins' next to the app, else in the settings folder."""
    return [base_dir() / "pins", data_dir() / "pins"]


def unlocked_themes() -> set[str]:
    found = set()
    for theme, lk in LOCKS.items():
        for d in pin_dirs():
            try:
                if (d / lk["file"]).read_text(encoding="utf-8").strip() == lk["hash"]:
                    found.add(theme)
                    break
            except OSError:
                pass
    return found


def save_unlock(theme: str) -> Path | None:
    lk = LOCKS[theme]
    for d in pin_dirs():
        try:
            d.mkdir(parents=True, exist_ok=True)
            (d / lk["file"]).write_text(lk["hash"] + "\n", encoding="utf-8")
            return d / lk["file"]
        except OSError:
            continue
    return None


def data_dir() -> Path:
    d = base_dir() / "universal_converter_data"
    try:
        d.mkdir(exist_ok=True)
        probe = d / ".write_test"
        probe.write_text("ok")
        probe.unlink()
        return d
    except OSError:
        loc = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        d = Path(loc) / "UniversalConverterApp"
        d.mkdir(parents=True, exist_ok=True)
        return d


def load_bundled_fonts() -> None:
    folders = [res_dir() / "fonts"]
    if base_dir() != res_dir():
        folders.append(base_dir() / "fonts")
    for folder in folders:
        if folder.is_dir():
            for f in sorted(folder.iterdir()):
                if f.suffix.lower() in (".ttf", ".otf"):
                    QFontDatabase.addApplicationFont(str(f))


LOGO_FILES = {"bee": ("bee.ico", "bee.png"), "crow": ("icon.ico", "icon.png"),
              "frontier": ("frontier.ico", "frontier.png")}
_ICONS: dict[str, QIcon] = {}


def app_icon(logo: str = "crow") -> QIcon:
    """'bee' = Socialab logo, 'crow' = the default logo."""
    if logo not in _ICONS:
        icon = QIcon()
        for name in LOGO_FILES.get(logo, LOGO_FILES["crow"]):
            p = res_dir() / "assets" / name
            if p.is_file():
                icon = QIcon(str(p))
                break
        _ICONS[logo] = icon
    return _ICONS[logo]


def theme_file(t: dict, name: str) -> Path | None:
    """A file named by a theme: inside its theme folder, else in the bundled assets."""
    if not name:
        return None
    if t.get("_dir"):
        p = Path(t["_dir"]) / name
        if p.is_file():
            return p
    p = res_dir() / "assets" / name
    return p if p.is_file() else None


def theme_icon(t: dict) -> QIcon:
    logo = t.get("logo", "crow")
    if logo in LOGO_FILES:
        return app_icon(logo)
    path = theme_file(t, logo)
    if path is None:
        return app_icon("crow")
    key = str(path)
    if key not in _ICONS:
        _ICONS[key] = QIcon(key)
    return _ICONS[key]


_PICTURES: dict[str, QPixmap] = {}


def theme_picture(t: dict) -> tuple[str, QPixmap | None]:
    path = theme_file(t, t.get("image", ""))
    if path is None:
        return "", None
    key = str(path)
    if key not in _PICTURES:
        _PICTURES[key] = QPixmap(key)
    return key, _PICTURES[key]


# ---- shortcuts (Windows): a desktop / Start-menu shortcut whose icon follows the theme.
# The .exe's own icon is baked in at build time and can't change; a shortcut's icon can.
SHORTCUT_NAME = "Universal Converter.lnk"
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0      # CREATE_NO_WINDOW: no console flash


def shortcuts_supported() -> bool:
    return sys.platform == "win32" and getattr(sys, "frozen", False)


def shortcut_paths() -> list[Path]:
    out = []
    for loc in (QStandardPaths.StandardLocation.DesktopLocation,
                QStandardPaths.StandardLocation.ApplicationsLocation):   # Start menu > Programs
        d = QStandardPaths.writableLocation(loc)
        if d:
            out.append(Path(d) / SHORTCUT_NAME)
    return out


def theme_ico_file(key: str, t: dict) -> Path | None:
    """An .ico on disk for this theme (shortcuts need a real file, not one inside the .exe)."""
    out = data_dir() / "icons" / f"{key}.ico"
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        logo = t.get("logo", "crow")
        if logo in LOGO_FILES:
            src = res_dir() / "assets" / LOGO_FILES[logo][0]
        else:
            src = theme_file(t, logo)
        if src is None:
            src = res_dir() / "assets" / "icon.ico"
        if src.suffix.lower() == ".ico":
            data = src.read_bytes()
            if not out.exists() or out.read_bytes() != data:
                out.write_bytes(data)
        else:
            with Image.open(src) as im:
                im = im.convert("RGBA")
                side = max(im.size)
                sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
                sq.paste(im, ((side - im.width) // 2, (side - im.height) // 2))
                sq.save(out, sizes=[(n, n) for n in (16, 24, 32, 48, 64, 128, 256) if n <= side] or [(side, side)])
        return out
    except Exception:
        return None


def _ps_quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def write_shortcut(lnk: Path, target: Path, icon: Path) -> bool:
    """Create or update a .lnk through Windows' own shortcut object (via PowerShell)."""
    script = (
        "$ws = New-Object -ComObject WScript.Shell;"
        f"$s = $ws.CreateShortcut({_ps_quote(str(lnk))});"
        f"$s.TargetPath = {_ps_quote(str(target))};"
        f"$s.WorkingDirectory = {_ps_quote(str(target.parent))};"
        f"$s.IconLocation = {_ps_quote(str(icon) + ',0')};"
        "$s.Description = 'Universal Converter';"
        "$s.Save()"
    )
    enc = base64.b64encode(script.encode("utf-16-le")).decode()
    try:
        r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                            "-EncodedCommand", enc], capture_output=True, timeout=30, creationflags=NO_WINDOW)
        ok = r.returncode == 0
    except Exception:
        ok = False
    if ok:
        try:   # ask Explorer to redraw icons now
            import ctypes
            ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x1000, None, None)
        except Exception:
            pass
    return ok


# ---- uninstall (Windows .exe): removes the app and everything it created, nothing else
OWN_DIRS = ("universal_converter_data", "pins")


def _safe(path: Path) -> bool:
    """Never touch a drive root, the user folder itself, or anything too shallow."""
    try:
        rp = path.resolve()
    except OSError:
        return False
    return len(rp.parts) >= 3 and rp != Path.home().resolve() and rp.parent != rp


def uninstall_plan(cfg: dict, keep_themes: bool) -> list[tuple[Path, str]]:
    """(path, kind) to remove. kind: file | tree (folder and contents) | emptydir (only if empty)."""
    b = base_dir()
    items: list[tuple[Path, str]] = []
    if getattr(sys, "frozen", False):
        items.append((Path(sys.executable), "file"))
    for name in OWN_DIRS:
        items.append((b / name, "tree"))
    loc = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    if loc:
        items.append((Path(loc) / "UniversalConverterApp", "tree"))
    themes = b / "themes"
    if not keep_themes and themes.is_dir():
        for f in themes.iterdir():          # only theme folders and our own files, nothing unknown
            if f.is_dir() and ((f / "theme.json").is_file() or f.name == "_template"):
                items.append((f, "tree"))
            elif f.is_file() and f.name in ("README.txt", ".write_test"):
                items.append((f, "file"))
        items.append((themes, "emptydir"))
    for lnk in {str(x) for x in list(cfg.get("shortcuts", [])) + [str(x) for x in shortcut_paths()]}:
        if lnk.lower().endswith(".lnk"):
            items.append((Path(lnk), "file"))
    items.append((b, "emptydir"))           # the app's folder, only if nothing else is left in it
    return [(pth, kind) for pth, kind in items if _safe(pth) and (pth.exists() or kind == "file")]


def uninstall_script(plan: list[tuple[Path, str]], pids: list[int]) -> str:
    lines = ["$ErrorActionPreference = 'SilentlyContinue'",
             "$log = Join-Path $env:TEMP 'universal_converter_uninstall.log'",
             "\"started $(Get-Date)\" | Out-File -LiteralPath $log -Encoding utf8"]
    for pid in pids:
        lines.append(f"try {{ Wait-Process -Id {int(pid)} -Timeout 60 }} catch {{}}")
    lines.append("Start-Sleep -Milliseconds 800")
    lines.append("$items = @()")
    for pth, kind in plan:
        lines.append(f"$items += ,@({_ps_quote(str(pth))}, '{kind}')")
    lines += [
        "for ($round = 0; $round -lt 15; $round++) {",
        "  $left = 0",
        "  foreach ($it in $items) {",
        "    $p = $it[0]; $k = $it[1]",
        "    if (-not (Test-Path -LiteralPath $p)) { continue }",
        "    if ($k -eq 'tree') { Remove-Item -LiteralPath $p -Recurse -Force }",
        "    elseif ($k -eq 'file') { Remove-Item -LiteralPath $p -Force }",
        "    elseif ($k -eq 'emptydir') {",
        "      if (@(Get-ChildItem -LiteralPath $p -Force).Count -eq 0) { Remove-Item -LiteralPath $p -Force }",
        "      continue",
        "    }",
        "    if (Test-Path -LiteralPath $p) { $left++; \"still there: $p\" | Add-Content -LiteralPath $log }",
        "  }",
        "  if ($left -eq 0) { break }",
        "  Start-Sleep -Seconds 1",
        "}",
        "\"finished, left: $left\" | Add-Content -LiteralPath $log",
    ]
    return "\n".join(lines)


def launch_uninstall(plan: list[tuple[Path, str]]) -> bool:
    pids = [os.getpid()]
    try:
        pids.append(os.getppid())            # the .exe's launcher process holds the file open too
    except Exception:
        pass
    enc = base64.b64encode(uninstall_script(plan, pids).encode("utf-16-le")).decode()
    try:
        subprocess.Popen(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                          "-EncodedCommand", enc],
                         creationflags=NO_WINDOW | 0x00000200,   # no window, own process group
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         close_fds=True)
        return True
    except Exception:
        return False


def resolve_font(candidates: list[tuple[str, float]]) -> tuple[str, float]:
    installed = set(QFontDatabase.families())
    for family, pt in candidates:
        if family in installed:
            return family, pt
    return QApplication.font().family(), candidates[-1][1]


# ----------------------------------------------------------------------------- formats

Image.init()

# key -> how to write it. alpha: keeps transparency. anim: can hold several frames.
_ALL_OUTPUTS = {
    "PNG":  dict(label="PNG",  ext=".png",  pil="PNG",  alpha=True,  anim=True,  quality=False),
    "JPEG": dict(label="JPG",  ext=".jpg",  pil="JPEG", alpha=False, anim=False, quality=True),
    "WEBP": dict(label="WebP", ext=".webp", pil="WEBP", alpha=True,  anim=True,  quality=True),
    "AVIF": dict(label="AVIF", ext=".avif", pil="AVIF", alpha=True,  anim=True,  quality=True),
    "GIF":  dict(label="GIF",  ext=".gif",  pil="GIF",  alpha=True,  anim=True,  quality=False),
    "BMP":  dict(label="BMP",  ext=".bmp",  pil="BMP",  alpha=False, anim=False, quality=False),
    "TIFF": dict(label="TIFF", ext=".tif",  pil="TIFF", alpha=True,  anim=True,  quality=False),
    "ICO":  dict(label="ICO (icon)", ext=".ico", pil="ICO", alpha=True, anim=False, quality=False),
    "TGA":  dict(label="TGA",  ext=".tga",  pil="TGA",  alpha=True,  anim=False, quality=False),
    "PDF":  dict(label="PDF",  ext=".pdf",  pil="PDF",  alpha=False, anim=True,  quality=False),
}
_FEATURE = {"WEBP": "webp", "AVIF": "avif", "JPEG": "jpg"}
OUTPUTS = {k: v for k, v in _ALL_OUTPUTS.items()
           if v["pil"] in Image.SAVE and (k not in _FEATURE or features.check(_FEATURE[k]))}

# extensions Pillow can read (used when scanning folders)
READ_EXTS = {ext for ext, fmt in Image.registered_extensions().items() if fmt in Image.OPEN}
# readers that need outside programs (Ghostscript) or are scientific/obscure: skip in folder scans
READ_EXTS -= {".eps", ".ps", ".epsf", ".epsi", ".h5", ".hdf", ".grib", ".bufr", ".fits", ".fit"}

SIXTEEN_BIT = {"I;16", "I;16B", "I;16L", "I;16N", "I", "F"}


# ----------------------------------------------------------------------------- themes

THEMES: dict[str, dict] = {
    "socialab": dict(
        label="Socialab",
        title=APP_TITLE,
        hint="Drop your images into the hive",
        hint_media="Drop your videos and audio into the hive",
        fonts=[("Nunito Medium", 11), ("Segoe UI", 10), ("Helvetica Neue", 11), ("sans-serif", 11)],
        title_fonts=[("Fredoka SemiBold", 26), ("Segoe UI Semibold", 22), ("sans-serif", 22)],
        backdrop="honeycomb", logo="bee", stripes=True, credit=SOCIALAB_CREDIT,
        bg="#fdf1c7", panel="#fffaf0", panel_a=0.94, drop="#fff3c4", drop_a=0.92,
        drop_hover="#ffe27a", text="#241917", muted="#6e5a2e", accent="#f8c917",
        accent_text="#241917", title_color="#241917", drop_border="#241917",
        border="#241917", border_style="solid", border_w=2, radius=14, effect="soft",
    ),
    # Darker Socialab: night hive. Not in the theme list; the "Darker" toggle switches to it.
    "socialab_dark": dict(
        label="Socialab",
        title=APP_TITLE,
        hint="Drop your images into the hive",
        hint_media="Drop your videos and audio into the hive",
        fonts=[("Nunito Medium", 11), ("Segoe UI", 10), ("Helvetica Neue", 11), ("sans-serif", 11)],
        title_fonts=[("Fredoka SemiBold", 26), ("Segoe UI Semibold", 22), ("sans-serif", 22)],
        backdrop="honeycomb_dark", logo="bee", stripes=True, credit=SOCIALAB_CREDIT, bees=True,
        stripe_a="#f8c917", stripe_b="#0d0a06",
        bg="#120e08", panel="#1d170e", panel_a=0.88, drop="#271f12", drop_a=0.86,
        drop_hover="#3a2d12", text="#f6e8c3", muted="#b59c63", accent="#f8c917",
        accent_text="#1a1206", title_color="#f8c917", drop_border="#f8c917",
        border="#6b5118", border_style="solid", border_w=2, radius=14, effect="glow",
    ),
    # Western night: your desert-galaxy picture as the backdrop, brass and leather UI, horses on the trail.
    "frontier": dict(
        label="Frontier",
        title=APP_TITLE,
        hint="Rustle up your images and drop 'em here",
        hint_media="Rustle up your videos and audio and drop 'em here",
        fonts=[("Rokkitt Medium", 12), ("Rockwell", 11), ("Georgia", 11), ("serif", 11)],
        title_fonts=[("Rye", 25), ("Rockwell Extra Bold", 24), ("Georgia", 24), ("serif", 24)],
        backdrop="image", image="frontier_bg.jpg", logo="frontier", stripes="stitch", horses=True,
        bg="#141a3a", panel="#0d1130", panel_a=0.66, drop="#161b45", drop_a=0.46,
        drop_hover="#262c66", text="#f2e6cc", muted="#aba5cc", accent="#e2b25a",
        accent_text="#1a1206", title_color="#f1d595", drop_border="#e2b25a",
        border="#a8813a", border_style="solid", border_w=2, radius=6, effect="glow",
    ),
    "medieval": dict(
        label="Medieval",
        title="Universal Converter",    # blackletter capitals are unreadable, so title case here
        hint="Lay thy images upon this page",
        hint_media="Lay thy videos and audio upon this page",
        fonts=[("IM FELL English", 13), ("Book Antiqua", 12), ("Palatino Linotype", 12),
               ("Garamond", 13), ("Georgia", 12), ("serif", 12)],
        title_fonts=[("UnifrakturMaguntia", 30), ("Old English Text MT", 28),
                     ("IM FELL English", 26), ("Book Antiqua", 24), ("serif", 24)],
        backdrop="parchment",
        bg="#d8c296", panel="#f4e7c6", panel_a=0.90, drop="#fbf3dc", drop_a=0.80,
        drop_hover="#fff4cf", text="#3a2312", muted="#7a5d3c", accent="#7d1d1d",
        accent_text="#f8ecd0", border="#5e3f22", border_style="double", border_w=3,
        radius=3, effect="soft",
    ),
    "elden": dict(
        label="Elden-style dark fantasy",
        title=APP_TITLE,
        hint="Offer your images to the forge",
        hint_media="Offer your videos and audio to the forge",
        fonts=[("Cinzel", 11), ("Trajan Pro", 11), ("Cormorant Garamond", 13),
               ("Palatino Linotype", 12), ("Book Antiqua", 12), ("serif", 12)],
        title_fonts=[("Cinzel", 24), ("Trajan Pro", 24), ("Palatino Linotype", 24), ("serif", 24)],
        backdrop="ember",
        bg="#0c0a07", panel="#16130e", panel_a=0.88, drop="#1d1810", drop_a=0.82,
        drop_hover="#2b2312", text="#e3d3a6", muted="#93805a", accent="#cfa64e",
        accent_text="#120e07", border="#5c4a24", border_style="solid", border_w=1,
        radius=2, effect="glow",
    ),
    "pixel": dict(
        label="Pixel",
        title=APP_TITLE,
        hint="DROP IMAGES HERE",
        hint_media="DROP VIDEO & AUDIO HERE",
        fonts=[("Press Start 2P", 8.5), ("VT323", 16), ("Consolas", 11),
               ("Courier New", 11), ("monospace", 11)],
        title_fonts=[("Press Start 2P", 14), ("VT323", 32), ("Consolas", 22), ("monospace", 22)],
        backdrop="grid",
        bg="#1c1a3c", panel="#2c2a63", panel_a=1.0, drop="#23214f", drop_a=1.0,
        drop_hover="#38368a", text="#f6f6f6", muted="#a9a7da", accent="#ffd23f",
        accent_text="#1c1a3c", border="#000000", border_style="solid", border_w=4,
        radius=0, effect="hard",
    ),
}


def _hactor(img: str, motion: str, count: int, size: int, speed: float, **kw) -> dict:
    return dict(path=str(res_dir() / "assets" / "holidays" / img), motion=motion, count=count, size=size,
                speed=speed, spin=kw.get("spin", False), flip=kw.get("flip", True), opacity=kw.get("opacity", 1.0))


THEMES.update({
    "halloween": dict(
        label="Halloween", title=APP_TITLE,
        hint="Feed your images to the night", hint_media="Feed your videos and audio to the night",
        fonts=[("Rokkitt Medium", 12), ("Georgia", 11), ("serif", 11)],
        title_fonts=[("Creepster", 32), ("Georgia", 24), ("serif", 24)],
        backdrop="image", image="holidays/halloween_bg.jpg", logo="holidays/halloween_icon.png",
        stripes="bee", stripe_a="#ff8a1f", stripe_b="#12061c",
        bg="#12061c", panel="#170a22", panel_a=0.80, drop="#24102f", drop_a=0.60, drop_hover="#3a1846",
        text="#f6e6d6", muted="#c39ab8", accent="#ff8a1f", accent_text="#1a0a04", title_color="#ff9a2e",
        drop_border="#ff8a1f", border="#6e2a6e", border_style="solid", border_w=2, radius=8, effect="glow",
        actors=[_hactor("bat.webp", "fly", 5, 34, 110), _hactor("ghost.png", "float", 3, 46, 22, opacity=0.7)],
        burst=["pumpkin.png"], burst_size=56,
    ),
    "christmas": dict(
        label="Christmas", title=APP_TITLE,
        hint="Wrap up your images and drop them here", hint_media="Wrap up your videos and audio and drop them here",
        fonts=[("Nunito Medium", 11), ("Segoe UI", 10), ("sans-serif", 10)],
        title_fonts=[("Mountains of Christmas", 34), ("Georgia", 24), ("serif", 24)],
        backdrop="image", image="holidays/christmas_bg.jpg", logo="holidays/christmas_icon.png",
        stripes="bee", stripe_a="#e3343f", stripe_b="#ffffff",
        bg="#0b1a33", panel="#0e2244", panel_a=0.78, drop="#12305a", drop_a=0.60, drop_hover="#1b4278",
        text="#fff8ee", muted="#b9cde6", accent="#e3343f", accent_text="#fff8ee", title_color="#ffd86b",
        drop_border="#ffd86b", border="#2f7a52", border_style="solid", border_w=2, radius=12, effect="glow",
        actors=[_hactor("snowflake.png", "fall", 28, 18, 45, spin=True, opacity=0.9)],
        burst=["present0.png", "present1.png", "present2.png", "present3.png"], burst_size=54,
    ),
    "newyear": dict(
        label="New Year", title=APP_TITLE,
        hint="Drop your images and count down", hint_media="Drop your videos and audio and count down",
        fonts=[("Nunito Medium", 11), ("Segoe UI", 10), ("sans-serif", 10)],
        title_fonts=[("Monoton", 26), ("Segoe UI Semibold", 22), ("sans-serif", 22)],
        backdrop="image", image="holidays/newyear_bg.jpg", logo="holidays/newyear_icon.png",
        stripes="bee", stripe_a="#ffcc4d", stripe_b="#0a0818",
        bg="#0a0818", panel="#120e2a", panel_a=0.78, drop="#1c1640", drop_a=0.60, drop_hover="#2a2160",
        text="#fff4e0", muted="#b6a8d8", accent="#ffcc4d", accent_text="#1a1206", title_color="#ffd76a",
        drop_border="#ffcc4d", border="#6d58b8", border_style="solid", border_w=2, radius=10, effect="glow",
        actors=[_hactor("confetti.webp", "fall", 14, 14, 70, spin=True, opacity=0.9)],
        fireworks=True, burst=["fireworks"],
    ),
    "easter": dict(
        label="Easter", title=APP_TITLE,
        hint="Hide your images in here", hint_media="Hide your videos and audio in here",
        fonts=[("Nunito Medium", 11), ("Segoe UI", 10), ("sans-serif", 10)],
        title_fonts=[("Pacifico", 28), ("Segoe UI Semibold", 22), ("sans-serif", 22)],
        backdrop="image", image="holidays/easter_bg.jpg", logo="holidays/easter_icon.png",
        stripes="bee", stripe_a="#ffd1e8", stripe_b="#b8f0d0",
        bg="#cfe9fb", panel="#ffffff", panel_a=0.84, drop="#fff6fb", drop_a=0.80, drop_hover="#ffe3f1",
        text="#3b2f4a", muted="#7c6d8f", accent="#ff7eb6", accent_text="#ffffff", title_color="#ff6fae",
        drop_border="#ff7eb6", border="#b9a3e3", border_style="solid", border_w=2, radius=18, effect="soft",
        actors=[_hactor("butterfly.webp", "fly", 5, 30, 70)],
        burst=["egg0.png", "egg1.png", "egg2.png", "egg3.png", "egg4.png"], burst_size=46,
    ),
    "aprilfools": dict(
        label="April Fools", title=APP_TITLE, credit="by zeharyus (allegedly)",
        hint=APRIL_HINTS[0], hint_media=APRIL_HINTS_MEDIA[0],
        fonts=[("Comic Neue", 12), ("Comic Sans MS", 11), ("sans-serif", 11)],
        title_fonts=[("Comic Neue", 28), ("Comic Sans MS", 24), ("sans-serif", 24)],
        backdrop="image", image="holidays/aprilfools_bg.jpg", logo="holidays/aprilfools_icon.png",
        stripes="bee", stripe_a="#ff3fa4", stripe_b="#ffe600",
        bg="#2a0d3a", panel="#1b0f2e", panel_a=0.84, drop="#2b1748", drop_a=0.72, drop_hover="#3d2066",
        text="#fffbe6", muted="#ffd76a", accent="#00e0ff", accent_text="#1b0f2e", title_color="#ffe600",
        drop_border="#39ff88", border="#ff3fa4", border_style="dashed", border_w=3, radius=22, effect="hard",
        actors=[_hactor("duck.png", "bounce", 4, 44, 150), _hactor("confetti.webp", "fall", 10, 14, 80, spin=True)],
        burst=["duck.png"], burst_size=52, troll=True,
    ),
})

BUILTIN_ORDER = ["socialab", "frontier", "medieval", "elden", "pixel"] + HOLIDAY_KEYS
THEME_ORDER = BUILTIN_ORDER + ["custom"]          # rebuilt by load_theme_folder()
CUSTOM_LABEL = "Custom wallpaper"
RESERVED_KEYS = {"socialab", "socialab_dark", "frontier", "custom", *HOLIDAY_KEYS}   # can't be replaced from the folder
EXPORT_KEYS = ["medieval", "elden", "pixel"]                          # written to the folder as editable examples

# Everything a theme can set. Missing keys take these values.
THEME_DEFAULTS = dict(
    label="My theme", title=APP_TITLE, hint="Drop your files here",
    fonts=[["Segoe UI", 10], ["Helvetica Neue", 11], ["sans-serif", 10]],
    title_fonts=[["Segoe UI Semibold", 22], ["sans-serif", 22]],
    backdrop="color", image="", logo="crow",
    bg="#1e1e24", panel="#2a2a33", panel_a=0.92, drop="#33333d", drop_a=0.9, drop_hover="#40404c",
    text="#ececf1", muted="#a0a0ad", accent="#5b8cff", accent_text="#ffffff", border="#4a4a57",
    border_style="solid", border_w=1, radius=6, effect="none",
)
COLOR_KEYS = ("bg", "panel", "drop", "drop_hover", "text", "muted", "accent", "accent_text", "border",
              "title_color", "drop_border", "stripe_a", "stripe_b")
BACKDROPS = {"color", "image", "parchment", "ember", "grid", "honeycomb", "honeycomb_dark"}
EFFECTS = {"none", "soft", "glow", "hard"}
THEME_PROBLEMS: list[str] = []


def themes_dir() -> Path:
    d = base_dir() / "themes"
    try:
        d.mkdir(exist_ok=True)
        probe = d / ".write_test"
        probe.write_text("ok")
        probe.unlink()
        return d
    except OSError:
        d = data_dir() / "themes"
        d.mkdir(parents=True, exist_ok=True)
        return d


THEMES_README = """UNIVERSAL CONVERTER - themes
============================

Every folder in here that contains a theme.json is a theme. The folder name is the theme's id.
Restart the app (or use More > Reload themes) after adding or editing one.

Make your own: copy the _template folder, rename the copy (e.g. "ocean"), edit its theme.json,
and drop your pictures and fonts into that folder. Folders starting with "_" are ignored.

theme.json keys (anything you leave out uses a sensible default):
  label          name shown in the Theme list
  title          big title text
  hint           text inside the drop area in Images mode
  hint_media     text inside the drop area in Video & Audio mode
  fonts          [["Font name", size], ...]  first one installed wins (.ttf/.otf files in the folder are loaded)
  title_fonts    same, for the title
  backdrop       color | image | parchment | ember | grid | honeycomb | honeycomb_dark
  image          picture file in this folder, used when backdrop is "image"
  logo           .png or .ico file in this folder (header, window and shortcut icon)
  bg panel drop drop_hover text muted accent accent_text border    colours, "#rrggbb"
  title_color drop_border                                            optional colours
  panel_a drop_a opacities 0..1 (lower = more of the background shows through)
  border_style   solid | double | dashed      border_w  pixels      radius  corner roundness
  effect         none | soft | glow | hard    (shadow on the header and drop area)
  stripes        false | "bee" | "stitch"     (band under the title; stripe_a / stripe_b colours)
  horses         true = little horses gallop along the bottom
  bees           true = little bees fly around the window

Animated backgrounds: "image" can be an animated GIF or animated WebP. Want a video as the
background? Convert it to an animated WebP or GIF with this app first (keep it short and small).

Your own moving things ("actors"): a list of pictures that move around the window.
  "actors": [
    {"image": "bird.webp", "motion": "fly",  "count": 4,  "size": 40, "speed": 90},
    {"image": "leaf.png",  "motion": "fall", "count": 12, "size": 24, "speed": 60, "spin": true},
    {"image": "car.gif",   "motion": "run",  "count": 3,  "size": 48, "speed": 160}
  ]
  image    PNG, or an animated GIF / WebP / PNG in the theme folder. Draw it facing RIGHT.
           Soft edges (glows, shadows) need WebP or PNG; GIF only has hard see-through edges.
  motion   fly    wanders around the whole window (like the bees)
           run    runs left/right along a strip at the bottom (like the horses)
           fall   drifts down from the top (snow, leaves, petals)
           float  drifts up from the bottom (bubbles, fireflies, sparks)
           bounce bounces off the window edges
  count    how many (1-30)            size   height in pixels (8-256)
  speed    pixels per second          spin   true = slowly rotates (good for fall/float/run)
  flip     false = never mirror it when it moves left (default true)
  opacity  0..1 (default 1)

The "example_theme" folder is a complete, working theme (it shows up as "Example Theme"): a
background picture, a logo, its own font, flying birds, floating fireflies and rolling
tumbleweeds. Its theme.json explains every line. The easiest way to start: copy that folder,
rename the copy, change things, and Reload themes. The example is created only once, the first
time the app runs; if you delete it, it stays deleted.

The built-in themes were copied here as examples. Editing them changes them; deleting one brings
the original back the next time the app starts.
"""


def _theme_to_json(key: str, t: dict, folder: Path) -> dict:
    """Copy a built-in theme into its own folder with its pictures, ready to edit."""
    out = {k: v for k, v in t.items() if not k.startswith("_")}
    logo = t.get("logo", "crow")
    if logo in LOGO_FILES:
        for name in LOGO_FILES[logo]:
            src = res_dir() / "assets" / name
            if src.is_file():
                (folder / ("logo" + src.suffix)).write_bytes(src.read_bytes())
        out["logo"] = "logo.png"
    if t.get("image"):
        src = res_dir() / "assets" / t["image"]
        if src.is_file():
            (folder / ("background" + src.suffix)).write_bytes(src.read_bytes())
            out["image"] = "background" + src.suffix
    out["fonts"] = [list(f) for f in t["fonts"]]
    out["title_fonts"] = [list(f) for f in t["title_fonts"]]
    return out


EXAMPLE_THEME = {
    "_READ_ME_FIRST": [
        "This is a normal theme, exactly like one you would make. Copy this whole folder,",
        "rename the copy (for example 'my_theme'), edit the copy's theme.json in Notepad,",
        "then in the app click More > Reload themes. Lines starting with _ are notes: the app ignores them.",
        "Every picture and font named below must be inside this same folder.",
    ],
    "label": "Example Theme",
    "_label": "The name shown in the Theme list.",
    "title": "UNIVERSAL CONVERTER",
    "hint": "Drop your images on the prairie",
    "hint_media": "Drop your videos and audio on the prairie",
    "_hint": "hint = drop-area text in Images mode, hint_media = in Video & Audio mode.",
    "fonts": [["Rokkitt Medium", 12], ["Georgia", 11], ["serif", 11]],
    "title_fonts": [["Rye", 25], ["Georgia", 24], ["serif", 24]],
    "_fonts": "[font name, size]. The first one that exists is used. Rye.ttf is in this folder, so the app loads it. Use the font's real name (double-click the .ttf to see it), not the file name.",
    "backdrop": "image",
    "image": "background.png",
    "_backdrop": "backdrop: image | color | parchment | ember | grid | honeycomb | honeycomb_dark. With image, 'image' is a picture in this folder (an animated GIF or WebP also works).",
    "logo": "logo.png",
    "_logo": "Shown in the header, on the window and on the desktop shortcut. Square pictures look best.",
    "bg": "#26184a",
    "panel": "#2a1838",
    "panel_a": 0.72,
    "drop": "#3a2147",
    "drop_a": 0.55,
    "drop_hover": "#55305f",
    "text": "#ffeedd",
    "muted": "#e0b39a",
    "accent": "#ffb15c",
    "accent_text": "#2a1222",
    "border": "#c4545c",
    "_colours": "Colours are #rrggbb codes. accent = buttons/highlights, accent_text = text on the accent colour, text = normal text, muted = small text, panel = the boxes, drop = the drop area, border = outlines, bg = shown when there is no picture. panel_a / drop_a = how solid the boxes are (0 = invisible, 1 = solid).",
    "radius": 10,
    "border_style": "solid",
    "border_w": 2,
    "effect": "glow",
    "stripes": "stitch",
    "_shape": "radius = corner roundness, border_style = solid | double | dashed, border_w = outline thickness, effect = none | soft | glow | hard, stripes = false | bee | stitch (the band under the title).",
    "actors": [
        {"image": "bird.webp", "motion": "fly", "count": 3, "size": 34, "speed": 90,
         "_note": "An animated WebP (wings flap). fly = wanders around the whole window."},
        {"image": "firefly.webp", "motion": "float", "count": 10, "size": 22, "speed": 18, "opacity": 0.9,
         "_note": "float = drifts up from the bottom. opacity 0.9 = slightly see-through."},
        {"image": "tumbleweed.png", "motion": "run", "count": 2, "size": 36, "speed": 140, "spin": True,
         "_note": "run = crosses a strip at the bottom. spin = rolls while it moves. Other motions: fall, bounce."},
    ],
    "_actors": "Moving pictures. Draw them facing right; they are mirrored when they move left (\"flip\": false turns that off). count 1-30, size = height in pixels, speed = pixels per second.",
}

EXAMPLE_COPY_HOWTO = """HOW TO MAKE YOUR OWN THEME FROM THIS ONE

1. Go back to the themes folder and copy this whole "example_theme" folder.
2. Rename the copy, for example "my_theme" (letters, numbers and _ are safest).
3. Inside the copy: replace background.png and logo.png with your own pictures
   (keep the names, or change the names in theme.json to match).
4. Open theme.json with Notepad and change "label" to your theme's name,
   then change colours, texts and moving pictures as you like. Save.
5. In the app: More > Reload themes, then pick your theme from the Theme list.

If your theme doesn't appear, the line at the bottom of the app says why
(usually a missing comma or quote in theme.json).
"""


def export_builtin_themes(root: Path) -> None:
    """Write the built-in themes (not the hidden one) into the folder, once each."""
    try:
        (root / "README.txt").write_text(THEMES_README, encoding="utf-8")
        tpl = root / "_template"
        if not (tpl / "theme.json").exists():
            tpl.mkdir(exist_ok=True)
            sample = dict(THEME_DEFAULTS, label="My theme", hint="Drop your files here",
                          backdrop="color", logo="logo.png")
            (tpl / "theme.json").write_text(json.dumps(sample, indent=2), encoding="utf-8")
            src = res_dir() / "assets" / "icon.png"
            if src.is_file():
                (tpl / "logo.png").write_bytes(src.read_bytes())
        # The example theme is a normal user theme: written once, on first run, never re-created.
        marker = data_dir() / "example_theme_created"
        src_dir = res_dir() / "assets" / "example_animated"
        if src_dir.is_dir() and not marker.exists():
            ex = root / "example_theme"
            if not (ex / "theme.json").exists():
                ex.mkdir(exist_ok=True)
                for f in src_dir.iterdir():
                    (ex / f.name).write_bytes(f.read_bytes())
                (ex / "theme.json").write_text(json.dumps(EXAMPLE_THEME, indent=2), encoding="utf-8")
                (ex / "HOW TO COPY THIS THEME.txt").write_text(EXAMPLE_COPY_HOWTO, encoding="utf-8")
            marker.write_text("The example theme was created once. Delete this file to get it back.\n",
                              encoding="utf-8")
        for key in EXPORT_KEYS:
            folder = root / key
            if (folder / "theme.json").exists():
                continue
            folder.mkdir(exist_ok=True)
            data = _theme_to_json(key, THEMES[key], folder)
            (folder / "theme.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


MOTIONS = {"fly", "run", "fall", "float", "bounce"}


def _clean_actors(raw, folder: Path) -> list[dict]:
    out = []
    if not isinstance(raw, list):
        raise ValueError("'actors' must be a list [ ... ]")
    for i, a in enumerate(raw[:12], 1):
        if not isinstance(a, dict) or not a.get("image"):
            raise ValueError(f"actor {i} needs an \"image\"")
        path = folder / str(a["image"])
        if not path.is_file():
            raise ValueError(f"actor {i}: can't find {a['image']}")
        motion = str(a.get("motion", "fly")).lower()
        if motion not in MOTIONS:
            raise ValueError(f"actor {i}: motion must be one of {', '.join(sorted(MOTIONS))}")
        out.append(dict(path=str(path), motion=motion,
                        count=max(1, min(30, int(a.get("count", 3)))),
                        size=max(8, min(256, int(a.get("size", 40)))),
                        speed=max(5.0, min(800.0, float(a.get("speed", 80)))),
                        spin=bool(a.get("spin", False)), flip=bool(a.get("flip", True)),
                        opacity=max(0.05, min(1.0, float(a.get("opacity", 1.0))))))
    return out


def _clean_theme(raw: dict, folder: Path) -> dict:
    t = dict(THEME_DEFAULTS)
    t.update({k: v for k, v in raw.items() if not str(k).startswith("_")})
    for k in COLOR_KEYS:
        if k in t and not QColor(str(t[k])).isValid():
            raise ValueError(f"'{k}' is not a colour: {t[k]!r}")
    for k in ("panel_a", "drop_a"):
        t[k] = max(0.0, min(1.0, float(t[k])))
    for k in ("border_w", "radius"):
        t[k] = max(0, int(t[k]))
    if t["backdrop"] not in BACKDROPS:
        raise ValueError(f"unknown backdrop '{t['backdrop']}'")
    if t["effect"] not in EFFECTS:
        t["effect"] = "none"
    if t["border_style"] not in ("solid", "double", "dashed", "dotted"):
        t["border_style"] = "solid"
    for k in ("fonts", "title_fonts"):
        t[k] = [(str(f[0]), float(f[1])) for f in t[k] if isinstance(f, (list, tuple)) and len(f) == 2]
        if not t[k]:
            t[k] = [tuple(f) for f in THEME_DEFAULTS[k]]
    t["actors"] = _clean_actors(t.get("actors", []), folder) if t.get("actors") else []
    t["_dir"] = str(folder)
    return t


def load_theme_folder() -> None:
    """Read every theme folder. Folder themes replace built-ins of the same id and add new ones."""
    global THEME_ORDER
    THEME_PROBLEMS.clear()
    root = themes_dir()
    export_builtin_themes(root)
    extra = []
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        key = folder.name
        if key.startswith("_") or key.startswith(".") or not (folder / "theme.json").is_file():
            continue
        if key.lower() in RESERVED_KEYS:
            if key.lower() == "custom":          # hidden themes' names are skipped silently
                THEME_PROBLEMS.append(f"{key}: that name is reserved")
            continue
        try:
            raw = json.loads((folder / "theme.json").read_text(encoding="utf-8-sig"))
            if not isinstance(raw, dict):
                raise ValueError("theme.json must be a { ... } object")
            for f in folder.iterdir():
                if f.suffix.lower() in (".ttf", ".otf"):
                    QFontDatabase.addApplicationFont(str(f))
            THEMES[key] = _clean_theme(raw, folder)
            if key not in BUILTIN_ORDER:
                extra.append(key)
        except Exception as e:            # a broken theme is skipped, never fatal
            THEME_PROBLEMS.append(f"{key}: {e}")
    extra.sort(key=lambda k: str(THEMES[k].get("label", k)).lower())
    THEME_ORDER = BUILTIN_ORDER + extra + ["custom"]


def rgba(hex_color: str, alpha: float) -> str:
    c = QColor(hex_color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {int(round(alpha * 255))})"


def build_qss(t: dict, family: str, pt: float, title_family: str, title_pt: float) -> str:
    bw, bs, r = t["border_w"], t["border_style"], t["radius"]
    border = f"{bw}px {bs} {t['border']}"
    thin = f"{min(bw, 2) if bs != 'double' else 3}px {bs} {t['border']}"
    panel = rgba(t["panel"], t["panel_a"])
    drop = rgba(t["drop"], t["drop_a"])
    hover = rgba(t["drop_hover"], max(t["drop_a"], 0.9))
    dashw = max(2, min(bw, 3))
    dropb = t.get("drop_border", t["accent"])
    return f"""
    QWidget {{ font-family: "{family}"; font-size: {pt}pt; color: {t['text']} }}
    QLabel {{ background: transparent; }}
    QDialog, QMessageBox {{ background: {t['panel']}; }}
    QDialog QAbstractItemView, QDialog QLineEdit {{ background: {t['drop']}; }}

    QFrame#card {{ background: {panel}; border: {border}; border-radius: {r}px; }}
    QFrame#dropZone {{ background: {drop}; border: {dashw}px dashed {dropb}; border-radius: {r}px; }}
    QFrame#dropZone[hover="true"] {{ background: {hover}; border: {dashw}px solid {dropb}; }}

    QLabel#title {{ font-family: "{title_family}"; font-size: {title_pt}pt; color: {t.get('title_color', t['accent'])}; }}
    QLabel#subtitle, QLabel#muted {{ color: {t['muted']}; }}
    QLabel#dropHint {{ font-size: {round(pt * 1.45, 1)}pt; }}

    QPushButton {{ background: {drop}; border: {thin}; border-radius: {r}px; padding: 6px 14px; }}
    QPushButton:hover, QPushButton:focus {{ background: {t['accent']}; color: {t['accent_text']}; }}
    QPushButton:pressed {{ background: {t['border']}; color: {t['text']}; }}
    QPushButton:disabled {{ color: {t['muted']}; background: transparent; }}
    QPushButton#modeBtn {{ border-radius: 0px; padding: 6px 16px; }}
    QPushButton#modeBtn:checked {{ background: {t['accent']}; color: {t['accent_text']}; }}

    QComboBox {{ background: {drop}; border: {thin}; border-radius: {r}px; padding: 5px 10px; }}
    QComboBox:focus {{ border-color: {t['accent']}; }}
    QComboBox::drop-down {{ border: none; width: 22px; }}
    QComboBox QAbstractItemView {{ background: {t['panel']}; border: {thin}; outline: none;
        selection-background-color: {t['accent']}; selection-color: {t['accent_text']}; }}

    QSlider::groove:horizontal {{ height: 6px; background: {drop}; border: 1px solid {t['border']};
        border-radius: {min(r, 3)}px; }}
    QSlider::sub-page:horizontal {{ background: {t['accent']}; border-radius: {min(r, 3)}px; }}
    QSlider::handle:horizontal {{ background: {t['accent']}; border: 1px solid {t['border']};
        width: 14px; margin: -6px 0; border-radius: {min(r, 7)}px; }}

    QListWidget#log {{ background: {drop}; border: {thin}; border-radius: {r}px; padding: 4px; outline: none; }}
    QListWidget#log::item {{ padding: 3px 4px; }}
    QListWidget#log::item:selected {{ background: {t['accent']}; color: {t['accent_text']}; }}

    QProgressBar {{ background: {drop}; border: {thin}; border-radius: {r}px;
        min-height: 14px; max-height: 14px; }}
    QProgressBar::chunk {{ background: {t['accent']}; }}

    QCheckBox {{ spacing: 8px; background: transparent; }}
    QCheckBox::indicator {{ width: 14px; height: 14px; border: {thin}; background: {drop};
        border-radius: {min(r, 3)}px; }}
    QCheckBox::indicator:checked {{ background: {t['accent']}; }}

    QToolTip {{ background: {t['panel']}; color: {t['text']}; border: 1px solid {t['accent']}; padding: 4px; }}
    QFrame#banner {{ background: {t['panel']}; border: 3px solid {t.get('title_color', t['accent'])};
        border-radius: {r + 6}px; }}
    QLabel#bannerTitle {{ font-family: "{title_family}"; font-size: {round(title_pt * 0.9, 1)}pt;
        color: {t.get('title_color', t['accent'])}; }}
    QLabel#bannerText {{ font-size: {round(pt * 1.15, 1)}pt; }}
    QToolButton {{ background: {drop}; border: {thin}; border-radius: {r}px; padding: 6px 14px; }}
    QToolButton:hover {{ background: {t['accent']}; color: {t['accent_text']}; }}
    QToolButton::menu-indicator {{ image: none; width: 0; }}
    QMenu {{ background: {t['panel']}; border: 1px solid {t['border']}; padding: 4px; }}
    QMenu::item {{ padding: 6px 18px; background: transparent; }}
    QMenu::item:selected {{ background: {t['accent']}; color: {t['accent_text']}; }}
    QMenu::item:disabled {{ color: {t['muted']}; }}
    QMenu::separator {{ height: 1px; background: {t['border']}; margin: 4px 8px; }}

    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {t['border']}; min-height: 24px; border-radius: {min(r, 4)}px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
    """


# ----------------------------------------------------------------------------- wallpaper palette

def _hex(rgb) -> str:
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(c)))) for c in rgb)


def _lum(rgb) -> float:
    def ch(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def _contrast(a, b) -> float:
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _to_hls(rgb):
    return colorsys.rgb_to_hls(*(c / 255 for c in rgb))


def _from_hls(h, l, s):
    return tuple(round(c * 255) for c in colorsys.hls_to_rgb(h, max(0, min(1, l)), max(0, min(1, s))))


def wallpaper_colors(path: Path) -> dict:
    """Derive a readable UI palette from an image: panels tinted with its dominant colour,
    accent from its most characterful colour, contrast checked against the panels."""
    with Image.open(path) as im:
        small = im.convert("RGB")
    small.thumbnail((160, 160))
    q = small.quantize(colors=8, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()
    counts = q.getcolors() or []
    total = sum(c for c, _ in counts) or 1
    cols = sorted(((c / total, tuple(pal[i * 3:i * 3 + 3])) for c, i in counts), reverse=True)

    dark = sum(w * _lum(rgb) for w, rgb in cols) < 0.35
    h, _, s = _to_hls(cols[0][1])
    s_panel = min(s, 0.35)
    panel = _from_hls(h, 0.11 if dark else 0.93, s_panel)
    drop = _from_hls(h, 0.17 if dark else 0.87, s_panel)
    hover = _from_hls(h, 0.24 if dark else 0.80, s_panel)
    text = _from_hls(h, 0.93 if dark else 0.10, min(s, 0.25))
    muted = _from_hls(h, 0.70 if dark else 0.35, min(s, 0.20))

    best, best_score = (h, 0.0), -1.0
    for w, rgb in cols:
        hh, ll, ss = _to_hls(rgb)
        score = ss * (w ** 0.5) * (1 - abs(ll - 0.5))
        if score > best_score:
            best, best_score = (hh, ss), score
    ah, asat = best
    if asat < 0.12:          # near-greyscale wallpaper: neutral accent
        asat, al = 0.0, (0.80 if dark else 0.25)
    else:
        asat, al = max(asat, 0.55), (0.62 if dark else 0.38)
    accent = _from_hls(ah, al, asat)
    for _ in range(25):
        if _contrast(accent, panel) >= 3.2:
            break
        al = al + 0.03 if dark else al - 0.03
        accent = _from_hls(ah, al, asat)
    ink_dark, ink_light = (14, 12, 10), (250, 248, 244)
    accent_text = ink_dark if _contrast(accent, ink_dark) >= _contrast(accent, ink_light) else ink_light
    border = _from_hls(ah, 0.42 if dark else 0.58, min(asat, 0.45))

    return dict(bg=_hex(panel), panel=_hex(panel), panel_a=0.80, drop=_hex(drop), drop_a=0.62,
                drop_hover=_hex(hover), text=_hex(text), muted=_hex(muted), accent=_hex(accent),
                accent_text=_hex(accent_text), border=_hex(border))


# ----------------------------------------------------------------------------- conversion

def sniff_format(p: Path) -> str | None:
    """Pillow's format name if Pillow can open the file, else None (reads only the header)."""
    try:
        with Image.open(p) as im:
            return im.format
    except Exception:
        return None


def collect_images(paths) -> tuple[list[tuple[Path, str]], int]:
    """Files and folders (recursive) -> [(path, format)]. Checks content, not just the
    extension. Returns (images, skipped_count)."""
    found, seen, skipped = [], set(), 0
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            cands = (c for c in p.rglob("*") if c.is_file() and c.suffix.lower() in READ_EXTS)
        elif p.is_file():
            cands = [p]
        else:
            continue
        for c in cands:
            key = os.path.normcase(str(c.resolve()))
            if key in seen:
                continue
            seen.add(key)
            fmt = sniff_format(c)
            if fmt:
                found.append((c, fmt))
            else:
                skipped += 1
    return found, skipped


def _claim(base: Path):
    """Atomically create a new output file; never overwrites ('name (1).png' etc.)."""
    i = 0
    while True:
        p = base if i == 0 else base.with_name(f"{base.stem} ({i}){base.suffix}")
        try:
            return p, open(p, "x+b")   # read+write: multi-page TIFF needs it
        except FileExistsError:
            i += 1


def _write(base: Path, writer) -> Path:
    p, fh = _claim(base)
    try:
        with fh:
            writer(fh)
    except Exception:
        try:
            p.unlink()
        except OSError:
            pass
        raise
    return p


def _has_alpha(im: Image.Image) -> bool:
    return "A" in im.getbands() or "transparency" in im.info


def _to_rgb_family(im: Image.Image, icc: bytes | None, key: str):
    """Bring odd modes (CMYK, 16-bit, palette, ...) into L / RGB / RGBA. Returns (image, icc)."""
    if im.mode == "CMYK":
        if icc:
            try:
                src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
                dst = ImageCms.createProfile("sRGB")
                im = ImageCms.profileToProfile(im, src, dst, outputMode="RGB")
                return im, None            # pixels are now plain sRGB
            except Exception:
                pass
        return im.convert("RGB"), None
    if im.mode in SIXTEEN_BIT:
        if key in ("PNG", "TIFF") and im.mode.startswith("I;16"):
            return im, icc                 # these formats keep 16-bit greyscale
        return im.convert("I").point(lambda v: v * (1 / 256)).convert("L"), icc
    if im.mode in ("L", "RGB", "RGBA"):
        return im, icc
    return im.convert("RGBA" if _has_alpha(im) else "RGB"), icc


def _prepare(im: Image.Image, key: str, want_alpha: bool, fill: tuple, icc):
    spec = OUTPUTS[key]
    im, icc = _to_rgb_family(im, icc, key)
    if want_alpha and spec["alpha"]:
        return (im if im.mode == "RGBA" else im.convert("RGBA")), icc
    if want_alpha:                         # target has no transparency: flatten onto fill colour
        rgba_im = im.convert("RGBA")
        bg = Image.new("RGB", rgba_im.size, fill)
        bg.paste(rgba_im, mask=rgba_im.getchannel("A"))
        return bg, icc
    if im.mode == "L" or im.mode.startswith("I;16"):
        if key in ("GIF", "ICO", "TGA", "PDF", "BMP", "WEBP", "AVIF"):
            return im.convert("RGB") if im.mode != "L" else im, icc
        return im, icc
    return (im if im.mode == "RGB" else im.convert("RGB")), icc


def _save_kwargs(key: str, opts: dict, icc, exif) -> dict:
    kw: dict = {}
    q = int(opts.get("quality", 90))
    if key == "JPEG":
        kw.update(quality=q, optimize=True, subsampling=0 if q >= 90 else 2)
    elif key == "WEBP":
        kw.update(quality=q, lossless=bool(opts.get("lossless")), method=4)
    elif key == "AVIF":
        kw.update(quality=q)
    elif key == "TIFF":
        kw.update(compression="tiff_lzw")
    elif key == "PNG":
        kw.update(optimize=False)
    elif key == "PDF":
        kw.update(resolution=96.0)
    if icc and key in ("PNG", "JPEG", "WEBP", "AVIF", "TIFF"):
        kw["icc_profile"] = icc
    if exif and key in ("PNG", "JPEG", "WEBP", "AVIF", "TIFF"):
        kw["exif"] = exif
    return kw


def _square_for_icon(im: Image.Image) -> Image.Image:
    im = im.convert("RGBA")
    side = max(im.size)
    if im.width == im.height:
        return im
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(im, ((side - im.width) // 2, (side - im.height) // 2))
    return canvas


def convert_image(src: Path, out_dir: Path, key: str, opts: dict) -> tuple[list[Path], str]:
    spec = OUTPUTS[key]
    pil = spec["pil"]
    fill = tuple(opts.get("fill", (255, 255, 255)))
    with Image.open(src) as im:
        icc = im.info.get("icc_profile")
        n = getattr(im, "n_frames", 1)
        anim = opts.get("anim", "keep")
        stem = src.stem

        # ---- every frame as its own file
        if n > 1 and anim == "all":
            outs = []
            for i, fr in enumerate(ImageSequence.Iterator(im), 1):
                img, icc2 = _prepare(fr.copy(), key, _has_alpha(fr), fill, icc)
                if key == "ICO":
                    img = _square_for_icon(img)
                kw = _save_kwargs(key, opts, icc2, None)
                outs.append(_write(out_dir / f"{stem}_frame{i:03d}{spec['ext']}",
                                   lambda fh, img=img, kw=kw: img.save(fh, pil, **kw)))
            return outs, f"{n} frames as separate files"

        # ---- keep the animation in one file
        if n > 1 and anim == "keep" and spec["anim"]:
            raw = [fr.copy() for fr in ImageSequence.Iterator(im)]
            durations = [fr.info.get("duration", im.info.get("duration", 100)) or 100 for fr in raw]
            alpha = any(_has_alpha(fr) for fr in raw)
            frames, icc2 = [], icc
            for fr in raw:
                img, icc2 = _prepare(fr, key, alpha, fill, icc)
                frames.append(img)
            kw = _save_kwargs(key, opts, icc2, None)
            if key in ("GIF", "PNG", "WEBP", "AVIF"):
                kw.update(duration=durations, loop=im.info.get("loop", 0))
            if key == "GIF":
                kw.update(disposal=2)
            first, rest = frames[0], frames[1:]
            out = _write(out_dir / f"{stem}{spec['ext']}",
                         lambda fh: first.save(fh, pil, save_all=True, append_images=rest, **kw))
            return [out], f"{n} frames, animated" if key != "PDF" and key != "TIFF" else f"{n} pages"

        # ---- single image (first frame)
        im.seek(0)
        frame = ImageOps.exif_transpose(im)        # apply camera rotation to the pixels
        exif_obj = frame.getexif()
        exif = exif_obj.tobytes() if len(exif_obj) else None
        img, icc2 = _prepare(frame, key, _has_alpha(frame), fill, icc)
        if key == "ICO":
            img = _square_for_icon(img)
            sizes = [(s, s) for s in (16, 24, 32, 48, 64, 128, 256) if s <= img.width] or [img.size]
            kw = {"sizes": sizes}
        else:
            kw = _save_kwargs(key, opts, icc2, exif)
        note = ""
        if n > 1:
            note = "animated: first frame only" + ("" if anim == "first" else f" ({spec['label']} can't animate)")
        out = _write(out_dir / f"{stem}{spec['ext']}", lambda fh: img.save(fh, pil, **kw))
        return [out], note


# ----------------------------------------------------------------------------- video & audio (FFmpeg)

MEDIA_EXTS = {".mp4", ".m4v", ".mkv", ".mov", ".avi", ".webm", ".flv", ".wmv", ".mpg", ".mpeg", ".ts", ".mts",
              ".m2ts", ".3gp", ".ogv", ".vob", ".gif", ".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg", ".oga",
              ".opus", ".wma", ".aiff", ".aif", ".ac3", ".amr", ".mka"}

# id -> (label, ffmpeg encoder)
VCODECS = {"h264": ("H.264", "libx264"), "hevc": ("H.265 / HEVC", "libx265"), "vp9": ("VP9", "libvpx-vp9"),
           "av1": ("AV1 (very slow)", "libaom-av1"), "mpeg4": ("MPEG-4 Part 2", "mpeg4"),
           "copy": ("Keep original (no re-encode)", "copy")}
ACODECS = {"aac": ("AAC", "aac"), "mp3": ("MP3", "libmp3lame"), "opus": ("Opus", "libopus"),
           "vorbis": ("Vorbis", "libvorbis"), "flac": ("FLAC (lossless)", "flac"), "pcm": ("PCM (WAV)", "pcm_s16le"),
           "copy": ("Keep original", "copy"), "none": ("No audio", None)}
MEDIA_OUTPUTS = {
    "MP4":  dict(label="MP4",  ext=".mp4",  kind="video", v=["h264", "hevc", "av1", "copy"], a=["aac", "mp3", "opus", "copy", "none"]),
    "MKV":  dict(label="MKV",  ext=".mkv",  kind="video", v=["h264", "hevc", "vp9", "av1", "copy"],
                 a=["aac", "opus", "mp3", "vorbis", "flac", "copy", "none"]),
    "WEBM": dict(label="WebM", ext=".webm", kind="video", v=["vp9", "av1"], a=["opus", "vorbis", "none"]),
    "MOV":  dict(label="MOV",  ext=".mov",  kind="video", v=["h264", "hevc", "copy"], a=["aac", "copy", "none"]),
    "AVI":  dict(label="AVI",  ext=".avi",  kind="video", v=["mpeg4", "h264"], a=["mp3", "none"]),
    "GIF":  dict(label="GIF (animated)", ext=".gif", kind="gif", v=[], a=[]),
    "MP3":  dict(label="MP3",  ext=".mp3",  kind="audio", v=[], a=["mp3"]),
    "M4A":  dict(label="M4A (AAC)", ext=".m4a", kind="audio", v=[], a=["aac"]),
    "WAV":  dict(label="WAV",  ext=".wav",  kind="audio", v=[], a=["pcm"]),
    "FLAC": dict(label="FLAC", ext=".flac", kind="audio", v=[], a=["flac"]),
    "OGG":  dict(label="OGG (Vorbis)", ext=".ogg", kind="audio", v=[], a=["vorbis"]),
    "OPUS": dict(label="Opus", ext=".opus", kind="audio", v=[], a=["opus"]),
}
SIZES = [(0, "Original size"), (2160, "4K (2160p)"), (1080, "1080p"), (720, "720p"), (480, "480p"), (360, "360p")]

_FFMPEG: str | None = None
_ENCODERS: set[str] | None = None


def ffmpeg_exe() -> str | None:
    """FFmpeg packed with the app (imageio-ffmpeg), else ffmpeg(.exe) next to the app, else on PATH."""
    global _FFMPEG
    if _FFMPEG is None:
        found = ""
        try:
            import imageio_ffmpeg
            found = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            pass
        if not found:
            for name in ("ffmpeg.exe", "ffmpeg"):
                if (base_dir() / name).is_file():
                    found = str(base_dir() / name)
                    break
        _FFMPEG = found or shutil.which("ffmpeg") or ""
    return _FFMPEG or None


def ffmpeg_encoders() -> set[str]:
    global _ENCODERS
    if _ENCODERS is None:
        _ENCODERS = set()
        exe = ffmpeg_exe()
        if exe:
            try:
                out = subprocess.run([exe, "-hide_banner", "-encoders"], capture_output=True, text=True,
                                     timeout=20, creationflags=NO_WINDOW).stdout
                _ENCODERS = {m.group(1) for m in re.finditer(r"^ [VAS][\.\w]{5} (\S+)", out, re.M)}
            except Exception:
                pass
    return _ENCODERS


def codec_available(enc: str | None) -> bool:
    return enc in (None, "copy") or enc in ffmpeg_encoders()


def collect_media(paths) -> tuple[list[tuple[Path, str]], int]:
    found, seen, skipped = [], set(), 0
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            cands = (c for c in p.rglob("*") if c.is_file() and c.suffix.lower() in MEDIA_EXTS)
        elif p.is_file():
            cands = [p]
        else:
            continue
        for c in cands:
            key = os.path.normcase(str(c.resolve()))
            if key in seen:
                continue
            seen.add(key)
            if c.suffix.lower() in MEDIA_EXTS:
                found.append((c, c.suffix.lower()))
            else:
                skipped += 1
    return found, skipped


def _lerp(q: int, worst: float, best: float) -> float:
    q = max(1, min(100, int(q)))
    return worst + (best - worst) * (q - 1) / 99


def _audio_args(acodec: str, q: int) -> list[str]:
    enc = ACODECS[acodec][1]
    if enc is None:
        return ["-an"]
    if enc == "copy":
        return ["-c:a", "copy"]
    kbps = int(round(_lerp(q, 96, 256) / 8) * 8)
    if enc == "aac":
        return ["-c:a", "aac", "-b:a", f"{kbps}k"]
    if enc == "libmp3lame":
        return ["-c:a", "libmp3lame", "-b:a", f"{min(kbps, 320)}k"]
    if enc == "libopus":
        return ["-c:a", "libopus", "-b:a", f"{min(kbps, 192)}k"]
    if enc == "libvorbis":
        return ["-c:a", "libvorbis", "-q:a", str(round(_lerp(q, 3, 8)))]
    return ["-c:a", enc]                                   # flac / pcm: lossless, no quality knob


def _video_args(vcodec: str, q: int, height: int, container: str) -> list[str]:
    enc = VCODECS[vcodec][1]
    if enc == "copy":
        return ["-c:v", "copy"]
    a = ["-c:v", enc]
    if enc == "libx264":
        a += ["-crf", str(round(_lerp(q, 35, 16))), "-preset", "medium"]
    elif enc == "libx265":
        a += ["-crf", str(round(_lerp(q, 37, 18))), "-preset", "medium"]
        if container in ("MP4", "MOV"):
            a += ["-tag:v", "hvc1"]                       # so Apple players accept it
    elif enc == "libvpx-vp9":
        a += ["-crf", str(round(_lerp(q, 45, 20))), "-b:v", "0", "-row-mt", "1", "-deadline", "good", "-cpu-used", "4"]
    elif enc == "libaom-av1":
        a += ["-crf", str(round(_lerp(q, 50, 22))), "-b:v", "0", "-cpu-used", "6", "-row-mt", "1"]
    elif enc == "mpeg4":
        a += ["-q:v", str(round(_lerp(q, 15, 2)))]
    a += ["-pix_fmt", "yuv420p"]
    if height:
        a += ["-vf", f"scale=-2:min(ih\\,{height})"]          # never upscale; keep even width
    return a


def media_command(exe: str, src: Path, out: Path, key: str, o: dict) -> list[str]:
    spec = MEDIA_OUTPUTS[key]
    q = int(o.get("mquality", 70))
    cmd = [exe, "-hide_banner", "-nostdin", "-y", "-i", str(src)]
    if spec["kind"] == "gif":
        h = o.get("height") or 480
        fps = round(_lerp(q, 8, 20))
        chain = (f"[0:v:0]fps={fps},scale=-2:min(ih\\,{h}):flags=lanczos,split[a][b];"
                 f"[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4")
        cmd += ["-filter_complex", chain, "-an", "-loop", "0"]
    elif spec["kind"] == "audio":
        cmd += ["-map", "0:a:0", "-vn", "-sn", "-dn"] + _audio_args(o.get("acodec") or spec["a"][0], q)
    else:
        cmd += ["-map", "0:v:0"]
        ac = o.get("acodec", "aac")
        if ac != "none":
            cmd += ["-map", "0:a?"]
        cmd += _video_args(o.get("vcodec", "h264"), q, int(o.get("height") or 0), key)
        cmd += _audio_args(ac, q)
        if key == "MKV":
            cmd += ["-map", "0:s?", "-c:s", "copy"]       # MKV keeps subtitle tracks
        else:
            cmd += ["-sn"]
        cmd += ["-dn"]
        if key in ("MP4", "MOV"):
            cmd += ["-movflags", "+faststart"]
    cmd += ["-progress", "pipe:1", "-nostats", "-loglevel", "error", str(out)]
    return cmd


class Stopped(Exception):
    pass


def media_probe(exe: str, src: Path) -> tuple[float, bool, bool]:
    """(duration in seconds, has a real video track, has an audio track) from FFmpeg's file summary."""
    try:
        r = subprocess.run([exe, "-hide_banner", "-nostdin", "-i", str(src)], capture_output=True, text=True,
                           errors="replace", timeout=60, creationflags=NO_WINDOW)
        info = r.stderr
    except Exception:
        return 0.0, True, True
    dur = 0.0
    m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", info)
    if m:
        dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    has_v = any("attached pic" not in line for line in re.findall(r"Stream #.*?Video:.*", info))
    has_a = bool(re.search(r"Stream #.*?Audio:", info))
    return dur, has_v, has_a


def convert_media(src: Path, out_dir: Path, key: str, o: dict, on_progress, stop: threading.Event,
                  running: set) -> tuple[list[Path], str]:
    exe = ffmpeg_exe()
    if not exe:
        raise RuntimeError("FFmpeg isn't available")
    if stop.is_set():
        raise Stopped()
    spec = MEDIA_OUTPUTS[key]
    total, has_v, has_a = media_probe(exe, src)
    if spec["kind"] == "audio" and not has_a:
        raise RuntimeError("this file has no audio track")
    if spec["kind"] in ("video", "gif") and not has_v:
        raise RuntimeError("this file has no video track (audio only)")
    p, fh = _claim(out_dir / f"{src.stem}{spec['ext']}")
    fh.close()                                              # FFmpeg writes the file itself
    proc = subprocess.Popen(media_command(exe, src, p, key, o), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            stdin=subprocess.DEVNULL, text=True, errors="replace", creationflags=NO_WINDOW)
    running.add(proc)
    errors: list[str] = []
    reader = threading.Thread(target=lambda: errors.extend(proc.stderr.read().splitlines()), daemon=True)
    reader.start()
    try:
        last = -1.0
        for line in proc.stdout:
            if line.startswith("out_time_us=") and total > 0:
                try:
                    pct = min(99.0, int(line.split("=", 1)[1]) / 1e6 / total * 100)
                except ValueError:
                    continue
                if pct - last >= 1:
                    last = pct
                    on_progress(pct)
        proc.wait()
        reader.join(timeout=5)
    finally:
        running.discard(proc)
    if stop.is_set() or proc.returncode in (-9, -15) or (proc.returncode != 0 and stop.is_set()):
        p.unlink(missing_ok=True)
        raise Stopped()
    if proc.returncode != 0:
        p.unlink(missing_ok=True)
        msg = next((e for e in reversed(errors) if e.strip()), f"FFmpeg exit code {proc.returncode}")
        if "does not contain any stream" in msg or "matches no streams" in msg:
            msg = "no audio track to convert" if spec["kind"] == "audio" else "no video track in this file"
        raise RuntimeError(msg.strip()[:200])
    on_progress(100.0)
    vc = o.get("vcodec") if spec["kind"] == "video" else None
    note = VCODECS[vc][0] if vc else ""
    return [p], note


# ----------------------------------------------------------------------------- widgets

class Bus(QObject):
    finished = Signal(str, list, str, str)  # src, outputs, note, error
    note = Signal(str)                      # status-line message from a background thread
    progress = Signal(str, float)           # src, percent (video/audio)


_GRAIN: QPixmap | None = None


def grain() -> QPixmap:
    global _GRAIN
    if _GRAIN is None:
        buf = io.BytesIO()
        Image.effect_noise((200, 200), 70).convert("L").save(buf, "PNG")
        _GRAIN = QPixmap()
        _GRAIN.loadFromData(QByteArray(buf.getvalue()), "PNG")
    return _GRAIN


class Backdrop(QWidget):
    """Paints the window background: procedural texture per theme, or the wallpaper."""

    def __init__(self):
        super().__init__()
        self.theme: dict = {}
        self.wall: QPixmap | None = None
        self._scaled: QPixmap | None = None
        self._scaled_for = None

    def set_look(self, theme: dict, wall: QPixmap | None):
        self.theme, self.wall, self._scaled = theme, wall, None
        if getattr(self, "movie", None) is not None:
            self.movie.stop()
            self.movie.deleteLater()
        self.movie = None
        if theme.get("backdrop") == "image":
            path = theme_file(theme, theme.get("image", ""))
            if path is not None and path.suffix.lower() in (".gif", ".webp", ".png", ".apng"):
                mv = QMovie(str(path))
                if mv.isValid() and mv.frameCount() > 1:     # an animated background
                    mv.setCacheMode(QMovie.CacheMode.CacheAll)
                    mv.frameChanged.connect(lambda _: self.update())
                    self.movie = mv
                    mv.start()
                else:
                    mv.deleteLater()
        self.update()

    def resizeEvent(self, e):
        self._scaled = None
        for name in ("swarm", "actor_layer", "fx_layer"):
            layer = getattr(self, name, None)
            if layer is not None:
                layer.setGeometry(self.rect())
        super().resizeEvent(e)

    def paintEvent(self, _):
        t, r = self.theme, self.rect()
        if not t:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.fillRect(r, QColor(t["bg"]))
        style = t["backdrop"]
        if style == "wallpaper" and self.wall and not self.wall.isNull():
            if self._scaled is None:
                self._scaled = self.wall.scaled(r.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                                Qt.TransformationMode.SmoothTransformation)
            s = self._scaled
            p.drawPixmap((r.width() - s.width()) // 2, (r.height() - s.height()) // 2, s)
            scrim = QColor(t["bg"])
            scrim.setAlphaF(0.22)
            p.fillRect(r, scrim)
        elif style == "parchment":
            g = QRadialGradient(QPointF(r.center()), max(r.width(), r.height()) * 0.78)
            g.setColorAt(0.0, QColor("#f2e3bd"))
            g.setColorAt(0.55, QColor("#dcc391"))
            g.setColorAt(1.0, QColor("#a9824c"))
            p.fillRect(r, g)
            p.setOpacity(0.09)
            p.drawTiledPixmap(r, grain())
        elif style == "ember":
            g = QRadialGradient(QPointF(r.width() / 2, -r.height() * 0.15), r.height() * 1.15)
            g.setColorAt(0.0, QColor(214, 168, 76, 80))
            g.setColorAt(0.45, QColor(120, 78, 28, 28))
            g.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.fillRect(r, g)
            v = QRadialGradient(QPointF(r.center()), max(r.width(), r.height()) * 0.8)
            v.setColorAt(0.5, QColor(0, 0, 0, 0))
            v.setColorAt(1.0, QColor(0, 0, 0, 180))
            p.fillRect(r, v)
            p.setOpacity(0.05)
            p.drawTiledPixmap(r, grain())
        elif style == "honeycomb":
            p.drawPixmap(0, 0, self._honeycomb(r.width(), r.height()))
        elif style == "image" and getattr(self, "movie", None) is not None:
            frame = self.movie.currentPixmap()
            if not frame.isNull():
                s = frame.scaled(r.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                 Qt.TransformationMode.FastTransformation)
                p.drawPixmap((r.width() - s.width()) // 2, r.height() - s.height(), s)
        elif style == "image":
            pic_key, pic = theme_picture(t)
            if pic is not None and not pic.isNull():
                if self._scaled is None or self._scaled_for != (r.size(), pic_key):
                    self._scaled = pic.scaled(r.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                              Qt.TransformationMode.SmoothTransformation)
                    self._scaled_for = (r.size(), pic_key)
                s = self._scaled
                p.drawPixmap((r.width() - s.width()) // 2, r.height() - s.height(), s)
                v = QRadialGradient(QPointF(r.center()), max(r.width(), r.height()) * 0.8)
                v.setColorAt(0.6, QColor(0, 0, 0, 0))
                v.setColorAt(1.0, QColor(5, 6, 20, 140))
                p.fillRect(r, v)
        elif style == "honeycomb_dark":
            p.drawPixmap(0, 0, self._honeycomb_dark(r.width(), r.height()))
        elif style == "grid":
            p.setPen(QPen(QColor(255, 255, 255, 16), 1))
            for x in range(0, r.width(), 16):
                p.drawLine(x, 0, x, r.height())
            for y in range(0, r.height(), 16):
                p.drawLine(0, y, r.width(), y)
        p.end()


    _hc_cache: tuple | None = None

    def _honeycomb(self, w: int, h: int) -> QPixmap:
        if self._hc_cache and self._hc_cache[0] == (w, h):
            return self._hc_cache[1]
        import math
        pm = QPixmap(w, h)
        pm.fill(QColor("#fdf1c7"))
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        g = QRadialGradient(QPointF(w * 0.15, h * 0.05), max(w, h) * 1.1)
        g.setColorAt(0.0, QColor("#fff8de"))
        g.setColorAt(1.0, QColor("#f9dc7a"))
        p.fillRect(pm.rect(), g)
        R = 26                                   # hexagon radius (pointy-top)
        hw, vh = math.sqrt(3) * R, 1.5 * R
        cx, cy = w * 0.9, h * 0.9                # cells near this corner get honey-filled
        p.setPen(QPen(QColor(150, 105, 10, 60), 1.6))
        row = 0
        y = 0.0
        while y < h + R:
            x = (hw / 2 if row % 2 else 0.0)
            while x < w + hw:
                pts = [QPointF(x + R * math.cos(math.radians(60 * k - 30)),
                               y + R * math.sin(math.radians(60 * k - 30))) for k in range(6)]
                d = math.hypot((x - cx) / w, (y - cy) / h)
                fill = QColor(248, 201, 23, int(max(0, 0.55 - d) * 220)) if d < 0.55 else QColor(0, 0, 0, 0)
                p.setBrush(fill)
                p.drawPolygon(pts)
                x += hw
            y += vh
            row += 1
        p.end()
        self._hc_cache = ((w, h), pm)
        return pm

    _hcd_cache: tuple | None = None

    def _honeycomb_dark(self, w: int, h: int) -> QPixmap:
        """Night hive: dark wax, faint amber cell walls, a few cells glowing with honey."""
        if self._hcd_cache and self._hcd_cache[0] == (w, h):
            return self._hcd_cache[1]
        pm = QPixmap(w, h)
        pm.fill(QColor("#0d0a06"))
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        g = QRadialGradient(QPointF(w * 0.2, h * 0.0), max(w, h) * 1.0)
        g.setColorAt(0.0, QColor("#3a2a0c"))
        g.setColorAt(0.6, QColor("#170f06"))
        g.setColorAt(1.0, QColor("#0a0704"))
        p.fillRect(pm.rect(), g)
        R = 26
        hw, vh = math.sqrt(3) * R, 1.5 * R
        rng = random.Random(7)                   # same glowing cells every time
        p.setPen(QPen(QColor(248, 201, 23, 38), 1.4))
        row, y = 0, 0.0
        while y < h + R:
            x = (hw / 2 if row % 2 else 0.0)
            while x < w + hw:
                pts = [QPointF(x + R * math.cos(math.radians(60 * k - 30)),
                               y + R * math.sin(math.radians(60 * k - 30))) for k in range(6)]
                roll = rng.random()
                if roll < 0.06:
                    glow = QRadialGradient(QPointF(x, y), R)
                    glow.setColorAt(0.0, QColor(248, 190, 30, 120))
                    glow.setColorAt(1.0, QColor(200, 130, 10, 25))
                    p.setBrush(glow)
                elif roll < 0.14:
                    p.setBrush(QColor(248, 201, 23, 14))
                else:
                    p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPolygon(pts)
                x += hw
            y += vh
            row += 1
        v = QRadialGradient(QPointF(w / 2, h / 2), max(w, h) * 0.75)
        v.setColorAt(0.55, QColor(0, 0, 0, 0))
        v.setColorAt(1.0, QColor(0, 0, 0, 150))
        p.fillRect(pm.rect(), v)
        p.end()
        self._hcd_cache = ((w, h), pm)
        return pm


class _Bee:
    __slots__ = ("x", "y", "ang", "turn", "speed", "phase", "size", "t0")

    def __init__(self, w, h):
        self.x, self.y = random.uniform(40, max(41, w - 40)), random.uniform(40, max(41, h - 40))
        self.ang = random.uniform(0, math.tau)
        self.turn = 0.0
        self.speed = random.uniform(45, 85)          # px per second
        self.phase = random.uniform(0, math.tau)
        self.size = random.uniform(1.0, 1.35)
        self.t0 = random.uniform(0, 100)

    def rect(self) -> QRect:
        r = int(26 * self.size)
        return QRect(int(self.x) - r, int(self.y) - r, 2 * r, 2 * r)


class BeeSwarm(QWidget):
    """Flat 2D bees wandering over the window. Ignores the mouse, so clicks and drops pass through."""

    def __init__(self, parent: QWidget, count: int = 6):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.count = count
        self.bees: list[_Bee] = []
        self.clock = QElapsedTimer()
        self.t = 0.0
        self.timer = QTimer(self)
        self.timer.setInterval(33)                   # ~30 fps
        self.timer.timeout.connect(self._tick)
        self.hide()

    def start(self):
        self.setGeometry(self.parentWidget().rect())
        if not self.bees:
            self.bees = [_Bee(self.width(), self.height()) for _ in range(self.count)]
        self.show()
        self.raise_()
        self.clock.start()
        self.timer.start()

    def stop(self):
        self.timer.stop()
        self.hide()

    def _tick(self):
        win = self.window()
        if not win.isVisible() or win.isMinimized():
            self.clock.restart()
            return
        dt = min(0.05, self.clock.restart() / 1000.0)
        self.t += dt
        w, h = self.width(), self.height()
        dirty = QRect()
        for b in self.bees:
            dirty = dirty.united(b.rect())
            b.turn += random.uniform(-4.0, 4.0) * dt                # wander
            b.turn = max(-2.4, min(2.4, b.turn * (1 - 0.6 * dt)))
            m = 70                                                  # steer back from the edges
            if b.x < m or b.x > w - m or b.y < m or b.y > h - m:
                want = math.atan2(h / 2 - b.y, w / 2 - b.x)
                diff = (want - b.ang + math.pi) % math.tau - math.pi
                b.ang += max(-3.0 * dt, min(3.0 * dt, diff))
            b.ang += b.turn * dt
            v = b.speed * (0.55 + 0.45 * math.sin(self.t * 0.8 + b.t0))   # drift, slow down, speed up
            b.x = max(10, min(w - 10, b.x + math.cos(b.ang) * v * dt))
            b.y = max(10, min(h - 10, b.y + math.sin(b.ang) * v * dt))
            b.phase += dt * 42                                             # wing beat
            dirty = dirty.united(b.rect())
        self.update(dirty)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for b in self.bees:
            if not b.rect().intersects(e.rect()):
                continue
            p.save()
            p.translate(b.x, b.y)
            p.rotate(math.degrees(b.ang))
            p.scale(b.size, b.size)
            glow = QRadialGradient(QPointF(0, 0), 20)                 # warm glow
            glow.setColorAt(0.0, QColor(248, 190, 30, 70))
            glow.setColorAt(1.0, QColor(248, 190, 30, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(glow)
            p.drawEllipse(QPointF(0, 0), 20, 20)
            flap = 0.45 + 0.55 * abs(math.sin(b.phase))              # wings seen from above
            p.setBrush(QColor(225, 238, 255, 150))
            p.setPen(QPen(QColor(255, 255, 255, 110), 0.8))
            for side in (-1, 1):
                p.save()
                p.translate(-1, side * 3)
                p.rotate(side * 28)
                p.drawEllipse(QRectF(-4, (0 if side > 0 else -9 * flap), 8, 9 * flap))
                p.restore()
            p.setPen(Qt.PenStyle.NoPen)                              # stinger
            p.setBrush(QColor("#2a1d0c"))
            p.drawPolygon([QPointF(-8.5, -1.3), QPointF(-12, 0), QPointF(-8.5, 1.3)])
            body = QPainterPath()                                    # striped body
            body.addEllipse(QRectF(-9, -5, 16, 10))
            p.setBrush(QColor("#f8c917"))
            p.drawPath(body)
            p.save()
            p.setClipPath(body)
            p.setBrush(QColor("#1a1206"))
            for sx in (-5.5, -1.0):
                p.drawRect(QRectF(sx, -6, 2.4, 12))
            p.restore()
            p.setBrush(QColor("#1a1206"))                            # head
            p.drawEllipse(QPointF(8, 0), 3.6, 3.6)
            p.restore()
        p.end()


# coat, mane/tail, lower legs, saddle blanket, saddle, pinto patches
HORSE_COATS = [
    ("#7b4a26", "#1f140c", "#1f140c", "#9c2f2a", "#5a3a1e", None),       # bay
    ("#d9a75a", "#f3e6c4", "#d9a75a", "#2f5f8a", "#4a2e17", None),       # palomino
    ("#a5552c", "#6e3417", "#a5552c", "#d8b25a", "#3d2512", None),       # chestnut
    ("#f1e9dc", "#3a2a1e", "#3a2a1e", "#3f7a52", "#5a3a1e", "#5b3a22"),  # pinto
    ("#c9a46a", "#2a1c12", "#2a1c12", "#7a3d6e", "#4a2e17", None),       # buckskin
]


def _leg(p, hip, a1, a2, l1, l2, coat, lower, hoof, w1=4.4, w2=2.9):
    """Two-part leg from the hip; angles in degrees from straight down (positive = forward)."""
    k = QPointF(hip.x() + l1 * math.sin(math.radians(a1)), hip.y() + l1 * math.cos(math.radians(a1)))
    f = QPointF(k.x() + l2 * math.sin(math.radians(a1 + a2)), k.y() + l2 * math.cos(math.radians(a1 + a2)))
    p.setPen(QPen(coat, w1, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawLine(hip, k)
    p.setPen(QPen(lower, w2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawLine(k, f)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(hoof)
    p.drawEllipse(f, 1.7, 1.4)


def draw_horse(p: QPainter, phase: float, coat, mane, lower, blanket, saddle, patches=None):
    """Small saddled horse, side view, facing +x, hooves on y=0, ~52 px long. One stride = 2*pi."""
    C, M, L = QColor(coat), QColor(mane), QColor(lower)
    hoof = QColor("#1d140c")
    bob = -1.6 * math.sin(2 * phase)
    s, c = math.sin(phase), math.cos(phase)
    far, far_l = C.darker(135), L.darker(135)
    _leg(p, QPointF(-12, -20 + bob), 25 * math.sin(phase + 0.5) - 5,
         30 + 25 * max(0.0, math.sin(phase + 2.1)), 10, 11, far, far_l, hoof)
    _leg(p, QPointF(12, -20 + bob), 35 * math.sin(phase + 1.3) + 5,
         -10 - 45 * max(0.0, math.sin(phase + 2.9)), 10, 11, far, far_l, hoof)
    p.save()
    p.translate(0, bob)
    tail = QPainterPath(QPointF(-17, -26))
    tail.cubicTo(QPointF(-26, -27 + 2 * s), QPointF(-30, -20 + 3 * c), QPointF(-34, -16 + 4 * s))
    p.setPen(QPen(M, 4.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(tail)
    body = QPainterPath()
    body.moveTo(-18, -24)
    body.cubicTo(-18, -32, -6, -31, 4, -30)
    body.cubicTo(10, -30, 13, -33, 16, -38)
    body.cubicTo(18, -42, 21, -45, 24, -45)
    body.lineTo(26, -47.5)
    body.lineTo(27.8, -44)
    body.cubicTo(30.5, -43, 34.5, -39, 36, -35.5)
    body.cubicTo(37, -33, 34.5, -31.5, 31.5, -32.5)
    body.cubicTo(28, -33.5, 24, -36, 22, -33)
    body.cubicTo(20, -30, 18, -24, 15, -20)
    body.cubicTo(10, -16, -10, -16, -15, -18)
    body.cubicTo(-19, -19, -19, -21, -18, -24)
    p.setPen(QPen(C.darker(150), 0.8))
    p.setBrush(C)
    p.drawPath(body)
    if patches:
        p.save()
        p.setClipPath(body)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(patches))
        p.drawEllipse(QRectF(-14, -30, 12, 11))
        p.drawEllipse(QRectF(4, -24, 9, 7))
        p.restore()
    mp = QPainterPath(QPointF(12, -33))
    mp.cubicTo(QPointF(15, -38), QPointF(19, -44), QPointF(24, -45))
    p.setPen(QPen(M, 3.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(mp)
    p.drawLine(QPointF(24, -45), QPointF(27, -42))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#140d07"))
    p.drawEllipse(QPointF(29.4, -40.3), 1.15, 1.15)
    p.setBrush(QColor(blanket))
    p.drawRoundedRect(QRectF(-8, -31, 13, 9), 1.5, 1.5)
    p.setBrush(QColor(saddle))
    p.drawRoundedRect(QRectF(-6, -34, 10, 5), 2, 2)
    p.drawRect(QRectF(2, -37, 1.6, 4))
    p.restore()
    _leg(p, QPointF(-13, -20 + bob), 25 * math.sin(phase) - 5,
         30 + 25 * max(0.0, math.sin(phase + 1.6)), 10, 11, C, L, hoof)
    _leg(p, QPointF(11, -20 + bob), 35 * math.sin(phase + 0.8) + 5,
         -10 - 45 * max(0.0, math.sin(phase + 2.4)), 10, 11, C, L, hoof)


class _Rider:
    __slots__ = ("x", "lane", "dir", "speed", "phase", "coat", "wait", "dust_t")


class HorseTrail(QWidget):
    """A strip at the bottom of the window where little horses gallop across in three lanes."""

    LANES = [(0.85, 0.80, 0.62), (1.05, 0.90, 0.81), (1.25, 1.0, 1.0)]   # scale, brightness, ground y (fraction)

    def __init__(self):
        super().__init__()
        self.setFixedHeight(72)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.riders: list[_Rider] = []
        self.dust: list[list[float]] = []            # x, y, age, size
        self.clock = QElapsedTimer()
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self._tick)
        self.hide()

    def _spawn(self, r: _Rider, first=False):
        r.lane = random.randrange(len(self.LANES))
        r.dir = random.choice((-1, 1))
        r.speed = random.uniform(110, 190)
        r.phase = random.uniform(0, math.tau)
        r.coat = random.choice(HORSE_COATS)
        r.dust_t = 0.0
        w = max(self.width(), 400)
        if first:
            r.x, r.wait = random.uniform(0, w), 0.0
        else:
            r.x = -60.0 if r.dir > 0 else w + 60.0
            r.wait = random.uniform(0.3, 3.5)        # pause before the next horse rides in

    def start(self):
        if not self.riders:
            for _ in range(4):
                r = _Rider()
                self._spawn(r, first=True)
                self.riders.append(r)
        self.show()
        self.clock.start()
        self.timer.start()

    def stop(self):
        self.timer.stop()
        self.hide()

    def _tick(self):
        win = self.window()
        if not win.isVisible() or win.isMinimized():
            self.clock.restart()
            return
        dt = min(0.05, self.clock.restart() / 1000.0)
        w, h = self.width(), self.height()
        for r in self.riders:
            if r.wait > 0:
                r.wait -= dt
                continue
            scale = self.LANES[r.lane][0]
            r.x += r.dir * r.speed * dt
            r.phase += (r.speed / (58 * scale)) * math.tau * dt         # legs keep pace with ground speed
            r.dust_t += dt
            if r.dust_t > 0.16:
                r.dust_t = 0.0
                gy = h * self.LANES[r.lane][2] - 4
                self.dust.append([r.x - r.dir * random.uniform(8, 18) * scale, gy + random.uniform(-1, 1),
                                  0.0, random.uniform(3.0, 5.5) * scale])
            if (r.dir > 0 and r.x > w + 70) or (r.dir < 0 and r.x < -70):
                self._spawn(r)
        for d in self.dust:
            d[2] += dt
            d[1] -= 8 * dt
        self.dust = [d for d in self.dust if d[2] < 0.7]
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        h = self.height()
        p.setPen(Qt.PenStyle.NoPen)
        for x, y, age, size in self.dust:                                # soft dust behind the hooves
            a = int(70 * (1 - age / 0.7))
            rad = size * (1 + age * 2.5)
            g = QRadialGradient(QPointF(x, y), rad)
            g.setColorAt(0.0, QColor(226, 222, 240, a))
            g.setColorAt(1.0, QColor(226, 222, 240, 0))
            p.setBrush(g)
            p.drawEllipse(QPointF(x, y), rad, rad * 0.7)
        for r in sorted(self.riders, key=lambda r: r.lane):            # far lanes first
            if r.wait > 0:
                continue
            scale, bright, gy = self.LANES[r.lane]
            p.save()
            p.translate(r.x, h * gy - 3)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(10, 10, 30, 70))
            p.drawEllipse(QPointF(0, 0), 20 * scale, 3 * scale)          # shadow on the sand
            p.scale(scale * r.dir, scale)
            coat = [QColor(c).darker(int(100 / bright)).name() if c else None for c in r.coat]
            draw_horse(p, r.phase, *coat)
            p.restore()
        p.end()


_SPRITES: dict = {}


def load_sprite(path: str, height: int):
    """Frames of a (possibly animated) picture at the given height: (frames, mirrored, durations_ms)."""
    key = (path, height)
    if key in _SPRITES:
        return _SPRITES[key]
    frames, mirrored, durs = [], [], []
    try:
        with Image.open(path) as im:
            for i, fr in enumerate(ImageSequence.Iterator(im)):
                if i >= 120:
                    break
                rgba = fr.convert("RGBA")
                w = max(1, round(rgba.width * height / max(1, rgba.height)))
                rgba = rgba.resize((w, height), Image.LANCZOS)
                qi = QImage(rgba.tobytes("raw", "RGBA"), w, height, QImage.Format.Format_RGBA8888).copy()
                frames.append(QPixmap.fromImage(qi))
                mirrored.append(QPixmap.fromImage(qi.mirrored(True, False)))
                durs.append(max(20, int(fr.info.get("duration", im.info.get("duration", 100)) or 100)))
    except Exception:
        frames = []
    _SPRITES[key] = (frames, mirrored, durs)
    return _SPRITES[key]


class _Actor:
    __slots__ = ("spec", "x", "y", "vx", "vy", "ang", "turn", "rot", "t", "frame", "ftime", "wait", "lane", "sway", "scale")


class ActorLayer(QWidget):
    """Draws a theme's own pictures moving over the window. Ignores the mouse."""

    LANES = [(0.8, 0.62), (1.0, 0.81), (1.2, 1.0)]       # run lanes: scale, ground position in the strip

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.actors: list[_Actor] = []
        self.lane_widget: QWidget | None = None
        self.clock = QElapsedTimer()
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self._tick)
        self.hide()

    def set_specs(self, specs: list[dict], lane_widget: QWidget | None):
        self.timer.stop()
        self.actors = []
        self.lane_widget = lane_widget
        if not specs:
            self.hide()
            return
        self.setGeometry(self.parentWidget().rect())
        for spec in specs:
            frames = load_sprite(spec["path"], spec["size"])[0]
            if not frames:
                continue
            for _ in range(spec["count"]):
                a = _Actor()
                a.spec = spec
                self._spawn(a, first=True)
                self.actors.append(a)
        if not self.actors:
            self.hide()
            return
        self.show()
        self.raise_()
        self.clock.start()
        self.timer.start()

    def stop(self):
        self.set_specs([], None)

    def _lane_rect(self) -> QRect:
        lw = self.lane_widget
        if lw is not None and lw.isVisible():
            return lw.geometry()
        return QRect(0, self.height() - 72, self.width(), 72)

    def _spawn(self, a: _Actor, first=False):
        w, h = max(self.width(), 300), max(self.height(), 300)
        sp, m = a.spec, a.spec["motion"]
        a.t = random.uniform(0, 100)
        a.frame, a.ftime, a.wait, a.rot, a.turn = random.randrange(8), 0.0, 0.0, random.uniform(0, 360), 0.0
        a.sway = random.uniform(0, math.tau)
        a.scale, a.lane = 1.0, 0
        v = sp["speed"] * random.uniform(0.75, 1.25)
        if m == "fly":
            a.x, a.y = random.uniform(40, w - 40), random.uniform(40, h - 40)
            a.ang = random.uniform(0, math.tau)
            a.vx = v
        elif m == "run":
            a.lane = random.randrange(len(self.LANES))
            a.scale = self.LANES[a.lane][0]
            d = random.choice((-1, 1))
            a.vx = d * v
            a.x = random.uniform(0, w) if first else (-60.0 if d > 0 else w + 60.0)
            a.wait = 0.0 if first else random.uniform(0.3, 3.0)
            a.y = 0
        elif m == "fall":
            a.x, a.y = random.uniform(0, w), (random.uniform(0, h) if first else -sp["size"])
            a.vy = v
        elif m == "float":
            a.x, a.y = random.uniform(0, w), (random.uniform(0, h) if first else h + sp["size"])
            a.vy = -v
        else:  # bounce
            a.x, a.y = random.uniform(40, w - 40), random.uniform(40, h - 40)
            ang = random.uniform(0, math.tau)
            a.vx, a.vy = math.cos(ang) * v, math.sin(ang) * v

    def _rect(self, a: _Actor) -> QRect:
        r = int(a.spec["size"] * a.scale * 1.6) + 4
        cx, cy = self._center(a)
        return QRect(int(cx) - r, int(cy) - r, 2 * r, 2 * r)

    def _center(self, a: _Actor) -> tuple[float, float]:
        if a.spec["motion"] == "run":
            lr = self._lane_rect()
            ground = lr.top() + lr.height() * self.LANES[a.lane][1]
            return a.x, ground - a.spec["size"] * a.scale / 2 - 2
        return a.x, a.y

    def _tick(self):
        win = self.window()
        if not win.isVisible() or win.isMinimized():
            self.clock.restart()
            return
        dt = min(0.05, self.clock.restart() / 1000.0)
        w, h = self.width(), self.height()
        region = QRegion()
        for a in self.actors:
            region += self._rect(a)
            sp, m = a.spec, a.spec["motion"]
            _, _, durs = load_sprite(sp["path"], sp["size"])
            a.ftime += dt * 1000
            while durs and a.ftime >= durs[a.frame % len(durs)]:
                a.ftime -= durs[a.frame % len(durs)]
                a.frame = (a.frame + 1) % len(durs)
            a.t += dt
            if sp["spin"]:
                a.rot = (a.rot + (a.vx if m == "run" else 40) * dt * (2.2 if m == "run" else 1)) % 360
            if a.wait > 0:
                a.wait -= dt
                continue
            if m == "fly":
                a.turn = max(-2.2, min(2.2, (a.turn + random.uniform(-3.5, 3.5) * dt) * (1 - 0.6 * dt)))
                if a.x < 60 or a.x > w - 60 or a.y < 60 or a.y > h - 60:
                    want = math.atan2(h / 2 - a.y, w / 2 - a.x)
                    diff = (want - a.ang + math.pi) % math.tau - math.pi
                    a.ang += max(-2.5 * dt, min(2.5 * dt, diff))
                a.ang += a.turn * dt
                spd = a.vx * (0.6 + 0.4 * math.sin(a.t * 0.8))
                a.x = max(8, min(w - 8, a.x + math.cos(a.ang) * spd * dt))
                a.y = max(8, min(h - 8, a.y + math.sin(a.ang) * spd * dt))
            elif m == "run":
                a.x += a.vx * dt
                if (a.vx > 0 and a.x > w + 80) or (a.vx < 0 and a.x < -80):
                    self._spawn(a)
            elif m in ("fall", "float"):
                a.y += a.vy * dt
                a.x += math.sin(a.t * 1.3 + a.sway) * 18 * dt
                if (m == "fall" and a.y > h + sp["size"]) or (m == "float" and a.y < -sp["size"]):
                    self._spawn(a)
            else:
                a.x += a.vx * dt
                a.y += a.vy * dt
                half = sp["size"] / 2
                if a.x < half or a.x > w - half:
                    a.vx = -a.vx
                    a.x = max(half, min(w - half, a.x))
                if a.y < half or a.y > h - half:
                    a.vy = -a.vy
                    a.y = max(half, min(h - half, a.y))
            region += self._rect(a)
        self.update(region)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        for a in self.actors:
            if a.wait > 0 or not self._rect(a).intersects(e.rect()):
                continue
            sp, m = a.spec, a.spec["motion"]
            frames, mirrored, _ = load_sprite(sp["path"], sp["size"])
            if not frames:
                continue
            if m == "fly":
                moving_left = math.cos(a.ang) < 0
            elif m == "bounce" or m == "run":
                moving_left = a.vx < 0
            else:
                moving_left = False
            pix = (mirrored if (moving_left and sp["flip"]) else frames)[a.frame % len(frames)]
            cx, cy = self._center(a)
            p.save()
            p.setOpacity(sp["opacity"])
            p.translate(cx, cy)
            if a.scale != 1.0:
                p.scale(a.scale, a.scale)
            if sp["spin"]:
                p.rotate(a.rot)
            p.drawPixmap(int(-pix.width() / 2), int(-pix.height() / 2), pix)
            p.restore()
        p.end()


class FxLayer(QWidget):
    """Things that fall when the app shakes, and fireworks. Sits on top and ignores the mouse."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.items: list[list] = []          # [pixmap, x, y, vx, vy, rot, vrot]
        self.sparks: list[list] = []         # [x, y, vx, vy, life, max_life, QColor, size]
        self.rockets: list[list] = []        # [x, y, vy, target_y, QColor]
        self.ambient_fireworks = False
        self.next_rocket = 0.0
        self.clock = QElapsedTimer()
        self.timer = QTimer(self)
        self.timer.setInterval(30)
        self.timer.timeout.connect(self._tick)
        self.hide()

    def _ensure_running(self):
        self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()
        if not self.timer.isActive():
            self.clock.start()
            self.timer.start()

    def set_ambient(self, fireworks: bool):
        self.ambient_fireworks = fireworks
        if fireworks:
            self._ensure_running()

    def rain(self, paths: list[str], size: int, count: int = 28):
        frames = [load_sprite(pth, size)[0] for pth in paths]
        frames = [f[0] for f in frames if f]
        if not frames:
            return
        w = max(self.parentWidget().width(), 300)
        for i in range(count):
            self.items.append([random.choice(frames), random.uniform(0, w), -random.uniform(40, 500),
                               random.uniform(-40, 40), random.uniform(260, 520), random.uniform(0, 360),
                               random.uniform(-220, 220)])
        self._ensure_running()

    def fireworks(self, count: int = 6):
        for i in range(count):
            self._launch(delay=i * 0.18)
        self._ensure_running()

    def _launch(self, delay=0.0):
        w, h = max(self.width(), 300), max(self.height(), 300)
        col = QColor.fromHsv(random.randrange(360), 140 + random.randrange(100), 255)
        self.rockets.append([random.uniform(w * 0.1, w * 0.9), h + 20 + delay * 600, -random.uniform(620, 820),
                             random.uniform(h * 0.12, h * 0.45), col])

    def _explode(self, x, y, col):
        n = random.randint(48, 72)
        speed = random.uniform(160, 260)
        for k in range(n):
            a = k / n * math.tau + random.uniform(-0.05, 0.05)
            v = speed * random.uniform(0.6, 1.0)
            life = random.uniform(0.9, 1.5)
            c = QColor(col) if random.random() < 0.85 else QColor(255, 255, 255)
            self.sparks.append([x, y, math.cos(a) * v, math.sin(a) * v, life, life, c, random.uniform(2.0, 3.4)])

    def _tick(self):
        win = self.window()
        if not win.isVisible() or win.isMinimized():
            self.clock.restart()
            return
        dt = min(0.05, self.clock.restart() / 1000.0)
        h = self.height()
        for it in self.items:
            it[4] += 380 * dt
            it[1] += it[3] * dt
            it[2] += it[4] * dt
            it[5] += it[6] * dt
        self.items = [it for it in self.items if it[2] < h + 120]
        for r in self.rockets:
            r[1] += r[2] * dt
        for r in [r for r in self.rockets if r[1] <= r[3]]:
            self._explode(r[0], r[1], r[4])
        self.rockets = [r for r in self.rockets if r[1] > r[3]]
        for sp in self.sparks:
            sp[3] += 140 * dt
            sp[2] *= (1 - 0.9 * dt)
            sp[3] *= (1 - 0.6 * dt)
            sp[0] += sp[2] * dt
            sp[1] += sp[3] * dt
            sp[4] -= dt
        self.sparks = [sp for sp in self.sparks if sp[4] > 0]
        if self.ambient_fireworks:
            self.next_rocket -= dt
            if self.next_rocket <= 0:
                self._launch()
                self.next_rocket = random.uniform(1.0, 2.6)
        if not (self.items or self.sparks or self.rockets or self.ambient_fireworks):
            self.timer.stop()
            self.hide()
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        for pix, x, y, _vx, _vy, rot, _vr in self.items:
            p.save()
            p.translate(x, y)
            p.rotate(rot)
            p.drawPixmap(int(-pix.width() / 2), int(-pix.height() / 2), pix)
            p.restore()
        p.setPen(Qt.PenStyle.NoPen)
        for x, y, vy, _t, col in self.rockets:
            p.setBrush(QColor(255, 230, 180))
            p.drawEllipse(QPointF(x, y), 2.5, 2.5)
            trail = QColor(col)
            trail.setAlpha(110)
            p.setBrush(trail)
            p.drawEllipse(QPointF(x, y + 10), 1.8, 7)
        for x, y, _vx, _vy, life, max_life, col, size in self.sparks:
            c = QColor(col)
            c.setAlphaF(max(0.0, min(1.0, life / max_life)))
            p.setBrush(c)
            p.drawEllipse(QPointF(x, y), size, size)
        p.end()


class Banner(QFrame):
    """A message card that pops up in the middle of the window and fades away."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("banner")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 18, 28, 20)
        lay.setSpacing(6)
        self.head = QLabel()
        self.head.setObjectName("bannerTitle")
        self.head.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.body = QLabel()
        self.body.setObjectName("bannerText")
        self.body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.body.setWordWrap(True)
        lay.addWidget(self.head)
        lay.addWidget(self.body)
        self.fx = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.fx)
        self.anim = QPropertyAnimation(self.fx, b"opacity", self)
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self._fade_out)
        self.anim.finished.connect(lambda: self.hide() if self.fx.opacity() < 0.05 else None)
        self.hide()

    def pop(self, title: str, text: str, ms: int = 4500):
        self.head.setText(title)
        self.body.setText(text)
        par = self.parentWidget()
        w = min(560, par.width() - 60)
        self.setFixedWidth(w)
        self.adjustSize()
        self.move((par.width() - w) // 2, int(par.height() * 0.30))
        self.show()
        self.raise_()
        self.anim.stop()
        self.anim.setDuration(220)
        self.anim.setStartValue(self.fx.opacity() if self.isVisible() else 0.0)
        self.anim.setEndValue(1.0)
        self.anim.start()
        self.hide_timer.start(ms)

    def _fade_out(self):
        self.anim.stop()
        self.anim.setDuration(600)
        self.anim.setStartValue(1.0)
        self.anim.setEndValue(0.0)
        self.anim.start()


class StripeBar(QWidget):
    """Thin bee-stripe band (diagonal yellow/black), shown only by themes that ask for it."""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(8)
        self.a, self.b = QColor("#f8c917"), QColor("#241917")

    style = "bee"

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if self.style == "stitch":                 # leather strap, cream stitching, brass rivets
            g = QLinearGradient(0, 0, 0, h)
            g.setColorAt(0.0, QColor("#7a4f2a"))
            g.setColorAt(1.0, QColor("#4a2d16"))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(g)
            p.drawRoundedRect(QRectF(0, 0, w, h), 3, 3)
            pen = QPen(QColor(242, 226, 190, 200), 1.1)
            pen.setDashPattern([3, 2.5])
            p.setPen(pen)
            p.drawLine(QPointF(10, 2), QPointF(w - 10, 2))
            p.drawLine(QPointF(10, h - 2), QPointF(w - 10, h - 2))
            p.setPen(QPen(QColor("#6b4e1c"), 0.8))
            p.setBrush(QColor("#e2b25a"))
            for x in (5, w - 5):
                p.drawEllipse(QPointF(x, h / 2), 2.6, 2.6)
            p.end()
            return
        p.fillRect(self.rect(), self.a)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.b)
        step = 16
        for x in range(-h, w + h, step):
            p.drawPolygon([QPointF(x, h), QPointF(x + h, 0), QPointF(x + h + step / 2, 0),
                           QPointF(x + step / 2, h)])
        p.end()


class DropZone(QFrame):
    clicked = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("dropZone")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(110)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(10)
        self.hint = QLabel()
        self.hint.setObjectName("dropHint")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sub = QLabel("or click to pick files. Folders work too.")
        self.sub.setObjectName("muted")
        self.sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.hint)
        lay.addWidget(self.sub)

    def set_hover(self, on: bool):
        self.setProperty("hover", on)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()


def card() -> QFrame:
    f = QFrame()
    f.setObjectName("card")
    return f


def muted(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("muted")
    return lbl


# ----------------------------------------------------------------------------- main window

DEFAULTS = {"theme": "elden", "base_theme": "elden", "shortcuts": [], "mode": "images",
            "mformat": "MP4", "vcodec": "h264", "acodec": "aac", "mquality": 70, "height": 0, "soc_dark": False, "out_mode": "next", "out_dir": "",
            "format": "PNG", "quality": 90, "lossless": False, "anim": "keep",
            "fill": [255, 255, 255], "skip_same": True, "geometry": ""}

ANIM_CHOICES = [("keep", "Keep animation"), ("first", "First frame only"),
                ("all", "Each frame as its own file")]


class Converter(QMainWindow):
    def __init__(self, startup_paths: list[str]):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setAcceptDrops(True)
        self.setMinimumSize(900, 720)
        self.resize(1000, 800)

        self.data = data_dir()
        self.cfg_path = self.data / "settings.json"
        self.wall_path = self.data / "wallpaper.png"
        self.cfg = self._load_cfg()
        self.unlocked = unlocked_themes()
        for k in ("theme", "base_theme"):               # settings copied from an unlocked PC
            if self.cfg[k] in LOCKS and self.cfg[k] not in self.unlocked:
                self.cfg[k] = DEFAULTS[k]
        self._typed = ""
        self.sealed = seal_open()
        self.forced, self.forced_until = (None, None) if self.sealed else forced_holiday(today())
        self.active_key = self.cfg["theme"]
        self._dodged: set = set()
        self._april_i = 0

        self.bus = Bus()
        self.bus.finished.connect(self._on_done)
        self.bus.note.connect(lambda m: self.status.setText(m))
        self.bus.progress.connect(self._on_progress)
        self.pool = ThreadPoolExecutor(max_workers=max(2, min(8, os.cpu_count() or 4)))
        self.media_pool = ThreadPoolExecutor(max_workers=1)   # FFmpeg already uses every core
        self.futures: list = []
        self.stop_event = threading.Event()
        self.running_procs: set = set()
        self.total = self.ok = self.fail = 0
        self.last_out_dir: Path | None = None
        self.wall_pm: QPixmap | None = None
        self.custom_colors: dict | None = None

        self._build_ui()
        self._load_wallpaper()
        theme = self.cfg["theme"]
        if theme == "custom" and not self.custom_colors:
            theme = self.cfg["base_theme"]
        if theme in HOLIDAY_KEYS and not self.sealed:
            theme = DEFAULTS["theme"]
        if self.forced:
            self.apply_theme(self.forced, persist=False)
        else:
            self.apply_theme(theme)
        QApplication.instance().installEventFilter(self)
        self._report_theme_problems()
        self.holiday_timer = QTimer(self)                 # notice when a holiday starts or ends
        self.holiday_timer.timeout.connect(self._check_holiday)
        self.holiday_timer.start(60_000)
        self.april_timer = QTimer(self)
        self.april_timer.timeout.connect(self._april_tick)
        self.april_timer.start(5000)
        if self.forced == "aprilfools":
            QTimer.singleShot(900, lambda: None if self.banner.isVisible() else self.banner.pop(
                "Universal Quackverter 🦆", "All your files will now be converted into ducks.\n"
                "(Kidding. Everything works normally. Mostly.)", 5500))

        if self.cfg.get("geometry"):
            self.restoreGeometry(QByteArray.fromBase64(self.cfg["geometry"].encode()))
        if startup_paths:
            self.enqueue(*collect_images(startup_paths))

    # ---- settings
    def _load_cfg(self) -> dict:
        cfg = dict(DEFAULTS)
        try:
            cfg.update(json.loads(self.cfg_path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
        if cfg["theme"] not in THEME_ORDER:            # e.g. a theme folder that was removed
            cfg["theme"] = DEFAULTS["theme"]
        if cfg["base_theme"] not in THEMES:
            cfg["base_theme"] = DEFAULTS["base_theme"]
        if cfg["format"] not in OUTPUTS:
            cfg["format"] = "PNG"
        if cfg["mode"] not in ("images", "media"):
            cfg["mode"] = "images"
        if cfg["mformat"] not in MEDIA_OUTPUTS:
            cfg["mformat"] = "MP4"
        if cfg["anim"] not in dict(ANIM_CHOICES):
            cfg["anim"] = "keep"
        return cfg

    def _save_cfg(self):
        if getattr(self, "_uninstalling", False):
            return
        try:
            self.cfg_path.write_text(json.dumps(self.cfg, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _set_cfg(self, k, v):
        self.cfg[k] = v
        self._save_cfg()

    # ---- UI
    def _build_ui(self):
        self.backdrop = Backdrop()
        self.setCentralWidget(self.backdrop)
        outer = QVBoxLayout(self.backdrop)
        outer.setContentsMargins(20, 18, 20, 18)
        outer.setSpacing(14)

        # header: crow + title + credit, theme controls
        self.header = card()
        hv = QVBoxLayout(self.header)
        hv.setContentsMargins(16, 12, 18, 12)
        hv.setSpacing(10)
        h = QHBoxLayout()
        h.setSpacing(14)
        hv.addLayout(h)
        self.logo = QLabel()
        self.logo.setFixedSize(56, 56)
        h.addWidget(self.logo)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.title = QLabel()
        self.title.setObjectName("title")
        self.subtitle = QLabel()
        self.subtitle.setObjectName("subtitle")
        titles.addWidget(self.title)
        titles.addWidget(self.subtitle)
        h.addLayout(titles, 1)

        row1 = QHBoxLayout()
        row1.setSpacing(10)
        self.theme_box = QComboBox()
        self.theme_box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._fill_theme_box()
        self.theme_box.currentIndexChanged.connect(self._on_theme_picked)
        row1.addWidget(muted("Theme"))
        row1.addWidget(self.theme_box)
        self.chk_dark = QCheckBox("Darker")
        self.chk_dark.setToolTip("Night version of the Socialab theme, with bees flying around")
        self.chk_dark.setChecked(bool(self.cfg["soc_dark"]))
        self.chk_dark.toggled.connect(self._on_dark_toggled)
        row1.addWidget(self.chk_dark)
        self.btn_wall = QPushButton("Set wallpaper")
        self.btn_wall.clicked.connect(self.pick_wallpaper)
        self.btn_wall_rm = QPushButton("Remove wallpaper")
        self.btn_wall_rm.setToolTip("Deletes the app's copy of the wallpaper.\nYour original image is not touched.")
        self.btn_wall_rm.clicked.connect(self.remove_wallpaper)
        row1.addWidget(self.btn_wall)
        row1.addWidget(self.btn_wall_rm)
        self.btn_more = QToolButton()
        self.btn_more.setText("More")
        self.btn_more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        more = QMenu(self.btn_more)
        more.addAction("Open themes folder", self.open_themes_folder)
        more.addAction("Reload themes", self.reload_themes)
        more.addSeparator()
        self.act_shortcut = more.addAction("Create desktop shortcut", self.create_shortcuts)
        if not shortcuts_supported():
            self.act_shortcut.setEnabled(False)
            self.act_shortcut.setText("Create desktop shortcut (only in the Windows .exe)")
        more.addSeparator()
        self.act_uninstall = more.addAction("Uninstall…", self.uninstall)
        if not shortcuts_supported():
            self.act_uninstall.setEnabled(False)
            self.act_uninstall.setText("Uninstall… (only in the Windows .exe)")
        self.btn_more.setMenu(more)
        row1.addWidget(self.btn_more)
        row1.addStretch(1)
        self.stripes = StripeBar()
        hv.insertWidget(1, self.stripes)
        hv.addLayout(row1)
        outer.addWidget(self.header)

        # drop zone
        self.drop = DropZone()
        self.drop.clicked.connect(self.browse_files)
        outer.addWidget(self.drop, 2)

        # options
        opts = card()
        ov = QVBoxLayout(opts)
        ov.setContentsMargins(16, 10, 16, 10)
        ov.setSpacing(8)

        # mode switch: images / video & audio
        r0 = QHBoxLayout()
        r0.setSpacing(0)
        r0.addWidget(QLabel("Mode"))
        r0.addSpacing(10)
        self.mode_group = QButtonGroup(self)
        self.btn_mode_img = QPushButton("Images")
        self.btn_mode_media = QPushButton("Video && Audio")
        for i, b in enumerate((self.btn_mode_img, self.btn_mode_media)):
            b.setCheckable(True)
            b.setObjectName("modeBtn")
            self.mode_group.addButton(b, i)
            r0.addWidget(b)
        r0.addStretch(1)
        ov.addLayout(r0)
        self.img_box = QWidget()
        ib = QVBoxLayout(self.img_box)
        ib.setContentsMargins(0, 0, 0, 0)
        ib.setSpacing(8)
        ov.addWidget(self.img_box)

        r1 = QHBoxLayout()
        r1.setSpacing(10)
        r1.addWidget(QLabel("Convert to"))
        self.fmt_box = QComboBox()
        self.fmt_box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        for key, spec in OUTPUTS.items():
            self.fmt_box.addItem(spec["label"], key)
        self.fmt_box.setCurrentIndex(list(OUTPUTS).index(self.cfg["format"]))
        self.fmt_box.currentIndexChanged.connect(self._on_format)
        r1.addWidget(self.fmt_box)
        r1.addSpacing(10)
        self.q_label = QLabel("Quality")
        self.q_slider = QSlider(Qt.Orientation.Horizontal)
        self.q_slider.setRange(1, 100)
        self.q_slider.setValue(int(self.cfg["quality"]))
        self.q_slider.setFixedWidth(120)
        self.q_value = muted(str(self.cfg["quality"]))
        self.q_value.setMinimumWidth(30)
        self.q_slider.valueChanged.connect(self._on_quality)
        self.chk_lossless = QCheckBox("Lossless")
        self.chk_lossless.setChecked(bool(self.cfg["lossless"]))
        self.chk_lossless.setToolTip("WebP only: exact pixels, bigger files. Quality is ignored.")
        self.chk_lossless.toggled.connect(self._on_lossless)
        self.fill_label = QLabel("Transparency fill")
        self.btn_fill = QPushButton()
        self.btn_fill.setToolTip("JPG, BMP and PDF can't store transparency,\nso see-through parts are filled with this colour.")
        self.btn_fill.clicked.connect(self.pick_fill)
        for w in (self.q_label, self.q_slider, self.q_value, self.chk_lossless):
            r1.addWidget(w)
        r1.addStretch(1)
        ib.addLayout(r1)

        r2 = QHBoxLayout()
        r2.setSpacing(10)
        r2.addWidget(QLabel("Save to"))
        self.out_box = QComboBox()
        self.out_box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.out_box.addItem("Next to the originals", "next")
        self.out_box.addItem("A chosen folder", "folder")
        self.out_box.setCurrentIndex(0 if self.cfg["out_mode"] == "next" else 1)
        self.out_box.currentIndexChanged.connect(self._on_out_mode)
        r2.addWidget(self.out_box)
        self.btn_out = QPushButton("Choose folder")
        self.btn_out.clicked.connect(self.choose_out_dir)
        r2.addWidget(self.btn_out)
        self.out_label = muted("")
        r2.addWidget(self.out_label, 1)
        self._save_row = r2

        r3 = QHBoxLayout()
        r3.setSpacing(10)
        r3.addWidget(QLabel("Animations"))
        self.anim_box = QComboBox()
        self.anim_box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        for k, label in ANIM_CHOICES:
            self.anim_box.addItem(label, k)
        self.anim_box.setCurrentIndex([k for k, _ in ANIM_CHOICES].index(self.cfg["anim"]))
        self.anim_box.setToolTip("Animated GIF/WebP/PNG/AVIF input.\n'Keep animation' works when converting "
                                 "to GIF, WebP, PNG or AVIF;\nTIFF and PDF get one page per frame.")
        self.anim_box.currentIndexChanged.connect(lambda _: self._set_cfg("anim", self.anim_box.currentData()))
        r3.addWidget(self.anim_box)
        r3.addSpacing(16)
        r3.addWidget(self.fill_label)
        r3.addWidget(self.btn_fill)
        r3.addStretch(1)
        ib.addLayout(r3)
        self.chk_skip = QCheckBox("Skip files already in that format")
        self.chk_skip.setChecked(bool(self.cfg["skip_same"]))
        self.chk_skip.toggled.connect(lambda v: self._set_cfg("skip_same", v))
        ib.addWidget(self.chk_skip)
        self._ov = ov

        # video & audio options
        self.media_box = QWidget()
        mb = QVBoxLayout(self.media_box)
        mb.setContentsMargins(0, 0, 0, 0)
        mb.setSpacing(8)
        m1 = QHBoxLayout()
        m1.setSpacing(10)
        m1.addWidget(QLabel("Convert to"))
        self.mfmt_box = QComboBox()
        self.mfmt_box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        for k, spec in MEDIA_OUTPUTS.items():
            self.mfmt_box.addItem(spec["label"], k)
        self.mfmt_box.setCurrentIndex(max(0, self.mfmt_box.findData(self.cfg["mformat"])))
        self.mfmt_box.currentIndexChanged.connect(self._on_media_format)
        m1.addWidget(self.mfmt_box)
        m1.addSpacing(10)
        self.v_label = QLabel("Video")
        self.vcodec_box = QComboBox()
        self.vcodec_box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.vcodec_box.currentIndexChanged.connect(self._on_codec_picked)
        self.a_label = QLabel("Audio")
        self.acodec_box = QComboBox()
        self.acodec_box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.acodec_box.currentIndexChanged.connect(self._on_codec_picked)
        for w in (self.v_label, self.vcodec_box, self.a_label, self.acodec_box):
            m1.addWidget(w)
        m1.addStretch(1)
        mb.addLayout(m1)
        m2 = QHBoxLayout()
        m2.setSpacing(10)
        self.mq_label = QLabel("Quality")
        self.mq_slider = QSlider(Qt.Orientation.Horizontal)
        self.mq_slider.setRange(1, 100)
        self.mq_slider.setValue(int(self.cfg["mquality"]))
        self.mq_slider.setFixedWidth(120)
        self.mq_slider.setToolTip("Higher = better picture and sound, bigger files")
        self.mq_value = muted(str(self.cfg["mquality"]))
        self.mq_value.setMinimumWidth(30)
        self.mq_slider.valueChanged.connect(self._on_mquality)
        self.size_label = QLabel("Size")
        self.size_box = QComboBox()
        self.size_box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        for h, label in SIZES:
            self.size_box.addItem(label, h)
        self.size_box.setCurrentIndex(max(0, self.size_box.findData(int(self.cfg["height"]))))
        self.size_box.setToolTip("Shrinks taller videos to this height. Never enlarges.")
        self.size_box.currentIndexChanged.connect(lambda _: self._set_cfg("height", self.size_box.currentData()))
        for w in (self.mq_label, self.mq_slider, self.mq_value, self.size_label, self.size_box):
            m2.addWidget(w)
        m2.addStretch(1)
        mb.addLayout(m2)
        self.media_note = muted("")
        self.media_note.setWordWrap(True)
        mb.addWidget(self.media_note)
        ov.addWidget(self.media_box)
        ov.addLayout(self._save_row)
        outer.addWidget(opts)
        self._refresh_out_label()
        self._refresh_format_controls()

        # results
        res = card()
        rv = QVBoxLayout(res)
        rv.setContentsMargins(16, 12, 16, 12)
        rv.setSpacing(8)
        self.log = QListWidget()
        self.log.setObjectName("log")
        self.log.setToolTip("Double-click a converted file to open it")
        self.log.itemDoubleClicked.connect(self._open_item)
        rv.addWidget(self.log, 1)
        foot = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedWidth(130)
        self.status = muted("Ready.")
        self.btn_open = QPushButton("Open output folder")
        self.btn_open.clicked.connect(self.open_out_folder)
        self.btn_clear = QPushButton("Clear list")
        self.btn_clear.clicked.connect(self.clear_log)
        foot.addWidget(self.progress)
        foot.addWidget(self.status, 1)
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setToolTip("Stop converting (the file in progress is discarded)")
        self.btn_stop.clicked.connect(self.stop_all)
        self.btn_stop.setVisible(False)
        foot.addWidget(self.btn_stop)
        foot.addWidget(self.btn_open)
        foot.addWidget(self.btn_clear)
        rv.addLayout(foot)
        outer.addWidget(res, 3)
        self.trail = HorseTrail()
        outer.addWidget(self.trail)
        self.lane = QWidget()                        # empty strip at the bottom for "run" actors
        self.lane.setFixedHeight(72)
        self.lane.hide()
        outer.addWidget(self.lane)

        self.mode_group.idClicked.connect(lambda i: self.set_mode("media" if i == 1 else "images"))
        self._refresh_media_controls()
        self.set_mode(self.cfg["mode"], save=False)

        self.swarm = BeeSwarm(self.backdrop)        # created last so it flies above everything
        self.backdrop.swarm = self.swarm
        self.actor_layer = ActorLayer(self.backdrop)
        self.backdrop.actor_layer = self.actor_layer
        self.fx = FxLayer(self.backdrop)
        self.backdrop.fx_layer = self.fx
        self.banner = Banner(self.backdrop)
        self._dodge_targets = {self.btn_wall, self.btn_wall_rm, self.btn_more, self.btn_open,
                               self.btn_clear, self.btn_out}

    # ---- mode
    def set_mode(self, mode: str, save=True):
        media = mode == "media"
        self.cfg["mode"] = "media" if media else "images"
        self.btn_mode_media.setChecked(media)
        self.btn_mode_img.setChecked(not media)
        self.img_box.setVisible(not media)
        self.media_box.setVisible(media)
        self.drop.sub.setText("Video & audio: MP4, MKV, MOV, AVI, WebM, MP3, WAV, FLAC and more. Click to pick files."
                              if media else "or click to pick files. Folders work too.")
        self._refresh_hint()
        if media:
            self._refresh_media_controls()
        if save:
            self._save_cfg()

    def _refresh_hint(self, t: dict | None = None):
        if t is None:
            t = self.current_theme(getattr(self, "active_key", self.cfg["theme"]))
        hint = t.get("hint", "")
        if self.cfg.get("mode") == "media":
            media = t.get("hint_media")
            if not media:                     # themes made without hint_media: swap the word for them
                media = (hint.replace("IMAGES", "VIDEO & AUDIO").replace("images", "videos and audio")
                         .replace("Images", "Videos and audio"))
                if media == hint:
                    media = "Drop your videos and audio here"
            hint = media
        self.drop.hint.setText(hint)

    def _on_media_format(self, _idx):
        self._set_cfg("mformat", self.mfmt_box.currentData())
        self._refresh_media_controls()

    def _on_codec_picked(self, _idx):
        if self._filling_codecs:
            return
        if self.vcodec_box.isVisible() and self.vcodec_box.currentData():
            self.cfg["vcodec"] = self.vcodec_box.currentData()
        if self.acodec_box.isVisible() and self.acodec_box.currentData():
            self.cfg["acodec"] = self.acodec_box.currentData()
        self._save_cfg()
        self._refresh_media_controls(refill=False)

    def _on_mquality(self, v):
        self.mq_value.setText(str(v))
        self._set_cfg("mquality", v)

    _filling_codecs = False

    def _refresh_media_controls(self, refill=True):
        spec = MEDIA_OUTPUTS[self.cfg["mformat"]]
        kind = spec["kind"]
        if refill:
            self._filling_codecs = True
            for box, ids, table, cfg_key in ((self.vcodec_box, spec["v"], VCODECS, "vcodec"),
                                             (self.acodec_box, spec["a"], ACODECS, "acodec")):
                box.clear()
                for cid in ids:
                    if codec_available(table[cid][1]) or not ffmpeg_exe():
                        box.addItem(table[cid][0], cid)
                i = box.findData(self.cfg[cfg_key])
                box.setCurrentIndex(i if i >= 0 else 0)
            self._filling_codecs = False
        video = kind == "video"
        for w in (self.v_label, self.vcodec_box):
            w.setVisible(video)
        for w in (self.a_label, self.acodec_box):
            w.setVisible(kind == "video")
        copy_v = video and self.vcodec_box.currentData() == "copy"
        for w in (self.size_label, self.size_box):
            w.setVisible(kind in ("video", "gif"))
            w.setEnabled(not copy_v)
        lossless_audio = kind == "audio" and spec["a"][0] in ("flac", "pcm")
        q_matters = not lossless_audio and not (copy_v and self.acodec_box.currentData() in ("copy", "none", "flac"))
        for w in (self.mq_label, self.mq_slider, self.mq_value):
            w.setEnabled(q_matters)
        self.media_note.setVisible(True)
        if not ffmpeg_exe():
            self.media_note.setText("FFmpeg wasn't found, so video and audio can't be converted. "
                                    "It's included when the app is built with build_exe.bat.")
        elif copy_v:
            self.media_note.setText("Keep original: copies the video as it is. Very fast, no quality loss, "
                                    "but only works if that codec fits the new container.")
        elif video and self.vcodec_box.currentData() == "av1":
            self.media_note.setText("AV1 gives the smallest files but encodes very slowly.")
        else:
            self.media_note.setText("")
            self.media_note.setVisible(False)

    def _media_opts(self) -> dict:
        spec = MEDIA_OUTPUTS[self.cfg["mformat"]]
        return {"mquality": self.cfg["mquality"], "height": int(self.cfg["height"] or 0),
                "vcodec": self.vcodec_box.currentData() if spec["kind"] == "video" else None,
                "acodec": (self.acodec_box.currentData() if spec["kind"] == "video"
                           else (spec["a"][0] if spec["a"] else None))}

    # ---- format options
    def _on_format(self, _idx):
        self._set_cfg("format", self.fmt_box.currentData())
        self._refresh_format_controls()

    def _on_quality(self, v):
        self.q_value.setText(str(v))
        self._set_cfg("quality", v)

    def _on_lossless(self, v):
        self._set_cfg("lossless", v)
        self._refresh_format_controls()

    def _refresh_format_controls(self):
        key = self.cfg["format"]
        spec = OUTPUTS[key]
        lossless = key == "WEBP" and self.chk_lossless.isChecked()
        for w in (self.q_label, self.q_slider, self.q_value):
            w.setVisible(spec["quality"])
            w.setEnabled(not lossless)
        self.chk_lossless.setVisible(key == "WEBP")
        for w in (self.fill_label, self.btn_fill):
            w.setVisible(not spec["alpha"])
        r, g, b = self.cfg["fill"]
        self.btn_fill.setText(f"#{r:02x}{g:02x}{b:02x}")
        self.btn_fill.setStyleSheet(
            f"QPushButton {{ background: rgb({r},{g},{b}); color: {'#000' if (r*299+g*587+b*114)/1000 > 128 else '#fff'}; }}")

    def pick_fill(self):
        c = QColorDialog.getColor(QColor(*self.cfg["fill"]), self, "Fill colour for transparent areas")
        if c.isValid():
            self._set_cfg("fill", [c.red(), c.green(), c.blue()])
            self._refresh_format_controls()

    # ---- theming
    def _on_theme_picked(self, _idx):
        key = self.theme_box.currentData()
        if self.forced:
            self._sync_theme_box(self.forced)
            self.sealed_reaction()
            return
        if key == "custom" and not self.custom_colors:
            if not self.pick_wallpaper():          # cancelled: go back to previous theme
                self._sync_theme_box(self.cfg["theme"])
            return
        self.apply_theme(key)

    def _sync_theme_box(self, key):
        self.theme_box.blockSignals(True)
        self.theme_box.setCurrentIndex(max(0, self.theme_box.findData(key)))
        self.theme_box.blockSignals(False)

    def _fill_theme_box(self):
        self.theme_box.blockSignals(True)
        self.theme_box.clear()
        n = 0
        for key in THEME_ORDER:
            if key in LOCKS and key not in self.unlocked:
                continue
            if key in HOLIDAY_KEYS and not self.sealed and key != self.forced:
                continue
            label = THEMES[key]["label"] if key in THEMES else CUSTOM_LABEL
            if self.forced == "aprilfools":                  # everything is a duck today
                label = APRIL_LABELS[n % len(APRIL_LABELS)]
            self.theme_box.addItem(label, key)
            n += 1
        self.theme_box.blockSignals(False)

    # ---- PIN: typed anywhere while the window is active (no box, nothing on screen)
    def eventFilter(self, obj, event):
        if (event.type() == QEvent.Type.MouseButtonPress and self.active_key == "aprilfools"
                and obj in getattr(self, "_dodge_targets", ()) and obj not in self._dodged):
            self._dodged.add(obj)
            old = obj.text()
            obj.setText(random.choice(["Missed me! 🦆", "Nope 🦆", "Too slow! 🦆", "Try again 🦆"]))
            QTimer.singleShot(900, lambda o=obj, t=old: o.setText(t))
            return True
        if (event.type() == QEvent.Type.KeyPress
                and isinstance(obj, QWindow) and obj is self.windowHandle()
                and not event.isAutoRepeat()):
            ch = event.text()
            if ch and ch.isprintable():
                self._typed = (self._typed + ch)[-_TYPED_MAX:]
                n = SEAL["length"]
                if len(self._typed) >= n and _seal_ok(self._typed[-n:]):
                    self._typed = ""
                    self._open_seal()
                    return super().eventFilter(obj, event)
                for theme, lk in LOCKS.items():
                    n = lk["length"]
                    if theme not in self.unlocked and len(self._typed) >= n and _code_ok(theme, self._typed[-n:]):
                        self._typed = ""
                        self._unlock(theme)
                        break
        return super().eventFilter(obj, event)

    def _unlock(self, theme: str):
        self.unlocked.add(theme)
        where = save_unlock(theme)
        self._fill_theme_box()
        name = LOCKS[theme]["name"]
        if self.forced:                       # unlocked for later; today belongs to the holiday
            self._sync_theme_box(self.forced)
            self.status.setText(f"{name} theme unlocked. You can use it once the holiday seal breaks.")
            return
        self.apply_theme(theme)
        self.status.setText(f"{name} theme unlocked." if where else
                            f"{name} theme unlocked for now (couldn't save the unlock file).")

    def current_theme(self, key: str) -> dict:
        if key == "custom":
            t = dict(THEMES[self.cfg["base_theme"]])   # keep fonts/shapes of the last theme...
            t.update(self.custom_colors or {})          # ...but colours from the wallpaper
            t["backdrop"] = "wallpaper"
            # Socialab branding (bee, edition name, stripes, flying bees) belongs to the Socialab theme only
            for k in ("logo", "credit", "stripes", "bees", "stripe_a", "stripe_b", "horses", "actors",
                      "fireworks", "burst", "troll"):
                t.pop(k, None)
            return t
        if key == "socialab" and self.cfg.get("soc_dark"):
            return THEMES["socialab_dark"]
        return THEMES[key]

    def _on_dark_toggled(self, on: bool):
        if self.forced:
            self.chk_dark.blockSignals(True)
            self.chk_dark.setChecked(not on)
            self.chk_dark.blockSignals(False)
            self.sealed_reaction()
            return
        self.cfg["soc_dark"] = bool(on)
        if self.cfg["theme"] == "socialab":
            self.apply_theme("socialab")
        else:
            self._save_cfg()

    def apply_theme(self, key: str, persist: bool = True):
        if persist:
            if key != "custom":
                self.cfg["base_theme"] = key
            self.cfg["theme"] = key
        self.active_key = key
        t = self.current_theme(key)
        family, pt = resolve_font(t["fonts"])
        tfamily, tpt = resolve_font(t["title_fonts"])
        app = QApplication.instance()
        app.setFont(QFont(family, int(round(pt))))
        app.setStyleSheet(build_qss(t, family, pt, tfamily, tpt))

        troll = bool(t.get("troll"))
        self.title.setText(upside_down(t["title"]) if troll else t["title"])
        credit = t.get("credit", APP_CREDIT)
        self.subtitle.setText(credit)
        self.setWindowTitle(f"{APP_TITLE} {credit}" + (" 🦆" if troll else ""))
        self.fx.set_ambient(bool(t.get("fireworks")))
        self._refresh_hint(t)
        self.chk_dark.setVisible(key == "socialab")
        if t.get("bees"):
            self.swarm.start()
        else:
            self.swarm.stop()
        if t.get("horses"):
            self.trail.start()
        else:
            self.trail.stop()
        specs = t.get("actors") or []
        runs = any(a["motion"] == "run" for a in specs)
        self.lane.setVisible(runs and not t.get("horses"))
        lane_w = self.trail if t.get("horses") else self.lane
        QTimer.singleShot(0, lambda: self.actor_layer.set_specs(specs, lane_w))
        icon = theme_icon(t)
        self.logo.setPixmap(icon.pixmap(56, 56))
        self.setWindowIcon(icon)
        app.setWindowIcon(icon)
        self.stripes.a = QColor(t.get("stripe_a", t["accent"]))
        self.stripes.b = QColor(t.get("stripe_b", t["border"]))
        self.stripes.style = "stitch" if t.get("stripes") == "stitch" else "bee"
        self.stripes.setFixedHeight(10 if self.stripes.style == "stitch" else 8)
        self.stripes.setVisible(bool(t.get("stripes")))
        self.stripes.update()
        self.backdrop.set_look(t, self.wall_pm if key == "custom" else None)
        self._apply_effects(t)
        self._sync_theme_box(key)
        self._refresh_wall_buttons()
        self._refresh_format_controls()       # re-apply the fill button's own colours
        if persist:
            self._save_cfg()
            self._sync_shortcuts()

    # ---- themes folder
    def open_themes_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(themes_dir())))

    def reload_themes(self):
        load_theme_folder()
        self._fill_theme_box()
        if self.forced:
            self.apply_theme(self.forced, persist=False)
            self._report_theme_problems(prefix="Themes reloaded.")
            return
        key = self.cfg["theme"] if self.cfg["theme"] in THEME_ORDER else DEFAULTS["theme"]
        if (key in LOCKS and key not in self.unlocked) or (key in HOLIDAY_KEYS and not self.sealed):
            key = DEFAULTS["theme"]
        self.apply_theme(key)
        self._report_theme_problems(prefix="Themes reloaded.")

    def _report_theme_problems(self, prefix=""):
        if THEME_PROBLEMS:
            self.status.setText(f"{prefix} Skipped {len(THEME_PROBLEMS)} theme(s): " + "; ".join(THEME_PROBLEMS)[:220])
            self.status.setToolTip("\n".join(THEME_PROBLEMS))
        elif prefix:
            self.status.setText(prefix)

    # ---- uninstall
    def uninstall(self):
        if not shortcuts_supported():
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Uninstall Universal Converter")
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(18, 16, 18, 14)
        lay.setSpacing(10)
        head = QLabel("Remove Universal Converter from this PC?")
        head.setStyleSheet("font-weight: bold;")
        lay.addWidget(head)
        info = QLabel()
        info.setWordWrap(True)
        lay.addWidget(info)
        keep = QCheckBox("Keep my themes folder (custom themes you made)")
        lay.addWidget(keep)
        note = muted("Your converted pictures, videos and audio are never touched.\nThis can't be undone.")
        lay.addWidget(note)
        buttons = QDialogButtonBox()
        btn_go = buttons.addButton("Uninstall", QDialogButtonBox.ButtonRole.DestructiveRole)
        buttons.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        btn_go.clicked.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        lay.addWidget(buttons)

        def describe():
            plan = uninstall_plan(self.cfg, keep.isChecked())
            names = []
            for pth, kind in plan:
                if kind == "emptydir":
                    continue
                if kind == "file" and pth.suffix.lower() == ".exe":
                    names.append(f"• the app: {pth}")
                elif pth.suffix.lower() == ".lnk":
                    names.append(f"• shortcut: {pth}")
                else:
                    names.append(f"• {pth}")
            folder_names = sum(1 for _, k in plan if k == "tree" and _.parent.name == "themes")
            shown = [n for n in names if "\\themes\\" not in n and "/themes/" not in n]
            if folder_names:
                shown.append(f"• {folder_names} theme folder(s) in {base_dir() / 'themes'}")
            info.setText("This removes:\n" + "\n".join(shown) +
                         "\n\nThe app's folder is removed too if nothing else is left in it.")
        keep.toggled.connect(lambda _: describe())
        describe()
        btn_go.setFocus()
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        plan = uninstall_plan(self.cfg, keep.isChecked())
        if not launch_uninstall(plan):
            QMessageBox.warning(self, "Uninstall", "Couldn't start the uninstaller. Nothing was removed.")
            return
        self._uninstalling = True
        QMessageBox.information(self, "Uninstall", "Universal Converter will now close and remove itself.")
        self.close()
        QApplication.instance().quit()

    # ---- shortcuts
    def create_shortcuts(self):
        if not shortcuts_supported():
            return
        made = [str(p) for p in shortcut_paths()]
        self.cfg["shortcuts"] = made
        self._save_cfg()
        self._sync_shortcuts(announce=True)

    def _sync_shortcuts(self, announce=False):
        if not shortcuts_supported():
            return
        paths = [Path(p) for p in self.cfg.get("shortcuts", [])]
        if not announce:
            paths = [p for p in paths if p.exists()]     # only refresh shortcuts that still exist
        if not paths:
            return
        key = self.cfg["theme"]
        t = self.current_theme(key)
        ico_key = "socialab" if key == "socialab" else (key if key != "custom" else self.cfg["base_theme"])
        target = Path(sys.executable)

        def work():
            ico = theme_ico_file(ico_key, self.current_theme(ico_key) if ico_key != key else t)
            ok = bool(ico) and all(write_shortcut(p, target, ico) for p in paths)
            if announce:
                self.bus.note.emit("Shortcut created on the desktop and in the Start menu." if ok
                                   else "Couldn't create the shortcut.")
        threading.Thread(target=work, daemon=True).start()

    def _apply_effects(self, t: dict):
        for w in (self.header, self.drop):
            kind = t.get("effect")
            eff = QGraphicsDropShadowEffect(w)
            if kind == "hard":
                eff.setBlurRadius(0)
                eff.setOffset(6, 6)
                eff.setColor(QColor(0, 0, 0, 255))
            elif kind == "glow":
                c = QColor(t["accent"])
                c.setAlpha(110)
                eff.setBlurRadius(32)
                eff.setOffset(0, 0)
                eff.setColor(c)
            elif kind == "soft":
                eff.setBlurRadius(22)
                eff.setOffset(0, 5)
                eff.setColor(QColor(50, 25, 5, 120))
            else:
                eff = None
            w.setGraphicsEffect(eff)

    # ---- wallpaper
    def _load_wallpaper(self):
        self.wall_pm, self.custom_colors = None, None
        if self.wall_path.is_file():
            pm = QPixmap(str(self.wall_path))
            if not pm.isNull():
                try:
                    self.custom_colors = wallpaper_colors(self.wall_path)
                    self.wall_pm = pm
                except Exception:
                    self.custom_colors = None

    def _refresh_wall_buttons(self):
        has = self.wall_pm is not None
        self.btn_wall.setText("Replace wallpaper" if has else "Set wallpaper")
        self.btn_wall_rm.setEnabled(has)

    def sealed_reaction(self):
        """Someone tried to change the theme on a holiday: shake, drop things, explain."""
        key = self.forced
        t = THEMES.get(key, {})
        self.shake()
        burst = t.get("burst") or []
        if burst == ["fireworks"]:
            self.fx.fireworks(7)
        elif burst:
            self.fx.rain([str(res_dir() / "assets" / "holidays" / b) for b in burst], t.get("burst_size", 50))
        title, text = SEALED_MESSAGES.get(key, ("Sealed", "Themes can't be changed until {until}."))
        until = self.forced_until.strftime("%d %B").lstrip("0") if self.forced_until else "tomorrow"
        self.banner.pop(title, text.format(until=until))

    def shake(self):
        if self.isMaximized() or self.isFullScreen():
            target, start = self.backdrop, self.backdrop.pos()
        else:
            target, start = self, self.pos()
        anim = QVariantAnimation(self)
        anim.setDuration(520)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)

        def step(v):
            k = float(v)
            off = int(math.sin(k * 34) * 14 * (1 - k))
            target.move(start + QPoint(off, int(math.cos(k * 29) * 4 * (1 - k))))
        anim.valueChanged.connect(step)
        anim.finished.connect(lambda: target.move(start))
        anim.start()
        self._shake_anim = anim

    def _check_holiday(self):
        if self.sealed:
            return
        forced, until = forced_holiday(today())
        if forced == self.forced:
            return
        self.forced, self.forced_until = forced, until
        self._fill_theme_box()
        if forced:
            self.apply_theme(forced, persist=False)
        else:
            self.apply_theme(self.cfg["theme"] if self.cfg["theme"] not in HOLIDAY_KEYS else DEFAULTS["theme"])
            self.banner.pop("The seal is broken", "You can change themes again.")

    def _open_seal(self):
        save_seal()
        was_forced = self.forced
        self.sealed = True
        self.forced = self.forced_until = None
        self._fill_theme_box()
        if was_forced:
            key = self.cfg["theme"] if self.cfg["theme"] not in LOCKS or self.cfg["theme"] in self.unlocked else DEFAULTS["theme"]
            self.apply_theme(key)
        else:
            self._sync_theme_box(self.active_key)
        self.banner.pop("You've unlocked the seal",
                        "Every holiday theme is now in the theme list,\nand none of them will take over again.", 5500)

    # ---- April Fools
    def _april_tick(self):
        if self.active_key != "aprilfools":
            return
        self._april_i += 1
        pool = APRIL_HINTS_MEDIA if self.cfg.get("mode") == "media" else APRIL_HINTS
        self.drop.hint.setText(pool[self._april_i % len(pool)])

    def pick_wallpaper(self) -> bool:
        if self.forced:
            self.sealed_reaction()
            return False
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose a wallpaper", "",
            "Images (*.png *.jpg *.jpeg *.webp *.avif *.bmp *.gif *.tif *.tiff);;All files (*)")
        if not path:
            return False
        tmp = self.data / "wallpaper.new.png"
        try:
            with Image.open(path) as im:
                im = ImageOps.exif_transpose(im).convert("RGB")
            im.thumbnail((3840, 3840))
            im.save(tmp, "PNG")
            os.replace(tmp, self.wall_path)
        except Exception as e:
            tmp.unlink(missing_ok=True)
            QMessageBox.warning(self, "Wallpaper", f"Couldn't use that image.\n\n{e}")
            return False
        self._load_wallpaper()
        if not self.custom_colors:
            QMessageBox.warning(self, "Wallpaper", "Couldn't read colours from that image.")
            return False
        self.apply_theme("custom")
        self.status.setText("Wallpaper set.")
        return True

    def remove_wallpaper(self):
        if self.forced:
            self.sealed_reaction()
            return
        try:
            self.wall_path.unlink(missing_ok=True)
        except OSError as e:
            QMessageBox.warning(self, "Wallpaper", f"Couldn't delete the wallpaper copy.\n\n{e}")
            return
        self.wall_pm, self.custom_colors = None, None
        self.apply_theme(self.cfg["base_theme"])
        self.status.setText("Wallpaper removed. Your original image file was not touched.")

    # ---- output location
    def _on_out_mode(self, _idx):
        mode = self.out_box.currentData()
        if mode == "folder" and not Path(self.cfg["out_dir"] or "\0").is_dir():
            if not self.choose_out_dir():
                self.out_box.blockSignals(True)
                self.out_box.setCurrentIndex(0)
                self.out_box.blockSignals(False)
                mode = "next"
        self._set_cfg("out_mode", mode)
        self._refresh_out_label()

    def choose_out_dir(self) -> bool:
        d = QFileDialog.getExistingDirectory(self, "Save converted files to…", self.cfg["out_dir"] or "")
        if not d:
            return False
        self.cfg["out_dir"] = d
        self.cfg["out_mode"] = "folder"
        self.out_box.blockSignals(True)
        self.out_box.setCurrentIndex(1)
        self.out_box.blockSignals(False)
        self._save_cfg()
        self._refresh_out_label()
        return True

    def _refresh_out_label(self):
        folder_mode = self.cfg["out_mode"] == "folder" and self.cfg["out_dir"]
        text = self.cfg["out_dir"] if folder_mode else ""
        self.out_label.setText(self.out_label.fontMetrics().elidedText(text, Qt.TextElideMode.ElideMiddle, 300))
        self.out_label.setToolTip(text)

    # ---- drag & drop
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self.drop.set_hover(True)

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self.drop.set_hover(False)

    def dropEvent(self, e):
        self.drop.set_hover(False)
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        e.acceptProposedAction()
        if self.cfg["mode"] == "media":
            self.enqueue_media(*collect_media(paths))
        else:
            self.enqueue(*collect_images(paths))

    def browse_files(self):
        if self.cfg["mode"] == "media":
            pattern = " ".join(f"*{x}" for x in sorted(MEDIA_EXTS))
            files, _ = QFileDialog.getOpenFileNames(self, "Choose video or audio files", "",
                                                    f"Video and audio ({pattern});;All files (*)")
            if files:
                self.enqueue_media(*collect_media(files))
            return
        pattern = " ".join(f"*{x}" for x in sorted(READ_EXTS))
        files, _ = QFileDialog.getOpenFileNames(self, "Choose images", "",
                                                f"Images ({pattern});;All files (*)")
        if files:
            self.enqueue(*collect_images(files))

    # ---- conversion
    def enqueue(self, items: list[tuple[Path, str]], skipped: int = 0):
        key = self.cfg["format"]
        same = 0
        if self.cfg["skip_same"]:
            target = OUTPUTS[key]["pil"]
            kept = [(p, f) for p, f in items if f != target]
            same = len(items) - len(kept)
            items = kept
        notes = []
        if skipped:
            notes.append(f"{skipped} not an image")
        if same:
            notes.append(f"{same} already {OUTPUTS[key]['label']}")
        extra = f" Skipped: {', '.join(notes)}." if notes else ""
        if not items:
            self.status.setText("Nothing to convert." + extra)
            return
        if self.cfg["out_mode"] == "folder":
            out = Path(self.cfg["out_dir"]) if self.cfg["out_dir"] else None
            if out is None or not out.is_dir():
                if not self.choose_out_dir():
                    self.status.setText("Pick an output folder first.")
                    return
                out = Path(self.cfg["out_dir"])
        else:
            out = None
        if self.ok + self.fail >= self.total:     # idle: start a fresh batch count
            self.total = self.ok = self.fail = 0
        self.total += len(items)
        self.progress.setRange(0, self.total)
        self.progress.setValue(self.ok + self.fail)
        self.status.setText(f"Converting {self.total - self.ok - self.fail} file(s) to "
                            f"{OUTPUTS[key]['label']}…" + extra)
        opts = {"quality": self.cfg["quality"], "lossless": self.cfg["lossless"],
                "anim": self.cfg["anim"], "fill": tuple(self.cfg["fill"])}
        self._begin_batch()
        for p, _fmt in items:
            self.futures.append(self.pool.submit(self._job, p, out or p.parent, key, opts))

    def _output_folder(self) -> tuple[bool, Path | None]:
        if self.cfg["out_mode"] != "folder":
            return True, None
        out = Path(self.cfg["out_dir"]) if self.cfg["out_dir"] else None
        if out is None or not out.is_dir():
            if not self.choose_out_dir():
                self.status.setText("Pick an output folder first.")
                return False, None
            out = Path(self.cfg["out_dir"])
        return True, out

    def _begin_batch(self):
        if self.stop_event.is_set():
            self.stop_event.clear()
        self.btn_stop.setVisible(True)

    def enqueue_media(self, items: list[tuple[Path, str]], skipped: int = 0):
        if not ffmpeg_exe():
            self.status.setText("Video and audio need FFmpeg, which wasn't found.")
            return
        extra = f" Skipped: {skipped} not a video or audio file." if skipped else ""
        if not items:
            self.status.setText("Nothing to convert." + extra)
            return
        ok, out = self._output_folder()
        if not ok:
            return
        if self.ok + self.fail >= self.total:
            self.total = self.ok = self.fail = 0
        self.total += len(items)
        self.progress.setRange(0, self.total)
        self.progress.setValue(self.ok + self.fail)
        key = self.cfg["mformat"]
        self.status.setText(f"Converting {self.total - self.ok - self.fail} file(s) to "
                            f"{MEDIA_OUTPUTS[key]['label']}…" + extra)
        opts = self._media_opts()
        self._begin_batch()
        for p, _ext in items:
            self.futures.append(self.media_pool.submit(self._media_job, p, out or p.parent, key, opts))

    def _media_job(self, src: Path, out_dir: Path, key: str, opts: dict):   # worker thread
        try:
            outs, note = convert_media(src, out_dir, key, opts,
                                       lambda pct: self.bus.progress.emit(str(src), pct),
                                       self.stop_event, self.running_procs)
            self.bus.finished.emit(str(src), [str(o) for o in outs], note, "")
        except Stopped:
            self.bus.finished.emit(str(src), [], "", "Stopped")
        except Exception as e:
            self.bus.finished.emit(str(src), [], "", f"{type(e).__name__}: {e}" if not isinstance(e, RuntimeError) else str(e))

    def _on_progress(self, src: str, pct: float):
        done = self.ok + self.fail
        self.status.setText(f"Converting {Path(src).name}… {pct:.0f}%   ({done + 1} of {self.total})")

    def stop_all(self):
        self.stop_event.set()
        for f in self.futures:
            f.cancel()
        for proc in list(self.running_procs):
            try:
                proc.kill()
            except Exception:
                pass
        running = sum(1 for f in self.futures if not f.done() and not f.cancelled())
        self.futures = [f for f in self.futures if not f.cancelled()]
        self.total = self.ok + self.fail + running
        self.progress.setRange(0, max(1, self.total))
        if running == 0:
            self.btn_stop.setVisible(False)
            self.status.setText(f"Stopped. {self.ok} converted" + (f", {self.fail} failed." if self.fail else "."))
        else:
            self.status.setText("Stopping…")

    def _job(self, src: Path, out_dir: Path, key: str, opts: dict):  # runs in a worker thread
        try:
            outs, note = convert_image(src, out_dir, key, opts)
            self.bus.finished.emit(str(src), [str(o) for o in outs], note, "")
        except Exception as e:
            self.bus.finished.emit(str(src), [], "", f"{type(e).__name__}: {e}")

    def _on_done(self, src: str, outs: list, note: str, err: str):
        name = Path(src).name
        if err:
            self.fail += 1
            item = QListWidgetItem(f"✖  {name}  —  {err}")
            item.setToolTip(src)
        else:
            self.ok += 1
            first = Path(outs[0])
            self.last_out_dir = first.parent
            extra = f"   ({note})" if note else ""
            item = QListWidgetItem(f"✔  {name}  →  {first.name}{extra}")
            item.setData(Qt.ItemDataRole.UserRole, str(first))
            item.setToolTip(str(first))
        self.log.addItem(item)
        self.log.scrollToBottom()
        done = self.ok + self.fail
        self.progress.setValue(done)
        if done >= self.total:
            stopped = self.stop_event.is_set()
            if stopped:
                self.status.setText(f"Stopped. {self.ok} converted before stopping.")
            else:
                self.status.setText(f"Done. {self.ok} of {self.total} converted" +
                                    (f", {self.fail} failed." if self.fail else ".") +
                                    (" " + random.choice(APRIL_QUIPS) if self.active_key == "aprilfools" else ""))
            self.btn_stop.setVisible(False)
            self.futures = []
        else:
            self.status.setText(f"Converting… {done} of {self.total}")

    def _open_item(self, item: QListWidgetItem):
        p = item.data(Qt.ItemDataRole.UserRole)
        if p and Path(p).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(p))

    def open_out_folder(self):
        d = self.last_out_dir or (Path(self.cfg["out_dir"]) if self.cfg["out_dir"] else None)
        if d and d.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(d)))
        else:
            self.status.setText("Nothing converted yet.")

    def clear_log(self):
        if self.ok + self.fail < self.total:
            self.status.setText("Still converting. Clear when it's done.")
            return
        self.log.clear()
        self.total = self.ok = self.fail = 0
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.status.setText("Ready.")

    _uninstalling = False

    def closeEvent(self, e):
        if not self._uninstalling:
            self.cfg["geometry"] = bytes(self.saveGeometry().toBase64()).decode()
            self._save_cfg()
        self.stop_event.set()
        for proc in list(self.running_procs):
            try:
                proc.kill()
            except Exception:
                pass
        self.pool.shutdown(wait=True, cancel_futures=True)
        self.media_pool.shutdown(wait=True, cancel_futures=True)
        super().closeEvent(e)


def main():
    QApplication.setApplicationName("Universal Converter")
    if sys.platform == "win32":   # own taskbar icon instead of the generic Python one
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("zeharyus.UniversalConverter.App")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setWindowIcon(app_icon("crow"))
    load_bundled_fonts()
    load_theme_folder()
    win = Converter(sys.argv[1:])
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
