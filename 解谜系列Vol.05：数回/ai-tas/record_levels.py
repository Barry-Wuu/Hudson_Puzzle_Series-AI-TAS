#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vol.5 数回 逐关录制（BGM / デザイン = ランダム，始终），支持 6x6 / 10x10 两档。

段首一次性把 BGM 与 デザイン 都设成「ランダム」(RANDOM)；该设置随 SRAM
持久化，实测 pkill 落盘重启后仍生效（关卡内主题色每关随机变化即为证据）。

每关产出一段 256×384 / 30fps 的 mp4（x11grab 视频 + pulse 音频，单进程实时编码），
驱动照 puzzles.json 的 edges_h/edges_v 一次连续拖动画出官方单环。

用法:
    bash ai-tas/boot_audio.sh                                  # 先起带音频环境
    python3 ai-tas/record_levels.py --lo 2 --hi 4              # 入門6x6 第 2..4 問（默认档）
    python3 ai-tas/record_levels.py --preset yasashii10 --lo 1 --hi 10
                                                               # やさしい10x10 第 1..10 問

档位差异（均为实机标定）:
    入門 nyuumon    6x6   x0=50 y0=8  pitch=26  step=13 gap=0.016 turn=0.015
                    idx = 1402 + 关号（第1..20 关 = idx1403..1422）
    やさしい yasashii10
                    10x10 x0=47 y0=6  pitch=16  step=8  gap=0.016 turn=0.015
                    idx = 1422 + 关号（第1..92 关 = idx1423..1514）
                    10x10 盘面 x[47..207] y[6..166] 完整落在下屏内，无需滚动；
                    92~104 边长环一次拖动约 5.0~5.6s 即可 Completion!!，无需分段。

