#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ふつう 18×10（lvl 1..64, idx1523..1586）—— 批量提速画法重录（带音频）。

复用：
  - fast_click 的批量点中点画法（skip-verify：画完直接チェック，无核查补边）
  - record_levels.rec_start/rec_stop 录像（x11grab 下屏 256×384 + pulse desmume_out 音频）
  - record18_v4/nav18/record_big 的导航与判定

安全设计：
  - 默认输出到新目录 vol5_recordings_futsuu_18x10_fast，不覆盖旧版拖拽成品。
  - 每关先录到 *.recording.mp4，判定过关且文件有效后才原子替换正式文件。
  - record_log.json 逐关写；断点续录（已存在且过关的跳过，--force 强制重录）。

用法：
  bash boot_audio.sh   # 必须先带音频启动
  DISPLAY=:99 XDG_RUNTIME_DIR=/tmp \
    CLICK_GAP=0.02 CLICK_HOLD=0.06 CLICK_AFTER=0.10 CHAIN=1 BATCH=24 LEAD=0.20 \
    python3.11 record_futsuu18_fast.py --lo 1 --hi 64
"""
import os, sys, time, subprocess, json, signal
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ds
import nav18 as N
import record18 as r18
import edgecheck as ec
import slither18 as s18
import record18_v4 as V
import record_big as RB
import record_levels as rl

IDX_BASE = 1522                      # idx = base + lvl (ふつう)
CHECK_BTN = (195, 182)
OUTDIR = os.environ.get("REC_OUTDIR", "/workspace/vol5_recordings_futsuu_18x10_fast")

GAP = float(os.environ.get("CLICK_GAP", "0.02"))
HOLD = float(os.environ.get("CLICK_HOLD", "0.06"))
AFTER = float(os.environ.get("CLICK_AFTER", "0.10"))
BATCH = int(os.environ.get("CLICK_BATCH", "24"))
LEAD = float(os.environ.get("CLICK_LEAD", "0.20"))
PARK = (ds.WIN_X + 250, ds.WIN_Y + 380)


def park():
    subprocess.run(["xdotool", "mousemove", str(PARK[0]), str(PARK[1])], env=ds.ENV)


def click_cmd(points, lead=0.0):
    cmd = ["xdotool"]
    for i, (mx, my) in enumerate(points):
        sx, sy = ds.WIN_X + mx, ds.WIN_Y + 192 + my
        g = GAP + (lead if i == 0 else 0.0)
        cmd += ["mousemove", str(sx), str(sy), "sleep", str(g),
                "mousedown", "1", "sleep", str(HOLD), "mouseup", "1",
                "sleep", str(AFTER)]
    return cmd


def pts_for(group, view):
    off = -r18.SHIFT_B if view == "B" else 0
    out = []
    for (k, r, c) in group:
        x1, y1, x2, y2 = r18.edge_px(k, r, c)
        out.append(((x1 + x2)//2 + off, (y1 + y2)//2))
    return out


def paint(A, B):
    """批量画两档，返回 (view->边列表)。画完停在 B 档。"""
    data = json.load(open(ec.PJ, encoding="utf-8"))
    ds.ensure_window()
    r18.ensure_view("A")
    cur = "A"
    for view, group in (("A", A), ("B", B)):
        if not group:
            continue
        if view != cur:
            r18.toggle_to(view, cur); cur = view
        time.sleep(0.3)
        pl = pts_for(group, view)
        for i in range(0, len(pl), BATCH):
            subprocess.run(click_cmd(pl[i:i+BATCH], lead=LEAD), env=ds.ENV, check=True)
        park(); time.sleep(0.2)
    return cur


def judge(timeout=8):
    """过关判定：Completion / 结算 / 橙色大字兜底 / 离开盘面。只观察不推进。"""
    t1 = time.time()
    while time.time() - t1 < timeout:
        if V.completion_anim() or V.real_result():
            return True
        bot = ec.bot_rgb()
        reg = bot[70:135, 30:230]
        orange = int(((reg[:, :, 0] > 150) & (reg[:, :, 1] > 60) &
                      (reg[:, :, 1] < 175) & (reg[:, :, 2] < 110)).sum())
        if orange > 2500:
            return True
        if not RB.on_board() and N._screen_kind() in ("select", "menu"):
            return True
        time.sleep(0.25)
    return False


def to_clean_board(lvl):
    """从当前状态导航到 lvl 的干净盘面。"""
    if not RB.to_select_of("futsuu"):
        return False
    N.goto_window(51 if lvl > 50 else 1)
    ok, _ = N.enter_level(lvl)
    if not ok:
        return False
    time.sleep(0.8)
    for _ in range(3):
        if V.completion_anim() or V.real_result() or RB.on_board():
            ds.tap(128, 96, hold=0.12, after=0.8)   # 成绩页 -> 净盘（触摸，不用 A）
        else:
            break
    N.wait_start_anim()
    time.sleep(0.4)
    return RB.on_board()


def leave_to_select():
    """从结算/Completion 回选关页，供下一关导航。"""
    for _ in range(8):
        if s18.is_select_ui():
            return True
        ds.tap(128, 96, hold=0.12, after=0.5)
    return s18.is_select_ui()


def record_one(lvl, force=False, retries=3):
    idx = IDX_BASE + lvl
    final_out = os.path.join(OUTDIR, f"数回_ふつう18x10_第{lvl:02d}問.mp4")
    tmp_out = os.path.join(OUTDIR, f".第{lvl:02d}問.recording.mp4")
    if not force and os.path.exists(final_out) and os.path.getsize(final_out) > 20000:
        return dict(lvl=lvl, idx=idx, skip=True, ok=True, size=os.path.getsize(final_out))

    data = json.load(open(ec.PJ, encoding="utf-8"))
    p = next(x for x in data if x["idx"] == idx)
    edges = [("h", r, c) for (r, c) in p["edges_h"]] + [("v", r, c) for (r, c) in p["edges_v"]]
    A = [e for e in edges if r18.edge_view(*e) == "A"]
    B = [e for e in edges if r18.edge_view(*e) == "B"]

    for attempt in range(1, retries + 1):
        if not to_clean_board(lvl):
            print(f"L{lvl}: 进关失败（第{attempt}次）", flush=True)
            leave_to_select()
            continue
        if os.path.exists(tmp_out):
            os.remove(tmp_out)
        rec = rl.rec_start(tmp_out)
        t0 = time.time()
        cleared = False
        rc = None
        try:
            paint(A, B)
            ds.tap(*CHECK_BTN, hold=0.18, after=0.0)
            park()
            cleared = judge()
            rc = rl.rec_stop(rec); rec = None
        finally:
            if rec:
                rl.rec_stop(rec); rc = -9
        draw_s = time.time() - t0
        size = os.path.getsize(tmp_out) if os.path.exists(tmp_out) else 0
        if cleared and size > 20000:
            os.replace(tmp_out, final_out)
            print(f"L{lvl} idx{idx}: OK 画{draw_s:.1f}s size={size} att={attempt}", flush=True)
            leave_to_select()
            return dict(lvl=lvl, idx=idx, edges=len(edges), ok=True, draw=round(draw_s, 1),
                        size=size, attempt=attempt, ff_rc=rc, cleared=True)
        print(f"L{lvl} idx{idx}: 未过关/坏文件（第{attempt}次）画{draw_s:.1f}s size={size}", flush=True)
        if os.path.exists(tmp_out):
            os.remove(tmp_out)
        leave_to_select()
    return dict(lvl=lvl, idx=idx, edges=len(edges), ok=False, cleared=False, attempt=retries)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--lo", type=int, default=1)
    ap.add_argument("--hi", type=int, default=64)
    ap.add_argument("--force", action="store_true", help="强制重录已存在且过关的关")
    ap.add_argument("--retries", type=int, default=3)
    a = ap.parse_args()
    os.makedirs(OUTDIR, exist_ok=True)
    logpath = os.path.join(OUTDIR, "record_log.json")
    merged = {}
    if os.path.exists(logpath):
        try:
            merged = {r["lvl"]: r for r in json.load(open(logpath, encoding="utf-8"))}
        except (ValueError, OSError):
            pass
    print(f"输出目录 {OUTDIR}  GAP={GAP} HOLD={HOLD} AFTER={AFTER} BATCH={BATCH} LEAD={LEAD}", flush=True)

    # 启动时确保从选关页开始（title 需先走一遍）
    import slither18 as s18chk
    if not s18chk.is_select_ui():
        N.goto_muzukashii_select()
    RB.to_select_of("futsuu")
    N.goto_window(1)

    for lvl in range(a.lo, a.hi + 1):
        r = record_one(lvl, force=a.force, retries=a.retries)
        if not r.get("skip"):
            merged[lvl] = r
            json.dump([merged[k] for k in sorted(merged)],
                      open(logpath, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    ok = sum(1 for r in merged.values() if r.get("ok"))
    print(f"=== 汇总: {ok}/{len(merged)} 关 ok ===", flush=True)


if __name__ == "__main__":
    main()
