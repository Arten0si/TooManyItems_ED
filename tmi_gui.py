# -*- coding: utf-8 -*-
"""
TooManyItems_ED – nowe okno (wygląd w stylu Enshrouded, projekt z sekcji 11 PROJEKT.md).

Uruchomienie: python tmi_gui.py   (albo start.bat)

Jak to działa:
- Python uruchamia lokalny serwer TYLKO na 127.0.0.1 (losowy port, losowy klucz – inne strony
  i inne komputery nie mają dostępu) i podaje z niego okno z folderu gui\\ oraz ikony z icons\\.
- Okno: 1) pywebview + WebView2 (składnik Windowsa) – własne okno programu,
        2) gdy nie ma WebView2/pywebview: Chrome/Edge/Brave/Opera w trybie aplikacji (--app),
        3) gdy nie ma żadnej przeglądarki: stare okno tkinter (tmi_app.py).
- Cały mechanizm gry bez zmian: tmi_core.py (te same funkcje co w tmi_app.py).
Opcje: --przegladarka (wymuś 2), --tk (wymuś 3), --bez-okna (tylko serwer, adres w konsoli – do testów).
"""

import json
import mimetypes
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import tmi_core as core
import tmi_categories

# Pliki programu (w .exe: folder _internal / tymczasowy – tylko odczyt)
RES = core.RES_DIR
GUI_DIR = os.path.join(RES, "gui")
ICON_DIR = os.path.join(RES, "icons")
FONT_DIR = os.path.join(GUI_DIR, "fonts")
DB_FILE = os.path.join(RES, "items_db.json")
TEXTS_FILE = os.path.join(RES, "items_texts.json")
# Pliki zapisywane (obok programu, a gdy tam nie wolno – %LOCALAPPDATA%\TooManyItems_ED)
SETTINGS_FILE = os.path.join(core.DATA_DIR, "settings.json")
APP_TITLE = f"TooManyItems – Enshrouded  v{core.APP_VERSION}"
# Strona wydań (sprawdzanie aktualizacji robi użytkownik – link w komunikacie o nowej wersji gry)
RELEASES_URL = "https://github.com/Arten0si/TooManyItems_ED/releases"

HIDDEN_CATS = {"Blueprints", "Customization"}
HIDDEN_DEBUG = re.compile(r"deprecated|depricated|^zz?_|(^|_)test(_|$)|debug|^ability_", re.I)
LANG_LABELS = {
    "Pl_Pl": "Polski", "En_Us": "English", "De_De": "Deutsch", "Fr_Fr": "Français",
    "It_It": "Italiano", "Es_Es": "Español", "Pt_Br": "Português (BR)", "Ru_Ru": "Русский",
    "Uk_Ua": "Українська", "Tr_Tr": "Türkçe", "Ja_Jp": "日本語", "Ko_Kr": "한국어",
    "Zh_Cn": "简体中文", "Zh_Tw": "繁體中文", "Th_Th": "ไทย",
}

# Typy plików na sztywno (rejestr Windowsa potrafi podać np. text/plain dla .js)
MIME = {".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".png": "image/png",
        ".svg": "image/svg+xml", ".json": "application/json", ".ttf": "font/ttf", ".woff2": "font/woff2",
        ".txt": "text/plain", ".ico": "image/x-icon"}

# Czcionki z projektu (licencja SIL OFL) – pobierane raz z oficjalnego repozytorium Google Fonts.
FONT_BASE = "https://raw.githubusercontent.com/google/fonts/main/ofl/"
FONTS = {
    "Cinzel.ttf": "cinzel/Cinzel%5Bwght%5D.ttf",
    "Cinzel-OFL.txt": "cinzel/OFL.txt",
    "AlegreyaSans-Regular.ttf": "alegreyasans/AlegreyaSans-Regular.ttf",
    "AlegreyaSans-Italic.ttf": "alegreyasans/AlegreyaSans-Italic.ttf",
    "AlegreyaSans-Medium.ttf": "alegreyasans/AlegreyaSans-Medium.ttf",
    "AlegreyaSans-Bold.ttf": "alegreyasans/AlegreyaSans-Bold.ttf",
    "AlegreyaSans-OFL.txt": "alegreyasans/OFL.txt",
}


