import struct, types, time
EXE = '/mnt/user-data/uploads/Enshrouded/enshrouded.exe'
def load(path):
    src = open(path, encoding="utf-8").read().replace('if os.name != "nt":', "if False:").replace(
        'ctypes.WinDLL("kernel32", use_last_error=True)', '__import__("unittest.mock").mock.MagicMock()')
    m = types.ModuleType('tmi_core'); m.__file__ = path
    exec(compile(src, path, 'exec'), m.__dict__); return m
core = load('/home/claude/build/core/tmi_core.py')
data = open(EXE, 'rb').read()
pe = struct.unpack_from('<I', data, 0x3C)[0]; nsec = struct.unpack_from('<H', data, pe+6)[0]; osz = struct.unpack_from('<H', data, pe+20)[0]
def image(shift=0, patch=None):
    """Obraz pamięci; shift = przesunięcie całej .text (symulacja łatki)."""
    img = bytearray(0x1700000); img[:0x1000] = data[:0x1000]
    for i in range(nsec):
        o = pe + 24 + osz + i*40
        name = data[o:o+8].rstrip(b'\0'); vsz, va, rsz, raw = struct.unpack_from('<IIII', data, o+8)
        if name == b'.text':
            img[va+shift:va+shift+rsz] = data[raw:raw+rsz]
            if shift: struct.pack_into('<I', img, o+8, vsz+shift); struct.pack_into('<I', img, o+12, va)  # .text zaczyna się wcześniej
            if shift: img[va:va+shift] = b'\xCC'*shift
    if patch:
        for rva, b in patch: img[rva+shift:rva+shift+len(b)] = b
    return img
class G:
    def __init__(self, img): self.img = img; self.base = 0x140000000; self.size = len(img); self.pid = 1
    def read(self, a, n):
        o = a - self.base
        return bytes(self.img[o:o+n]) if 0 <= o and o+n <= len(self.img) else None
    def write(self, a, d): o = a - self.base; self.img[o:o+len(d)] = d; return True
    def exe_path(self): return EXE
def run(title, img, expect_shift):
    g = G(img); sc = core.CodeScanner(g); t = time.time(); res = {}
    for n in core.SIGNATURES:
        a = sc.resolve(n); res[n] = None if a is None else a - g.base
    ok = all(res[n] == core.EXPECTED_RVA[n] + expect_shift for n in res)
    print(f"{title}: {'OK' if ok else 'BŁĄD'}  ({time.time()-t:.1f}s, skan={sc.scanned})")
    if not ok: print('   ', {k: (hex(v) if v else v) for k, v in res.items()})
    return g, sc
assert core.STUB3_CODE[-13:-6] == bytes.fromhex('C681A871000000'), core.STUB3_CODE[-13:-6].hex()
print('wersja:', core.game_version(G(image())))
run('A) obecna wersja gry (szybki test)', image(), 0)
run('B) cały kod przesunięty o 0x2340 (typowa łatka)', image(0x2340), 0x2340)
# C) zmieniony rozmiar stosu w CREATE (prolog nie pasuje) – kotwice muszą wystarczyć
run('C) + zmieniony prolog „nowy przedmiot w slocie”', image(0x2340, [(0x40B760+18, b'\x38')]), 0x2340)
# D) zmienione pole [rsp+0x1F0] -> 0x1F8: HOOK ma NIE zostać znaleziony
g = G(image(0x2340, [(0xEED13F-24+4, b'\xF8')])); sc = core.CodeScanner(g)
print('D) zmienione [rsp+0x1F0] -> HOOK =', sc.resolve('HOOK'), '(oczekiwane None)')
# E) zmienione pole transakcji 0x71A8 -> 0x7230: CREATE_SITE dalej znalezione, kopia instrukcji z gry
g = G(image(0x2340, [(0x411DF0+2, b'\x30\x72')])); sc = core.CodeScanner(g)
a = sc.resolve('CREATE_SITE'); print('E) zmienione pole tx -> CREATE_SITE', hex(a - g.base), 'pierwsza instr.', g.read(a, 7).hex())

print('--- instalacja na symulacji (kod przesunięty o 0x2340) ---')
img = image(0x2340); g = G(img); g.h = 1
SH = 0x2340
alloc = iter([0x13F000000, 0x13E000000, 0x13D000000, 0x13C000000])
core.Hook._alloc_near = lambda self, site: next(alloc)
core.Creator._alloc_near = lambda self, site: next(alloc)
img2 = bytearray(0x1700000 + 0x4000000)    # pamięć na stuby poniżej modułu
class G2(G):
    def read(self, a, n):
        if a < self.base:
            o = a - 0x13C000000; return bytes(img2[o:o+n])
        return super().read(a, n)
    def write(self, a, d):
        if a < self.base:
            o = a - 0x13C000000; img2[o:o+len(d)] = d; return True
        return super().write(a, d)
g = G2(img); g.h = 1
h = core.Hook(g); print('Hook 1:', h.install(), 'site', hex(h.site - g.base), 'oczek.', hex(0xEED13F + SH))
assert g.read(h.site, 1) == b'\xE9'
fn = struct.unpack('<Q', g.read(h.stub + core.OFF_FN, 8))[0] - g.base; print('   funkcja zapisu', hex(fn), 'oczek.', hex(0x225B70 + SH))
c = core.Creator(g); print('Creator 1:', c.install(), 'site', hex(c.site - g.base), 'oczek.', hex(0x411DF0 + SH))
for off, name in core.CREATE_FUNCS:
    v = struct.unpack('<Q', g.read(c.blk + off, 8))[0] - g.base
    assert v == core.EXPECTED_RVA[name] + SH, (name, hex(v))
tail = g.read(c.blk + core.C_CODE + len(core.STUB3_CODE) - 13, 7).hex(); print('   adresy 6 funkcji OK, kopia instrukcji w stubie:', tail)
h2 = core.Hook(g); print('Hook 2 (drugie uruchomienie):', h2.install(), h2.stub == h.stub)
c2 = core.Creator(g); print('Creator 2 (drugie uruchomienie):', c2.install(), c2.blk == c.blk)
