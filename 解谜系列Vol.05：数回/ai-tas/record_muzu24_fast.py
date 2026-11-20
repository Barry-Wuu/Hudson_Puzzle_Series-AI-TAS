#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""むずかしい 24×14（lvl 1..17, idx1623..1639）—— 批量提速画法重录（带音频）。

派生自 record_futsuu24_fast.py，仅改难度相关参数：IDX_BASE/DIFF/OUTDIR/文件名/窗口。
几何(SCROLL_SEQ/DRAW_VIEWS/TAPS)按 24×14 尺寸通用，旧 muzu log 的 views 与 fuzu 一致。

与 18×10 版(record_futsuu18_fast.py)的关键差异：
  - 绘制改用 fast_click_big.draw_all_fast（4 视口滚动 + 批量点中点）。
    ★ AFTER 必须 >=0.25：0.10/0.18 会让相邻边快速连点被识别成拖动，
      产生多余线 -> 线集!=答案 -> チェック不弹 Completion（实测）。
  - 判定用 record_big.judge：它的 finish() 会 touch 到 real_result
    (绿色星结算页, 取得星数/スコア) 并停留 1.8s，因此**视频结尾录到星结算**。
  - 输出新目录 vol5_recordings_muzukashii_24x14_fast，不覆盖旧版拖拽成品。

安全：每关先录 .recording.mp4，判定过关且文件有效才原子落位；断点续录；失败重试。

用法:
  bash boot_audio.sh
  DISPLAY=:99 XDG_RUNTIME_DIR=/tmp \
    CLICK_GAP=0.02 CLICK_HOLD=0.08 CLICK_AFTER=0.25 CHAIN=1 BATCH=24 LEAD=0.25 \
    python3.11 record_muzu24_fast.py --lo 1 --hi 17
