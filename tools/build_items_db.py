# -*- coding: utf-8 -*-
"""
Odbudowa bazy przedmiotów (np. po aktualizacji gry) – wersja 2 (19.10.2026):
nazwy + DANE DO KART (opis, statystyki, poziom, atuty, pancerz, obrażenia).

Kroki (w folderze D:\\TooManyItems_ED\\tools, w wierszu poleceń cmd – NIE PowerShell):
  1) kfc-parser.exe unpack -g "E:\\Steam\\steamapps\\common\\Enshrouded" -s -f "tkeen::ItemInfo" > ..\\unpacked\\items_all.jsonl
  2) kfc-parser.exe unpack -g "E:\\Steam\\steamapps\\common\\Enshrouded" -o ..\\unpacked -f "tkeen::LocaTagCollectionResource"
  3) kfc-parser.exe unpack -g "E:\\Steam\\steamapps\\common\\Enshrouded" -s -f "tkeen::Perk" > ..\\unpacked\\perks_all.jsonl
  4) python build_items_db.py "E:\\Steam\\steamapps\\common\\Enshrouded"
(kfc-parser i ten skrypt TYLKO CZYTAJĄ pliki gry.)

Wynik:
  ..\\items_db.json     – przedmioty (jak dawniej: id, cat, rarity, stack, debug, names, pide,
                          obsolete) + nowe pola kart (niżej) + słownik "perks".
  ..\\items_texts.json  – teksty kart w 15 językach: {"Pl_Pl": {"<locaId>": "tekst", …}, …}
  ..\\items_db_old.json – kopia poprzedniej bazy.
  ..\\unpacked\\loca_Pl_Pl.json, loca_En_Us.json – pełne tabele tłumaczeń (do analizy).

Nowe pola przedmiotu (wszystkie opcjonalne – brak pola = brak danych):
  desc, lore, caption, hint : locaId tekstu (klucz w items_texts.json, jako liczba)
  lvl     : [min, max] poziom przedmiotu (pomijane, gdy 0/0)
  stats   : [[locaId etykiety, format, wartość, ze_znakiem(0/1), skalowana(0/1)], …]
            format: Normal | Percentage | Duration (ms) | DurationMilliseconds | Float
  buffs   : jak stats (uiBuffValues)
  perks   : [guid atutu, …] – szczegóły w db["perks"][guid]
  armor   : {rodzaj: udział} pancerz (niezerowe), np. {"physical": 0.06, "magical": 0.08}
  dmg     : {"dist": {rodzaj: udział}, "speed": x, "mod": x} obrażenia broni
  block   : jakość bloku (tarcze)
  slot    : equipment.slot (Armour_Head, MeleeWeapon, Backpack…)
  cls     : Mage | Ranger | Warrior (klasa przedmiotu)
  fuel, comfort : czas palenia (burnTime.value) / komfort
  rbase   : rzadkość zapisana w pliku gry, gdy gra ją LOSUJE (generateRarity) – "rarity" jest wtedy poprawione:
  rgen    : [dozwolone rzadkości] – broń/wyposażenie z egzemplarzem: okno daje wybór, a TMI3 przekazuje go grze
            (pole rzadkości w zdarzeniu transakcji, event+0x14); "rarity" = domyślny wybór (rbase, gdy dozwolona,
            inaczej najwyższa dozwolona). Bez wyboru gra daje NAJNIŻSZĄ dozwoloną (kod gry +40AE43) – dla reszty
            przedmiotów z generateRarity "rarity" = właśnie ta najniższa (tak jak widać w grze).
db["perks"][guid] = {"debug", "name", "desc" (locaId), "stats": [...]}.

Format (ustalony 18.10.2026, build 25988036):
- items_all.jsonl: jedna linia = keen::ItemInfo (itemId.value, debugName, category, rarity,
  maxStackSize, name/description = GUID tagu tłumaczenia; uiValues.locaId.value = już id tagu).
- LocaTagCollectionResource: dla każdego języka ContentHash (size, hash0..2) danych tłumaczeń.
- enshrouded.kfc (KFC4): nagłówek z KFCLocation (u32 offset względny do pola, u32 count);
  content_keys = ContentHash[16 B], content_values = {u32 offset, u16 flags, u16 container, 8 B}.
  Plik danych = enshrouded_{container:03}.dat.
- Dane tłumaczeń: u32 relOffset(=8), u32 count; wpisy po 24 B:
  u32 id, u32 relOffsetTekstu (od pola +4), u32 długość (UTF-8), 12 B zer.
- id tagu = FNV-1a 32 z 16 bajtów GUID-a w kolejności Windows (uuid.bytes_le).
"""

