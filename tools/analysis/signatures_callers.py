from gen import *
import numpy as np
T = np.frombuffer(TEXT, dtype=np.uint8)
def callers(rva):
    idx = np.nonzero(T[:-5] == 0xE8)[0]
    rel = (T[idx+1].astype(np.int64) | (T[idx+2].astype(np.int64) << 8) | (T[idx+3].astype(np.int64) << 16) | (T[idx+4].astype(np.int64) << 24))
    rel = np.where(rel >= 2**31, rel - 2**32, rel)
    tgt = idx + TVA + 5 + rel
    return [int(i) + TVA for i in idx[tgt == rva]]
if __name__ == '__main__':
    for name, r in [('CREATE 40B760', 0x40B760), ('LOOKUP E7A870', 0xE7A870), ('CTOR', 0x21DD00), ('SITE', 0x411DF0)]:
        c = callers(r); print(name, len(c), [hex(x) for x in c[:12]])