"""
import os, sys, time, json, argparse, subprocess
import numpy as np
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ds
import nav18 as N
import slither18 as s18
import record18_v4 as V
import slither_big as SB
import record_big as RB
import record_levels as rl
import fast_click_big as FB

IDX_BASE = 1622
OUTDIR = os.environ.get("REC_OUTDIR", "/workspace/vol5_recordings_muzukashii_24x14_fast")
DIFF = "muzukashii"


def judge_to_stars():
    """点チェック并把画面推进到星结算页(real_result)，停留2s供录像收录。

    返回 (cleared, waited, kind)。★ 关键：必须确认 real_result(绿色取得星数页)
    在画面上为真后才返回，视频才以星结算页结尾——RB.judge 的 finish 会在
    Completion 阶段就返回，导致视频停在 Completion 弹窗（第65問实证）。
    """
    time.sleep(1.2)
    t0 = time.time()
    # 点チェック，低频重试直到出现 Completion 或结算页
    while time.time() - t0 < 26:
        ds.tap(*RB.CHECK_BTN, hold=0.18, after=0.9)
        for _ in range(4):
            if V.completion_anim() or V.real_result():
                break
            time.sleep(0.35)
        if V.completion_anim() or V.real_result():
            break
    if not (V.completion_anim() or V.real_result()):
        return False, time.time() - t0, None
    # 从 Completion 推进到星结算页：touch 直到 real_result "稳定"为真。
    # ★ 关键（2026-11-18）：探针证实真正 star 页不点击可稳定停留 >4.5s；
    #   而"瞬时 real"是误报（tap 恰在过场帧，画面随即翻回 Completion）。
    #   故必须连续 N 次确认为 real 才认定到站，避免瞬时误报导致尾帧无 star。
    t1 = time.time()
    ok = False
    while time.time() - t1 < 14:
        if V.real_result():
            # 连续 4 次(间隔 0.25s)确认为真 = 稳定 star 页
            stable = True
            for _ in range(4):
                time.sleep(0.25)
                if not V.real_result():
                    stable = False
                    break
            if stable:
                ok = True
                break
            # 不稳定 -> 继续 tap 推进到真正的 star 页
        ds.tap(128, 96, hold=0.14, after=0.8)
    if ok:
        time.sleep(1.5)   # 给 ffmpeg/x11grab 缓冲 flush 留出 star 帧写入时间
    return ok, time.time() - t0, ("stars" if ok else "completion-only")


def last_frame_is_star(path):
    """抽视频最后一帧判定是否清晰星结算页，用于落位前自检。
    判据与 V.real_result 一致（绿底+中蓝+下屏无橙），但对暗化/セーブ中页鲁棒。"""
    probe = os.path.join("/tmp", f"v5_last_{os.getpid()}.png")
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-sseof", "-0.5",
                        "-i", path, "-frames:v", "1", probe],
                       capture_output=True)
    try:
        if r.returncode != 0 or not os.path.exists(probe):
            return False, None
        a = np.asarray(Image.open(probe).convert("RGB")).astype(int)
        if a.shape[0] < 300:
            return False, None
        t, b = a[0:192], a[192:384]
        R, G, B = t[:, :, 0], t[:, :, 1], t[:, :, 2]
        green = float(((G > R + 25) & (G > B + 25) & (G > 80)).mean())
        mid = t[45:115]; Rm, Gm, Bm = mid[:, :, 0], mid[:, :, 1], mid[:, :, 2]
        blue = float(((Bm > Rm + 25) & (Bm > Gm + 5) & (Bm > 90)).mean())
        Rb, Gb, Bb = b[:, :, 0], b[:, :, 1], b[:, :, 2]
        orange = int(((Rb > 150) & (Gb > 60) & (Gb < 175) & (Bb < 110)).sum())
        return (green > 0.42 and blue > 0.15 and orange < 500), (round(green, 3), round(blue, 3), orange)
    finally:
        if os.path.exists(probe):
            os.remove(probe)


def record_one(lvl, force=False, retries=3):
    idx = IDX_BASE + lvl
    final_out = os.path.join(OUTDIR, f"数回_むずかしい24x14_第{lvl:02d}問.mp4")
    tmp_out = os.path.join(OUTDIR, f".第{lvl:02d}問.recording.mp4")
    if not force and os.path.exists(final_out) and os.path.getsize(final_out) > 20000:
        return dict(lvl=lvl, idx=idx, skip=True, ok=True, size=os.path.getsize(final_out))

    for attempt in range(1, retries + 1):
        # 稳健进关：到ふつう选关页 -> 滚到窗口2 -> 进关 -> 视口复位校验
        if not RB.to_select_of(DIFF):
            print(f"L{lvl}: 无法到选关页（第{attempt}次）", flush=True)
            continue
        N.goto_window(1)
        ok, _ = N.enter_level(lvl)
        if not ok or not RB.ensure_board(lvl, DIFF):
            print(f"L{lvl}: 进关/净盘失败（第{attempt}次）", flush=True)
            continue
        M0 = SB.measure(idx)
        if (M0["r0"], M0["c0"]) != (0, 0) or M0["score"] < 110:
            print(f"L{lvl}: 视口未复位 {M0['r0']},{M0['c0']} score={M0['score']}，重来", flush=True)
            continue

        if os.path.exists(tmp_out):
            os.remove(tmp_out)
        rec = rl.rec_start(tmp_out)
        t0 = time.time()
        cleared, waited, kind = False, 0.0, None
        rc = None
        try:
            pts, nv, rem = FB.draw_all_fast(idx, verbose=False)
            cleared, waited, kind = judge_to_stars()   # 推进到星结算页并停留，视频以星结算结尾
            rc = rl.rec_stop(rec); rec = None
        finally:
            if rec:
                rl.rec_stop(rec); rc = -9
        draw_s = time.time() - t0
        size = os.path.getsize(tmp_out) if os.path.exists(tmp_out) else 0
        # ★ 落位前自检：结尾帧必须是清晰星结算页，否则重试（用户要求带星结算）
        star_ok, metr = (False, None)
        if cleared and size > 20000:
            star_ok, metr = last_frame_is_star(tmp_out)
        if cleared and size > 20000 and star_ok:
            os.replace(tmp_out, final_out)
            print(f"L{lvl} idx{idx}: OK 视口{nv} 点{pts}边 剩{rem} 画{draw_s:.1f}s "
                  f"结算={kind} 尾帧星={metr} size={size} att={attempt}", flush=True)
            return dict(lvl=lvl, idx=idx, pts=pts, views=nv, remaining=rem,
                        ok=True, draw=round(draw_s, 1), result=kind, judge_s=round(waited, 1),
                        size=size, attempt=attempt, ff_rc=rc, cleared=True, tail_star=True)
        why = "尾帧非星结算" if (cleared and size > 20000) else "未过关/坏文件"
        print(f"L{lvl} idx{idx}: {why}（第{attempt}次）画{draw_s:.1f}s "
              f"结算={kind} 尾帧={metr} size={size}", flush=True)
        if os.path.exists(tmp_out):
            # 诊断：保留最后一次失败视频供抽帧取证（正式跑完可删 KEEP_FAIL）
            if os.environ.get("KEEP_FAIL"):
                keep = f"/tmp/fail_{lvl}_a{attempt}.mp4"
                os.replace(tmp_out, keep)
                print(f"  [诊断] 失败视频保留到 {keep}", flush=True)
            else:
                os.remove(tmp_out)
    return dict(lvl=lvl, idx=idx, ok=False, cleared=False, attempt=retries)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lo", type=int, default=1)
    ap.add_argument("--hi", type=int, default=17)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--retries", type=int, default=6)
    a = ap.parse_args()
    os.makedirs(OUTDIR, exist_ok=True)
    logpath = os.path.join(OUTDIR, "record_log.json")
    merged = {}
    if os.path.exists(logpath):
        try:
            merged = {r["lvl"]: r for r in json.load(open(logpath, encoding="utf-8"))}
        except (ValueError, OSError):
            pass
    print(f"输出 {OUTDIR} GAP={FB.GAP} HOLD={FB.HOLD} AFTER={FB.AFTER} "
          f"BATCH={FB.BATCH} LEAD={FB.LEAD}", flush=True)
    if not s18.is_select_ui():
        N.goto_muzukashii_select()
    RB.to_select_of(DIFF)
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
