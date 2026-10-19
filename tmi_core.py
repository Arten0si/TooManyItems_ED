# -*- coding: utf-8 -*-
"""
TooManyItems_ED – rdzeń (hook + dodawanie przez funkcje gry)

Jak to działa:
  1. Program podpina mały kawałek kodu (hook) w pętli gry, która ciągle
     przegląda rzędy ekwipunku. Hook zapisuje adresy rzędów, które gra widzi.
  2. Z tych adresów program sam znajduje Twój ekwipunek – po każdym restarcie.
  3. Po wpisaniu przedmiotu prosi grę (przez hook), żeby oznaczyła rząd jako
     zmieniony. Gra wtedy sama odświeża ekran – bez przekładania przedmiotów.

Tylko biblioteka standardowa Pythona. Uruchomienie:  python tmi_core.py
Build gry, dla którego to ustalono: 25988036 (16.10.2026).
"""

import ctypes
import ctypes.wintypes as wt
import json
import os
import re
import struct
import sys
import time

# ---------------------------------------------------------------------------
# Ustalenia techniczne (patrz ce/NOTATKI_TECHNICZNE.md)
# ---------------------------------------------------------------------------

PROCESS_NAME = "enshrouded.exe"

# Miejsce hooka: pętla przeglądająca rzędy ekwipunku (enshrouded.exe+EED13F)
HOOK_RVA = 0xEED13F
HOOK_PATTERN = "48 8B 38 48 85 FF 0F 84 ?? ?? ?? ?? 48 8D 6F 60 48 3B FD"
HOOK_ORIGINAL = bytes.fromhex("488B384885FF")

# Funkcja gry "dostęp do zapisu komponentu" (enshrouded.exe+225B70) –
# szukana przez miejsce wywołania w funkcji ekwipunku (enshrouded.exe+40F37A)
WRITE_FN_CALLSITE_RVA = 0x40F37A
WRITE_FN_CALLSITE_PATTERN = "49 8B 56 20 48 85 D2 74 ?? 44 8B 44 24 24 49 8B 0E E8"

# Kod hooka (zbudowany z ce/stub.s); dane na początku bloku, kod od 0x1900
STUB_CODE = bytes.fromhex(
    "57488b38505152488d0d32e7ffffba00010000488b014885c0740f4839f874194883c118ff"
    "ca75ebeb0f488939488b442418488941088959105a5958483b3dd5e6ffff7559f0ff05e0e6"
    "ffff5031c08605cbe6ffff3c015875445051524150415141524153554889e54883e4f04883"
    "ec20488b4d40488b95380200004189d8488b0582e6ffffffd0f0ff0599e6ffff4889ec5d41"
    "5b415a415941585a59584883c4084885ffff2565e6ffff")
STUB_MAGIC = b"TMI2hook"
OLD_MAGICS = (b"TMI1hook",)
OFF_MAGIC, OFF_FN, OFF_RET, OFF_TARGET = 0x000, 0x008, 0x010, 0x018
OFF_REQUEST, OFF_DONE, OFF_HITS, OFF_TABLE = 0x020, 0x028, 0x02C, 0x040
TABLE_ENTRIES, TABLE_ENTRY = 256, 24
OFF_CODE = 0x1900
STUB_SIZE = 0x2000

ROW = 0x60                 # rząd = 8 slotów po 12 bajtów
SLOT_SIZE = 12             # +0 ID (u32), +4 ilość (u32), +8 dane dodatkowe (u32)
# Układ od rzędu 1 plecaka: r1, r2, pasek Alt, pasek akcji, r3, potem rzędy z plecaka
BASE_SLOTS = 40
ARRAY_SLOTS = 80           # 10 rzędów (r3 + do 5 rzędów rozszerzeń)
VISIBLE_SLOTS = list(range(0, 16)) + list(range(32, 40))   # bez założonego plecaka
# ID plecaka -> ile rzędów dodaje (z danych gry: uiValues / 8)
BACKPACK_ROWS = {531058391: 1, 3728213390: 2, 3773368910: 3, 996296787: 4,
                 4231879756: 1, 4053516652: 2, 3131144042: 3}
MAX_QTY = 9999

APP_VERSION = "1.0.0"
# Ścieżki: w .exe (PyInstaller) pliki programu leżą w folderze tymczasowym/_internal (RES_DIR, tylko odczyt),
# a ustawienia, dziennik i diag.txt zapisujemy obok TooManyItems.exe (APP_DIR) albo w %LOCALAPPDATA%.
FROZEN = bool(getattr(sys, "frozen", False))
APP_DIR = os.path.dirname(os.path.abspath(sys.executable if FROZEN else __file__))
RES_DIR = getattr(sys, "_MEIPASS", APP_DIR)
HERE = APP_DIR
ITEMS_FILE = os.path.join(HERE, "items.json")
FALLBACK_DIR = os.path.join(os.environ.get("LOCALAPPDATA", HERE), "TooManyItems_ED")


def _dir_writable(d):
    try:
        test = os.path.join(d, ".tmi_zapis_test")
        with open(test, "w") as f:
            f.write("1")
        os.remove(test)
        return True
    except OSError:
        return False


DATA_DIR = APP_DIR if _dir_writable(APP_DIR) else FALLBACK_DIR
FALLBACK_ITEMS_FILE = os.path.join(FALLBACK_DIR, "items.json")

DEFAULT_ITEMS = {
    "631520303": "Kamień",
    "1798662696": "Patyk",
    "3316218728": "Włókno roślinne",
}

# ---------------------------------------------------------------------------
# WinAPI
# ---------------------------------------------------------------------------

if os.name != "nt":
    print("Ten program działa tylko na Windows.")
    sys.exit(1)

k32 = ctypes.WinDLL("kernel32", use_last_error=True)

PROCESS_ALL_NEEDED = 0x0010 | 0x0020 | 0x0008 | 0x0400   # VM_READ|VM_WRITE|VM_OPERATION|QUERY
TH32CS_SNAPPROCESS = 0x00000002
TH32CS_SNAPMODULE = 0x00000008
TH32CS_SNAPMODULE32 = 0x00000010
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
MEM_COMMIT, MEM_RESERVE = 0x1000, 0x2000
PAGE_EXECUTE_READWRITE = 0x40


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD),
                ("th32DefaultHeapID", ctypes.c_void_p), ("th32ModuleID", wt.DWORD),
                ("cntThreads", wt.DWORD), ("th32ParentProcessID", wt.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", wt.DWORD),
                ("szExeFile", ctypes.c_wchar * 260)]


class MODULEENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("th32ModuleID", wt.DWORD), ("th32ProcessID", wt.DWORD),
                ("GlblcntUsage", wt.DWORD), ("ProccntUsage", wt.DWORD),
                ("modBaseAddr", ctypes.c_void_p), ("modBaseSize", wt.DWORD),
                ("hModule", wt.HMODULE), ("szModule", ctypes.c_wchar * 256),
                ("szExePath", ctypes.c_wchar * 260)]


k32.CreateToolhelp32Snapshot.restype = wt.HANDLE
k32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
k32.Process32FirstW.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
k32.Process32NextW.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
k32.Module32FirstW.argtypes = [wt.HANDLE, ctypes.POINTER(MODULEENTRY32W)]
k32.Module32NextW.argtypes = [wt.HANDLE, ctypes.POINTER(MODULEENTRY32W)]
k32.OpenProcess.restype = wt.HANDLE
k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
k32.CloseHandle.argtypes = [wt.HANDLE]
k32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                  ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.WriteProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                   ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.GetExitCodeProcess.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD)]
k32.VirtualAllocEx.restype = ctypes.c_void_p
k32.VirtualAllocEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wt.DWORD, wt.DWORD]
k32.VirtualProtectEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wt.DWORD,
                                 ctypes.POINTER(wt.DWORD)]
k32.FlushInstructionCache.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_size_t]
k32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, ctypes.c_wchar_p,
                                           ctypes.POINTER(wt.DWORD)]


