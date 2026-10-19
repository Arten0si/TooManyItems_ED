# -*- coding: utf-8 -*-
"""
TooManyItems_ED – sonda transakcji ekwipunku (narzędzie badawcze, jednorazowe).

Co robi:
  Na czas pomiaru podpina się pod funkcję gry enshrouded.exe+411DF0, którą gra
  woła na początku KAŻDEJ transakcji ekwipunku (podniesienie, przesunięcie,
  rzemiosło…). Zapisuje: kto ją wołał, z którego wątku, i kopię „referencji”
  (0xF0 bajtów: świat + typy komponentów). Nic nie zmienia w ekwipunku.
  Na końcu przywraca oryginalne bajty gry.

Uruchomienie (gra włączona, świat wczytany):
  cd D:\\TooManyItems_ED\\tools
  python tx_probe.py
Wynik: tools\\tx_probe.txt i tools\\tx_probe.json
"""

import json
import os
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import tmi_core as core                          # noqa: E402

SITE_RVA = 0x411DF0
SITE_PATTERN = "C6 81 A8 71 00 00 00 48 8B 42 08 48 89 01 48 8B 42 10 48 89 41 08"
ORIGINAL = bytes.fromhex("C681A871000000")
MAGIC = b"TMIprobe"
CODE = bytes.fromhex(
    "c681a871000000505156579cb801000000f00fc105f7feffff89c125ff000000c1e008488d3dd60e"
    "00004801c7488b442428488907658b042548000000894708894f0c4883c7104889d6b91e000000fc"
    "f348a59d5f5e5958ff25aafeffff")
OFF_RET, OFF_COUNT, OFF_CODE, OFF_RING = 0x8, 0x10, 0x100, 0x1000
RING, ENTRY, REFS = 256, 0x100, 0xF0
BLOCK = 0x12000


