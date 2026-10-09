UNIVERSAL CONVERTER
===================

Convert images, videos and audio on Windows, with themes you can make
yourself.

Download: see "Releases" on the right-hand side of this page.


WHAT IT IS
----------

Universal Converter is a desktop program for Windows that changes files from
one format to another. It handles three kinds of files in one place:

  - Images
  - Videos
  - Audio

You don't need to install anything extra or type any commands. Download it,
unzip it, and open it like any other program.

The look of the program is controlled by themes, so you can change its
colors, lettering and style. You can also make your own themes and share them
with other people.


WHAT IT CAN CONVERT
-------------------

  Images   Converted with Pillow.
  Video    Converted with FFmpeg (including H.264 and H.265 video).
  Audio    Converted with FFmpeg.

  [FILL IN: list the exact formats the app supports, for example
   PNG, JPG, WEBP for images / MP4, MKV, WEBM for video / MP3, WAV, FLAC
   for audio.]


HOW TO INSTALL
--------------

  1. Go to "Releases" on this page and download the latest
     UniversalConverter-...-windows.zip file.
  2. Unzip it. Right-click the zip and choose "Extract All".
  3. Open the "Universal Converter" folder and run the program (the .exe)
     inside it.

Keep the program's files together in that folder. The program needs the files
next to it, so don't move the .exe out on its own.


HOW TO USE IT
-------------

  [FILL IN: a few simple steps, for example:
   1. Open the program.
   2. Drag your files into the window, or click Add.
   3. Pick the format you want.
   4. Click Convert.]

  Screenshot: [add a picture of the app here]


THEMES
------

Themes change how the program looks. You can use the themes that come with
it, or make your own and share them.

  [FILL IN: where theme files go and what a theme contains, so people know
   how to make one.]

A theme may only contain your own work. It must not contain any of Universal
Converter's code or graphics, and you shouldn't put pictures or fonts in a
theme unless you have the right to share them.


RUNNING FROM THE SOURCE CODE
----------------------------

If you want to run the program from its code instead of the download, you
need:

  - Python
  - PySide6, Pillow and imageio-ffmpeg (install them with pip)

Then run:

  python universal_converter.py


LICENSE
-------

See the file named LICENSE for what you may and may not do with Universal
Converter.

The parts of Universal Converter that other people made keep their own
licenses. See THIRD_PARTY_NOTICES.md and the "licenses" folder.


CREDITS
-------

Universal Converter is made by zeharyus.

It is built with free software and fonts made by other people. Thank you to:

  Python            Runs the app. PSF License. https://www.python.org
  PyInstaller       Packs the app into a program. GPL 2.0 with the
                    Bootloader Exception. https://pyinstaller.org
  Qt 6 / PySide6    The windows and buttons. LGPL 3.0. https://www.qt.io
  Pillow            Image conversion. MIT-CMU license.
                    https://python-pillow.org
  imageio-ffmpeg    Delivers FFmpeg. BSD 2-Clause license.
                    https://github.com/imageio/imageio-ffmpeg
  FFmpeg 7.1        Video and audio conversion. GPL 3.0.
                    https://ffmpeg.org
  Fonts             Theme lettering, under the SIL Open Font License 1.1.
                    Each font's license is in the "licenses" folder.

About FFmpeg: this program includes FFmpeg 7.1, which is free software under
the GPL 3.0. Its source code is attached to each release as
FFmpeg-n7.1.tar.gz.

Full credits and license texts: THIRD_PARTY_NOTICES.md and the "licenses"
folder.