import glob
import json
import os
import re
import shutil
import struct
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
UNPACKED = os.path.join(ROOT, "unpacked")
OUT = os.path.join(ROOT, "items_db.json")
OUT_TEXTS = os.path.join(ROOT, "items_texts.json")
OUT_OLD = os.path.join(ROOT, "items_db_old.json")
DUMP_LANGS = ("Pl_Pl", "En_Us")

HEADER_FIELDS = ["version", "containers", "unused0", "unused1", "res_loc", "res_idx",
                 "c_buckets", "c_keys", "c_values", "r_buckets", "r_keys", "r_values",
                 "rb_buckets", "rb_keys", "rb_values", "r_chunks"]
TAG_RX = re.compile(r"<[^>]+>")
OBSOLETE_RX = re.compile(r"<b>\s*(outdated|deprecated|obsolete)\s*</b>", re.I)


RARITIES = ["Common", "Uncommon", "Rare", "Epic", "Legendary"]


def rarity_fields(it, rec):
    """Rzadkość taka, jak nada ją gra (patrz opis pól rbase/rgen na górze)."""
    if not it.get("generateRarity"):
        return
    off = set(it.get("disableRarityGeneration") or [])
    allowed = [r for r in RARITIES if r not in off]
    if not allowed:
        return
    base = rec["rarity"]
    rec["rbase"] = base
    if rec.get("pide") and rec["cat"] in ("Equipment", "Weapons") and len(allowed) > 1:
        rec["rgen"] = allowed
        rec["rarity"] = base if base in allowed else allowed[-1]
    else:
        rec["rarity"] = allowed[0]


def fnv1a32(data):
    h = 0x811C9DC5
    for b in data:
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return h


def tag_id(guid):
    return fnv1a32(uuid.UUID(guid).bytes_le) if guid else None