class Probe:
    def __init__(self, game):
        self.g = game
        self.site = None
        self.blk = None

    def install(self):
        g = self.g
        site = core.find_code(g, SITE_PATTERN, SITE_RVA)
        if site is None:
            cur = g.read(g.base + SITE_RVA, 7)
            if cur and cur[0] == 0xE9:                    # sonda z poprzedniego razu
                dest = g.base + SITE_RVA + 5 + struct.unpack("<i", cur[1:5])[0]
                if g.read(dest - OFF_CODE, 8) == MAGIC:
                    self.site, self.blk = g.base + SITE_RVA, dest - OFF_CODE
                    return "Sonda była już podpięta – używam jej."
            raise RuntimeError("Nie znaleziono funkcji +411DF0 – inna wersja gry?")
        blk = self._alloc_near(site)
        if not blk:
            raise RuntimeError("Nie udało się przydzielić pamięci.")
        data = bytearray(OFF_RING)
        data[0:8] = MAGIC
        data[OFF_RET:OFF_RET + 8] = (site + 7).to_bytes(8, "little")
        data[OFF_CODE:OFF_CODE + len(CODE)] = CODE
        if not g.write(blk, bytes(data)):
            raise RuntimeError("Nie udało się zapisać sondy.")
        self._patch(site, b"\xE9" + struct.pack("<i", blk + OFF_CODE - (site + 5)) + b"\x90\x90")
        self.site, self.blk = site, blk
        return "Sonda podpięta."

    def _alloc_near(self, site):
        g = self.g
        start = (site - 0x10000) & ~0xFFFF
        for step in range(0, 0x7FF0):
            for a in (start - step * 0x10000, start + step * 0x10000 + 0x40000):
                if a <= 0x10000:
                    continue
                p = core.k32.VirtualAllocEx(g.h, core.ctypes.c_void_p(a), BLOCK,
                                            core.MEM_COMMIT | core.MEM_RESERVE,
                                            core.PAGE_EXECUTE_READWRITE)
                if p and abs(p - site) < 0x7FFF0000:
                    return p
        return None

    def _patch(self, site, data):
        g = self.g
        old = core.wt.DWORD()
        core.k32.VirtualProtectEx(g.h, core.ctypes.c_void_p(site), len(data),
                                  core.PAGE_EXECUTE_READWRITE, core.ctypes.byref(old))
        ok = g.write(site, data)
        core.k32.VirtualProtectEx(g.h, core.ctypes.c_void_p(site), len(data), old.value,
                                  core.ctypes.byref(core.wt.DWORD()))
        core.k32.FlushInstructionCache(g.h, core.ctypes.c_void_p(site), len(data))
        if not ok:
            raise RuntimeError("Nie udało się zmienić kodu gry.")

    def remove(self):
        if self.site:
            self._patch(self.site, ORIGINAL)

    def count(self):
        return self.g.u32(self.blk + OFF_COUNT) or 0

    def ring(self):
        raw = self.g.read(self.blk + OFF_RING, RING * ENTRY) or b""
        out = []
        for i in range(len(raw) // ENTRY):
            e = raw[i * ENTRY:(i + 1) * ENTRY]
            ret, tid, seq = struct.unpack_from("<QII", e, 0)
            if ret:
                out.append((seq, ret, tid, e[0x10:0x10 + REFS]))
        return out


def tmi_contexts(game):
    """Konteksty światów z hooka TooManyItems (jeśli aplikacja była uruchomiona)."""
    site = game.base + core.HOOK_RVA
    cur = game.read(site, 5)
    if not cur or cur[0] != 0xE9:
        return {}
    stub = site + 5 + struct.unpack("<i", cur[1:5])[0] - core.OFF_CODE
    if game.read(stub, 8) != core.STUB_MAGIC:
        return {}
    h = core.Hook(game)
    h.site, h.stub = site, stub
    ctxs = {}
    for row, ctx, handle in h.rows():
        ctxs.setdefault(ctx, []).append(handle)
    return ctxs


def measure(probe, game, label, seconds, stats, seen):
    c0 = probe.count()
    t0 = time.time()
    while time.time() - t0 < seconds:
        for seq, ret, tid, refs in probe.ring():
            if seq in seen:
                continue
            seen.add(seq)
            rva = ret - game.base
            s = stats.setdefault(rva, {"phases": {}, "threads": set(), "worlds": {}})
            s["phases"][label] = s["phases"].get(label, 0) + 1
            s["threads"].add(tid)
            world = struct.unpack_from("<Q", refs, 8)[0]
            s["worlds"].setdefault(world, refs.hex())
        time.sleep(0.03)
        left = int(seconds - (time.time() - t0))
        print(f"\r  {label}: zostało {left:2d} s, wywołań: {probe.count() - c0}   ", end="")
    total = probe.count() - c0
    print(f"\r  {label}: gotowe, wywołań w sumie: {total}                 ")
    return total


def main():
    print("=== Sonda transakcji ekwipunku (TooManyItems_ED) ===")
    try:
        game = core.Game()
        probe = Probe(game)
        print(probe.install())
    except RuntimeError as e:
        print("BŁĄD:", e)
        input("Enter, aby zakończyć...")
        return
    stats, seen, totals = {}, set(), {}
    phases = [
        ("1_spokoj", 10, "Faza 1: NIC nie rób w grze (stój w miejscu, ekwipunek zamknięty)."),
        ("2_przesun", 15, "Faza 2: otwórz ekwipunek i PRZESUŃ 2-3 razy dowolny przedmiot na inny slot."),
        ("3_podnies", 20, "Faza 3: PODNIEŚ coś z ziemi albo zetnij/zbierz roślinę (kamień, patyk…)."),
    ]
    try:
        for label, secs, text in phases:
            print("\n" + text)
            input("  Wciśnij Enter, kiedy będziesz gotowy (potem masz %d s)... " % secs)
            totals[label] = measure(probe, game, label, secs, stats, seen)
    except KeyboardInterrupt:
        print("\nPrzerwano.")
    finally:
        try:
            probe.remove()
            print("\nSonda odpięta – kod gry przywrócony.")
        except RuntimeError as e:
            print("\nUWAGA: nie udało się odpiąć sondy:", e, "– najlepiej zrestartuj grę.")

    ctxs = tmi_contexts(game)
    lines = [f"Sonda +411DF0  moduł {game.base:#x}  PID {game.pid}",
             "Wywołań w fazach: " + ", ".join(f"{k}={v}" for k, v in totals.items()),
             "Konteksty z hooka TMI: " + (", ".join(f"{c:#x}({len(h)} rzędów)" for c, h in ctxs.items())
                                         or "brak (aplikacja nie była uruchomiona)"),
             ""]
    for rva, s in sorted(stats.items(), key=lambda kv: -sum(kv[1]["phases"].values())):
        ph = " ".join(f"{k}={v}" for k, v in sorted(s["phases"].items()))
        lines.append(f"wołający +{rva:X}  {ph}  wątki={sorted(s['threads'])}  "
                     f"światy={[hex(w) for w in s['worlds']]}")
    text = "\n".join(lines)
    print("\n" + text)
    out = {"base": game.base, "pid": game.pid, "totals": totals,
           "tmi_contexts": {hex(c): [hex(x) for x in h] for c, h in ctxs.items()},
           "callers": {f"{rva:X}": {"phases": s["phases"], "threads": sorted(s["threads"]),
                                    "refs": {hex(w): r for w, r in s["worlds"].items()}}
                       for rva, s in stats.items()}}
    for path, data in (("tx_probe.txt", text), ("tx_probe.json", json.dumps(out, indent=1))):
        try:
            with open(os.path.join(HERE, path), "w", encoding="utf-8") as f:
                f.write(data)
        except OSError as e:
            print("Nie udało się zapisać", path, e)
    print("\nZapisano tools\\tx_probe.txt i tools\\tx_probe.json")
    game.close()
    input("Enter, aby zakończyć...")


if __name__ == "__main__":
    main()
