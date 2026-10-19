# -*- coding: utf-8 -*-
"""
TooManyItems_ED – aplikacja z okienkiem.

Wymaga: tmi_core.py i items_db.json w tym samym folderze.
Uruchomienie: python tmi_app.py   (albo start.bat)
"""

import json
import os
import re
import queue
import threading
import tkinter as tk
from tkinter import ttk

import tmi_core as core

HERE = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(HERE, "items_db.json")
SETTINGS_FILE = os.path.join(HERE, "settings.json")

LANG_LABELS = {
    "Pl_Pl": "Polski", "En_Us": "English", "De_De": "Deutsch", "Fr_Fr": "Français",
    "It_It": "Italiano", "Es_Es": "Español", "Pt_Br": "Português (BR)", "Ru_Ru": "Русский",
    "Uk_Ua": "Українська", "Tr_Tr": "Türkçe", "Ja_Jp": "日本語", "Ko_Kr": "한국어",
    "Zh_Cn": "简体中文", "Zh_Tw": "繁體中文", "Th_Th": "ไทย",
}
CAT_LABELS = {
    "Materials": "Materiały", "BuildTools": "Budowanie", "Equipment": "Wyposażenie",
    "Weapons": "Broń", "Consumables": "Jedzenie i mikstury", "Ammunition": "Amunicja i czary",
    "Customization": "Personalizacja", "Collectibles": "Kolekcje", "ColorPalette": "Kolory",
    "Blueprints": "Schematy", "WeaponGem": "Klejnoty", "Tools": "Narzędzia",
    "AnimalFood": "Karma dla zwierząt", "Instrument": "Instrumenty", "FishingRod": "Wędki",
    "Currency": "Waluta",
}
RARITY_LABELS = {"Common": "Zwykły", "Uncommon": "Niezwykły", "Rare": "Rzadki",
                 "Epic": "Epicki", "Legendary": "Legendarny"}
AUTO = "Automatycznie (jak w grze)"
# Kategorie, których nie pokazujemy w aplikacji
HIDDEN_CATS = {"Blueprints", "Customization"}
# Wpisy wycofane / testowe (oznaczone tak przez twórców w nazwie wewnętrznej)
HIDDEN_DEBUG = re.compile(r"deprecated|depricated|^zz?_|(^|_)test(_|$)|debug|^ability_", re.I)


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