LOG_FILE = os.path.join(core.DATA_DIR, "tmi_gui.log")


def log(*parts):
    """Dziennik pracy okna (tmi_gui.log obok programu, zapasowo w %LOCALAPPDATA%) – do diagnozy."""
    line = time.strftime("%H:%M:%S ") + " ".join(str(p) for p in parts)
    print(line)
    for path in (LOG_FILE, os.path.join(core.FALLBACK_DIR, "tmi_gui.log")):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            return
        except OSError:
            continue


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def ensure_fonts(timeout=6.0):
    """Pobiera brakujące czcionki (najwyżej raz; bez internetu okno użyje czcionek zastępczych)."""
    missing = [n for n in FONTS if not os.path.exists(os.path.join(FONT_DIR, n))]
    if not missing or core.FROZEN:                 # w .exe czcionki są w paczce
        return
    try:
        os.makedirs(FONT_DIR, exist_ok=True)
    except OSError:
        return
    end = time.time() + timeout
    for name in missing:
        left = end - time.time()
        if left <= 0.5:
            break
        try:
            req = urllib.request.Request(FONT_BASE + FONTS[name],
                                         headers={"User-Agent": "TooManyItems_ED"})
            with urllib.request.urlopen(req, timeout=left) as r:
                data = r.read()
            with open(os.path.join(FONT_DIR, name), "wb") as f:
                f.write(data)
        except Exception:
            break


# ------------------------------------------------------------------ dane

class Data:
    def __init__(self):
        db = load_json(DB_FILE, {"items": []})
        self.perks = db.get("perks", {})
        self.items = [it for it in db.get("items", [])
                      if it["cat"] not in HIDDEN_CATS and it["names"]
                      and not it.get("obsolete") and not HIDDEN_DEBUG.search(it["debug"])]
        self.by_id = {it["id"]: it for it in self.items}
        self.languages = sorted({l for it in self.items for l in it["names"]},
                                key=lambda l: (l != "Pl_Pl", l != "En_Us", LANG_LABELS.get(l, l)))
        self._texts = None
        self.icons = self._scan_icons()

    def _scan_icons(self):
        """Kolejność: wiki -> gra (strzały w plikach gry są szare) -> foto (tools/icon_photographer.py) -> symbol."""
        found = {}
        for sub in ("foto", "gra", "wiki"):         # późniejsze nadpisują wcześniejsze
            d = os.path.join(ICON_DIR, sub)
            try:
                names = os.listdir(d)
            except OSError:
                continue
            for n in names:
                if n.endswith(".png") and n[:-4].isdigit():
                    found[int(n[:-4])] = f"icons/{sub}/{n}"
        return found

    def texts(self, lang):
        if self._texts is None:
            self._texts = load_json(TEXTS_FILE, {}).get("texts", {})
        t = self._texts
        out = dict(t.get("En_Us", {}))
        out.update(t.get(lang, {}))
        return out

    def client_payload(self):
        items = []
        for it in self.items:
            rec = {k: v for k, v in it.items() if k not in ("obsolete",)}
            ic = self.icons.get(it["id"])
            if ic:
                rec["icon"] = ic
            sub = tmi_categories.subcategory(it)
            if sub:
                rec["sub"] = sub
            items.append(rec)
        used = {g for it in self.items for g in it.get("perks", [])}
        return {"items": items, "perks": {g: self.perks[g] for g in used if g in self.perks},
                "languages": [{"key": l, "label": LANG_LABELS.get(l, l)} for l in self.languages],
                "subOrder": tmi_categories.ORDER}


# ------------------------------------------------------------------ gra

