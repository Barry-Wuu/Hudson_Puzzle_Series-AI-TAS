#!/usr/bin/env python3
"""mode1(入門) 3星执行器 v4 —— 纯执行 puzzles.json 已知 wall 答案（零求解，答案全在仓库）。

3星打法（2026-10-23 定标钉死：cal lvl4-7 全部 0:00:02 + 3★）：
  - 游戏计时起点 = 按 A 进关后 ~7.2s；输入解锁 ~4.7s → 中间是「白涂窗口」
  - 进关: 选关页单击格(after=0.5) → x键(=A,wait=0.1) → t0 → sleep 4.8
    → 盲发连涂全部墙格(0.10s/格, 首击被 START 遮罩吞) → 校验补点(只补仍为白的墙格)
    → fill_done ≈ 计时起点+0.7s → 显示 0:00:02 → 3★
  - 铁律: 不预扫(遮罩会污染读数)、不碰非墙格(v3 的预扫误涂曾多丢星)
  - 关卡记录只保留最好成绩(ベストタイム) → 重复刷安全，只会更好不会变差
  - 星级: 通关页金星需要 ~1-2s 动画，抓证前 sleep 2.5s；金=得星、深蓝=未得/动画中
  - 存档在 ~/.config/desmume/game.dsv，跨重启持久；记录 best-kept

用法: python3 mode1_fast.py <lo> <hi> [outdir]
"""
import json, shutil, subprocess, sys, time
sys.path.insert(0, "/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas")
sys.path.insert(0, "/workspace/vol11_env")
import ds
import numpy as np
from play_common import PX0, PY0, P, grab_gray, scan_board
from state2 import detect as _detect

REPO = "/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙"
OUT = f"{REPO}/validation/mode1_tutorial"
PUZ = json.load(open(f"{REPO}/validation/puzzles.json"))["入門"]
TAP = dict(gap=0.03, hold=0.05, after=0.02)   # 实测 0% 丢击的最快连发
WAIT_DELTA = 4.8                              # 白涂窗口中点：解锁 ~4.7s 后、计时起点 ~7.2s 前
CX0, CY0 = 68, 228                            # 教程盘格心


def state():
    return _detect(ds.grab(None))


def poll(want, timeout=8.0, iv=0.12):
    t0 = time.time()
    st = state()
    while time.time() - t0 < timeout:
        if st in want:
            return st
        time.sleep(iv)
        st = state()
    return st


def walls_of(idx):
    return [(r, c) for r in range(6) for c in range(6) if PUZ[idx]["wall"][r * 6 + c]]


def cell_nds(r, c):
    return (PX0 + P * c, PY0 + P * r - 192)


def cell_nds_tut(r, c):
    return (CX0 + P * c, CY0 + P * r - 192)


def safe_mouseup():
    subprocess.run(["xdotool", "mouseup", "1"], env=ds.ENV)


# ---------- 教程（仅真正全新存档 lvl1 出现；教程时间不计入 クリアタイム） ----------
def fast_tutorial(max_rounds=150):
    for rnd in range(max_rounds):
        frames = [np.asarray(ds.grab(None).convert("L"), dtype=float) for _ in range(6)]
        st = np.stack(frames)
        blink = []
        for r in range(6):
            for c in range(6):
                cx, cy = CX0 + P * c, CY0 + P * r
                mt = st[:, cy - 6:cy + 6, cx - 6:cx + 6].mean(axis=(1, 2))
                if mt.std() > 22 and mt.max() > 222:
                    blink.append((r, c))
        if blink:
            ds.tap_batch([cell_nds_tut(r, c) for r, c in blink], **TAP)
            safe_mouseup()
            time.sleep(0.25)
            continue
        ds.press("w", wait=0.45)
        if state() != "tut":
            print(f"  [tut] done after {rnd} rounds", flush=True)
            return True
    return False


# ---------- 填充：盲发 + 校验（复刻定标流程，零求解） ----------
def burst_fill(idx):
    """连涂全部墙格；校验只补仍为白的墙格。返回 (补了几格, 是否全黑)。"""
    walls = walls_of(idx)
    ds.tap_batch([cell_nds(r, c) for r, c in walls], **TAP)
    safe_mouseup()
    fixes = 0
    for k in range(3):
        if state() == "clear":                   # 已自动通关，立刻停手
            return fixes, True
        time.sleep(0.3)
        b = scan_board(grab_gray())
        miss = [w for w in walls if b[w] == "W"]  # 只有明确还是白的墙格才补
        if not miss:
            return fixes, True
        fixes += len(miss)
        print(f"  [verify k{k}] miss={len(miss)}", flush=True)
        ds.tap_batch([cell_nds(r, c) for r, c in miss], **TAP)
        safe_mouseup()
    b = scan_board(grab_gray())
    return fixes, not [w for w in walls if b[w] == "W"]


def wait_clear(timeout=6.0, iv=0.1):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if state() == "clear":
            return True
        time.sleep(iv)
    return False