def find_pid(name):
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == INVALID_HANDLE_VALUE:
        return None
    try:
        e = PROCESSENTRY32W()
        e.dwSize = ctypes.sizeof(e)
        ok = k32.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            if e.szExeFile.lower() == name.lower():
                return e.th32ProcessID
            ok = k32.Process32NextW(snap, ctypes.byref(e))
    finally:
        k32.CloseHandle(snap)
    return None


def find_module(pid, name):
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid)
    if snap == INVALID_HANDLE_VALUE:
        return None, None
    try:
        m = MODULEENTRY32W()
        m.dwSize = ctypes.sizeof(m)
        ok = k32.Module32FirstW(snap, ctypes.byref(m))
        while ok:
            if m.szModule.lower() == name.lower():
                return m.modBaseAddr, m.modBaseSize
            ok = k32.Module32NextW(snap, ctypes.byref(m))
    finally:
        k32.CloseHandle(snap)
    return None, None


class Game:
    def __init__(self):
        self.pid = find_pid(PROCESS_NAME)
        if not self.pid:
            raise RuntimeError("Nie znaleziono procesu enshrouded.exe – włącz grę.")
        self.base, self.size = find_module(self.pid, PROCESS_NAME)
        if not self.base:
            raise RuntimeError("Nie udało się odczytać modułu enshrouded.exe "
                               "(spróbuj uruchomić jako administrator).")
        self.h = k32.OpenProcess(PROCESS_ALL_NEEDED, False, self.pid)
        if not self.h:
            raise RuntimeError("Brak dostępu do procesu gry (uruchom jako administrator).")

    def exe_path(self):
        buf = ctypes.create_unicode_buffer(1024)
        n = wt.DWORD(1024)
        if k32.QueryFullProcessImageNameW(self.h, 0, buf, ctypes.byref(n)):
            return buf.value
        return None

    def close(self):
        if self.h:
            k32.CloseHandle(self.h)
            self.h = None

    def alive(self):
        code = wt.DWORD()
        return bool(k32.GetExitCodeProcess(self.h, ctypes.byref(code))) and code.value == 259

    def read(self, addr, n):
        buf = ctypes.create_string_buffer(n)
        got = ctypes.c_size_t()
        if not k32.ReadProcessMemory(self.h, ctypes.c_void_p(addr), buf, n, ctypes.byref(got)):
            return None
        return buf.raw if got.value == n else None

    def u32(self, addr):
        b = self.read(addr, 4)
        return None if b is None else int.from_bytes(b, "little")

    def write(self, addr, data):
        done = ctypes.c_size_t()
        ok = k32.WriteProcessMemory(self.h, ctypes.c_void_p(addr), data, len(data),
                                    ctypes.byref(done))
        return bool(ok) and done.value == len(data)

    def write_u32(self, addr, v):
        return self.write(addr, int(v).to_bytes(4, "little"))

    def write_u64(self, addr, v):
        return self.write(addr, int(v).to_bytes(8, "little"))


# ---------------------------------------------------------------------------
# Szukanie kodu po wzorze bajtów (odporność na łatki gry)
# ---------------------------------------------------------------------------

def compile_pattern(s):
    return re.compile(b"".join(b"." if t == "??" else re.escape(bytes([int(t, 16)]))
                               for t in s.split()), re.S)


def find_code(game, pattern, expected_rva):
    rx = compile_pattern(pattern)
    n = len(pattern.split())
    b = game.read(game.base + expected_rva, n)
    if b is not None and rx.fullmatch(b):
        return game.base + expected_rva
    # nie ma w oczekiwanym miejscu (inna wersja gry) – szukamy w całym module
    chunk = 8 << 20
    found = []
    off = 0
    while off < game.size:
        data = game.read(game.base + off, min(chunk + n, game.size - off))
        if data:
            for m in rx.finditer(data):
                a = game.base + off + m.start()
                if a not in found:
                    found.append(a)
        off += chunk
    return found[0] if len(found) == 1 else None


# ---------------------------------------------------------------------------
# Wzory kodu gry – odporność na aktualizacje (19.10)
# Najpierw szybki test pod znanym adresem (build 25988036), a gdy nie pasuje – przeszukanie
# całego .text wszystkimi metodami. Adres przyjmujemy tylko, gdy wszystkie znalezione metody
# wskazują to samo miejsce. Wzory zawierają też liczby, od których zależy kod naszych hooków
# (np. [rsp+0x1F0], pola transakcji 0x71xx) – gdy się zmienią, wzór nie pasuje i program
# odmawia zamiast ryzykować awarię gry.
# ---------------------------------------------------------------------------

# Znane wersje gry: (PE TimeDateStamp, rozmiar exe) -> Build ID Steama
KNOWN_BUILDS = {(0x6AD20259, 35327560): "25988036"}
SUPPORTED_BUILDS = sorted(set(KNOWN_BUILDS.values()))


class UnsupportedGameVersion(RuntimeError):
    """Kod gry nie pasuje do wzorów (nowa łatka). Rzucany ZANIM program cokolwiek zapisze w grze."""

# Sekwencja transakcji w grze (+225650, +225850): CTOR, INIT, TAKE, COMMIT, DTOR, ROLLBACK
ANCHOR_TX = ("E8 ?? ?? ?? ?? 48 8D 54 24 ?? 48 8D 4D ?? E8 ?? ?? ?? ?? ?? ?? ?? C7 44 24 20 01 00 00 00 "
             "?? ?? ?? 48 8D 55 ?? 48 8D 4C 24 ?? E8 ?? ?? ?? ?? 80 7C 24 ?? 00 75 ?? 83 7C 24 ?? 00 "
             "75 ?? 48 8D 4D ?? E8 ?? ?? ?? ?? ?? ?? 48 8D 4D ?? ?? ?? ?? ?? ?? E8 ?? ?? ?? ?? EB ?? "
             "48 8D 4D ?? E8 ?? ?? ?? ??")
# Metody: ("at", wzór, przesunięcie) = adres = trafienie + przesunięcie
#         ("call", wzór, pozycja E8) = adres = cel wywołania w trafieniu
# Pierwsza metoda "at" służy też do szybkiego testu pod znanym adresem (EXPECTED_RVA).
SIGNATURES = {
    # hook odświeżania (TMI2): kontekst z [rsp+0x1F0] (typ komponentu – używa go stub.s)
    "HOOK": [("at", "4C 8B 84 24 F0 01 00 00 48 8D 4C 24 ?? 48 8B D0 44 8B CB E8 ?? ?? ?? ?? "
                    "48 8B 38 48 85 FF 0F 84 ?? ?? ?? ?? 48 8D 6F 60 48 3B FD", 24)],
    "WRITE_FN": [("call", "49 8B 56 20 48 85 D2 74 ?? 44 8B 44 24 24 49 8B 0E E8 ?? ?? ?? ??", 17)],
    # TMI3 – dodawanie przez funkcje gry
    "CREATE_SITE": [("at", "C6 81 ?? ?? 00 00 00 48 8B 42 08 48 89 01 48 8B 42 10", 0),
                    ("call", ANCHOR_TX, 14)],
    "CTOR": [("at", "33 D2 33 C0 48 89 11 48 89 51 08 48 89 51 10 48 89 51 18 48 89 51 20 48 89 51 28 "
                    "48 89 51 30 48 89 51 38 48 89 51 40 48 89 51 48 48 89 51 50 48 89 51 58 48 89 51 60 "
                    "48 89 51 68 48 89 51 70 48 89 51 78 48 89 81 80 00 00 00", 0),
             ("call", ANCHOR_TX, 0)],
    "LOOKUP": [("at", "89 4C 24 08 48 83 EC 28 85 C9 74 1B 48 8D 4A 38", 0),
               ("call", "48 8B 52 08 41 8B C9 41 8B D8 E8 ?? ?? ?? ?? 4C 8B E0 48 85 C0 0F 84", 10)],
    "CREATE": [("at", "48 89 5C 24 18 48 89 74 24 20 57 41 56 41 57 48 83 EC 30 4D 8B F1", 0),
               ("call", "48 8D 4C 24 ?? 48 89 44 24 28 C7 44 24 20 01 00 00 00 E8 ?? ?? ?? ??", 18),
               ("call", "4C 8B C7 49 8B D4 C7 44 24 20 01 00 00 00 ?? ?? ?? ?? E8 ?? ?? ?? ??", 18)],
    "COMMIT": [("at", "40 55 53 41 55 48 8D AC 24 30 FC FF FF 48 81 EC D0 04 00 00", 0),
               ("call", ANCHOR_TX, 65)],
    "ROLLBACK": [("at", "4C 8B DC 55 56 41 55 41 56 41 57 49 8D 6B A1 48 81 EC C0 00 00 00", 0),
                 ("call", ANCHOR_TX, 92)],
    "DTOR": [("at", "48 89 5C 24 08 48 89 74 24 10 57 48 83 EC 20 48 8B F9 45 33 C0 48 81 C1 40 71 00 00", 0),
             ("call", ANCHOR_TX, 81)],
}
EXPECTED_RVA = {"HOOK": 0xEED13F, "WRITE_FN": 0x225B70, "CREATE_SITE": 0x411DF0, "CTOR": 0x21DD00,
                "LOOKUP": 0xE7A870, "CREATE": 0x40B760, "COMMIT": 0x408B50, "ROLLBACK": 0x410E60,
                "DTOR": 0x21DE50}