class Backend:
    """To samo co tmi_app.App, bez okna: zadania w tle + stan do odpytywania przez okno.
    Status = kod komunikatu + wartości (okno tłumaczy go na wybrany język, gui/i18n.js) + polski tekst zapasowy."""

    def __init__(self, data):
        self.data = data
        self.settings = load_json(SETTINGS_FILE, {})
        self.game = self.hook = self.inv = self.creator = None
        self.game_lang = None
        self.lock = threading.Lock()
        self.busy = False
        self.seq = 0
        self.status = {"key": "", "args": {}, "error": False, "text": ""}
        self.conn = "off"                 # off | connecting | on
        self.conn_mode = ""               # game | old
        self.last_added = None

    # --- stan
    def state(self):
        return {"conn": self.conn, "connMode": self.conn_mode, "busy": self.busy,
                "seq": self.seq, "status": self.status, "gameLang": self.game_lang,
                "language": self.settings.get("language"), "creator": bool(self.creator),
                "lastAdded": self.last_added, "appVersion": core.APP_VERSION,
                "releasesUrl": RELEASES_URL}

    def _set(self, key, args=None, error=False, text=""):
        self.status = {"key": key, "args": args or {}, "error": error, "text": text}
        self.seq += 1
        log("STATUS", key, json.dumps(args or {}, ensure_ascii=False), "BŁĄD" if error else "", text)

    def _run(self, fn, key, args=None):
        with self.lock:
            if self.busy:
                log("ODRZUCONE (zajęty):", key)
                return False
            self.busy = True
        self._set(key, args)

        def worker():
            try:
                res = fn()
            except Exception as e:                   # nie wysypuj okna
                log("WYJĄTEK:", traceback.format_exc())
                res = ("error", {"d": str(e)}, True, f"Błąd: {e}")
            self.busy = False
            self._set(*res)
        threading.Thread(target=worker, daemon=True).start()
        return True

    # --- akcje
    def set_language(self, lang):
        self.settings["language"] = lang or None
        save_json(SETTINGS_FILE, self.settings)

    def connect(self):
        self.conn = "connecting"
        return self._run(self._connect_job, "connecting")

    def _connect_job(self):
        try:
            if self.game:
                self.game.close()
            game = core.Game()
            hook = core.Hook(game)
            msg = hook.install()
            self.game, self.hook, self.inv = game, hook, core.Inventory(game, hook)
            self.creator = core.Creator(game)
            mode, unsup = "game", False
            try:
                msg += " " + self.creator.install()
            except RuntimeError as e:
                self.creator = None
                mode = "old"
                unsup = isinstance(e, core.UnsupportedGameVersion)
                msg += f" Dodawanie przez grę niedostępne ({e}) – używam starej metody."
            self.game_lang = core.detect_game_language(game)
            build, stamp = core.game_version(game)
            steam = core.steam_build_id(game)
            log("Wersja gry:", build or f"NIEZNANA (exe {stamp:#x}, Steam build {steam or '?'}) – adresy wyszukane wzorami")
            self.conn, self.conn_mode = "on", mode
            args = {"mode": mode, "lang": self.game_lang}
            if not build:                             # nowa łatka, ale wzory znalazły adresy
                args.update(newBuild=True, build=steam or f"{stamp:#x}", ok=", ".join(core.SUPPORTED_BUILDS))
            if unsup:
                args["unsup"] = True
            return "connected", args, False, f"Połączono z grą. {msg}"
        except core.UnsupportedGameVersion as e:
            # nic nie zostało zmienione w grze – hook odmówił przed zapisem
            steam = None
            try:
                steam = core.steam_build_id(game)
                build, stamp = core.game_version(game)
                log("Wersja gry NIEOBSŁUGIWANA:", f"Steam build {steam or '?'}, exe {stamp:#x} –", e)
            except Exception:
                pass
            try:
                game.close()
            except Exception:
                pass
            self.game = None
            self.conn, self.conn_mode = "unsupported", ""
            return ("unsupported", {"build": steam or "?", "ok": ", ".join(core.SUPPORTED_BUILDS), "d": str(e)},
                    True, f"Ta wersja gry nie jest jeszcze obsługiwana ({e}).")
        except RuntimeError as e:
            self.game = None
            self.conn, self.conn_mode = "off", ""
            return "connFail", {"d": str(e)}, True, f"{e}  Włącz grę, wczytaj świat i kliknij „Połącz z grą”."

    def _check_alive(self):
        if not self.game:
            return "noConn", {}, True, "Brak połączenia z grą."
        if not self.game.alive():
            self.game = None
            self.conn, self.conn_mode = "off", ""
            return "closed", {}, True, "Gra została zamknięta."
        return None

    def add(self, item_id, qty, rarity=None):
        it = self.data.by_id.get(item_id)
        if not it:
            self._set("unknown", {}, True)
            return False
        if not self.game:
            self._set("noConn", {}, True)
            return False
        qty = max(1, min(int(qty), core.MAX_QTY))
        # rzadkość tylko dla przedmiotów, przy których gra ją losuje (rgen = dozwolone – tools/build_items_db.py)
        rarity = rarity if rarity in (it.get("rgen") or ()) else (it["rarity"] if it.get("rgen") else None)
        return self._run(lambda: self._add_job(it, qty, rarity), "adding",
                         {"id": it["id"], "qty": qty, "rar": rarity})

    def _add_job(self, it, qty, rarity=None):
        err = self._check_alive()
        if err:
            return err
        ok, msg = core.add_items_smart(self.game, self.hook, self.inv, it["id"], qty, it["stack"],
                                       pide=bool(it.get("pide")), creator=self.creator, rarity=rarity)
        if not ok:
            if msg.startswith("Brak miejsca"):
                return "noroom", {"n": qty}, True, msg
            if "jednoznacznie" in msg or "nie utworzyła" in msg:
                path = self._write_diag()
                if path:
                    msg += f" Raport zapisany automatycznie: {path}"
            return "addFail", {"d": msg}, True, msg
        self.last_added = {"id": it["id"], "qty": qty, "t": time.time()}
        args = parse_added(msg, it["id"], qty)
        if rarity:
            args["rar"] = rarity
            if not self.creator or "starej metody" in msg:
                args["rarLost"] = True            # stara metoda – rzadkość wybierze gra
        return "added", args, False, msg

    def rescue(self):
        if not self.game:
            self._set("noConn", {}, True)
            return False

        def job():
            err = self._check_alive()
            if err:
                return err
            ok, msg = core.rescue_hidden(self.game, self.hook, self.inv)
            if not ok:
                return "error", {"d": msg}, True, msg
            if msg.startswith("Nie ma ukrytych"):
                return "rescueNone", {}, False, msg
            moved = re.search(r"Przeniesiono (\d+)", msg)
            left = re.search(r"Zabrakło miejsca na (\d+)", msg)
            return "rescueDone", {"n": int(moved.group(1)) if moved else 0,
                                  "left": int(left.group(1)) if left else 0}, False, msg
        return self._run(job, "rescueWait")

    def _write_diag(self):
        text = core.diag_report(self.game, self.hook, self.inv, self.creator)
        for path in (os.path.join(core.DATA_DIR, "diag.txt"), os.path.join(core.FALLBACK_DIR, "diag.txt")):
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
                return path
            except OSError:
                continue
        return None

    def diag(self):
        if not self.game:
            self._set("noConn", {}, True)
            return False

        def job():
            err = self._check_alive()
            if err:
                return err
            path = self._write_diag()
            if path:
                return "diagSaved", {"p": path}, False, f"Zapisano raport diagnostyczny: {path}"
            return "diagFail", {}, True, "Nie udało się zapisać raportu diagnostycznego."
        return self._run(job, "diagWait")