# ---------- 星级（通关页：金=得星；须等动画 ~2.5s） ----------
def stars_gold(im):
    a = np.asarray(im.convert("RGB")).astype(int)
    R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    gold = (R > 200) & (G > 120) & (B < 150) & (G > R * 0.45) & (G < R * 0.95)
    prof = gold[296:316, 80:180].sum(axis=0)
    xs = np.where(prof > 0)[0]
    if len(xs) == 0:
        return 0
    groups = []; s = xs[0]; p = xs[0]
    for x in xs[1:]:
        if x - p > 3:
            groups.append((s, p)); s = x
        p = x
    groups.append((s, p))
    return len(groups)


# ---------- 导航 ----------
def _digits_below(y0, y1):
    g = np.asarray(ds.grab(None).convert("L"), dtype=float)
    return int((g[y0:y1, 8:248] > 200).sum())


def ensure_select():
    """从任意页面回到 入門选关页。"""
    for _ in range(16):
        st = state()
        if st == "select":
            if _digits_below(303, 340) < 150:      # 入門只有 2 行数字
                return True
            ds.press("z", wait=1.5)                # 回难度页重选
            if state() != "diff":
                continue
            for _ in range(5):
                if _digits_below(128, 162) < 150:
                    break
                ds.press("Up", wait=0.6)
            ds.press("x", wait=1.5)
            continue
        if st == "clear":
            ds.tap(128, 300 - 192, after=1.5)
        elif st == "play":
            ds.press("Return", wait=1.2)           # → オプション
        elif st == "option":
            ds.tap(205, 24, after=0.8); ds.press("x", wait=1.5)
        elif st == "slot":
            time.sleep(2.0)                        # セーブ中，等
        elif st == "menu":
            ds.tap(170, 83, after=1.5)             # スタート
        elif st == "diff":
            for _ in range(5):
                if _digits_below(128, 162) < 150:
                    break
                ds.press("Up", wait=0.6)
            ds.press("x", wait=1.5)
        elif st == "title":
            ds.tap(128, 23, after=1.0)
        else:
            ds.press("z", wait=1.0)
        time.sleep(0.2)
    return False


def enter_level(lvl):
    """从选关页进入指定关。返回 t0（按 A 后时刻）或 None。"""
    for att in range(6):
        if not ensure_select():
            print(f"  [enter {lvl}] cannot reach select", flush=True)
            return None
        wy = 280 + 16 * ((lvl - 1) // 10)
        wx = 19 + 24 * ((lvl - 1) % 10)
        ds.tap(wx, wy - 192, after=0.5)            # 单击选中
        ds.press("x", wait=0.1)                    # A 进入
        t0 = time.time()
        st = poll(("play", "tut"), timeout=6)
        if st in ("play", "tut"):
            time.sleep(0.6)                        # 等滑入动画收尾
            return t0
        print(f"  [enter {lvl}] att{att} state={st}", flush=True)
    return None


# ---------- 单关主流程 ----------
def play_level(lvl, idx, t0):
    """进关后到通关。返回 (ok, 金星数)。"""
    st = state()
    if st == "tut":
        if not fast_tutorial():
            return False, -1
        poll(("play",), timeout=5)
        time.sleep(0.4)
        fixes, ok = burst_fill(idx)                # 教程交接盘直接连发
    else:
        remain = WAIT_DELTA - (time.time() - t0)
        if remain > 0:
            time.sleep(remain)                     # 卡在计时起点前连发
        fixes, ok = burst_fill(idx)
    if not ok or not wait_clear():
        print("  [retry] second attempt", flush=True)
        t0 = time.time()
        st2 = state()
        if st2 == "play":
            time.sleep(max(0.0, WAIT_DELTA - 0.5))
            fixes, ok = burst_fill(idx)
        if not ok or not wait_clear(8.0):
            return False, -1
    time.sleep(2.5)                                # 等金星动画渲染完
    im = ds.grab(f"clear_l{lvl:03d}")
    n = stars_gold(im)
    shutil.copy(f"/root/.codebuddy/artifact/vol11/clear_l{lvl:03d}.png",
                f"{OUT}/l{lvl:03d}_clear.png")
    print(f"  lvl{lvl:02d} cleared fixes={fixes} gold_stars={n}", flush=True)
    return True, n


def main():
    lo = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    hi = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    print(f"=== mode1 fast v4 (3-star run): lvl {lo}..{hi}", flush=True)
    results = []
    for lvl in range(lo, hi + 1):
        idx = lvl - 1
        t0 = enter_level(lvl)
        if t0 is None:
            print(f"FAIL enter lvl{lvl}", flush=True)
            ds.grab(f"fail_enter_l{lvl:03d}")
            break
        ok, n = play_level(lvl, idx, t0)
        results.append((lvl, ok, n))
        if not ok:
            print(f"FAIL solve lvl{lvl}", flush=True)
            ds.grab(f"fail_solve_l{lvl:03d}")
            break
    print("=== summary ===", flush=True)
    for lvl, ok, n in results:
        mark = "OK " if (ok and n == 3) else "   "
        print(f"{mark} lvl{lvl:02d} ok={ok} gold_stars={n}", flush=True)
    good = sum(1 for _, ok, n in results if ok and n == 3)
    print(f"3-star: {good}/{len(results)}", flush=True)
    return 0 if good == len(results) and len(results) == hi - lo + 1 else 1


if __name__ == "__main__":
    sys.exit(main())
