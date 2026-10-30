import os, sys, time
import mode2_fast as m
lo, hi = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) >= 3 else (1, 20)
if not m.ensure_select():
    print("FATAL cannot reach select", flush=True); sys.exit(1)
print("reached select (DIFF=%s)" % m.DIFF, flush=True)
for lvl in range(lo, hi + 1):
    t0 = m.enter_level(lvl)
    if t0 is None:
        print("FAIL enter lvl", lvl, flush=True); sys.exit(2)
    ok, n = m.play_level(lvl, t0)
    print(f"RESULT lvl{lvl} ok={ok} stars={n}", flush=True)
    if not ok:
        print("FAIL solve lvl", lvl, flush=True); sys.exit(3)
print("back_to_select", m.ensure_select(), flush=True)
print("SEG1_DRIVER_DONE", flush=True)