def parse_added(msg, item_id, qty):
    """Komunikat tmi_core („Dodano 5 szt. Gotowe do użycia…”) -> wartości do przetłumaczenia w oknie."""
    a = {"id": item_id}
    m = re.search(r"Dodano (\d+) szt", msg, re.I)
    a["n"] = int(m.group(1)) if m else qty
    if "Gotowe do użycia" in msg:
        a["ready"] = True
    m = re.search(r"(?:Zabrakło miejsca na|Nie dodano) (\d+) szt", msg)
    if m:
        a["noroom"] = int(m.group(1))
    if "przesuń" in msg.lower():
        a["hint"] = True
    if not re.search(r"Dodano \d+ szt", msg, re.I):
        a["extra"] = msg
    return a


# ------------------------------------------------------------------ serwer

class Server:
    def __init__(self, data, backend):
        self.data, self.backend = data, backend
        self.token = secrets.token_urlsafe(24)
        self.payload = None
        srv = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _send(self, code, body, ctype="application/json; charset=utf-8", cache=False):
                if isinstance(body, (dict, list)):
                    body = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                elif isinstance(body, str):
                    body = body.encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "max-age=86400" if cache else "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)

            def _host_ok(self):
                host = (self.headers.get("Host") or "").split(":")[0]
                return host in ("127.0.0.1", "localhost")

            def _auth(self):
                return self._host_ok() and secrets.compare_digest(
                    self.headers.get("X-TMI-Token", ""), srv.token)

            def do_GET(self):
                if not self._host_ok():
                    return self._send(403, {"error": "host"})
                path = urllib.parse.urlparse(self.path).path
                if path == "/":
                    self.send_response(302)
                    self.send_header("Location", "/gui/index.html")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                if path.startswith("/api/"):
                    if not self._auth():
                        return self._send(403, {"error": "token"})
                    return self._api_get(path, urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query))
                for prefix, root in (("/gui/", GUI_DIR), ("/icons/", ICON_DIR)):
                    if path.startswith(prefix):
                        rel = urllib.parse.unquote(path[len(prefix):])
                        full = os.path.realpath(os.path.join(root, rel))
                        if not full.startswith(os.path.realpath(root) + os.sep) or not os.path.isfile(full):
                            return self._send(404, {"error": "brak"})
                        ext = os.path.splitext(full)[1].lower()
                        ctype = MIME.get(ext) or mimetypes.guess_type(full)[0] or "application/octet-stream"
                        if ctype.startswith("text/") or ctype.endswith("javascript"):
                            ctype += "; charset=utf-8"
                        with open(full, "rb") as f:
                            return self._send(200, f.read(), ctype, cache=prefix == "/icons/")
                return self._send(404, {"error": "brak"})

            def _api_get(self, path, q):
                b = srv.backend
                if path == "/api/data":
                    if srv.payload is None:
                        srv.payload = json.dumps(srv.data.client_payload(), ensure_ascii=False,
                                                 separators=(",", ":")).encode("utf-8")
                    return self._send(200, srv.payload)
                if path == "/api/texts":
                    lang = (q.get("lang") or ["Pl_Pl"])[0]
                    return self._send(200, srv.data.texts(lang))
                if path == "/api/state":
                    return self._send(200, b.state())
                return self._send(404, {"error": "brak"})

            def do_POST(self):
                try:
                    return self._post()
                except Exception:
                    log("WYJĄTEK API:", traceback.format_exc())
                    return self._send(500, {"error": "wyjątek – zobacz tmi_gui.log"})

            def _post(self):
                if not self._auth():
                    return self._send(403, {"error": "token"})
                n = int(self.headers.get("Content-Length") or 0)
                try:
                    body = json.loads(self.rfile.read(n) or b"{}")
                except ValueError:
                    body = {}
                b = srv.backend
                path = urllib.parse.urlparse(self.path).path
                log("API", path, json.dumps(body, ensure_ascii=False))
                if path == "/api/connect":
                    ok = b.connect()
                elif path == "/api/add":
                    ok = b.add(int(body.get("id", 0)), int(body.get("qty", 1)), body.get("rarity"))
                elif path == "/api/rescue":
                    ok = b.rescue()
                elif path == "/api/diag":
                    ok = b.diag()
                elif path == "/api/settings":
                    b.set_language(body.get("language"))
                    ok = True
                else:
                    return self._send(404, {"error": "brak"})
                return self._send(200, {"ok": ok, "state": b.state()})

        class QuietServer(ThreadingHTTPServer):
            def handle_error(self, request, client_address):
                pass                                   # zerwane połączenia okna – bez śmiecenia w konsoli

        self.httpd = QuietServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}/gui/index.html#t={self.token}"

    def stop(self):
        try:
            self.httpd.shutdown()
        except Exception:
            pass


