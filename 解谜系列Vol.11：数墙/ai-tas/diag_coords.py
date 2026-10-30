#!/usr/bin/env python3
# 临时诊断 v6：复制 v3 play_level 的 tut 推进(do_step+按A) 让说明屏进入 play，
# 进入 play 后用「线索位置集合 == 攻略线索位置的某几何变换」确认，得到映射 mode。
import os, sys, time, json
os.environ.setdefault("V11_DIFF", "入門")
sys.path.insert(0, "/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas")
import ds, state2, tut, nyumon_play as N, seg1_run as S, guide

LVL = 2
PZ = LVL - 1

def state():
    return state2.detect(ds.grab(None))

if state() != "select":
    import boot_to_select
    boot_to_select.boot_to_select()
S.enter_level(LVL)
S.wait_start_done()

puz = json.load(open("/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/validation/puzzles.json", encoding="utf-8"))["入門"][PZ]
W = puz["w"]; H = puz["h"]
guide_clue_pos = sorted((r, c) for r in range(H) for c in range(W) if puz["clue"][r*W+c] >= 1)
guide_black = set((r, c) for r in range(H) for c in range(W) if puz["wall"][r*W+c] == 1)

def mapped_pos(cells, mode):
    out = set()
    for (r, c) in cells:
        if mode == "id":            (nr, nc) = (r, c)
        elif mode == "rot180":      (nr, nc) = (H-1-r, W-1-c)
        elif mode == "fliprow":     (nr, nc) = (H-1-r, c)
        elif mode == "flipcol":     (nr, nc) = (r, W-1-c)
        elif mode == "transpose":   (nr, nc) = (c, r)
        elif mode == "tr_fliprow":  (nr, nc) = (c, H-1-r)
        elif mode == "tr_flipcol":  (nr, nc) = (W-1-c, r)
        elif mode == "tr_rot180":   (nr, nc) = (W-1-c, H-1-r)
        out.add((nr, nc))
    return out

modes = ("id","rot180","fliprow","flipcol","transpose","tr_fliprow","tr_flipcol","tr_rot180")
matched = None
last_S = None
for _ in range(160):
    st = state()
    if st == "play":
        f = tut.grab_np(); g = tut.detect_grid(f)
        if g:
            b = N.read_board(f)
            if b and len(b["clues"]) >= 1:
                S = set(b["clues"].keys())
                last_S = S
                for mode in modes:
                    if mapped_pos(set(guide_clue_pos), mode) == S:
                        matched = mode
                        break
                if matched:
                    break
    elif st == "tut":
        f = tut.grab_np(); g = tut.detect_grid(f)
        if g:
            fp0 = tut.upper_fp(f)
            advanced = tut.do_step(g, fp0)
            if not advanced and state() != "clear":
                ds.press("x", wait=0.4, hold=0.05)
        time.sleep(0.3)
    elif st == "clear":
        time.sleep(0.2)
    else:
        ds.press("x", wait=0.25, hold=0.05)
    time.sleep(0.1)
print("GUIDE clue pos:", sorted(guide_clue_pos), flush=True)
print("matched S (SCREEN play clue pos):", sorted(last_S), flush=True)
print("MATCH mode =", matched, flush=True)
print("GUIDE black pos:", sorted(guide_black), flush=True)
print("DONE diag", flush=True)
