# -*- coding: utf-8 -*-
"""
Fotograf ikon – TooManyItems_ED (19.10.2026). Robi ikony przedmiotom, które nie mają ich
ani z wiki (icons\\wiki), ani z plików gry (icons\\gra): wpisuje przedmiot do PIERWSZEGO slotu
plecaka (zwykły zapis + odświeżenie – bez zdarzeń gry: bez powiadomień „+1” i bez tworzenia
egzemplarzy), robi zdjęcie ekranu, wycina tło (porównanie z pustym slotem), czyści slot. Wynik: ..\\icons\\foto\\<ID>.png  (+ surowe zdjęcia w icons\\foto\\_surowe).

PRZYGOTOWANIE (najlepiej świat testowy):
  1. Gra: Ustawienia -> Grafika -> Tryb wyświetlania: OKNO BEZ RAMKI (Borderless). HDR wyłączony.
     Gra na GŁÓWNYM monitorze.
  2. Zamknij okno TooManyItems (nie mogą działać dwa programy naraz).
  3. W grze: pierwszy slot plecaka (lewy górny) PUSTY. Otwórz ekwipunek i zostaw otwarty.
     Kursor myszy odsuń na pusty obszar (nie nad slotami i nie nad postacią).
Użycie (cmd w D:\\TooManyItems_ED\\tools):
  python icon_photographer.py probny     – 10 pierwszych przedmiotów (sprawdzenie jakości)
  python icon_photographer.py wszystkie  – wszystkie bez ikony (pomija już zrobione)
  python icon_photographer.py 123 456    – wybrane ID
  python icon_photographer.py przetworz  – ikony od nowa z zapisanych surowych zrzutów (bez gry)
Po starcie masz 10 s na przełączenie się do gry. W trakcie nie ruszaj myszą ani klawiaturą.
Przerwanie: Ctrl+C w oknie cmd (albo Alt+Tab i Ctrl+C).
"""

import ctypes
import json
import os
import re
import struct
import sys
import time
import zlib
from ctypes import wintypes as wt

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import tmi_core as core  # noqa: E402

DB = os.path.join(ROOT, "items_db.json")
ICONS = os.path.join(ROOT, "icons")
OUT = os.path.join(ICONS, "foto")
RAW = os.path.join(OUT, "_surowe")
STONE, TWIGS, FIBRE = 631520303, 1798662696, 3316218728   # kamień, gałązki, włókno – kalibracja
SLOT = 0                                     # pierwszy slot plecaka (r1, slot 0)
HIDDEN_CATS = {"Blueprints", "Customization"}
HIDDEN_DEBUG = re.compile(r"deprecated|depricated|^zz?_|(^|_)test(_|$)|debug|^ability_", re.I)
SKIP_DEBUG = re.compile(r"^Icon_(Eye|Hair)Color_", re.I)        # mają kółka w kolorze

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)


# ------------------------------------------------------------------ zrzuty ekranu (GDI)

def dpi_aware():
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))       # per-monitor v2
    except Exception:
        try:
            ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)
        except Exception:
            user32.SetProcessDPIAware()


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
                ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG),
                ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]


def grab(x, y, w, h):
    """Zrzut prostokąta ekranu -> bajty BGRA (w*h*4), wiersze od góry."""
    hdc = user32.GetDC(None)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    old = gdi32.SelectObject(mem, bmp)
    gdi32.BitBlt(mem, 0, 0, w, h, hdc, x, y, 0x00CC0020 | 0x40000000)   # SRCCOPY | CAPTUREBLT
    bi = BITMAPINFOHEADER()
    bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.biWidth, bi.biHeight, bi.biPlanes, bi.biBitCount = w, -h, 1, 32
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bi), 0)
    gdi32.SelectObject(mem, old)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(None, hdc)
    return buf.raw