WRITE_FN_CALLSITE_EXPECTED = 0x40F37A


class CodeScanner:
    """Szuka wzorów w sekcji .text działającej gry (czyta ją raz, gdy trzeba)."""

    def __init__(self, game):
        self.g = game
        self._text = None              # (adres, bajty)
        self.scanned = False

    def text(self):
        if self._text is None:
            g = self.g
            hdr = g.read(g.base, 0x1000) or b""
            pe = struct.unpack_from("<I", hdr, 0x3C)[0]
            nsec = struct.unpack_from("<H", hdr, pe + 6)[0]
            osz = struct.unpack_from("<H", hdr, pe + 20)[0]
            for i in range(nsec):
                o = pe + 24 + osz + i * 40
                if hdr[o:o + 8].rstrip(b"\0") == b".text":
                    vsz, va = struct.unpack_from("<II", hdr, o + 8)
                    chunks, off = [], 0
                    while off < vsz:
                        n = min(8 << 20, vsz - off)
                        chunks.append(g.read(g.base + va + off, n) or bytes(n))
                        off += n
                    self._text = (g.base + va, b"".join(chunks))
                    break
            else:
                self._text = (g.base, b"")
            self.scanned = True
        return self._text

    def find(self, pattern):
        start, data = self.text()
        return [start + m.start() for m in compile_pattern(pattern).finditer(data)]

    def match_at(self, addr, pattern):
        n = len(pattern.split())
        b = self.g.read(addr, n)
        return b is not None and compile_pattern(pattern).fullmatch(b) is not None

    def call_target(self, e8_addr):
        b = self.g.read(e8_addr, 5)
        if not b or b[0] != 0xE8:
            return None
        return e8_addr + 5 + struct.unpack("<i", b[1:5])[0]

    def resolve(self, name, allow_scan=True):
        """Adres funkcji/miejsca `name` albo None (nie znaleziono / metody się nie zgadzają)."""
        g = self.g
        methods = SIGNATURES[name]
        # szybko: znany adres + pierwsza metoda "at"
        if name == "WRITE_FN":
            cs = g.base + WRITE_FN_CALLSITE_EXPECTED
            if self.match_at(cs, methods[0][1]):
                return self.call_target(cs + methods[0][2])
        else:
            kind, pat, off = methods[0]
            if kind == "at" and self.match_at(g.base + EXPECTED_RVA[name] - off, pat):
                return g.base + EXPECTED_RVA[name]
        if not allow_scan:
            return None
        found = set()
        for kind, pat, off in methods:
            hits = self.find(pat)
            if kind == "at":
                if len(hits) == 1:                   # niejednoznaczny wzór nie głosuje
                    found.add(hits[0] + off)
            else:
                targets = {t for t in (self.call_target(h + off) for h in hits) if t}
                if len(targets) == 1:                # wszystkie wywołania muszą wskazywać to samo
                    found |= targets
        return found.pop() if len(found) == 1 else None   # metody muszą się zgadzać


def game_version(game):
    """(Build ID albo None, TimeDateStamp exe) – do komunikatów i diagnostyki."""
    try:
        hdr = game.read(game.base, 0x400)
        pe = struct.unpack_from("<I", hdr, 0x3C)[0]
        stamp = struct.unpack_from("<I", hdr, pe + 8)[0]
        size = os.path.getsize(game.exe_path()) if game.exe_path() else 0
    except Exception:
        return None, 0
    return KNOWN_BUILDS.get((stamp, size)), stamp


def steam_build_id(game):
    """Build ID z pliku Steama appmanifest_1203620.acf (to, co widać w Steamie) albo None."""
    exe = game.exe_path() if game else None
    if not exe:
        return None
    acf = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(exe))), "appmanifest_1203620.acf")
    try:
        with open(acf, "r", encoding="utf-8", errors="replace") as f:
            m = re.search(r'"buildid"\s+"(\d+)"', f.read())
    except OSError:
        return None
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Hook
# ---------------------------------------------------------------------------

class Hook:
    def __init__(self, game):
        self.g = game
        self.site = None
        self.stub = None

    def install(self):
        g = self.g
        scan = CodeScanner(g)
        site = scan.resolve("HOOK", allow_scan=False) or g.base + HOOK_RVA
        cur = g.read(site, 6)
        if cur is None:
            raise RuntimeError("Nie da się odczytać kodu gry.")
        replace_old = False
        if cur[0] == 0xE9:
            dest = site + 5 + struct.unpack("<i", cur[1:5])[0]
            if g.read(dest - OFF_CODE, 8) == STUB_MAGIC:
                self.site, self.stub = site, dest - OFF_CODE
                return "Hook był już zainstalowany – używam go."
            if g.read(dest - 0x700, 8) in OLD_MAGICS:
                replace_old = True          # starsza wersja naszego hooka – podmieniamy
            else:
                raise RuntimeError("W tym miejscu siedzi inny hook. Wyłącz skrypt "
                                   "w Cheat Engine (odznacz go) i uruchom program ponownie.")
        if not replace_old and (cur != HOOK_ORIGINAL or not scan.match_at(site - 24, SIGNATURES["HOOK"][0][1])):
            site = scan.resolve("HOOK")
            if site is None:
                # nowa wersja gry, a nasz hook już siedzi w kodzie (drugie uruchomienie programu):
                # szukamy samego kontekstu (24 B przed miejscem) i sprawdzamy, czy tam jest nasz skok
                prefix = " ".join(SIGNATURES["HOOK"][0][1].split()[:24])
                mine = []
                for h in scan.find(prefix):
                    b = g.read(h + 24, 6)
                    if b and b[0] == 0xE9:
                        dest = h + 24 + 5 + struct.unpack("<i", b[1:5])[0]
                        if g.read(dest - OFF_CODE, 8) == STUB_MAGIC:
                            mine.append((h + 24, dest))
                if len(mine) == 1:
                    self.site, self.stub = mine[0][0], mine[0][1] - OFF_CODE
                    return "Hook był już zainstalowany – używam go."
                raise UnsupportedGameVersion("Nie znaleziono miejsca hooka – ta wersja gry nie jest jeszcze obsługiwana.")
        fn = scan.resolve("WRITE_FN")
        if fn is None:
            raise UnsupportedGameVersion("Nie znaleziono funkcji odświeżania – ta wersja gry nie jest jeszcze obsługiwana.")
        stub = self._alloc_near(site)
        if not stub:
            raise RuntimeError("Nie udało się przydzielić pamięci blisko kodu gry.")
        blk = bytearray(STUB_SIZE)
        blk[OFF_MAGIC:OFF_MAGIC + 8] = STUB_MAGIC
        blk[OFF_FN:OFF_FN + 8] = fn.to_bytes(8, "little")
        blk[OFF_RET:OFF_RET + 8] = (site + 6).to_bytes(8, "little")
        blk[OFF_CODE:OFF_CODE + len(STUB_CODE)] = STUB_CODE
        if not g.write(stub, bytes(blk)):
            raise RuntimeError("Nie udało się zapisać kodu hooka.")
        rel = (stub + OFF_CODE) - (site + 5)
        patch = b"\xE9" + struct.pack("<i", rel) + b"\x90"
        old = wt.DWORD()
        k32.VirtualProtectEx(g.h, ctypes.c_void_p(site), 6, PAGE_EXECUTE_READWRITE,
                             ctypes.byref(old))
        ok = g.write(site, patch)
        k32.VirtualProtectEx(g.h, ctypes.c_void_p(site), 6, old.value, ctypes.byref(wt.DWORD()))
        k32.FlushInstructionCache(g.h, ctypes.c_void_p(site), 6)
        if not ok:
            raise RuntimeError("Nie udało się podpiąć hooka.")
        self.site, self.stub = site, stub
        return "Hook zainstalowany."

    def _alloc_near(self, site):
        g = self.g
        start = (site - 0x10000) & ~0xFFFF
        for step in range(0, 0x7FF0):                     # do ~2 GB w dół i w górę
            for a in (start - step * 0x10000, start + step * 0x10000 + 0x20000):
                if a <= 0x10000:
                    continue
                p = k32.VirtualAllocEx(g.h, ctypes.c_void_p(a), STUB_SIZE,
                                       MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE)
                if p and abs(p - site) < 0x7FFF0000:
                    return p
        return None

    def rows(self):
        raw = self.g.read(self.stub + OFF_TABLE, TABLE_ENTRIES * TABLE_ENTRY)
        out = []
        if raw:
            for i in range(TABLE_ENTRIES):
                row, ctx, handle = struct.unpack_from("<QQI", raw, i * TABLE_ENTRY)
                if row:
                    out.append((row, ctx, handle))
        return out

    def clear_rows(self):
        self.g.write(self.stub + OFF_TABLE, bytes(TABLE_ENTRIES * TABLE_ENTRY))

    def refresh_row(self, row_addr, timeout=2.0):
        g = self.g
        before = g.u32(self.stub + OFF_DONE)
        g.write_u64(self.stub + OFF_TARGET, row_addr)
        g.write(self.stub + OFF_REQUEST, b"\x01")
        t = time.time()
        ok = False
        while time.time() - t < timeout:
            if g.u32(self.stub + OFF_DONE) != before:
                ok = True
                break
            time.sleep(0.01)
        g.write(self.stub + OFF_REQUEST, b"\x00")
        g.write_u64(self.stub + OFF_TARGET, 0)
        return ok


