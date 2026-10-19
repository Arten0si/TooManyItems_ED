# -*- mode: python ; coding: utf-8 -*-
# Przepis PyInstallera dla TooManyItems_ED. Uruchamiany przez release\build_exe.bat (nie ręcznie).
# Wynik: release\dist\TooManyItems\TooManyItems.exe + folder _internal (wersja "folder", nie jeden plik:
# szybszy start – nie rozpakowuje 4000 ikon przy każdym uruchomieniu – i rzadziej fałszywe alarmy antywirusa).
import os

ROOT = os.path.dirname(SPECPATH)          # D:\TooManyItems_ED
W = os.path.join(ROOT, "release")


def pngs(sub):
    """Same ikony <ID>.png z icons\\<sub> (bez podfolderów typu foto\\_surowe)."""
    d = os.path.join(ROOT, "icons", sub)
    if not os.path.isdir(d):
        return []
    return [(os.path.join(d, n), f"icons/{sub}") for n in os.listdir(d)
            if n.endswith(".png") and n[:-4].isdigit()]


datas = [
    (os.path.join(ROOT, "gui", "index.html"), "gui"),
    (os.path.join(ROOT, "gui", "app.css"), "gui"),
    (os.path.join(ROOT, "gui", "app.js"), "gui"),
    (os.path.join(ROOT, "gui", "i18n.js"), "gui"),
    (os.path.join(ROOT, "gui", "fonts"), "gui/fonts"),
    (os.path.join(ROOT, "items_db.json"), "."),
    (os.path.join(ROOT, "items_texts.json"), "."),
] + pngs("wiki") + pngs("gra") + pngs("foto")

a = Analysis(
    [os.path.join(ROOT, "tmi_gui.py")],
    pathex=[ROOT],
    datas=datas,
    hiddenimports=[],
    # bez starego okna tkinter (w .exe zapasem jest przeglądarka) i bez nieużywanych silników pywebview
    excludes=["tkinter", "_tkinter", "tmi_app", "numpy", "PIL", "matplotlib", "pytest", "unittest",
              "pydoc_data", "test", "PyQt5", "PyQt6", "PySide2", "PySide6", "qtpy", "gi", "cefpython3"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="TooManyItems",
    icon=os.path.join(W, "TooManyItems.ico"),
    version=os.path.join(W, "version_info.txt"),
    console=False,                 # bez czarnego okna; dziennik: tmi_gui.log obok .exe
    upx=False,                     # UPX = częsty powód fałszywych alarmów antywirusa
    debug=False, strip=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="TooManyItems")