def screen_size():
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def write_png(path, w, h, rgba):
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + rgba[y * w * 4:(y + 1) * w * 4] for y in range(h))
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def bgra_to_rgba(b):
    out = bytearray(b)
    out[0::4], out[2::4] = b[2::4], b[0::4]
    out[3::4] = b"\xff" * (len(b) // 4)
    return bytes(out)


# ------------------------------------------------------------------ obróbka obrazu

def diff_mask(a, b, w, h, step=1, thr=30):
    """Lista (x, y) pikseli (co `step`), gdzie a i b różnią się bardziej niż thr."""
    out = []
    for y in range(0, h, step):
        row = y * w * 4
        for x in range(0, w, step):
            i = row + x * 4
            if max(abs(a[i] - b[i]), abs(a[i + 1] - b[i + 1]), abs(a[i + 2] - b[i + 2])) > thr:
                out.append((x, y))
    return out


def largest_cluster(points, step):
    """Największa grupa sąsiadujących punktów siatki -> (x0, y0, x1, y1) albo None."""
    pts = set(points)
    best = []
    while pts:
        start = pts.pop()
        comp, stack = [start], [start]
        while stack:
            x, y = stack.pop()
            for dx in (-step, 0, step):
                for dy in (-step, 0, step):
                    q = (x + dx, y + dy)
                    if q in pts:
                        pts.remove(q)
                        comp.append(q)
                        stack.append(q)
        if len(comp) > len(best):
            best = comp
    if not best:
        return None
    xs, ys = [p[0] for p in best], [p[1] for p in best]
    return min(xs), min(ys), max(xs) + step, max(ys) + step


def overlay_mask(shots, bg, w, h):
    """1 = piksel nakładki gry (cyfra, ramka „nowy”): zmieniony i identyczny na wszystkich zdjęciach."""
    m = bytearray(w * h)
    for p in range(w * h):
        i = p * 4
        if all(max(abs(s[i + c] - bg[i + c]) for c in range(3)) > 25 for s in shots) and \
           all(max(abs(shots[0][i + c] - s[i + c]) for c in range(3)) < 14 for s in shots[1:]):
            m[p] = 1
    return m


def extract(shot, bg, overlay, w, h):
    """Ikona z przezroczystością: alfa z różnicy względem pustego slotu, kolor „odmnożony” od tła."""
    out = bytearray(w * h * 4)
    for p in range(w * h):
        i = p * 4
        if overlay and overlay[p]:
            continue
        d = max(abs(shot[i] - bg[i]), abs(shot[i + 1] - bg[i + 1]), abs(shot[i + 2] - bg[i + 2]))
        a = min(1.0, max(0.0, (d - 14) / 45.0))
        if a <= 0:
            continue
        for c, o in ((2, 0), (1, 1), (0, 2)):                      # BGR -> RGB
            v = (shot[i + c] - (1 - a) * bg[i + c]) / a
            out[i + o] = max(0, min(255, int(v)))
        out[i + 3] = int(a * 255)
    return bytes(out)


def components(mask, w, h):
    """Spójne obszary (4-sąsiedztwo) maski 0/1 -> lista (piksele, x0, y0, x1, y1)."""
    seen = bytearray(w * h)
    out = []
    for p in range(w * h):
        if not mask[p] or seen[p]:
            continue
        seen[p] = 1
        stack, pix = [p], []
        x0 = y0 = 10 ** 9
        x1 = y1 = -1
        while stack:
            q = stack.pop()
            pix.append(q)
            x, y = q % w, q // w
            x0, x1, y0, y1 = min(x0, x), max(x1, x), min(y0, y), max(y1, y)
            for r in ((q - 1) if x > 0 else -1, (q + 1) if x < w - 1 else -1, q - w, q + w):
                if 0 <= r < w * h and mask[r] and not seen[r]:
                    seen[r] = 1
                    stack.append(r)
        out.append((pix, x0, y0, x1, y1))
    return out


def clean(rgba, w, h):
    """Zostawia sam przedmiot: usuwa napisy (drobne kształty), kreski i resztki tła."""
    strong = bytearray(1 if rgba[p * 4 + 3] >= 128 else 0 for p in range(w * h))
    comps = components(strong, w, h)
    if not comps:
        return rgba
    big = max(len(c[0]) for c in comps)
    keep = bytearray(w * h)
    for pix, x0, y0, x1, y1 in comps:
        cw, ch = x1 - x0 + 1, y1 - y0 + 1
        if len(pix) < max(120, big * 0.06):
            continue                                   # litery, kropki, okruchy tła
        if ch <= 6 and cw > w * 0.3:
            continue                                   # pozioma kreska
        if y1 < h * 0.16 and len(pix) < big * 0.5:
            continue                                   # pas napisu u góry
        for q in pix:
            keep[q] = 1
    # poszerz o 3 px (miękkie brzegi), wyzeruj resztę
    grow = bytearray(keep)
    for _ in range(3):
        nxt = bytearray(grow)
        for p in range(w * h):
            if grow[p]:
                continue
            x = p % w
            if (x > 0 and grow[p - 1]) or (x < w - 1 and grow[p + 1]) or (p >= w and grow[p - w]) or (p < w * h - w and grow[p + w]):
                nxt[p] = 1
        grow = nxt
    out = bytearray(rgba)
    for p in range(w * h):
        if not grow[p]:
            out[p * 4:p * 4 + 4] = b"\0\0\0\0"
    return bytes(out)


def erase_bottom_line(rgba, w, h):
    """Kreska-separator pod podglądem: wiersz w dolnych 15%, prawie cały „zmieniony” -> czyść od niego w dół."""
    out = bytearray(rgba)
    for y in range(int(h * 0.85), h):
        n = sum(1 for x in range(w) if rgba[(y * w + x) * 4 + 3] > 64)
        if n > w * 0.5:
            for p in range(max(0, y - 4) * w, w * h):
                out[p * 4:p * 4 + 4] = b"\0\0\0\0"
            break
    return bytes(out)


def cut_title(rgba, w, h, band=0.17):
    """Gdy napis z nazwą nachodzi na przedmiot (kremowe ~(255,251,236) piksele w wąskim pasie u góry,
    jak linia tekstu), obcina obraz tuż pod napisem. Zwraca (rgba, czy_obcięto)."""
    pts = [(p % w, p // w) for p in range(int(h * band) * w)
           if rgba[p * 4 + 3] > 40 and rgba[p * 4] >= 249 and 245 <= rgba[p * 4 + 1] <= 255
           and 226 <= rgba[p * 4 + 2] <= 242]
    if len(pts) < 40:
        return rgba, False
    ys = sorted(y for _, y in pts)
    xs = [x for x, _ in pts]
    y_lo, y_hi = ys[len(ys) // 20], ys[-1 - len(ys) // 20]           # bez skrajnych 5%
    if y_hi - y_lo > h * 0.12 or max(xs) - min(xs) < w * 0.2:
        return rgba, False                                           # to nie linia tekstu (np. włosy)
    cut = min(h, ys[-1] + 4)
    out = bytearray(rgba)
    out[:cut * w * 4] = bytes(cut * w * 4)
    return bytes(out), True


def read_png(path):
    """Czyta PNG 8-bit RGBA/RGB (np. nasze surowe zrzuty) -> (w, h, bajty RGBA)."""
    data = open(path, "rb").read()
    pos, idat, w = 8, b"", 0
    while pos < len(data):
        n = struct.unpack(">I", data[pos:pos + 4])[0]
        tag, body = data[pos + 4:pos + 8], data[pos + 8:pos + 8 + n]
        if tag == b"IHDR":
            w, h, depth, ctype = struct.unpack(">IIBB", body[:10])
            bpp = 4 if ctype == 6 else 3
        elif tag == b"IDAT":
            idat += body
        pos += 12 + n
    raw = zlib.decompress(idat)
    stride = w * bpp
    out, prev = bytearray(), bytearray(stride)
    for y in range(h):
        f = raw[y * (stride + 1)]
        line = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            if f == 1:
                line[i] = (line[i] + a) & 255
            elif f == 2:
                line[i] = (line[i] + b) & 255
            elif f == 3:
                line[i] = (line[i] + (a + b) // 2) & 255
            elif f == 4:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        out += line if bpp == 4 else b"".join(bytes(line[i:i + 3]) + b"\xff" for i in range(0, stride, 3))
        prev = line
    return w, h, bytes(out)


def rgba_to_bgra(b):
    out = bytearray(b)
    out[0::4], out[2::4] = b[2::4], b[0::4]
    return bytes(out)


def fill_holes(rgba, shot, bg, w, h, min_diff=20):
    """Zamknięte „dziury” w przedmiocie (ciemne miejsca podobne do tła panelu, np. nocne niebo na obrazie):
    przezroczyste obszary nieosiągalne od brzegu, które wyraźnie różnią się od tła -> kolor ze zdjęcia.
    Prawdziwe prześwity (np. między kijami) różnią się od tła tylko oświetleniem (~14) i zostają."""
    tr = bytearray(1 if rgba[p * 4 + 3] < 128 else 0 for p in range(w * h))
    seen = bytearray(w * h)
    st = [p for p in range(w * h) if tr[p] and (p < w or p >= w * h - w or p % w in (0, w - 1))]
    for p in st:
        seen[p] = 1
    while st:
        p = st.pop()
        x = p % w
        for q in ((p - 1) if x else -1, (p + 1) if x < w - 1 else -1, p - w, p + w):
            if 0 <= q < w * h and tr[q] and not seen[q]:
                seen[q] = 1
                st.append(q)
    out = bytearray(rgba)
    for pix, *_ in components(bytearray(1 if tr[p] and not seen[p] else 0 for p in range(w * h)), w, h):
        d = sum(max(abs(shot[q * 4 + c] - bg[q * 4 + c]) for c in range(3)) for q in pix) / len(pix)
        if d >= min_diff:
            for q in pix:
                i = q * 4
                out[i:i + 4] = bytes((shot[i + 2], shot[i + 1], shot[i], 255))
    return bytes(out)


def make_icon(shot, bg, overlay, w, h):
    """Zdjęcie (BGRA) -> ikona RGBA z przezroczystością: tło, kreska, napis, okruchy – precz."""
    rgba = extract(shot, bg, overlay, w, h)
    rgba = clean(erase_bottom_line(rgba, w, h), w, h)
    rgba, cut = cut_title(rgba, w, h)
    if cut:
        rgba = clean(rgba, w, h)
    rgba = fill_holes(rgba, shot, bg, w, h)
    return trim(rgba, w, h)


def trim(rgba, w, h, pad=2):
    """Przycina przezroczyste brzegi (ikona wycentrowana w kwadracie)."""
    xs = [p % w for p in range(w * h) if rgba[p * 4 + 3] > 24]
    if not xs:
        return None
    ys = [p // w for p in range(w * h) if rgba[p * 4 + 3] > 24]
    x0, x1, y0, y1 = max(0, min(xs) - pad), min(w, max(xs) + 1 + pad), max(0, min(ys) - pad), min(h, max(ys) + 1 + pad)
    side = max(x1 - x0, y1 - y0)
    out = bytearray(side * side * 4)
    ox, oy = (side - (x1 - x0)) // 2, (side - (y1 - y0)) // 2
    for y in range(y0, y1):
        src = rgba[(y * w + x0) * 4:(y * w + x1) * 4]
        d = ((oy + y - y0) * side + ox) * 4
        out[d:d + len(src)] = src
    return side, bytes(out)


# ------------------------------------------------------------------ gra

class Studio:
    def __init__(self):
        self.g = core.Game()
        self.hook = core.Hook(self.g)
        print(" ", self.hook.install())
        self.inv = core.Inventory(self.g, self.hook)
        start, err = core.ensure_server(self.g, self.hook, self.inv)
        if start is None:
            raise SystemExit(f"Ekwipunek: {err}")
        self.start = start
        self.ctx = self.inv.server_ctx or self.inv.ctx_of(start)
        self.region = None

    def slot_empty(self):
        return core.read_slots(self.g, self.start)[SLOT][1] == 0

    def put(self, item_id):
        a = self.start + SLOT * core.SLOT_SIZE
        if not core.write_slot(self.g, a, item_id, 1):
            return False
        self.hook.refresh_row(core.slot_row_addr(self.start, SLOT))
        return True

    def clear(self):
        self.g.write(self.start + SLOT * core.SLOT_SIZE, bytes(core.SLOT_SIZE))
        self.hook.refresh_row(core.slot_row_addr(self.start, SLOT))

    def settle(self, x, y, w, h, timeout=4.0, min_wait=0.6):
        """Czeka, aż obraz się ustabilizuje (ikona narysowana, animacje skończone)."""
        time.sleep(min_wait)
        prev = grab(x, y, w, h)
        t = time.time()
        while time.time() - t < timeout:
            time.sleep(0.2)
            cur = grab(x, y, w, h)
            if len(diff_mask(prev, cur, w, h, step=2, thr=12)) < 4:
                return cur
            prev = cur
        return prev

    def calibrate(self):
        sw, sh = screen_size()
        print(f"  Ekran {sw}x{sh}. Szukam pierwszego slotu plecaka…")
        empty = []
        for _ in range(3):
            empty.append(grab(0, 0, sw, sh))
            time.sleep(0.25)
        if max(empty[0][::4097]) == 0:
            raise SystemExit("Zrzut ekranu jest czarny – ustaw w grze tryb OKNO BEZ RAMKI (Borderless).")
        step = 4
        unstable = set(diff_mask(empty[0], empty[1], sw, sh, step, 12)) | set(diff_mask(empty[1], empty[2], sw, sh, step, 12))
        if not self.put(STONE):
            raise SystemExit("Gra nie włożyła kamienia do pierwszego slotu.")
        s1 = self.settle(0, 0, sw, sh, timeout=3.0, min_wait=1.0)
        s2 = grab(0, 0, sw, sh)
        still = set(diff_mask(empty[2], s2, sw, sh, step, 30))
        changed = [p for p in diff_mask(empty[2], s1, sw, sh, step, 30) if p not in unstable and p in still]
        box = largest_cluster(changed, step)
        self.clear()
        if not box:
            raise SystemExit("Nie widzę zmiany po włożeniu kamienia. Czy ekwipunek jest otwarty i pierwszy slot widoczny?")
        x0, y0, x1, y1 = box
        cx, cy, side = (x0 + x1) // 2, (y0 + y1) // 2, int(max(x1 - x0, y1 - y0) * 1.45) + 8
        self.region = (max(0, cx - side // 2), max(0, cy - side // 2), side, side)
        print(f"  Slot znaleziony: x={self.region[0]} y={self.region[1]} rozmiar {side}px")
        x, y, w, h = self.region
        self.bg = self.settle(x, y, w, h)
        os.makedirs(RAW, exist_ok=True)
        write_png(os.path.join(RAW, "_tlo.png"), w, h, bgra_to_rgba(self.bg))
        # wspólne nakładki (np. liczba „1”, znacznik nowości): to, co wygląda identycznie u 3 różnych przedmiotów
        shots = []
        for iid in (STONE, TWIGS, FIBRE):
            if not self.put(iid):
                raise SystemExit("Gra nie włożyła przedmiotu kalibracyjnego.")
            shots.append(self.settle(x, y, w, h))
            self.clear()
            self.settle(x, y, w, h)
        self.overlay = overlay_mask(shots, self.bg, w, h)
        with open(os.path.join(RAW, "_nakladka.bin"), "wb") as f:
            f.write(struct.pack("<II", w, h) + bytes(self.overlay))
        print(f"  Kalibracja gotowa (nakładki: {sum(self.overlay)} px).")

    def shoot(self, item_id):
        x, y, w, h = self.region
        if not self.slot_empty():
            self.clear()
            self.settle(x, y, w, h)
        if not self.put(item_id):
            return None, "gra nie włożyła przedmiotu"
        shot = self.settle(x, y, w, h)
        self.clear()
        self.settle(x, y, w, h, min_wait=0.3)
        write_png(os.path.join(RAW, f"{item_id}.png"), w, h, bgra_to_rgba(shot))
        t = make_icon(shot, self.bg, self.overlay, w, h)
        if not t:
            return None, "na zdjęciu nic się nie zmieniło"
        side, img = t
        write_png(os.path.join(OUT, f"{item_id}.png"), side, side, img)
        return side, None


# ------------------------------------------------------------------ lista

def have_icon(iid):
    return any(os.path.exists(os.path.join(ICONS, d, f"{iid}.png")) for d in ("wiki", "gra", "foto"))


def todo_items(args):
    db = json.load(open(DB, encoding="utf-8"))
    items = [it for it in db["items"] if it["cat"] not in HIDDEN_CATS and it["names"]
             and not it.get("obsolete") and not HIDDEN_DEBUG.search(it["debug"])]
    ids = [int(a) for a in args if a.isdigit()]
    if ids:
        return [it for it in items if it["id"] in ids]
    out = [it for it in items if not SKIP_DEBUG.search(it["debug"]) and not have_icon(it["id"])]
    return out[:10] if "probny" in args else out


def reprocess():
    """Tryb „przetworz”: ikony od nowa z surowych zrzutów (bez gry)."""
    tlo = os.path.join(RAW, "_tlo.png")
    if not os.path.exists(tlo):
        print("Brak surowych zrzutów (icons\\foto\\_surowe).")
        return 1
    w, h, bg = read_png(tlo)
    bg = rgba_to_bgra(bg)
    overlay = None
    nb = os.path.join(RAW, "_nakladka.bin")
    if os.path.exists(nb):
        d = open(nb, "rb").read()
        if struct.unpack("<II", d[:8]) == (w, h):
            overlay = d[8:]
    names = sorted(f for f in os.listdir(RAW) if f[0].isdigit() and f.endswith(".png"))
    ok = 0
    for n, f in enumerate(names, 1):
        ww, hh, shot = read_png(os.path.join(RAW, f))
        if (ww, hh) != (w, h):
            continue
        t = make_icon(rgba_to_bgra(shot), bg, overlay, w, h)
        if t:
            side, img = t
            write_png(os.path.join(OUT, f), side, side, img)
            ok += 1
        print(f"\r  {n}/{len(names)}", end="", flush=True)
    print(f"\nPrzetworzono {ok} ikon -> {OUT}")
    return 0


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 1
    if args[0] == "przetworz":
        return reprocess()
    dpi_aware()
    items = todo_items(args)
    print(f"Do sfotografowania: {len(items)} przedmiotów.")
    if not items:
        return 0
    os.makedirs(RAW, exist_ok=True)
    print("Łączę z grą…")
    st = Studio()
    if not st.slot_empty():
        raise SystemExit("Pierwszy slot plecaka nie jest pusty – opróżnij go i uruchom ponownie.")
    for s in range(10, 0, -1):
        print(f"\r  Przełącz się do gry i otwórz ekwipunek… {s} s ", end="", flush=True)
        time.sleep(1)
    print()
    st.calibrate()
    ok = bad = 0
    t0 = time.time()
    for n, it in enumerate(items, 1):
        name = it["names"].get("Pl_Pl") or it["names"].get("En_Us") or it["debug"]
        try:
            side, err = st.shoot(it["id"])
        except Exception as e:                       # jeden przedmiot nie zatrzymuje reszty
            side, err = None, str(e)
        if err:
            bad += 1
            print(f"  [{n}/{len(items)}] {name}: POMINIĘTO ({err})")
        else:
            ok += 1
            print(f"  [{n}/{len(items)}] {name}: {side}px")
    print(f"Gotowe w {time.time() - t0:.0f} s: zrobiono {ok}, pominięto {bad}. Ikony: {OUT}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nPrzerwano.")
