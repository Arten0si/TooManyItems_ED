# -*- coding: utf-8 -*-
"""
Ikony przedmiotów z oficjalnej wiki Enshrouded (enshrouded.wiki.gg) – TooManyItems_ED, 19.10.2026.

Wiki nazywa ikonę po ANGIELSKIEJ nazwie przedmiotu, np. "Circlet_Of_Lightning.png".
Skrypt dopasowuje nazwy z items_db.json (En_Us) do listy plików wiki (bez względu na wielkość liter).

Użycie (cmd w folderze D:\\TooManyItems_ED\\tools):
  python icons_wiki.py sprawdz   – liczy pokrycie, zapisuje icons_wiki_report.txt. Nic nie ściąga.
                                   Listę plików wiki pobiera raz (tools\\wiki_images.json);
                                   „sprawdz odswiez” pobiera ją od nowa.
  python icons_wiki.py pobierz   – ściąga dopasowane ikony (128 px) do ..\\icons\\wiki\\<ID>.png
                                   (pomija już pobrane; można przerwać Ctrl+C i wznowić).

Grzecznie dla serwera: 1 zapytanie naraz, przerwa między zapytaniami. Tylko biblioteka standardowa.
"""

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DB = os.path.join(ROOT, "items_db.json")
CACHE = os.path.join(HERE, "wiki_images.json")
REPORT = os.path.join(HERE, "icons_wiki_report.txt")
MAP_OUT = os.path.join(ROOT, "icons", "wiki_map.json")
OUT_DIR = os.path.join(ROOT, "icons", "wiki")
API = "https://enshrouded.wiki.gg/api.php"
UA = "TooManyItems_ED/1.0 (private non-commercial item browser for Enshrouded; python-urllib)"
SIZE = 128
PAUSE = 0.6

HIDDEN_CATS = {"Blueprints", "Customization"}
HIDDEN_DEBUG = re.compile(r"deprecated|depricated|^zz?_|(^|_)test(_|$)|debug|^ability_", re.I)


def norm(s):
    s = s.replace("_", " ").replace("\u2019", "'").replace("\u2018", "'")
    s = re.sub(r"\.(png|webp|jpg|gif)$", "", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def get(params):
    params = dict(params, format="json", formatversion="2")
    url = API + "?" + urllib.parse.urlencode(params)
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode("utf-8"))
            time.sleep(PAUSE)
            return data
        except Exception as e:
            print(f"  błąd ({e}), ponawiam za {5 * (attempt + 1)} s…")
            time.sleep(5 * (attempt + 1))
    raise SystemExit("Wiki nie odpowiada – spróbuj później.")


def list_wiki_images(refresh=False):
    if os.path.exists(CACHE) and not refresh:
        return json.load(open(CACHE, encoding="utf-8"))
    names, cont = [], {}
    while True:
        d = get(dict({"action": "query", "list": "allimages", "ailimit": "500"}, **cont))
        names += [x["name"] for x in d.get("query", {}).get("allimages", [])]
        print(f"  lista plików wiki: {len(names)}")
        if "continue" not in d:
            break
        cont = {"aicontinue": d["continue"]["aicontinue"]}
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(names, f, ensure_ascii=False)
    return names


def load_items():
    db = json.load(open(DB, encoding="utf-8"))
    return [it for it in db["items"]
            if it["cat"] not in HIDDEN_CATS and it["names"] and not it.get("obsolete")
            and not HIDDEN_DEBUG.search(it["debug"])]


ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]
ROMAN_RX = re.compile(r"^(.*?) (i|ii|iii|iv|v|vi|vii|viii|ix|x)$", re.I)
# pisownia gry -> pisownia wiki (porównanie bez spacji/znaków, małymi literami)
SPELLING = [("waggon", "wagon"), ("baordwalk", "boardwalk")]
# nazwy, które wiki ma pod inną nazwą (sprawdzone ręcznie 19.10)
EXPLICIT = {
    "capybara bait": "capybara food bait",
    "invisible barrier ward": "invisible barrier",
    "ethereal ward": "spectral ward",
    "shroud meteor scroll": "shroud meteor shower",
    "fired bricks": "fired brick",
}


def compact(s):
    """Klucz porównania: tylko litery i cyfry ("Throne Room" == "Throneroom", "Mei-Yin" == "MeiYin")."""
    s = norm(s)
    for a, b in SPELLING:
        s = s.replace(a, b)
    return re.sub(r"[^0-9a-z+]+", "", s)


def candidates(en, debug):
    """Kolejne próby nazwy na wiki: (nazwa, dokładna?)."""
    base = norm(en).replace('"', "")
    out = [(base, True)]
    if base in EXPLICIT:
        out.append((EXPLICIT[base], True))
    if "flower_pot" in debug.lower():
        out += [(base + " pot", True), (base + " plant pot", True)]
    if base.startswith("fake "):
        out.append(("secret " + base[5:], True))
    m = ROMAN_RX.match(base)
    if m:
        stem, num = m.group(1), m.group(2)
        if num.lower() == "i":
            out.append((stem, True))                       # "Fire Bolt I" -> "Fire Bolt"
        out.append((stem, False))
        out += [(stem + " " + r.lower(), False) for r in ROMAN if r.lower() != num.lower()]  # inny poziom
    else:
        out += [(base + " i", False)] + [(base + " " + r.lower(), False) for r in ROMAN[1:]]
    return out


