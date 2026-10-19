import re, struct, subprocess, sys
EXE = '/mnt/user-data/uploads/Enshrouded/enshrouded.exe'
data = open(EXE, 'rb').read()
pe = struct.unpack_from('<I', data, 0x3C)[0]
nsec = struct.unpack_from('<H', data, pe + 6)[0]
opt = pe + 24; osz = struct.unpack_from('<H', data, pe + 20)[0]
base = struct.unpack_from('<Q', data, opt + 24)[0]
secs = []
for i in range(nsec):
    o = opt + osz + i * 40
    name = data[o:o+8].rstrip(b'\0').decode()
    vsz, va, rsz, raw = struct.unpack_from('<IIII', data, o + 8)
    secs.append((name, va, vsz, raw, rsz))
text = [s for s in secs if s[0] == '.text'][0]
_, TVA, TVS, TRAW, TRS = text
TEXT = data[TRAW:TRAW + TRS]
def rva2off(r): return r - TVA + TRAW
def disasm(rva, n=120):
    a = base + rva
    out = subprocess.run(['objdump', '-d', '-M', 'intel', '--start-address=%#x' % a, '--stop-address=%#x' % (a + n), EXE],
                         capture_output=True, text=True).stdout
    ins = []
    for line in out.splitlines():
        m = re.match(r'\s+([0-9a-f]+):\s+((?:[0-9a-f]{2} )+)\s*(.*)', line)
        if m:
            ins.append((int(m.group(1), 16) - base, bytes.fromhex(m.group(2).replace(' ', '')), m.group(3)))
    # objdump lamie dlugie instrukcje na 2 linie (bez mnemonika) – sklej
    merged = []
    for r, b, t in ins:
        if merged and not t:
            pr, pb, pt = merged[-1]; merged[-1] = (pr, pb + b, pt)
        else:
            merged.append((r, b, t))
    return merged
def masked(ins):
    toks = []
    for r, b, t in ins:
        mask = [False] * len(b)
        op = b[0] if b[0] not in (0x48, 0x49, 0x4c, 0x4d, 0x44, 0x41, 0x40, 0x66, 0xf3, 0xf2) else None
        if b[0] in (0xe8, 0xe9) and len(b) == 5 or (len(b) == 6 and b[0] == 0x0f and 0x80 <= b[1] <= 0x8f):
            for k in range(len(b) - 4, len(b)): mask[k] = True
        elif 'rip' in t:
            m = re.search(r'# (0x[0-9a-f]+|[0-9a-f]+)', t)
            if m:
                tgt = int(m.group(1), 16); nxt = base + r + len(b)
                disp = struct.pack('<i', tgt - nxt)
                k = b.find(disp)
                if k >= 0:
                    for j in range(k, k + 4): mask[j] = True
        toks += ['??' if mask[k] else '%02X' % b[k] for k in range(len(b))]
    return toks
def rx(toks):
    return re.compile(b''.join(b'.' if t == '??' else re.escape(bytes([int(t, 16)])) for t in toks), re.S)
def unique_sig(rva, minlen=16, maxlen=96):
    ins = disasm(rva, maxlen + 16)
    toks = masked(ins)
    for n in range(minlen, min(len(toks), maxlen) + 1):
        hits = [m.start() for m in rx(toks[:n]).finditer(TEXT)]
        if len(hits) == 1:
            assert hits[0] == rva2off(rva) - TRAW, hits
            # dopelnij do granicy instrukcji
            L = 0
            for r, b, t in ins:
                L += len(b)
                if L >= n: break
            return ' '.join(toks[:L]), ins
    return None, ins
if __name__ == '__main__':
    print('base %#x text va %#x size %#x' % (base, TVA, TVS))
    for name, rva in [('CREATE_SITE', 0x411DF0), ('CTOR', 0x21DD00), ('LOOKUP', 0xE7A870), ('CREATE', 0x40B760),
                      ('COMMIT', 0x408B50), ('ROLLBACK', 0x410E60), ('DTOR', 0x21DE50)]:
        sig, ins = unique_sig(rva)
        print(name, hex(rva), '->', sig)
        if not sig:
            for r, b, t in ins[:8]: print('    ', hex(r), b.hex(), t)