# ------------------------------------------------------------------ okno

def webview2_version():
    """Wersja WebView2 Runtime z rejestru (None = brak)."""
    try:
        import winreg
    except ImportError:
        return None
    key = r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    for hive, path in ((winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node" + key[8:]),
                       (winreg.HKEY_LOCAL_MACHINE, key), (winreg.HKEY_CURRENT_USER, key)):
        try:
            with winreg.OpenKey(hive, path) as k:
                v, _ = winreg.QueryValueEx(k, "pv")
                if v and v != "0.0.0.0":
                    return v
        except OSError:
            continue
    return None


def run_webview(url):
    """1) Własne okno: pywebview + WebView2. Zwraca False, gdy się nie da."""
    if not webview2_version():
        print("WebView2 nie znaleziono – próbuję przeglądarki.")
        return False
    try:
        import webview
    except ImportError:
        print("Brak biblioteki pywebview (pip install pywebview) – próbuję przeglądarki.")
        return False
    try:
        webview.create_window(APP_TITLE, url, width=1440, height=920, min_size=(1000, 640),
                              background_color="#0b1012", text_select=True)
        try:
            webview.start(gui="edgechromium", private_mode=False,
                          storage_path=os.path.join(core.FALLBACK_DIR, "webview"))
        except TypeError:                            # starsza wersja pywebview
            webview.start(gui="edgechromium")
        return True
    except Exception as e:
        print(f"pywebview nie zadziałał ({e}) – próbuję przeglądarki.")
        return False


def find_browser():
    pf = [os.environ.get(v) for v in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
    rel = [r"Google\Chrome\Application\chrome.exe", r"Microsoft\Edge\Application\msedge.exe",
           r"BraveSoftware\Brave-Browser\Application\brave.exe", r"Chromium\Application\chrome.exe",
           r"Vivaldi\Application\vivaldi.exe", r"Programs\Opera\opera.exe"]
    for r in rel:
        for base in pf:
            if base and os.path.isfile(os.path.join(base, r)):
                return os.path.join(base, r)
    for exe in ("chrome", "msedge", "brave", "chromium", "chromium-browser", "google-chrome"):
        p = shutil.which(exe)
        if p:
            return p
    return None


def run_browser(url):
    """2) Przeglądarka w trybie aplikacji (osobny profil – zamknięcie okna kończy program)."""
    exe = find_browser()
    if not exe:
        return False
    profile = os.path.join(core.FALLBACK_DIR, "okno")
    try:
        p = subprocess.Popen([exe, f"--app={url}", f"--user-data-dir={profile}",
                              "--window-size=1440,920", "--no-first-run",
                              "--no-default-browser-check"])
    except OSError:
        return False
    print(f"Okno w przeglądarce: {os.path.basename(exe)}. Zamknij okno, aby zakończyć.")
    p.wait()
    return True


def run_tk():
    """3) Stare okno (w .exe go nie ma – wtedy tylko komunikat)."""
    try:
        import tmi_app
    except ImportError:
        msg = ("Nie znaleziono składnika Microsoft Edge WebView2 ani przeglądarki Chrome/Edge.\n"
               "Zainstaluj WebView2 Runtime ze strony Microsoftu i uruchom program ponownie.\n\n"
               "Microsoft Edge WebView2 Runtime was not found. Please install it and start the program again.")
        print(msg)
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, msg, APP_TITLE, 0x30)
        except Exception:
            pass
        return
    tmi_app.main()


def main():
    args = set(sys.argv[1:])
    if "--tk" in args:
        return run_tk()
    if not os.path.isfile(os.path.join(GUI_DIR, "index.html")):
        print("Brak folderu gui – uruchamiam stare okno.")
        return run_tk()
    log("=== START tmi_gui", core.APP_VERSION, "exe" if core.FROZEN else "py", "Python", sys.version.split()[0],
        "dane:", core.DATA_DIR)
    ensure_fonts()
    data = Data()
    log("Przedmiotów:", len(data.items), "ikon:", len(data.icons))
    backend = Backend(data)
    server = Server(data, backend)
    backend.connect()
    try:
        if "--bez-okna" in args:
            print(server.url)
            while True:
                time.sleep(1)
        log("Serwer:", f"http://127.0.0.1:{server.port}/")
        if "--przegladarka" not in args and run_webview(server.url):
            return
        if run_browser(server.url):
            return
        print("Nie znaleziono WebView2 ani przeglądarki – uruchamiam stare okno.")
        server.stop()
        run_tk()
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()


if __name__ == "__main__":
    main()