# ---------------------------------------------------------------------------
# Tworzenie przedmiotu funkcjami gry (TMI3) – z egzemplarzem (PIDE) od razu
# ---------------------------------------------------------------------------
# Hook na wejściu enshrouded.exe+411DF0 (gra woła ją przy każdej transakcji
# ekwipunku, ~400×/s na wątku serwera – zmierzone sondą tools/tx_probe.py).
# Gdy program zgłosi prośbę, hook – na wątku gry – robi własną transakcję tak
# jak gra przy łupach:
#   +21DD00 konstruktor → +411DF0 wypełnij (referencje skopiowane z bieżącego
#   wywołania gry) → +E7A870 ItemInfo z ID → +40B760 „nowy przedmiot w slocie”
#   → +408B50 zatwierdź (tu gra tworzy egzemplarz: zdarzenie 0 → +40AB40)
#   albo +410E60 cofnij → +21DE50 destruktor.   Źródło kodu: ce/stub3.s

CREATE_SITE_RVA = 0x411DF0
CREATE_SITE_ORIGINAL = bytes.fromhex("C681A871000000")
# (offset w bloku, RVA funkcji, jej pierwsze bajty – kontrola wersji gry)
# (offset w bloku, nazwa wzoru w SIGNATURES) – adresy szukane przy instalacji
CREATE_FUNCS = (
    (0x40, "CTOR"),        # konstruktor transakcji      (+21DD00 w buildzie 25988036)
    (0x48, "LOOKUP"),      # ItemInfo z ID               (+E7A870)
    (0x58, "CREATE"),      # nowy przedmiot w slocie     (+40B760)
    (0x60, "COMMIT"),      # zatwierdź                   (+408B50)
    (0x68, "ROLLBACK"),    # cofnij                      (+410E60)
    (0x70, "DTOR"),        # destruktor                  (+21DE50)
)
STUB3_ORIG_AT = -13        # w STUB3_CODE: kopia 1. instrukcji +411DF0 (7 B), potem jmp [ret] (6 B)
TX_MAX_FIELD = 0x7E00      # transakcja leży w bloku od 0x1000 do C_BLOCK
STUB3_CODE = bytes.fromhex(
    "833d11feffff010f858501000050488b4208483b05f7fdffff0f857201000051b801000000b90200"
    "0000f00fb10de6fdffff590f85580100005850515253555657415041514152415341544155415641"
    "579cf0ff05dbfdffff4889e54883e4f04883ec60fc4889d6488d3d91feffffb91e000000f348a548"
    "8d0d820d0000ff15bcfdffff488d0d750d0000488d156efeffffe8fb0000008b0d8bfdffff488b15"
    "640d0000ff159efdffff4885c00f848c0000004989c1440fb60566fdffff49c1e0208b0558fdffff"
    "4909c08b055bfdffff4889442420488d05b3fdffff4889442428488d05b7fdffff4889442430488d"
    "05bbfdffff4889442438488d0d7ffdffff488d15f80c0000ff154afdffff0fb6056bfdffff890501"
    "fdffff8b0567fdffff890509fdffff803d52fdffff007519488d0dc90c0000ff1523fdffffeb17c7"
    "05d3fcffff00010000488d0db00c0000ff1512fdffff488d0da30c0000ff150dfdfffff0ff05cefc"
    "ffffc705a4fcffff030000004889ec9d415f415e415d415c415b415a415941585f5e5d5b5a5958eb"
    "0158c681a871000000ff2569fcffff")
STUB3_MAGIC = b"TMI3new\x00"
PROBE_MAGIC = b"TMIprobe"                       # sonda tools/tx_probe.py (kod od 0x100)
C_RET, C_WORLD, C_REQ, C_RESULT = 0x08, 0x10, 0x18, 0x1C
C_HANDLE, C_SLOT, C_ITEM, C_QTY = 0x20, 0x24, 0x28, 0x2C
C_LEFT, C_HITS, C_DONE = 0x30, 0x34, 0x38
# Opcje przekazywane grze (stub3 podaje wskaźniki do CREATE +40B760 jako optA/optB/optC):
#   +0x90 poziom  {u32 wartość, u8 jest}  -> zdarzenie+0x0C (bez niego gra LOSUJE poziom z itemLevelRange)
#   +0xA0 rzadkość {u8 wartość, u8 jest}  -> zdarzenie+0x14 (bez niej przy generateRarity gra daje najniższą
#                                            dozwoloną – kod +40AE43); wartości jak keen::ItemRarity niżej
#   +0xB0 nieznane {f32, u8 jest} – zawsze puste
C_OPT_LEVEL, C_OPT_RARITY = 0x90, 0xA0
RARITY_CODE = {"Common": 0, "Uncommon": 1, "Rare": 2, "Epic": 3, "Legendary": 4}
C_CODE, C_BLOCK = 0x200, 0x9000                 # transakcja (0x71B0 B) od 0x1000