def read_jsonl(path):
    raw = open(path, "rb").read()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = raw.decode("utf-16")
    else:
        text = raw.decode("utf-8-sig")
    out = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{"):
            out.append(json.loads(line))
    return out


def read_kfc_content_index(kfc_path):
    k = open(kfc_path, "rb").read()
    if k[:4] != b"KFC4":
        print(f"UWAGA: nagłówek {k[:4]!r} – oczekiwano KFC4, format mógł się zmienić.")
    loc = {}
    for i, name in enumerate(HEADER_FIELDS):
        off = 16 + i * 8
        rel, cnt = struct.unpack_from("<II", k, off)
        loc[name] = (off + rel, cnt)
    ka, kc = loc["c_keys"]
    va, _ = loc["c_values"]
    index = {}
    for i in range(kc):
        key = struct.unpack_from("<IIII", k, ka + i * 16)
        off, _flags, cont = struct.unpack_from("<IHH", k, va + i * 16)
        index[key] = (cont, off)
    return index


def parse_loca(blob):
    off, cnt = struct.unpack_from("<II", blob, 0)
    tags = {}
    for i in range(cnt):
        e = off + i * 24
        tid, trel, tlen = struct.unpack_from("<III", blob, e)
        p = e + 4 + trel
        tags[tid] = blob[p:p + tlen].decode("utf-8", "replace")
    return tags


def ui_values(lst):
    out = []
    for v in lst or []:
        lid = (v.get("locaId") or {}).get("value")
        if not lid:
            continue
        val = v.get("value")
        if isinstance(val, float) and val.is_integer():
            val = int(val)
        out.append([lid, v.get("valueFormat"), val,
                    1 if v.get("isSigned") else 0, 1 if v.get("isScaled") else 0])
    return out


def nonzero(dist, digits=4):
    out = {}
    for k, v in (dist or {}).items():
        if isinstance(v, (int, float)) and v:
            out[k] = round(v, digits) if isinstance(v, float) else v
    return out


def card_fields(it, rec, used):
    """Dopisuje do rec pola karty; used = zbiór potrzebnych locaId."""
    for key, field in (("desc", "description"), ("lore", "lore"),
                       ("caption", "caption"), ("hint", "acquisitionHint")):
        t = tag_id(it.get(field))
        if t:
            rec[key] = t
            used.add(t)
    lr = it.get("itemLevelRange") or {}
    lo, hi = lr.get("minLevel", 0), lr.get("maxLevel", 0)
    if lo or hi:
        rec["lvl"] = [lo, hi]
    for key, field in (("stats", "uiValues"), ("buffs", "uiBuffValues")):
        s = ui_values(it.get(field))
        if s:
            rec[key] = s
            used.update(x[0] for x in s)
    perks = [p for p in (it.get("perkReferences") or []) if p]
    if perks:
        rec["perks"] = perks
    a = it.get("armorSetup") or {}
    if a.get("isSet"):
        d = nonzero(a.get("distribution"))
        if d:
            rec["armor"] = d
    d = it.get("damageSetup") or {}
    if d.get("isSet"):
        rec["dmg"] = {"dist": nonzero(d.get("distribution")),
                      "speed": round(d.get("speedMod", 1.0), 4),
                      "mod": round(d.get("dmgMod", 1.0), 4)}
    b = it.get("blockSetup") or {}
    if b.get("isSet"):
        rec["block"] = round(b.get("quality", 0.0), 4)
    eq = it.get("equipment") or {}
    if eq.get("slot") and eq["slot"] != "Invalid":
        rec["slot"] = eq["slot"]
    if it.get("itemClassAlignment") not in (None, "None"):
        rec["cls"] = it["itemClassAlignment"]
    f = it.get("fuelSetup") or {}
    if f.get("isSet"):
        rec["fuel"] = (f.get("burnTime") or {}).get("value")
    c = it.get("comfortSetup") or {}
    if c.get("isSet"):
        rec["comfort"] = c.get("comfortAmount")


def main():
    game = sys.argv[1] if len(sys.argv) > 1 else r"E:\Steam\steamapps\common\Enshrouded"
    items_path = os.path.join(UNPACKED, "items_all.jsonl")
    perks_path = os.path.join(UNPACKED, "perks_all.jsonl")
    loca_res = glob.glob(os.path.join(UNPACKED, "LocaTagCollectionResource", "*.json"))
    if not os.path.exists(items_path) or not loca_res:
        print("Brak plików z kfc-parser – zobacz instrukcję na górze skryptu.")
        return 1

    items = read_jsonl(items_path)
    print(f"Przedmiotów: {len(items)}")

    perks_raw = []
    if os.path.exists(perks_path):
        perks_raw = [p for p in read_jsonl(perks_path) if p.get("$type") == "keen::Perk"]
        print(f"Atutów: {len(perks_raw)}")
    else:
        print("UWAGA: brak unpacked\\perks_all.jsonl (krok 3) – baza będzie bez atutów.")

    index = read_kfc_content_index(os.path.join(game, "enshrouded.kfc"))
    lr = json.load(open(loca_res[0], encoding="utf-8"))
    langs = {}
    for entry in lr["languages"]:
        h = entry["data"]["hash"]
        key = (h["size"], h["hash0"], h["hash1"], h["hash2"])
        if key not in index:
            print(f"  {entry['language']}: nie znaleziono w indeksie")
            continue
        cont, off = index[key]
        with open(os.path.join(game, f"enshrouded_{cont:03d}.dat"), "rb") as f:
            f.seek(off)
            langs[entry["language"]] = parse_loca(f.read(h["size"]))
        print(f"  {entry['language']}: {len(langs[entry['language']])} tekstów")

    # pełne tabele PL/EN do analizy (Claude czyta je przy dalszej pracy)
    for lang in DUMP_LANGS:
        if lang in langs:
            p = os.path.join(UNPACKED, f"loca_{lang}.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump({str(k): v for k, v in langs[lang].items()}, f,
                          ensure_ascii=False, separators=(",", ":"))

    used = set()

    # atuty
    perks = {}
    for p in perks_raw:
        guid = p.get("$guid") or p.get("objectId")
        rec = {"debug": p.get("debugName") or ""}
        for key, field in (("name", "name"), ("desc", "description")):
            t = tag_id(p.get(field))
            if t:
                rec[key] = t
                used.add(t)
        s = ui_values(p.get("uiValues"))
        if s:
            rec["stats"] = s
            used.update(x[0] for x in s)
        perks[guid] = rec
        if p.get("objectId") and p.get("objectId") != guid:
            perks[p["objectId"]] = rec

    en = langs.get("En_Us", {})
    out = []
    missing_perks = set()
    for it in items:
        t = tag_id(it.get("name"))
        names = {}
        if t is not None:
            for lang, tags in langs.items():
                v = tags.get(t)
                if v:
                    names[lang] = TAG_RX.sub("", v).strip()
        rec = {"id": it["itemId"]["value"], "cat": it["category"], "rarity": it["rarity"],
               "stack": it["maxStackSize"], "debug": it["debugName"], "names": names}
        if "HasPIDE" in (it.get("flags") or []):
            rec["pide"] = True      # potrzebuje egzemplarza (plecak, wyposażenie…)
        rarity_fields(it, rec)
        desc = en.get(tag_id(it.get("description"))) or ""
        if OBSOLETE_RX.search(desc):
            rec["obsolete"] = True
        card_fields(it, rec, used)
        for g in rec.get("perks", []):
            if g not in perks:
                missing_perks.add(g)
        out.append(rec)
    out.sort(key=lambda x: (x["cat"], x["names"].get("En_Us") or x["debug"]))

    texts = {}
    for lang, tags in langs.items():
        texts[lang] = {str(i): tags[i] for i in sorted(used) if i in tags}

    old_meta = {}
    if os.path.exists(OUT):
        try:
            old_meta = json.load(open(OUT, encoding="utf-8")).get("meta", {})
        except Exception:
            pass
        shutil.copyfile(OUT, OUT_OLD)
    meta = {"source": "kfc-parser ItemInfo + Perk + LocaTagCollectionResourceData",
            "languages": sorted(langs), "card_version": 1}
    if old_meta.get("game_build"):
        meta["game_build"] = old_meta["game_build"]
    perks_unique = {}
    for g, r in perks.items():
        perks_unique.setdefault(g, r)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "items": out, "perks": perks_unique}, f,
                  ensure_ascii=False, separators=(",", ":"))
    with open(OUT_TEXTS, "w", encoding="utf-8") as f:
        json.dump({"meta": {"languages": sorted(langs)}, "texts": texts}, f,
                  ensure_ascii=False, separators=(",", ":"))

    pl = texts.get("Pl_Pl", {})
    def has_pl(i):
        return str(i) in pl
    n_desc = sum(1 for x in out if x.get("desc") and has_pl(x["desc"]))
    n_stats = sum(1 for x in out if x.get("stats"))
    n_lbl = sum(1 for x in out for s in x.get("stats", []) if has_pl(s[0]))
    n_lbl_all = sum(len(x.get("stats", [])) for x in out)
    n_perk = sum(1 for x in out if x.get("perks"))
    print(f"Zapisano {OUT}: {len(out)} przedmiotów, "
          f"{sum(1 for x in out if x['names'])} z nazwą, "
          f"{sum(1 for x in out if x.get('obsolete'))} przestarzałych.")
    print(f"  karty: opis PL {n_desc}, ze statystykami {n_stats} "
          f"(etykiety PL {n_lbl}/{n_lbl_all}), z poziomem "
          f"{sum(1 for x in out if x.get('lvl'))}, z atutami {n_perk}, "
          f"atutów w słowniku {len(perks_unique)}, brakujących atutów {len(missing_perks)}")
    print(f"Zapisano {OUT_TEXTS}: {len(used)} tekstów × {len(texts)} języków.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