class App:
    def __init__(self, root):
        self.root = root
        root.title("TooManyItems_ED")
        root.geometry("900x620")
        root.minsize(700, 450)

        db = load_json(DB_FILE, {"items": []})
        self.items = [it for it in db.get("items", [])
                      if it["cat"] not in HIDDEN_CATS
                      and it["names"]                       # bez nazwy = wewnętrzne
                      and not it.get("obsolete")            # gra oznacza je jako przestarzałe
                      and not HIDDEN_DEBUG.search(it["debug"])]
        self.by_id = {it["id"]: it for it in self.items}
        self.settings = load_json(SETTINGS_FILE, {})
        self.game_lang = None
        self.game = self.hook = self.inv = self.creator = None
        self.jobs = queue.Queue()
        self.busy = False

        self._build_ui()
        if not self.items:
            self.set_status("Brak pliku items_db.json obok programu.", error=True)
        self.refresh_list()
        self.connect()
        self.root.after(100, self._poll_jobs)

    # ---------------- UI ----------------
    def _build_ui(self):
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill="x")

        ttk.Label(top, text="Szukaj:").pack(side="left")
        self.q = tk.StringVar()
        self.q.trace_add("write", lambda *_: self.refresh_list())
        e = ttk.Entry(top, textvariable=self.q, width=30)
        e.pack(side="left", padx=(4, 12))
        e.focus_set()

        ttk.Label(top, text="Kategoria:").pack(side="left")
        cats = sorted({it["cat"] for it in self.items}, key=lambda c: CAT_LABELS.get(c, c))
        self.cat_values = ["Wszystkie"] + [CAT_LABELS.get(c, c) for c in cats]
        self.cat_keys = [None] + cats
        self.cat = ttk.Combobox(top, values=self.cat_values, state="readonly", width=20)
        self.cat.current(0)
        self.cat.bind("<<ComboboxSelected>>", lambda *_: self.refresh_list())
        self.cat.pack(side="left", padx=(4, 12))

        ttk.Label(top, text="Język:").pack(side="left")
        langs = sorted({l for it in self.items for l in it["names"]},
                       key=lambda l: (l != "Pl_Pl", l != "En_Us", LANG_LABELS.get(l, l)))
        self.lang_keys = [None] + langs
        self.lang_values = [AUTO] + [LANG_LABELS.get(l, l) for l in langs]
        self.lang = ttk.Combobox(top, values=self.lang_values, state="readonly", width=24)
        saved = self.settings.get("language")
        self.lang.current(self.lang_keys.index(saved) if saved in self.lang_keys else 0)
        self.lang.bind("<<ComboboxSelected>>", self._lang_changed)
        self.lang.pack(side="left", padx=4)

        opts = ttk.Frame(self.root, padding=(8, 0))
        opts.pack(fill="x")
        self.count_lbl = ttk.Label(opts, text="")
        self.count_lbl.pack(side="right")

        mid = ttk.Frame(self.root, padding=8)
        mid.pack(fill="both", expand=True)
        cols = ("name", "cat", "rarity", "stack", "id")
        self.tree = ttk.Treeview(mid, columns=cols, show="headings", selectmode="browse")
        for c, label, w, anchor in (("name", "Nazwa", 330, "w"), ("cat", "Kategoria", 150, "w"),
                                    ("rarity", "Rzadkość", 100, "w"), ("stack", "Maks. stos", 80, "e"),
                                    ("id", "ID", 110, "e")):
            self.tree.heading(c, text=label)
            self.tree.column(c, width=w, anchor=anchor)
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda *_: self.add_selected())
        self.tree.bind("<Return>", lambda *_: self.add_selected())
        self.tree.bind("<<TreeviewSelect>>", self._selected)

        bot = ttk.Frame(self.root, padding=8)
        bot.pack(fill="x")
        ttk.Label(bot, text="Ilość:").pack(side="left")
        self.qty = tk.IntVar(value=1)
        self.qty_box = ttk.Spinbox(bot, from_=1, to=9999, textvariable=self.qty, width=8)
        self.qty_box.pack(side="left", padx=4)
        ttk.Button(bot, text="1", width=3, command=lambda: self.qty.set(1)).pack(side="left")
        ttk.Button(bot, text="Pełny stos", command=self._full_stack).pack(side="left", padx=4)
        self.add_btn = ttk.Button(bot, text="Dodaj do ekwipunku", command=self.add_selected)
        self.add_btn.pack(side="left", padx=12)
        ttk.Button(bot, text="Połącz z grą", command=self.connect).pack(side="right")
        ttk.Button(bot, text="Diagnostyka", command=self.diagnose).pack(side="right", padx=4)
        ttk.Button(bot, text="Odzyskaj ukryte", command=self.rescue).pack(side="right")

        self.status = tk.StringVar(value="")
        self.status_lbl = ttk.Label(self.root, textvariable=self.status, padding=(8, 0, 8, 8),
                                    wraplength=860, justify="left")
        self.status_lbl.pack(fill="x")

    def set_status(self, text, error=False):
        self.status.set(text)
        self.status_lbl.configure(foreground="#b00020" if error else "")

    # ---------------- dane ----------------
    def current_lang(self):
        sel = self.lang_keys[self.lang.current()]
        return sel or self.game_lang or "Pl_Pl"

    def name_of(self, it):
        n = it["names"]
        return n.get(self.current_lang()) or n.get("En_Us") or it["debug"]

    def refresh_list(self):
        q = self.q.get().strip().lower()
        cat = self.cat_keys[self.cat.current()] if hasattr(self, "cat") else None
        lang = self.current_lang()
        self.tree.delete(*self.tree.get_children())
        rows = []
        for it in self.items:
            if cat and it["cat"] != cat:
                continue
            name = it["names"].get(lang) or it["names"].get("En_Us") or it["debug"]
            if q and q not in name.lower() and q not in it["debug"].lower() and q != str(it["id"]):
                continue
            rows.append((name.lower(), it, name))
        rows.sort(key=lambda r: r[0])
        for _, it, name in rows[:3000]:
            self.tree.insert("", "end", iid=str(it["id"]),
                             values=(name, CAT_LABELS.get(it["cat"], it["cat"]),
                                     RARITY_LABELS.get(it["rarity"], it["rarity"]),
                                     it["stack"], it["id"]))
        more = f" (pokazuję 3000 z {len(rows)})" if len(rows) > 3000 else ""
        self.count_lbl.configure(text=f"Przedmiotów: {len(rows)}{more}")

    def _lang_changed(self, *_):
        self.settings["language"] = self.lang_keys[self.lang.current()]
        save_json(SETTINGS_FILE, self.settings)
        self.refresh_list()

    def _selected(self, *_):
        it = self._sel_item()
        try:
            if it and self.qty.get() > it["stack"]:
                self.qty.set(it["stack"])
        except (tk.TclError, ValueError):
            self.qty.set(1)

    def _sel_item(self):
        sel = self.tree.selection()
        return self.by_id.get(int(sel[0])) if sel else None

    def _full_stack(self):
        it = self._sel_item()
        if it:
            self.qty.set(it["stack"])

    # ---------------- gra ----------------
    def connect(self):
        if self.busy:
            return
        self.set_status("Łączenie z grą…")
        self._run(self._connect_job)

    def _connect_job(self):
        try:
            if self.game:
                self.game.close()
            game = core.Game()
            hook = core.Hook(game)
            msg = hook.install()
            self.game, self.hook, self.inv = game, hook, core.Inventory(game, hook)
            self.creator = core.Creator(game)
            try:
                msg += " " + self.creator.install()
            except RuntimeError as e:       # stara droga nadal działa
                self.creator = None
                msg += f" Dodawanie przez grę niedostępne ({e}) – używam starej metody."
            self.game_lang = core.detect_game_language(game)
            lang = LANG_LABELS.get(self.game_lang, "nie wykryto")
            return False, f"Połączono z grą. {msg} Język gry: {lang}.", True
        except RuntimeError as e:
            self.game = None
            return True, f"{e}  Włącz grę, wczytaj świat i kliknij „Połącz z grą”.", False

    def add_selected(self):
        it = self._sel_item()
        if not it:
            self.set_status("Wybierz przedmiot z listy.", error=True)
            return
        if not self.game:
            self.set_status("Brak połączenia z grą – kliknij „Połącz z grą”.", error=True)
            return
        try:
            qty = max(1, min(int(self.qty.get()), 9999))
        except (tk.TclError, ValueError):
            qty = 1
        name = self.name_of(it)
        self.set_status(f"Dodaję {qty}× {name}…")
        self._run(lambda: self._add_job(it, qty, name))

    def rescue(self):
        if not self.game:
            self.set_status("Brak połączenia z grą – najpierw „Połącz z grą”.", error=True)
            return
        self.set_status("Szukam ukrytych przedmiotów…")
        self._run(lambda: (lambda r: (not r[0], r[1], False))(
            core.rescue_hidden(self.game, self.hook, self.inv)))

    def diagnose(self):
        if not self.game:
            self.set_status("Brak połączenia z grą – najpierw „Połącz z grą”.", error=True)
            return
        self.set_status("Zbieram dane diagnostyczne…")
        self._run(self._diag_job)

    def _write_diag(self):
        text = core.diag_report(self.game, self.hook, self.inv, self.creator)
        for path in (os.path.join(HERE, "diag.txt"),
                     os.path.join(core.FALLBACK_DIR, "diag.txt")):
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
                return path
            except OSError:
                continue
        return None

    def _diag_job(self):
        if not self.game.alive():
            self.game = None
            return True, "Gra została zamknięta – włącz ją, wczytaj świat i kliknij „Połącz z grą”.", False
        path = self._write_diag()
        if path:
            return False, f"Zapisano raport diagnostyczny: {path}", False
        return True, "Nie udało się zapisać raportu diagnostycznego.", False

    def _add_job(self, it, qty, name):
        if not self.game.alive():
            self.game = None
            return True, "Gra została zamknięta. Włącz ją i kliknij „Połącz z grą”.", False
        ok, msg = core.add_items_smart(self.game, self.hook, self.inv, it["id"], qty, it["stack"],
                                       pide=bool(it.get("pide")), creator=self.creator)
        if not ok and ("jednoznacznie" in msg or "nie utworzyła" in msg):
            path = self._write_diag()
            if path:
                msg += f" Raport zapisany automatycznie: {path}"
        return (not ok), (f"{name}: {msg}" if ok else f"Nie udało się: {msg}"), ok

    # ---------------- wątki ----------------
    def _run(self, fn):
        self.busy = True
        self.add_btn.state(["disabled"])

        def worker():
            try:
                res = fn()
            except Exception as e:                     # nie wysypuj okna
                res = (True, f"Błąd: {e}", False)
            self.jobs.put(res)
        threading.Thread(target=worker, daemon=True).start()

    def _poll_jobs(self):
        try:
            while True:
                error, text, changed = self.jobs.get_nowait()
                self.busy = False
                self.add_btn.state(["!disabled"])
                self.set_status(text, error=error)
                if changed:
                    self.refresh_list()
        except queue.Empty:
            pass
        self.root.after(100, self._poll_jobs)


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
