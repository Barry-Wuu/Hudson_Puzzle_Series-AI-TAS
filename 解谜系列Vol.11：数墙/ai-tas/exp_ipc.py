#!/usr/bin/env python3
"""IPC 触摸结构逆向：dump 共享内存 -> xdotool 点一格 -> dump -> diff。"""
import subprocess
import sys
import time

sys.path.insert(0, "/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas")
import ds
import mode2_fast as M

GDB_CMDS = """target remote localhost:1234
dump binary memory {out} 0x027F0000 0x02800000
quit
"""


def gdb_dump(out):
    open("/tmp/gdbdump.txt", "w").write(GDB_CMDS.format(out=out))
    subprocess.run(["gdb", "-nx", "-batch", "-x", "/tmp/gdbdump.txt"],
                   capture_output=True, timeout=60)


walls = M.walls_of(28)  # lvl29
r, c = walls[0]
print(f"lvl29 walls[0] = ({r},{c}) nds={M.cell_nds(r, c)}", flush=True)

gdb_dump("/tmp/dumpA.bin")
print("dumpA done", flush=True)

# xdotool 点这一格（hold 长一点确保被采到）
ds.tap(*M.cell_nds(r, c), hold=0.15, after=0.05)
print("tapped", flush=True)

gdb_dump("/tmp/dumpB.bin")
print("dumpB done", flush=True)

# 等 2s 让触摸抬起（tap 已 up），再 dump C
time.sleep(2.0)
gdb_dump("/tmp/dumpC.bin")
print("dumpC done", flush=True)

A = open("/tmp/dumpA.bin", "rb").read()
B = open("/tmp/dumpB.bin", "rb").read()
C = open("/tmp/dumpC.bin", "rb").read()
print("sizes:", len(A), len(B), len(C), flush=True)

BASE = 0x027F0000
diffs_ab = [(i, A[i], B[i]) for i in range(min(len(A), len(B))) if A[i] != B[i]]
diffs_ac = [(i, A[i], C[i]) for i in range(min(len(A), len(C))) if A[i] != C[i]]
diffs_bc = [(i, B[i], C[i]) for i in range(min(len(B), len(C))) if B[i] != C[i]]
print(f"diff A->B (点击中): {len(diffs_ab)}", flush=True)
for i, va, vb in diffs_ab[:60]:
    print(f"  0x{BASE+i:08x}: {va:02x} -> {vb:02x}", flush=True)
print(f"diff A->C (点击后2s): {len(diffs_ac)}", flush=True)
for i, va, vc in diffs_ac[:40]:
    print(f"  0x{BASE+i:08x}: {va:02x} -> {vc:02x}", flush=True)
print(f"diff B->C: {len(diffs_bc)}", flush=True)
for i, vb, vc in diffs_bc[:40]:
    print(f"  0x{BASE+i:08x}: {vb:02x} -> {vc:02x}", flush=True)