class Creator:
    """Dodawanie przedmiotu „jak gra” – egzemplarz powstaje od razu."""

    def __init__(self, game):
        self.g = game
        self.site = None
        self.blk = None

    def install(self):
        g = self.g
        scan = CodeScanner(g)
        site = scan.resolve("CREATE_SITE", allow_scan=False)
        if site is None:
            # może to nasz hook (E9) pod znanym adresem, albo nowa wersja gry
            known = g.base + CREATE_SITE_RVA
            b = g.read(known, 5)
            ours = False
            if b and b[0] == 0xE9:
                dest = known + 5 + struct.unpack("<i", b[1:5])[0]
                ours = g.read(dest - C_CODE, 8) == STUB3_MAGIC or g.read(dest - 0x100, 8) == PROBE_MAGIC
            site = known if ours else scan.resolve("CREATE_SITE")
        if site is None:
            raise UnsupportedGameVersion("nie znaleziono miejsca w grze (nowa wersja gry?)")
        cur = g.read(site, 7)
        if cur is None:
            raise RuntimeError("nie da się odczytać kodu gry")
        funcs = {}
        for _off, name in CREATE_FUNCS:
            a = scan.resolve(name)
            if a is None:
                raise UnsupportedGameVersion(f"nie znaleziono funkcji gry {name} (ta wersja gry nie jest jeszcze obsługiwana)")
            funcs[name] = a
        if cur[0] == 0xE9:
            dest = site + 5 + struct.unpack("<i", cur[1:5])[0]
            if g.read(dest - C_CODE, 8) == STUB3_MAGIC:
                self.site, self.blk = site, dest - C_CODE
                return "Dodawanie przez grę: włączone."
            if g.read(dest - 0x100, 8) != PROBE_MAGIC:
                raise RuntimeError("w +411DF0 siedzi obcy hook (Cheat Engine?)")
        elif not (cur[0] == 0xC6 and cur[1] == 0x81 and cur[4:7] == b"\0\0\0"
                  and struct.unpack("<I", cur[2:6])[0] < TX_MAX_FIELD):
            raise UnsupportedGameVersion("kod gry w miejscu hooka TMI3 jest inny (ta wersja gry nie jest jeszcze obsługiwana)")
        blk = self._alloc_near(site)
        if not blk:
            raise RuntimeError("nie udało się przydzielić pamięci")
        data = bytearray(C_CODE)
        data[0:8] = STUB3_MAGIC
        data[C_RET:C_RET + 8] = (site + 7).to_bytes(8, "little")
        for off, name in CREATE_FUNCS:
            data[off:off + 8] = funcs[name].to_bytes(8, "little")
        code = bytearray(STUB3_CODE)
        code[STUB3_ORIG_AT:STUB3_ORIG_AT + 7] = cur      # oryginalna instrukcja z tej wersji gry
        if not g.write(blk, bytes(data) + bytes(code)):
            raise RuntimeError("nie udało się zapisać kodu")
        rel = (blk + C_CODE) - (site + 5)
        self._patch(site, b"\xE9" + struct.pack("<i", rel) + b"\x90\x90")
        self.site, self.blk = site, blk
        return "Dodawanie przez grę: włączone."

    def _alloc_near(self, site):
        g = self.g
        start = (site - 0x10000) & ~0xFFFF
        for step in range(0, 0x7FF0):
            for a in (start - step * 0x10000, start + step * 0x10000 + 0x40000):
                if a <= 0x10000:
                    continue
                p = k32.VirtualAllocEx(g.h, ctypes.c_void_p(a), C_BLOCK,
                                       MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE)
                if p and abs(p - site) < 0x7FFF0000:
                    return p
        return None

    def _patch(self, site, data):
        g = self.g
        old = wt.DWORD()
        k32.VirtualProtectEx(g.h, ctypes.c_void_p(site), len(data), PAGE_EXECUTE_READWRITE,
                             ctypes.byref(old))
        ok = g.write(site, data)
        k32.VirtualProtectEx(g.h, ctypes.c_void_p(site), len(data), old.value,
                             ctypes.byref(wt.DWORD()))
        k32.FlushInstructionCache(g.h, ctypes.c_void_p(site), len(data))
        if not ok:
            raise RuntimeError("nie udało się podpiąć hooka")

    def stats(self):
        g = self.g
        return {k: g.u32(self.blk + o) for k, o in
                (("req", C_REQ), ("result", C_RESULT), ("left", C_LEFT),
                 ("hits", C_HITS), ("done", C_DONE))}

    def create(self, world, handle, slot, item_id, qty, timeout=2.0, rarity=None, level=None):
        """Prosi grę o utworzenie przedmiotu w slocie (rząd = uchwyt encji, slot 0–7).
        rarity = "Common"…"Legendary" albo None (gra wybiera sama), level = liczba albo None.
        Zwraca (status, kod_błędu_gry, reszta); status: 'ok' | 'timeout' | 'busy'."""
        g, b = self.g, self.blk
        t = time.time()
        while g.u32(b + C_REQ) in (1, 2):              # poprzednia prośba jeszcze trwa
            if time.time() - t > timeout:
                return "busy", None, qty
            time.sleep(0.01)
        g.write_u64(b + C_WORLD, world)
        code = RARITY_CODE.get(rarity)
        g.write(b + C_OPT_RARITY, bytes([code or 0, 1 if code is not None else 0]))
        g.write(b + C_OPT_LEVEL, struct.pack("<IB", int(level or 0), 1 if level else 0))
        for off, v in ((C_HANDLE, handle), (C_SLOT, slot), (C_ITEM, item_id), (C_QTY, qty),
                       (C_RESULT, 0xFFFFFFFF), (C_LEFT, qty)):
            g.write_u32(b + off, v)
        g.write_u32(b + C_REQ, 1)                       # zgłoszenie – na samym końcu
        t = time.time()
        while True:
            req = g.u32(b + C_REQ)
            if req == 3:
                res, left = g.u32(b + C_RESULT), g.u32(b + C_LEFT)
                g.write_u32(b + C_REQ, 0)
                return "ok", res, left
            waited = time.time() - t
            if req == 1 and waited > timeout:
                g.write_u32(b + C_REQ, 0)               # gra nie podjęła – odwołujemy
                time.sleep(0.3)                         # (gdyby podjęła w tej samej chwili)
                if g.u32(b + C_REQ) == 3:
                    res, left = g.u32(b + C_RESULT), g.u32(b + C_LEFT)
                    g.write_u32(b + C_REQ, 0)
                    return "ok", res, left
                return "timeout", None, qty
            if waited > timeout + 3.0:
                return "timeout", None, qty
            time.sleep(0.005)


def row_handle(hook, ctx, row_addr):
    for row, c, handle in hook.rows():
        if row == row_addr and c == ctx:
            return handle
    return None


# ---------------------------------------------------------------------------
# Ekwipunek
# ---------------------------------------------------------------------------

def read_slots(game, start):
    raw = game.read(start, ARRAY_SLOTS * SLOT_SIZE)
    if raw is None:
        return None
    return [struct.unpack_from("<III", raw, i * SLOT_SIZE) for i in range(ARRAY_SLOTS)]


def slots_look_valid(slots):
    if slots is None:
        return False
    for item_id, qty, _ in slots[:BASE_SLOTS]:
        if qty > MAX_QTY or (qty > 0 and item_id == 0):
            return False
    return True


