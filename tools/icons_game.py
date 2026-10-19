# -*- coding: utf-8 -*-
"""
Ikony przedmiotów, które gra ma jako gotowe obrazki 2D (pole iconImage) – TooManyItems_ED, 19.10.2026.

Wymaga (w ..\\unpacked): items_all.jsonl i textures_all.jsonl (kfc-parser, tylko odczyt gry):
  kfc-parser.exe unpack -g "E:\\Steam\\steamapps\\common\\Enshrouded" -s -f "tkeen::UiTextureResource" > ..\\unpacked\\textures_all.jsonl
Użycie (cmd w D:\\TooManyItems_ED\\tools):
  python icons_game.py "E:\\Steam\\steamapps\\common\\Enshrouded"
Wynik: ..\\icons\\gra\\<ID>.png (pełna rozdzielczość, z przezroczystością). Pliki gry tylko CZYTA.

Format (build 25988036): keen::UiTextureResource {size{x,y}, format "R8G8B8A8_unorm", levelCount 1,
data = ContentHash} – dane = surowe piksele RGBA, x*y*4 bajtów, w enshrouded_XXX.dat (indeks z enshrouded.kfc).
"""

import os
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_items_db import ROOT, UNPACKED, read_jsonl, read_kfc_content_index  # noqa: E402

OUT_DIR = os.path.join(ROOT, "icons", "gra")


def write_png(path, w, h, rgba):
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    stride = w * 4
    raw = b"".join(b"\x00" + rgba[y * stride:(y + 1) * stride] for y in range(h))
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 9))
           + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)


def main():
    game = sys.argv[1] if len(sys.argv) > 1 else r"E:\Steam\steamapps\common\Enshrouded"
    tex_path = os.path.join(UNPACKED, "textures_all.jsonl")
    if not os.path.exists(tex_path):
        print("Brak unpacked\\textures_all.jsonl – zobacz instrukcję na górze skryptu.")
        return 1
    items = read_jsonl(os.path.join(UNPACKED, "items_all.jsonl"))
    tex = {t["$guid"]: t for t in read_jsonl(tex_path) if t.get("$type") == "keen::UiTextureResource"}
    index = read_kfc_content_index(os.path.join(game, "enshrouded.kfc"))
    os.makedirs(OUT_DIR, exist_ok=True)

    cache = {}
    ok = skip = 0
    for it in items:
        g = it.get("iconImage")
        if not g:
            continue
        t = tex.get(g)
        if not t:
            print(f"  {it['debugName']}: brak tekstury {g}")
            skip += 1
            continue
        fmt = t.get("format", "")
        w, h = t["size"]["x"], t["size"]["y"]
        if fmt.lower() not in ("r8g8b8a8_unorm", "r8g8b8a8_srgb"):
            print(f"  {it['debugName']}: format {fmt} – pomijam (nieobsługiwany)")
            skip += 1
            continue
        hh = t["data"]["hash"]
        key = (hh["size"], hh["hash0"], hh["hash1"], hh["hash2"])
        if key not in index:
            print(f"  {it['debugName']}: brak danych w indeksie")
            skip += 1
            continue
        if key not in cache:
            cont, off = index[key]
            with open(os.path.join(game, f"enshrouded_{cont:03d}.dat"), "rb") as f:
                f.seek(off)
                cache[key] = f.read(hh["size"])
        data = cache[key]
        if len(data) < w * h * 4:
            print(f"  {it['debugName']}: za mało danych ({len(data)} < {w * h * 4})")
            skip += 1
            continue
        write_png(os.path.join(OUT_DIR, f"{it['itemId']['value']}.png"), w, h, data[:w * h * 4])
        ok += 1
    print(f"Zapisano {ok} ikon do {OUT_DIR} (pominięto {skip}, różnych obrazków {len(cache)}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
