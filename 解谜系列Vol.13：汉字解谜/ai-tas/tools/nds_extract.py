#!/usr/bin/env python3
"""NitroFS extractor for variant FNT (file entries omit u16 file id; ids sequential)."""
import struct, sys, os

def extract(nds_path, out_dir):
    data = open(nds_path, 'rb').read()
    fnt_off = struct.unpack_from('<I', data, 0x40)[0]
    fat_off = struct.unpack_from('<I', data, 0x48)[0]
    fat_size = struct.unpack_from('<I', data, 0x4C)[0]
    n = fat_size // 8
    out = []
    def walk(dir_id, prefix):
        off, first_id = struct.unpack_from('<II', data, fnt_off + 8 * dir_id)
        first_id &= 0xFFFF
        fid = first_id
        sub = data[fnt_off + off:]
        pos = 0
        while True:
            etype = sub[pos]; pos += 1
            if etype == 0:
                break
            nl = etype & 0x7F
            raw = sub[pos:pos + nl]; pos += nl
            try:
                nm = raw.decode('utf-8')
            except UnicodeDecodeError:
                nm = raw.decode('shift_jis', 'replace')
            if etype & 0x80:
                did = struct.unpack_from('<H', sub, pos)[0] & 0xFFF; pos += 2
                walk(did, prefix + nm + '/')
            else:
                out.append((fid, prefix + nm))
                fid += 1
    walk(0, '')
    os.makedirs(out_dir, exist_ok=True)
    for fid, name in out:
        if fid >= n:
            print(f'!! fid {fid} out of range for {name}')
            continue
        start, end = struct.unpack_from('<II', data, fat_off + fid * 8)
        if end <= start:
            continue
        p = os.path.join(out_dir, name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, 'wb').write(data[start:end])
    print(f'Extracted {len(out)} files (max fid {max(f for f,_ in out)}, FAT entries {n})')

if __name__ == '__main__':
    extract(sys.argv[1], sys.argv[2])