剂量硬下限 gap>=0.016（≈ DeSmuME 60fps 1 帧）；step 按 pitch 等比缩放（每边 2 个插值点），
10x10 的 pitch=16 必须 step=8，step>=13 会因插值过疏丢线段、环不闭合。
"""
import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import time

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ds  # noqa: E402  仓库公用操作层（窗口/抓屏/触摸/按键）

BASE = os.path.dirname(HERE)
PJ = os.path.join(BASE, "validation", "puzzles.json")
DSV = "/root/.config/desmume/解谜系列Vol.05：数回.dsv"
REC_ENV = dict(os.environ, DISPLAY=":99", XDG_RUNTIME_DIR="/tmp",
               PULSE_SERVER="unix:/tmp/pulse_native")

# ---- 尺寸档位配置 ----
# 剂量按格点 pitch 缩放：pitch 26 -> step 13，pitch 16 -> step 8（每边 2 个插值点）。
# gap>=0.016 是 DeSmuME 60fps 1 帧硬下限（与尺寸无关）；turn=0.015 为拐角停顿。
# 6x6 入門默认；10x10 やさしい 是 2026-11-11 实测推广（idx1423..1514，共 92 题）。
PRESETS = {
    "nyuumon": dict(
        name="入門", size="6x6", layout="nyuumon",
        x0=50, y0=8, pitch=26,
        dose=dict(step=13, gap=0.016, turn=0.015),
        idx_base=1402, lo=1, hi=20,
        outdir="/workspace/vol5_recordings",
        filepat="数回_入門_第{lvl:02d}問.mp4",
        evi=("18_random_before.png", "19_random_after.png", "20_random_rows_6x.png"),
    ),
    "yasashii10": dict(
        name="やさしい 10x10", size="10x10", layout="yasashii10",
        x0=47, y0=6, pitch=16,
        dose=dict(step=8, gap=0.016, turn=0.015),
        idx_base=1422, lo=1, hi=50,
        outdir="/workspace/vol5_recordings_10x10",
        filepat="数回_やさしい10x10_第{lvl:02d}問.mp4",
        evi=("24_y10_random_before.png", "25_y10_random_after.png", "26_y10_random_rows_6x.png"),
    ),
}
CFG = PRESETS["nyuumon"]     # main() 按 --preset 覆盖
DOSE = PRESETS["nyuumon"]["dose"]   # 兼容旧引用

# ---- 状态判据（颜色无关；DESIGN=RANDOM 只换关卡内盘面配色）----
GREEN_SELECT = 15000
ORANGE_COMPLETION = 2500
TR_SELECT_LO, TR_SELECT_HI = 1200, 2100


def bot():
    return ds.grab(None).convert("RGB").crop((0, 192, 256, 384))


def feats(b):
    a = np.asarray(b).astype(int)
    R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    green = int(((G > R + 25) & (G > B + 25)).sum())
    m = a[65:140, 5:250]
    orange = int(((m[:, :, 0] > 190) & (m[:, :, 1] > 70) &
                  (m[:, :, 1] < 215) & (m[:, :, 2] < 130)).sum())
    tr = a[4:30, 140:250]
    tr_dark = int((tr.mean(axis=2) < 110).sum())
    return green, orange, tr_dark


def state():
    b = bot()
    g, o, t = feats(b)
    if o > ORANGE_COMPLETION:
        return "completion"
    if g < 500:
        return "board"
    if g > GREEN_SELECT:
        if TR_SELECT_LO < t < TR_SELECT_HI:
            return "select"
        # DESIGN=RANDOM 的「绿色主题答题盘」：右上没有「クリア数」标签，
        # tr_dark 很低（选关页 1573~1708 / 主菜单 2550+ / 绿色盘面约 330）
        if t < 1200:
            return "board"
        return "menu"
    return "menu"


def is_option(b):
    """オプション面板：绿色背景像素 1000~6000、右上无クリア数。"""
    g, o, t = feats(b)
    return 1000 < g < 6000 and t < 900


def random_set(b):
    """两行最右「ランダム」按钮是否都为红底选中。返回 (是否都选中, 各自红底像素)。"""
    a = np.asarray(b).astype(int)
    vals = []
    for y0, y1 in ((56, 78), (80, 102)):
        r = a[y0:y1, 210:252]
        vals.append(int(((r[:, :, 0] > 140) & (r[:, :, 0] > r[:, :, 1] + 50) &
                         (r[:, :, 0] > r[:, :, 2] + 50)).sum()))
    return all(v >= 150 for v in vals), vals


def level_xy(lvl):
    """选关页关卡格子中心（下屏局部坐标）。

    nyuumon(入門 20 关)：2 行 x 10 列，起始 (18,48)，间距 24。
    yasashii10(やさしい 100 关)：每页 5 行 x 10 列，起始 (20,44)，间距 24；
      第 51~100 关需翻页，本档 hi 暂限 50（第 1 页，均为 10x10）。
    """
    if CFG["layout"] == "nyuumon":
        row = 0 if lvl <= 10 else 1
        col = (lvl - 1) % 10
        return 18 + 24 * col, (48 if row == 0 else 72)
    # yasashii10
    col = (lvl - 1) % 10
    row = ((lvl - 1) % 50) // 10
    return 20 + 24 * col, 44 + 24 * row


# ---- 画线 ----
def ring_path(idx, x0=None, y0=None, pitch=None):
    x0 = CFG["x0"] if x0 is None else x0
    y0 = CFG["y0"] if y0 is None else y0
    pitch = CFG["pitch"] if pitch is None else pitch
    data = json.load(open(PJ, encoding="utf-8"))
    p = next(x for x in data if x["idx"] == idx)
    adj, n = {}, 0
    for (r, c) in p["edges_h"]:
        a, b = (r, c), (r, c + 1)
        adj.setdefault(a, []).append(b); adj.setdefault(b, []).append(a); n += 1
    for (r, c) in p["edges_v"]:
        a, b = (r, c), (r + 1, c)
        adj.setdefault(a, []).append(b); adj.setdefault(b, []).append(a); n += 1
    assert all(len(v) == 2 for v in adj.values()), "非单环"
    s = next(iter(adj)); path = [s]; cur, used = s, set()
    while True:
        nxt = None
        for nb in adj[cur]:
            k = tuple(sorted([cur, nb]))
            if k not in used:
                nxt = nb; used.add(k); break
        if nxt is None or nxt == s:
            break
        path.append(nxt); cur = nxt
        if len(path) > n + 2:
            break
    assert len(used) == n and len(path) == n, "未闭合"
    return [(x0 + pitch * c, y0 + pitch * r) for (r, c) in path]


def drag_path(points, step=13, gap=0.016, turn=0.015,
              head=0.15, down=0.12, tail=0.12, settle=0.3):
    t0 = time.time()
    x0, y0 = points[0]
    cmd = ["xdotool", "mousemove", str(ds.WIN_X + x0), str(ds.WIN_Y + 192 + y0),
           "sleep", str(head), "mousedown", "1", "sleep", str(down)]
    seq = list(points) + [points[0]]
    for (xa, ya), (xb, yb) in zip(seq, seq[1:]):
        L = max(abs(xb - xa), abs(yb - ya))
        if L:
            for i in range(step, L + 1, step):
                xx = int(xa + (xb - xa) * i / L); yy = int(ya + (yb - ya) * i / L)
                cmd += ["mousemove", str(ds.WIN_X + xx), str(ds.WIN_Y + 192 + yy), "sleep", str(gap)]
        cmd += ["mousemove", str(ds.WIN_X + xb), str(ds.WIN_Y + 192 + yb), "sleep", str(turn)]
    cmd += ["sleep", str(tail), "mouseup", "1"]
    subprocess.run(cmd, env=ds.ENV)
    time.sleep(settle)
    return time.time() - t0


def select_line_tool():
    ds.tap(20, 183, hold=0.15, after=0.7)


# ---- 导航 ----
def ensure_select(maxsteps=10):
    for k in range(maxsteps):
        if state() == "select":
            return True, k
        ds.tap(128, 96, hold=0.15, after=1.6)
    return False, maxsteps


def enter(lvl, settle=4.0):
    x, y = level_xy(lvl)
    for k in range(6):
        ds.tap(x, y, hold=0.15, after=2.0)
        if state() == "board":
            time.sleep(settle)   # 等 START 演出过去
            return True, k + 1
    return False, 6


def wait_completion(timeout=9.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if state() == "completion":
            return True, time.time() - t0
        time.sleep(0.3)
    return False, time.time() - t0


def settle_to_select():
    """Completion!! 出现后等动画稳定再结算；结算后先纯等「セーブ中です…」保存屏
    自行结束（此间 tap 会被吞），再按需补 tap 直到回到选关页。"""
    time.sleep(2.5)
    ds.tap(128, 96, hold=0.15, after=2.5)
    # 保存屏 / 结算演出期间不 tap，纯等自动回选关
    for k in range(20):
        if state() == "select":
            return True, k
        time.sleep(0.6)
    for k in range(10):
        ds.tap(128, 96, hold=0.15, after=1.5)
        if state() == "select":
            return True, 20 + k
    return False, 30


# ---- RANDOM 段首设置 ----
def setup_random(lvl, evidence_dir):
    """进 lvl 关 -> 打开オプション -> 确认/设置 BGM 与 デザイン 都为「ランダム」
    -> 关面板，返回时停在干净盘面（该关即录制的第一关）。

    设置随 SRAM 持久化：若重启后已是 RANDOM（红底），跳过重复点击，避免误切。
    """
    ok, taps = enter(lvl)
    if not ok:
        raise RuntimeError(f"setup_random: 进第{lvl}問失败")
    # START 演出期间 tap 会被吞，重试直到面板确实打开
    b = bot()
    for k in range(4):
        ds.tap(235, 180, hold=0.20, after=2.0)   # オプション
        b = bot()
        if is_option(b):
            break
    else:
        raise RuntimeError("setup_random: オプション面板未打开")
    e_before, e_after, e_rows = CFG["evi"]
    if evidence_dir:
        b.save(os.path.join(evidence_dir, e_before))

    ok_rand, vals = random_set(b)
    if not ok_rand:
        ds.tap(232, 66, hold=0.15, after=1.2)    # BGM -> ランダム
        ds.tap(232, 90, hold=0.15, after=1.2)    # デザイン -> ランダム
        b = bot()
        ok_rand, vals = random_set(b)
    if evidence_dir:
        b.save(os.path.join(evidence_dir, e_after))
        b.crop((100, 52, 256, 104)).resize((156 * 6, 52 * 6)).save(
            os.path.join(evidence_dir, e_rows))
    print(f"  RANDOM 红底像素 BGM/デザイン={vals} 已持久化={ok_rand}", flush=True)
    if not ok_rand:
        raise RuntimeError(f"RANDOM 设置校验失败 {vals}")
    ds.tap(70, 172, hold=0.30, after=2.0)        # 問題を再開する -> 关面板
    print(f"  RANDOM 已设并校验（第{lvl}問面板），当前状态 {state()}", flush=True)
    return state() == "board"


# ---- 录制 ----
def rec_start(out):
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "x11grab", "-draw_mouse", "0", "-framerate", "30",
           "-video_size", "256x384", "-i", ":99+384,192",
           "-f", "pulse", "-i", "desmume_out.monitor",
           "-c:v", "libopenh264", "-pix_fmt", "yuv420p", "-b:v", "2500k", "-r", "30",
           "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2",
           out]
    p = subprocess.Popen(cmd, env=REC_ENV,
                         stdout=open("/tmp/v5_ff.log", "a"),
                         stderr=subprocess.STDOUT)
    time.sleep(1.2)
    return p


def rec_stop(p):
    p.send_signal(signal.SIGINT)
    try:
        p.wait(timeout=25)
    except subprocess.TimeoutExpired:
        p.kill(); p.wait()
    return p.returncode


def main():
    global CFG
    ap = argparse.ArgumentParser()
    ap.add_argument("--preset", choices=list(PRESETS), default="nyuumon",
                    help="尺寸档位：nyuumon=入門6x6(默认)，yasashii10=やさしい10x10")
    ap.add_argument("--lo", type=int, default=None, help="起始关（默认取档位 lo）")
    ap.add_argument("--hi", type=int, default=None, help="结束关（默认取档位 hi）")
    ap.add_argument("--outdir", default=None, help="成品目录（默认取档位 outdir）")
    ap.add_argument("--evidence", default=os.path.join(HERE, "evidence"))
    ap.add_argument("--no-setup", action="store_true", help="跳过段首 RANDOM 设置")
    ap.add_argument("--step", type=int, default=None, help="覆盖档位剂量 step")
    ap.add_argument("--gap", type=float, default=None, help="覆盖档位剂量 gap")
    ap.add_argument("--turn", type=float, default=None, help="覆盖档位剂量 turn")
    args = ap.parse_args()

    # 默认值延迟到 parse 之后按档位取，避免 argparse 定义时锁死 6x6 参数
    CFG = PRESETS[args.preset]
    lo = CFG["lo"] if args.lo is None else args.lo
    hi = CFG["hi"] if args.hi is None else args.hi
    outdir = CFG["outdir"] if args.outdir is None else args.outdir
    dose = dict(CFG["dose"])
    if args.step is not None:
        dose["step"] = args.step
    if args.gap is not None:
        dose["gap"] = args.gap
    if args.turn is not None:
        dose["turn"] = args.turn

    os.makedirs(outdir, exist_ok=True)
    ds.ensure_window()
    print(f"档位 {args.preset} / {CFG['name']} ({CFG['size']}) "
          f"几何 x0={CFG['x0']} y0={CFG['y0']} pitch={CFG['pitch']} "
          f"idx_base={CFG['idx_base']} 区间 {lo}..{hi}", flush=True)
    print("起点状态", state(), "剂量", dose, flush=True)

    setup_ok = False
    if not args.no_setup:
        setup_ok = setup_random(lo, args.evidence)
        print("setup_random ->", setup_ok, flush=True)

    # 读取既有日志并按关号合并：分批 --lo/--hi 录制不再互相覆盖。
    # （早期版本每次运行都重写，导致多批录制后只剩最后一批，已修正。）
    logpath = os.path.join(outdir, "record_log.json")
    merged = {}
    if os.path.exists(logpath):
        try:
            for r in json.load(open(logpath, encoding="utf-8")):
                merged[r["lvl"]] = r
        except (ValueError, OSError):
            pass
    for lvl in range(lo, hi + 1):
        idx = CFG["idx_base"] + lvl
        out = os.path.join(outdir, CFG["filepat"].format(lvl=lvl))
        if os.path.exists(out) and os.path.getsize(out) > 20000:
            print(f"第{lvl}問 已存在，跳过", flush=True)
            continue
        # 第一关若已完成 setup 则已在盘面；其余关需从选关页进入
        if not (setup_ok and lvl == lo):
            ok_sel, n = ensure_select()
            if not ok_sel:
                print(f"第{lvl}問 ensure_select 失败，中止", flush=True)
                break
            ok_enter, taps = enter(lvl)
            if not ok_enter:
                print(f"第{lvl}問 进关失败，中止", flush=True)
                break
        rec = rec_start(out)
        select_line_tool()
        pts = ring_path(idx)
        wall = drag_path(pts, **dose)
        ok, waited = wait_completion()
        if ok:
            back, nk = settle_to_select()
        else:
            back, nk = False, -1
        rc = rec_stop(rec)
        size = os.path.getsize(out) if os.path.exists(out) else 0
        row = dict(lvl=lvl, idx=idx, preset=args.preset, board=CFG["size"],
                   verts=len(pts), drag=round(wall, 2),
                   completion=ok, waited=round(waited, 1), back=back,
                   ff_rc=rc, size=size, dose=dose)
        merged[lvl] = row
        print(f"第{lvl}問 idx={idx} 边={len(pts)} drag={wall:.2f}s "
              f"Completion={ok}({waited:.1f}s) 回选关={back} "
              f"mp4={size}B rc={rc}", flush=True)
        if not ok or not back:
            print("  !! 该关未完整闭环，停止后续录制（保留已录片段）", flush=True)
            break

    json.dump([merged[k] for k in sorted(merged)],
              open(logpath, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("录制日志", logpath, "共", len(merged), "关", "终点状态", state(), flush=True)


if __name__ == "__main__":
    main()