def match(items, files, with_quality=False):
    by_norm, by_key = {}, {}
    variants = {}      # "archaic essence" -> ["Archaic_Essence_(5).png", …]
    for f in sorted(files):
        if f.lower().endswith((".png", ".webp", ".jpg")):
            by_norm.setdefault(norm(f), f)
            by_key.setdefault(compact(f), f)
            v = re.match(r"^(.*?) \(.*\)$", norm(f))
            if v:
                variants.setdefault(compact(v.group(1)), []).append(f)
    m, quality = {}, {}
    for it in items:
        en = it["names"].get("En_Us")
        if not en:
            continue
        hit = None
        for cand, exact in candidates(en, it["debug"]):
            f = by_norm.get(cand) or by_key.get(compact(cand))
            if f:
                hit = (f, exact)
                break
        if not hit:                                       # "Statue Piece" -> "Statue Piece (Arm)"
            base = ROMAN_RX.match(norm(en).replace('"', ""))
            key = compact(base.group(1) if base else en)
            if variants.get(key):
                hit = (sorted(variants[key])[0], False)
        if hit:
            m[it["id"]] = hit[0]
            quality[it["id"]] = hit[1]
    return (m, quality) if with_quality else m


def sprawdz(refresh=False):
    items = load_items()
    files = list_wiki_images(refresh=refresh)
    m, q = match(items, files, with_quality=True)
    n_sim = sum(1 for v in q.values() if not v)
    lines = [f"Plików na wiki: {len(files)}", f"Przedmiotów na liście: {len(items)}",
             f"Dopasowanych ikon: {len(m)} ({100 * len(m) // max(1, len(items))}%), "
             f"w tym {n_sim} podobnych (inny poziom/wariant tego samego przedmiotu)", ""]
    cats = {}
    for it in items:
        c = cats.setdefault(it["cat"], [0, 0])
        c[0] += 1
        c[1] += it["id"] in m
    lines.append("Kategoria: dopasowane / wszystkie")
    for c, (n, k) in sorted(cats.items(), key=lambda x: -x[1][0]):
        lines.append(f"  {c:14s} {k:5d} / {n}")
    lines += ["", "PODOBNE (nazwa angielska -> plik wiki):"]
    for it in sorted(items, key=lambda x: (x["cat"], x["names"].get("En_Us", ""))):
        if it["id"] in m and not q[it["id"]]:
            lines.append(f"  [{it['cat']}] {it['names'].get('En_Us', '?')} -> {m[it['id']]}")
    lines += ["", "NIEDOPASOWANE (nazwa angielska | debugName):"]
    for it in sorted(items, key=lambda x: (x["cat"], x["names"].get("En_Us", ""))):
        if it["id"] not in m:
            lines.append(f"  [{it['cat']}] {it['names'].get('En_Us', '?')} | {it['debug']}")
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n".join(lines[:4 + len(cats) + 1]))
    print(f"\nPełny raport: {REPORT}")


def pobierz():
    items = load_items()
    m = match(items, list_wiki_images())
    os.makedirs(OUT_DIR, exist_ok=True)
    todo = [(i, f) for i, f in m.items() if not os.path.exists(os.path.join(OUT_DIR, f"{i}.png"))]
    print(f"Do pobrania: {len(todo)} (już jest: {len(m) - len(todo)})")
    # adresy miniatur 128 px – po 50 plików na zapytanie
    files = sorted({f for _, f in todo})
    thumbs = {}
    for k in range(0, len(files), 50):
        chunk = files[k:k + 50]
        d = get({"action": "query", "prop": "imageinfo", "iiprop": "url",
                 "iiurlwidth": str(SIZE), "titles": "|".join("File:" + f for f in chunk)})
        for p in d.get("query", {}).get("pages", []):
            ii = (p.get("imageinfo") or [{}])[0]
            u = ii.get("thumburl") or ii.get("url")
            if u:
                thumbs[norm(p["title"].split(":", 1)[1])] = u
        print(f"  adresy: {min(k + 50, len(files))}/{len(files)}")
    ok = bad = 0
    for n, (iid, f) in enumerate(todo, 1):
        u = thumbs.get(norm(f))
        if not u:
            bad += 1
            continue
        try:
            req = urllib.request.Request(u, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
            with open(os.path.join(OUT_DIR, f"{iid}.png"), "wb") as out:
                out.write(data)
            ok += 1
        except Exception as e:
            print(f"  {f}: {e}")
            bad += 1
        if n % 50 == 0:
            print(f"  pobrano {n}/{len(todo)}")
        time.sleep(PAUSE)
    with open(MAP_OUT, "w", encoding="utf-8") as f:
        json.dump({str(i): f for i, f in m.items()}, f, ensure_ascii=False)
    print(f"Gotowe: pobrano {ok}, nieudane {bad}. Ikony w {OUT_DIR}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "sprawdz":
        sprawdz(refresh="odswiez" in sys.argv[2:])
    elif cmd == "pobierz":
        pobierz()
    else:
        print(__doc__)