def slot_row_addr(start, idx):
    return start + (idx // 8) * ROW


def slot_position(idx):
    if idx < 16:
        return idx // 8 + 1, idx % 8 + 1
    if idx >= 32:
        return 3 + (idx - 32) // 8, (idx - 32) % 8 + 1
    if idx < 24:
        return "Alt", idx - 16 + 1
    return "Akcja", idx - 24 + 1


def occupied_signature(slots):
    return tuple((i, s[0], s[1]) for i, s in enumerate(slots[:BASE_SLOTS]) if s[1] > 0)


def backpack_extra_rows(game, hook, ctx, start):
    """Ile rzędów dodaje założony plecak (0, gdy brak albo plecak jeszcze
    bez swoich danych – np. dodany programem, przed ponownym wczytaniem świata)."""
    block = {start + k * ROW for k in range(-1, ARRAY_SLOTS // 8)}
    for row, c, _h in hook.rows():
        if c != ctx or row in block:
            continue
        raw = game.read(row, ROW)
        if not raw:
            continue
        for i in range(8):
            iid, q, ex = struct.unpack_from("<III", raw, i * SLOT_SIZE)
            if q and ex and iid in BACKPACK_ROWS:
                return BACKPACK_ROWS[iid]
    return 0


def visible_slots(game, hook, ctx, start):
    # Gra ma 5 rzędów na rozszerzenia (indeksy 40–79) i plecak włącza OSTATNIE z nich
    # (duży plecak = 4 ostatnie). Sprawdzone porównaniem ekranu z pamięcią.
    extra = min(backpack_extra_rows(game, hook, ctx, start), (ARRAY_SLOTS - BASE_SLOTS) // 8)
    return VISIBLE_SLOTS + list(range(ARRAY_SLOTS - 8 * extra, ARRAY_SLOTS))


def hidden_bag_slots(vis):
    """Sloty plecaka (r1–r3 i rozszerzenia), których gra teraz nie pokazuje. Paski pomijamy."""
    bag = set(range(0, 16)) | set(range(32, ARRAY_SLOTS))
    return sorted(bag - set(vis))


def rescue_hidden(game, hook, inv):
    """Przenosi przedmioty z niewidocznych slotów do wolnych widocznych."""
    start, found = inv.server_start()
    if start is None and not found:
        return False, "Nie znaleziono ekwipunku."
    # Gdy nie wiemy jeszcze, która kopia to serwer – przestawiamy identycznie w obu.
    copies = [(start, inv.ctx_of(start))] if start is not None else list(found)
    s0, c0 = copies[0]
    slots = read_slots(game, s0)
    vis = visible_slots(game, hook, c0, s0)
    hidden = [i for i in hidden_bag_slots(vis) if slots[i][1] > 0]
    if not hidden:
        return True, "Nie ma ukrytych przedmiotów."
    free = [i for i in vis if slots[i][1] == 0]
    pairs = list(zip(hidden, free))
    for base, _c in copies:
        rows = set()
        for src, dst in pairs:
            raw = game.read(base + src * SLOT_SIZE, SLOT_SIZE)
            game.write(base + dst * SLOT_SIZE, raw)
            game.write(base + src * SLOT_SIZE, bytes(SLOT_SIZE))
            rows.add(slot_row_addr(base, src))
            rows.add(slot_row_addr(base, dst))
        for r in sorted(rows):
            hook.refresh_row(r)
    moved = len(pairs)
    left = len(hidden) - moved
    msg = f"Przeniesiono {moved} ukrytych przedmiotów do widocznych slotów."
    if left:
        msg += f" Zabrakło miejsca na {left} – zwolnij sloty i kliknij jeszcze raz."
    return True, msg


class Inventory:
    """Znajduje ekwipunek gracza (kopię serwera) z rzędów zebranych przez hook."""

    def __init__(self, game, hook):
        self.g, self.hook = game, hook
        self.server_ctx = None

    def candidates(self):
        by_ctx = {}
        for row, ctx, handle in self.hook.rows():
            by_ctx.setdefault(ctx, set()).add(row)
        # Ekwipunek gracza = blok 6 rzędów leżących obok siebie:
        #   wyposażenie, plecak r1, plecak r2, pasek Alt, pasek akcji, plecak r3.
        # Szukamy plecaka r1 (r): r−1 rząd jest, r−2 rzędu nie ma, r+1..r+4 są.
        # Zapasowo (gdy hook nie widzi rzędu wyposażenia): r+1..r+4 są, r−1 i r+5 nie.
        cands = []
        for ctx, rs in by_ctx.items():
            for r in rs:
                if not all(r + k * ROW in rs for k in (1, 2, 3, 4)):
                    continue
                with_equip = (r - ROW in rs) and (r - 2 * ROW not in rs)
                no_equip = (r - ROW not in rs) and (r + 5 * ROW not in rs)
                if with_equip or no_equip:
                    slots = read_slots(self.g, r)
                    if slots_look_valid(slots):
                        cands.append((r, ctx, slots))
        return cands

    def locate(self, wait=3.0):
        """Lista (adres, ctx): kopia serwera i klienta tego samego ekwipunku."""
        t = time.time()
        cleared = False
        while True:
            cands = self.candidates()
            if self.server_ctx is not None:
                for r, ctx, _ in cands:
                    if ctx == self.server_ctx:
                        return [(r, ctx)]
            # Para serwer+klient = ten sam rząd r1 w grze (uchwyt encji) i ta sama zawartość r1.
            # Nie porównujemy kolejnych rzędów: u klienta leżą w pamięci w innej kolejności (19.10).
            handles = {(row, c): h for row, c, h in self.hook.rows()}
            groups = {}
            for r, ctx, slots in cands:
                key = (handles.get((r, ctx)), occupied_signature(slots[:8]))
                groups.setdefault(key, []).append((r, ctx))
            pairs = [v for v in groups.values() if len({c for _, c in v}) >= 2]
            if len(pairs) == 1:
                return pairs[0]
            if len(cands) == 1:
                return [(cands[0][0], cands[0][1])]
            if time.time() - t > wait:
                if not cleared:
                    self.hook.clear_rows()      # stare wpisy (np. po zmianie świata)
                    self.server_ctx = None
                    cleared = True
                    t = time.time()
                    continue
                return []                       # niejednoznacznie – lepiej nic nie pisać
            time.sleep(0.2)

    def ctx_of(self, start):
        for row, ctx, _h in self.hook.rows():
            if row == start:
                return ctx
        return self.server_ctx

    def server_start(self):
        found = self.locate()
        if not found:
            return None, found
        if self.server_ctx is not None:
            for r, ctx in found:
                if ctx == self.server_ctx:
                    return r, found
        if len(found) == 1:
            return found[0][0], found
        return None, found       # jeszcze nie wiadomo, która kopia to serwer


def write_slot(game, addr, item_id, qty, extra=0):
    return (game.write_u32(addr, item_id) and game.write_u32(addr + 8, extra)
            and game.write_u32(addr + 4, qty))


def wait_slot(game, addr, item_id, qty, timeout=1.0):
    t = time.time()
    while time.time() - t < timeout:
        b = game.read(addr, 8)
        if b and struct.unpack("<II", b) == (item_id, qty):
            return True
        time.sleep(0.02)
    return False


def describe(idx, qty, refreshed):
    r, c = slot_position(idx)
    msg = f"Dodano {qty} szt. do slotu: rząd {r}, kolumna {c}."
    if refreshed:
        return msg + " Gra powinna pokazać przedmiot od razu."
    return msg + (" Automatyczne odświeżenie nie zadziałało – przesuń dowolny "
                  f"przedmiot z rzędu {r}, żeby się pokazał.")


def add_item(game, hook, inv, item_id, qty):
    start, found = inv.server_start()
    if start is None and not found:
        return False, ("Nie znaleziono jednoznacznie ekwipunku. Czy świat jest wczytany? "
                       "Otwórz na chwilę ekwipunek w grze i spróbuj ponownie. Jeśli to się "
                       "powtarza, kliknij „Diagnostyka” w oknie.")
    if start is not None:
        slots = read_slots(game, start)
        vis = visible_slots(game, hook, inv.ctx_of(start), start)
        free = [i for i in vis if slots[i][1] == 0]
        if not free:
            return False, "Brak wolnego widocznego slotu w ekwipunku."
        idx = free[0]
        if not write_slot(game, start + idx * SLOT_SIZE, item_id, qty):
            return False, "Zapis do pamięci gry się nie udał."
        return True, describe(idx, qty, hook.refresh_row(slot_row_addr(start, idx)))

    # Pierwsze dodanie w sesji: są dwie kopie (serwer i klient). Wpisujemy do jednej,
    # odświeżamy i patrzymy, czy druga się zaktualizuje – wtedy ta pierwsza to serwer.
    # Najpierw próbujemy kopię pod wyższym adresem – w testach to był serwer.
    (a, ca), (b, cb) = sorted(found[:2], key=lambda t: t[0], reverse=True)
    sa, sb = read_slots(game, a), read_slots(game, b)
    vis = visible_slots(game, hook, ca, a)
    # Tylko sloty z rzędu, który w obu kopiach jest tym samym rzędem gry (ten sam uchwyt) –
    # u klienta rzędy bywają w pamięci w innej kolejności niż u serwera.
    handles = {(row, c): h for row, c, h in hook.rows()}
    same = lambda i: (handles.get((slot_row_addr(a, i), ca)) is not None and
                      handles.get((slot_row_addr(a, i), ca)) == handles.get((slot_row_addr(b, i), cb)))
    free = [i for i in vis if sa[i][1] == 0 and sb[i][1] == 0 and same(i)]
    if not free:
        return False, "Brak wolnego widocznego slotu w ekwipunku."
    idx = free[0]
    for (x, cx), (y, _cy) in (((a, ca), (b, cb)), ((b, cb), (a, ca))):
        ax, ay = x + idx * SLOT_SIZE, y + idx * SLOT_SIZE
        old = game.read(ax, SLOT_SIZE)
        write_slot(game, ax, item_id, qty)
        refreshed = hook.refresh_row(slot_row_addr(x, idx))
        if refreshed and wait_slot(game, ay, item_id, qty):
            inv.server_ctx = cx
            inv.last_idx = idx
            return True, describe(idx, qty, True)
        game.write(ax, old)                    # cofamy próbę
        hook.refresh_row(slot_row_addr(x, idx), timeout=0.5)
    return False, ("Nie udało się ustalić, która kopia ekwipunku jest prawdziwa. "
                   "Rusz coś w ekwipunku i spróbuj ponownie.")


def diag_report(game, hook, inv, creator=None):
    """Tekstowy raport: rzędy widziane przez hook i ich zawartość."""
    out = []
    out.append(f"PID {game.pid}  moduł {game.base:#x}  hook {hook.stub:#x}")
    build, stamp = game_version(game)
    out.append(f"Wersja gry: {build or 'NIEZNANA (adresy wyszukane wzorami)'}  (exe {stamp:#x}, "
               f"Steam build {steam_build_id(game) or '?'}, program {APP_VERSION})")
    if creator is not None and creator.blk:
        try:
            out.append(f"TMI3 {creator.blk:#x}: " + " ".join(f"{k}={v}" for k, v in
                                                             creator.stats().items()))
        except Exception:
            pass
    else:
        out.append("TMI3: wyłączone")
    try:
        out.append(f"done={game.u32(hook.stub + OFF_DONE)} hits={game.u32(hook.stub + OFF_HITS)}")
    except Exception:
        pass
    by_ctx = {}
    for row, ctx, handle in hook.rows():
        by_ctx.setdefault(ctx, []).append((row, handle))
    out.append(f"Rzędów w tabeli: {sum(len(v) for v in by_ctx.values())} / {TABLE_ENTRIES}")
    for ctx, lst in by_ctx.items():
        out.append(f"\nkontekst {ctx:#x}  ({len(lst)} rzędów)")
        for row, handle in sorted(lst):
            raw = game.read(row, ROW)
            cells = []
            if raw:
                for i in range(8):
                    iid, q, ex = struct.unpack_from("<III", raw, i * SLOT_SIZE)
                    cells.append(f"{iid}x{q}" + (f"+{ex}" if ex else "") if q else ".")
            out.append(f"  {row:#x} h={handle:#x}  " + " ".join(cells))
    out.append("\nKandydaci: " + ", ".join(f"{r:#x}(ctx {c:#x})" for r, c, _ in inv.candidates()))
    out.append(f"Serwer ctx: {inv.server_ctx:#x}" if inv.server_ctx else "Serwer ctx: ?")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Język gry (ze Steama) i dodawanie z dokładaniem do stosów
# ---------------------------------------------------------------------------

STEAM_LANG = {
    "english": "En_Us", "german": "De_De", "french": "Fr_Fr", "italian": "It_It",
    "spanish": "Es_Es", "latam": "Es_Es", "russian": "Ru_Ru", "polish": "Pl_Pl",
    "japanese": "Ja_Jp", "koreana": "Ko_Kr", "brazilian": "Pt_Br", "portuguese": "Pt_Br",
    "thai": "Th_Th", "turkish": "Tr_Tr", "schinese": "Zh_Cn", "tchinese": "Zh_Tw",
    "ukrainian": "Uk_Ua",
}


def detect_game_language(game):
    """Czyta język gry z pliku Steama appmanifest_1203620.acf."""
    exe = game.exe_path() if game else None
    if not exe:
        return None
    # ...\steamapps\common\Enshrouded\enshrouded.exe -> ...\steamapps\appmanifest_1203620.acf
    steamapps = os.path.dirname(os.path.dirname(os.path.dirname(exe)))
    acf = os.path.join(steamapps, "appmanifest_1203620.acf")
    try:
        with open(acf, "r", encoding="utf-8", errors="replace") as f:
            m = re.search(r'"language"\s+"([^"]+)"', f.read())
    except OSError:
        return None
    return STEAM_LANG.get(m.group(1).lower()) if m else None


STONE_ID = 631520303                 # kamień – do ustalenia kopii serwera
CREATE_ERRORS = {0x12: "slot niedostępny", 0x27: "brak miejsca na zdarzenie w transakcji",
                 0x100: "gra nie zna tego ID przedmiotu"}
PIDE_HINT = (" WAŻNE: przesuń ten przedmiot raz na inny slot w ekwipunku – gra dopiero "
             "wtedy go w pełni aktywuje (np. plecak doda rzędy).")


def ensure_server(game, hook, inv):
    """Ustala kopię serwera (jak przy pierwszym dodaniu): na chwilę kładzie 1 kamień
    i od razu go zabiera. Zwraca (start, komunikat_błędu)."""
    start, found = inv.server_start()
    if start is not None:
        return start, None
    if not found:
        return None, ("Nie znaleziono jednoznacznie ekwipunku. Czy świat jest wczytany? "
                      "Otwórz na chwilę ekwipunek w grze i spróbuj ponownie. Jeśli to się "
                      "powtarza, kliknij „Diagnostyka” w oknie.")
    ok, msg = add_item(game, hook, inv, STONE_ID, 1)
    if not ok:
        return None, msg
    start, _ = inv.server_start()
    if start is None:
        return None, "Nie udało się ustalić, która kopia ekwipunku jest prawdziwa."
    i = getattr(inv, "last_idx", None)
    if i is not None:
        a = start + i * SLOT_SIZE
        if struct.unpack("<II", game.read(a, 8)) == (STONE_ID, 1):
            game.write(a, bytes(SLOT_SIZE))
            hook.refresh_row(slot_row_addr(start, i))
    return start, None


def add_via_game(game, hook, inv, creator, item_id, qty, max_stack, pide=False, rarity=None):
    """Dodaje przez funkcje gry (TMI3): najpierw dokłada do stosów, potem wolne sloty.
    Przedmioty z egzemplarzem (pide) – sztuka na wolny slot, egzemplarz tworzy gra.
    Zwraca (ok, komunikat) albo None = gra nie podjęła prośby, użyj starej drogi."""
    start, err = ensure_server(game, hook, inv)
    if start is None:
        return False, err
    ctx = inv.server_ctx or inv.ctx_of(start)
    max_stack = 1 if pide else max(1, min(int(max_stack or 1), MAX_QTY))
    slots = read_slots(game, start)
    vis = visible_slots(game, hook, ctx, start)
    plan, left = [], qty                         # (idx, ile dołożyć)
    if not pide:
        for i in vis:
            sid, sq, _ = slots[i]
            if left and sq > 0 and sid == item_id and sq < max_stack:
                n = min(max_stack - sq, left)
                plan.append((i, n))
                left -= n
    for i in vis:
        if left and slots[i][1] == 0:
            n = min(max_stack, left)
            plan.append((i, n))
            left -= n
    if not plan:
        return False, "Brak miejsca w ekwipunku."
    added = with_pide = done_slots = 0
    problem = None
    for i, n in plan:
        handle = row_handle(hook, ctx, slot_row_addr(start, i))
        if handle is None:
            problem = "nie znam uchwytu rzędu"
            break
        status, res, rest = creator.create(ctx, handle, i % 8, item_id, n, rarity=rarity)
        if status != "ok":
            if added == 0:
                return None
            problem = "gra przestała odpowiadać"
            break
        if res != 0:
            problem = CREATE_ERRORS.get(res, f"kod gry {res:#x}")
            break
        got = n - min(rest, n)
        added += got
        if got:
            done_slots += 1
            if pide and struct.unpack_from("<I", game.read(start + i * SLOT_SIZE + 8, 4))[0]:
                with_pide += 1
    if added == 0:
        return False, f"Gra nie utworzyła przedmiotu ({problem or 'brak miejsca'})."
    msg = f"Dodano {added} szt."
    if pide:
        if with_pide == done_slots:
            msg += " Gotowe do użycia (gra utworzyła egzemplarz)."
        else:
            msg += f" Egzemplarz ma {with_pide} z {done_slots}." + PIDE_HINT
    if added < qty:
        msg += f" Nie dodano {qty - added} szt.: {problem or 'brak miejsca'}."
    return True, msg


def add_items_smart(game, hook, inv, item_id, qty, max_stack, pide=False, creator=None, rarity=None):
    """Dokłada do istniejących stosów, resztę wkłada do wolnych slotów. Zwraca (ok, komunikat).
    Gdy TMI3 działa – przez funkcje gry (add_via_game); inaczej starą metodą (zapis w pamięci
    + odświeżenie hookiem), przy pierwszym dodaniu w sesji add_item() ustala kopię serwera."""
    if creator is not None and creator.blk:
        res = add_via_game(game, hook, inv, creator, item_id, qty, max_stack, pide, rarity)
        if res is not None:
            return res
        ok, msg = add_items_smart(game, hook, inv, item_id, qty, max_stack)
        note = " (Gra nie podjęła prośby – użyto starej metody.)"
        return ok, msg + ((note + (PIDE_HINT if pide else "")) if ok else "")
    if pide:
        ok, msg = add_items_smart(game, hook, inv, item_id, qty, max_stack)
        return ok, msg + (PIDE_HINT if ok else "")
    max_stack = max(1, min(int(max_stack or 1), MAX_QTY))
    pre = 0
    start, found = inv.server_start()
    if start is None:
        first = min(qty, max_stack)
        ok, msg = add_item(game, hook, inv, item_id, first)
        if not ok or qty == first:
            return ok, msg
        qty -= first
        pre = first
        start, found = inv.server_start()
        if start is None:
            return True, msg + f" (Pozostałe {qty} szt. dodaj jeszcze raz.)"
    slots = read_slots(game, start)
    vis = visible_slots(game, hook, inv.ctx_of(start), start)
    plan = []                                   # (idx, nowa_ilość)
    left = qty
    for i in vis:                               # najpierw dokładanie do stosów
        sid, sq, _ = slots[i]
        if left and sq > 0 and sid == item_id and sq < max_stack:
            add = min(max_stack - sq, left)
            plan.append((i, sq + add))
            left -= add
    for i in vis:                               # potem wolne sloty
        if left and slots[i][1] == 0:
            add = min(max_stack, left)
            plan.append((i, add))
            left -= add
    if not plan:
        if pre:
            return True, f"Dodano {pre} szt. Zabrakło miejsca na {qty} szt."
        return False, "Brak miejsca w ekwipunku."
    rows = set()
    for i, new_q in plan:
        a = start + i * SLOT_SIZE
        if slots[i][1] == 0:
            write_slot(game, a, item_id, new_q)
        else:
            game.write_u32(a + 4, new_q)
        rows.add(slot_row_addr(start, i))
    refreshed = all(hook.refresh_row(r) for r in sorted(rows))
    added = qty - left + pre
    msg = f"Dodano {added} szt."
    if left:
        msg += f" Zabrakło miejsca na {left} szt."
    if not refreshed:
        msg += " (Odświeżenie nie zadziałało – przesuń przedmiot w tym rzędzie.)"
    return True, msg


# ---------------------------------------------------------------------------
# Baza itemów
# ---------------------------------------------------------------------------

def load_items():
    items = dict(DEFAULT_ITEMS)
    for path in (ITEMS_FILE, FALLBACK_ITEMS_FILE):
        try:
            with open(path, "r", encoding="utf-8") as f:
                items.update(json.load(f))
        except (OSError, ValueError):
            pass
    return items


def save_items(items):
    for path in (ITEMS_FILE, FALLBACK_ITEMS_FILE):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(items, f, ensure_ascii=False, indent=2)
            return path
        except OSError:
            continue
    print("UWAGA: nie udało się zapisać bazy itemów.")
    return None


# ---------------------------------------------------------------------------
# Menu tekstowe
# ---------------------------------------------------------------------------

def ask_int(prompt, lo, hi):
    while True:
        s = input(prompt).strip()
        if s.isdigit() and lo <= int(s) <= hi:
            return int(s)
        print(f"  Podaj liczbę od {lo} do {hi}.")


def current_start(inv):
    start, found = inv.server_start()
    if start is None and found:
        start = found[0][0]
    return start


def show_inventory(game, inv, items):
    start, found = inv.server_start()
    if start is None and not found:
        print("Nie znaleziono ekwipunku (otwórz go na chwilę w grze i spróbuj ponownie).")
        return
    if start is None:
        start = found[0][0]
        print("(Jeszcze nie wiem, która kopia to serwer – ustalę to przy pierwszym dodaniu.)")
    print(f"Ekwipunek: {start:#x}")
    for idx, (iid, qty, extra) in enumerate(read_slots(game, start)):
        if qty:
            r, c = slot_position(idx)
            pos = f"r{r}k{c}" if isinstance(r, int) else f"{r}:{c}"
            name = items.get(str(iid), "?")
            print(f"  [{idx:2}] {pos:8} {name:20} ID {iid:<10} x{qty}  +8={extra}")


def main():
    try:
        game = Game()
        hook = Hook(game)
        print(f"Połączono z grą (PID {game.pid}).")
        print(hook.install())
    except RuntimeError as e:
        print(e)
        input("Enter, aby zakończyć...")
        return
    inv = Inventory(game, hook)
    items = load_items()

    while True:
        if not game.alive():
            print("Gra została zamknięta.")
            break
        print("\n=== TooManyItems_ED ===")
        keys = list(items.keys())
        for n, k in enumerate(keys, 1):
            print(f"  {n}. {items[k]}  (ID {k})")
        print("  N. Naucz się itemu ze slotu 1")
        print("  P. Pokaż ekwipunek")
        print("  D. Diagnostyka (rzędy widziane przez hook)")
        print("  Q. Wyjście")
        choice = input("> ").strip().lower()

        if choice == "q":
            break
        elif choice == "p":
            show_inventory(game, inv, items)
        elif choice == "d":
            by_ctx = {}
            for row, ctx, handle in hook.rows():
                by_ctx.setdefault(ctx, []).append((row, handle))
            print(f"Hook: {hook.stub:#x}, rzędów: {sum(len(v) for v in by_ctx.values())}")
            for ctx, lst in by_ctx.items():
                print(f"  kontekst {ctx:#x}:")
                for row, handle in sorted(lst):
                    print(f"    rząd {row:#x}  uchwyt {handle:#x}")
            print("Kandydaci na ekwipunek:",
                  [f"{r:#x}" for r, _c, _s in inv.candidates()],
                  " serwer ctx:", hex(inv.server_ctx) if inv.server_ctx else "?")
        elif choice == "n":
            start = current_start(inv)
            if start is None:
                print("Nie znaleziono ekwipunku.")
                continue
            iid, qty, extra = read_slots(game, start)[0]
            if qty == 0:
                print("Slot 1 jest pusty.")
                continue
            print(f"Slot 1: ID {iid}, ilość {qty}, pole +8 = {extra}")
            if extra != 0:
                print("UWAGA: pole +8 nie jest zerem – to broń/wyposażenie z dodatkowymi "
                      "danymi; dodawanie takich itemów może nie działać poprawnie.")
            name = input("Nazwa tego przedmiotu: ").strip()
            if name:
                items[str(iid)] = name
                where = save_items(items)
                if where:
                    print(f"Zapisano w: {where}")
        elif choice.isdigit() and 1 <= int(choice) <= len(keys):
            k = keys[int(choice) - 1]
            qty = ask_int(f"Ile sztuk '{items[k]}'? (1–999): ", 1, 999)
            ok, msg = add_item(game, hook, inv, int(k), qty)
            print(("OK: " if ok else "BŁĄD: ") + msg)
        else:
            print("Nie rozumiem wyboru.")

    game.close()


if __name__ == "__main__":
    main()
