# Third-party notices

Universal Converter is made by **zeharyus** and released under the MIT License (see `LICENSE`).
The app bundles the open-source software and fonts below. Each keeps its own license;
the full license texts are in the `licenses` folder.

| Part | What it does in the app | License | License file |
|---|---|---|---|
| **Python** (CPython 3) | Runs the app | Python Software Foundation License | `licenses/Python-LICENSE.txt` |
| **PyInstaller** 6.22.3 | Packs everything into one .exe | GPL 2.0 with the Bootloader Exception (no obligations for the packed app) | `licenses/PyInstaller-COPYING.txt` |
| **Qt 6 / PySide6** 6.12.0 (with Shiboken6) | Window, buttons, drawing | GNU LGPL 3.0 | `licenses/LGPL-3.0.txt` (+ `licenses/GPL-3.0.txt`) |
| **Pillow** 12.1.1 | Reads and writes images | MIT-CMU (HPND) | `licenses/Pillow-LICENSE.txt` |
| ↳ bundled in Pillow | brotli, FreeType, HarfBuzz, Little CMS, libavif, libjpeg-turbo, libpng, libwebp, OpenJPEG, LibTIFF, XZ, zlib-ng | Their own licenses (BSD, MIT, FreeType, IJG, zlib, libpng and similar) | inside `licenses/Pillow-LICENSE.txt` |
| **imageio-ffmpeg** 0.6.0 | Delivers FFmpeg | BSD 2-Clause | `licenses/imageio-ffmpeg-LICENSE.txt` |
| **FFmpeg** 7.1 (Gyan.dev essentials build) | Converts video and audio | GNU GPL 3.0 | `licenses/GPL-3.0.txt`, `licenses/FFmpeg-LICENSE.md`, `licenses/FFmpeg-NOTICE.txt` (source links) |

## Fonts

All fonts are under the SIL Open Font License 1.1 (texts in `licenses/fonts`).

| Font | Copyright |
|---|---|
| Cinzel | Copyright 2020 The Cinzel Project Authors (https://github.com/NDISCOVER/Cinzel) |
| IM FELL English | Copyright (c) 2010, Igino Marini (mail@iginomarini.com) |
| UnifrakturMaguntia | Copyright (c) 2010, j. 'mach' wust, with Reserved Font Name UnifrakturMaguntia |
| Press Start 2P | Copyright 2012 The Press Start 2P Project Authors (cody@zone38.net), with Reserved Font Name "Press Start 2P" |
| Rye | Copyright (c) 2011 by Sorkin Type Co (www.sorkintype.com), with Reserved Font Name "Rye" |
| Rokkitt | Copyright 2016 The Rokkit Project Authors (https://github.com/googlefonts/RokkittFont) |

Rokkitt Medium is a fixed-weight version made from the Rokkitt variable font, as the license allows.

## More information

- Qt's own third-party components: https://doc.qt.io/qt-6/licenses-used-in-qt.html
- Python's incorporated software (Windows builds include OpenSSL, libffi and others): https://docs.python.org/3/license.html
- FFmpeg source code and build details: `licenses/FFmpeg-NOTICE.txt`
- Qt and PySide6 are used unmodified. Source code: PySide6 at https://download.qt.io/official_releases/QtForPython/pyside6/ and Qt at https://download.qt.io/official_releases/qt/

## Graphics

The app's icons, the Elden-style, Medieval and Pixel theme graphics and the Example Theme
pictures were made for Universal Converter and are covered by its MIT License.
