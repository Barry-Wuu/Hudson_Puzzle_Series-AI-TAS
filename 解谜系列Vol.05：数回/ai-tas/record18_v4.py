#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vol.05 数回 —— 18x10（やさしい 93~100）连续录制（v4，生产版）。

关键实机行为：通关后按 A 不是回选关页，而是**直接进入下一关**（上屏 HUD 变
第 N+1 問）。因此 93~100 可以一条链录下来：每关只需「画 -> 补 -> チェック -> A」。

正确性自校验：每关都按 puzzles.json 里该关的官方单环画，若关卡号错位则判定
必然失败（不会静默录错），因此「过关」本身就是关卡号正确的证明。

用法:
    bash ai-tas/boot_audio.sh
    python3 ai-tas/record18_v4.py --lo 95 --hi 100
    python3 ai-tas/record18_v4.py --lo 95 --hi 95 --dry
"""
import argparse
import json
import numpy as np
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ds                      # noqa: E402
import nav18 as N              # noqa: E402
import record_levels as rl     # noqa: E402
import slither18 as s18        # noqa: E402

OUTDIR = "/workspace/vol5_recordings_18x10"

# 难度档：模式选择页按钮坐标 + 题库 idx 基数 + 关数
#   やさしい 1..92 = 10x10、93..100 = 18x10（idx = 1422 + 关号）
#   ふつう   1..64 = 18x10、65..100 = 24x14（idx = 1522 + 关号）
#   むずかしい 1..17 = 24x14、18..50 = 36x20（idx = 1622 + 关号）
DIFFS = {
    "yasashii":   dict(label="やさしい",   tap=(176, 86),  base=1422, total=100),
    "futsuu":     dict(label="ふつう",     tap=(176, 127), base=1522, total=100),
    "muzukashii": dict(label="むずかしい", tap=(176, 167), base=1622, total=50),
}
CHECK_BTN = (190, 178)
MISS_TH = 80
MAX_LEVEL_S = 210          # 单关硬上限：超过就不再补边，保证整批不撞命令超时

# 结算页左上标签的二值字形模板（结算页配色固定，不随 RANDOM 变）。
# 实机实测：同为「クリア済」的两帧 xor=12；「未クリア」与「クリア済」xor=172。
# 只判断「进没进结算页」会把「未クリア」误报成过关（ふつう 第2問 曾因此漏检）。
try:
    _TP = np.load(os.path.join(HERE, "result_templates.npz"))
    TP_CLEAR = _TP["clear"]
    TP_FAIL = _TP["fail"]
except (OSError, KeyError):
    TP_CLEAR = TP_FAIL = None
try:
    TP_COMPLETION = np.load(os.path.join(HERE, "completion_template.npz"))["mask"]
except (OSError, KeyError):
    TP_COMPLETION = None


def result_kind(a=None):
    """'clear'(クリア済/历史有记录) / 'first'(未クリア/历史无记录，即首次通关) / None。

    注意：「未クリア」不是本次失败！实测 ふつう 第2問 出现 "Completion!!" 后
    结算页就是「未クリア + 空心星 + 00:00:00」，表示这关之前没通关过；
    やさしい 第97/99 問（确定已通关）也是这个页面。真正的失败是点了チェック
    后压根不进结算页（上屏不变）。
    """
    if TP_CLEAR is None:
        return None
    a = top_rgb() if a is None else a
    r = a[15:50, 5:120]
    R, G, B = r[:, :, 0], r[:, :, 1], r[:, :, 2]
    m = ((B > 70) & (B > R + 25) & (B > G + 10)).astype(np.uint8)
    dc = int((m ^ TP_CLEAR).sum())
    df = int((m ^ TP_FAIL).sum())
    if min(dc, df) > 60:
        return None                      # 还在盘面/别的画面
    return "clear" if dc < df else "first"


def completion_anim():
    """下屏中央 "Completion!!" 橙色大字 —— 用二值模板，不用颜色阈值。

    颜色阈值踩过两次坑：橙色主题的数字、以及整条橙色横幅都会误报
    （第9/10問 因此 13.7s / 0.6s 就停手）。实测：
      真演出(02 t92 / 04 t120)：橙 3416/3415、模板 xor 0/87、白 1541/1713
      误检(09/10 开盘)      ：橙 98~1707、模板 xor 3500+、白 455~2755
    """
    if TP_COMPLETION is None:
        return False
    a = s18.bot_rgb()
    r = a[70:135, 30:230]
    R, G, B = r[:, :, 0], r[:, :, 1], r[:, :, 2]
    m = ((R > 150) & (G > 60) & (G < 175) & (B < 110)).astype(np.uint8)
    if int(m.sum()) <= 2500:
        return False
    if int((m ^ TP_COMPLETION).sum()) > 600:
        return False
    return int(((R > 215) & (G > 215) & (B > 215)).sum()) > 900


def real_result():
    # 上屏是否已进入真正通关结算页（绿色底 + クリアタイム/取得星数）
    # 实测：真结算页 上屏绿0.66/下屏橙0；Completion 弹窗 上屏绿0/下屏橙1100~4700
    #       RANDOM 绿橙蓝盘面 上屏绿<=0.34，不误触发；结算页配色不随 RANDOM 变
    a = np.asarray(ds.grab(None).convert("RGB")).astype(int)
    t, b = a[0:192], a[192:384]
    R, G, B = t[:, :, 0], t[:, :, 1], t[:, :, 2]
    green = float(((G > R + 25) & (G > B + 25) & (G > 80)).mean())
    mid = t[45:115]; Rm, Gm, Bm = mid[:, :, 0], mid[:, :, 1], mid[:, :, 2]
    blue_mid = float(((Bm > Rm + 25) & (Bm > Gm + 5) & (Bm > 90)).mean())
    Rb, Gb, Bb = b[:, :, 0], b[:, :, 1], b[:, :, 2]
    orange = int(((Rb > 150) & (Gb > 60) & (Gb < 175) & (Bb < 110)).sum())
    # 真结算页 绿0.66/中蓝0.247/下屏橙0；成绩页 绿0.41~0.53/中蓝0.09/下屏橙1700
    return green > 0.45 and blue_mid > 0.18 and orange < 300


def settled():
    """是否已经判定完成。

    认两种终局画面：Completion!! 弹窗（补齐最后一条边瞬间弹出）、以及触摸
    确认后的真结算页。必须两者都认：只认弹窗时，弹窗被确认进真结算页后
    go()/toggle() 会继续点滑块，把结算页点回选关页（ふつう 第3問 实测片尾
    25 秒全是选关页）。不认 result_kind() 成绩页（进关初期短暂显示，曾让
    第6問 1.9s 误停手）；实测成绩页/选关页 中蓝<=0.095、下屏橙>1600，
    real_result() 的三重判据不会误报。
    """
    return completion_anim() or real_result()


def draw_pass(idx, cur, base):
    """逐条边绘制。返回 (cur, stopped)；stopped=已自动结算，不可再动屏幕。"""
    edges = s18.edges_of(idx)
    a = [e for e in edges if s18.view_of_edge(*e) == "A"]
    b = [e for e in edges if s18.view_of_edge(*e) == "B"]
    # 基线采集只靠 toggle() 的「整屏均差>4」判成功，不保证实际档位。开画前
    # 用 which_view() 闭环强制确认在 A 档，否则 A 段 141 条边会画在 B 档坐标上
    # （第35問 实测核查结果忽 2 忽 9、补边分数为 0，疑似档位错乱）。
    cur, _ = s18.go("A", cur, base)
    for e in a:
        s18.draw_line(*e, "A")
        if settled():
            print("  !! A 段绘完前已自动结算，立即停手", flush=True)
            return cur, True
    if settled():
        return cur, True
    ok = False
    for attempt in range(3):
        cur, ok = s18.go("B", cur, base)
        if ok:
            break
        print(f"  .. 切 B 档第{attempt + 1}次未生效，重试", flush=True)
        time.sleep(1.5)
    if not ok:
        if settled():                       # go() 被 STOP_HOOK 挡住 = 已自动结算
            return cur, True
        print("  !! 切 B 档多次失败，本关大概率不过", flush=True)
    for e in b:
        s18.draw_line(*e, "B")
        if settled():
            print("  !! B 段绘完前已自动结算，立即停手", flush=True)
            return cur, True
    print(f"  A {len(a)} + B {len(b)} 边绘完", flush=True)
    return cur, False


def repair(idx, cur, base, rounds=6, deadline=None, stopped=False):
    """净盘差分核查 + 补边。每一步都先查是否已自动结算——否则继续点滑块会
    把结算页误操作成「タイトルへ戻る」（第2問 曾因此在 Completion!! 后回标题）。
    """
    fixed = 0
    left = 0
    if stopped:
        print("  已自动结算，跳过核查", flush=True)
        return cur, 0, fixed
    for it in range(rounds):
        if settled():
            print("  !! 核查前已自动结算，立即停手", flush=True)
            return cur, 0, fixed
        if deadline and time.time() > deadline:
            print("  !! 核查触及单关时限，停止补边", flush=True)
            return cur, left, fixed
        missing = []
        for v in ("A", "B"):
            if settled():
                return cur, 0, fixed
            cur, _ = s18.go(v, cur, base)
            if settled():
                return cur, 0, fixed
            sc = s18.score_edges(base[v], s18.shot(), idx, v)
            missing += [(e, v) for e, s in sc.items() if s < MISS_TH]
        print(f"  核查#{it} 缺 {len(missing)} {[e for e, _ in missing][:8]}", flush=True)
        left = len(missing)
        if not missing:
            return cur, 0, fixed
        # 不再补边：实测「核查缺 1~2 条（几乎都是 r=10 底边）后再补」会把已画
        # 好的回路 toggle 坏，连续多次不过关（ふつう 11/13 関）；而逐边画一次
        # 就缺 0 补 0 的关全部成功。缺边直接判失败，交给 run() 自动重录整关。
        print(f"  !! 缺 {left} 条边，不补边，交自动重试整关重录", flush=True)
        return cur, left, fixed
    return cur, left, fixed


def top_rgb():
    return np.asarray(ds.grab(None).convert("RGB").crop((0, 0, 256, 192))).astype(int)


def judge(timeout=16.0):
    """判定 -> 触摸确认 -> 停在真正的通关结算页。返回 (过关, 耗时, 标签)。

    实机链路：画完最后一条边 -> 下屏弹出 "Completion!!" + "Please touch!"
    （等触摸，按 A 无效）-> 触摸 -> 上屏变「- ふつう - / 第N問 / クリアタイム /
    取得星数」真结算页。「クリア済 / 未クリア + ベストタイム + マス」是另一个
    成绩页/选关预览，绝不能据此判过关（ふつう 11/12/13 假过关根因）。
    触摸确认会被吞（第10問 片尾 6 秒都停在 Completion!!），故循环 tap 直到
    real_result() 为真；仍不进结算页就如实判失败，绝不假报过关。
    """
    def finish(tag, t0):
        ok = False
        for _ in range(6):
            if real_result():
                ok = True
                break
            ds.tap(128, 96, hold=0.15, after=1.0)   # 确认 "Please touch!"
        else:
            ok = real_result()
        time.sleep(1.8)                             # 结算演出稳定，片尾停在结算页
        return ok, time.time() - t0, tag if ok else "touch-failed"

    t0 = time.time()
    if real_result():                        # 已自动完成触摸（少见）
        return True, time.time() - t0, "result-auto"
    ds.tap(*CHECK_BTN, hold=0.18, after=1.0)   # チェック
    while time.time() - t0 < timeout:
        if completion_anim() or real_result():  # 只认 Completion!! / 真结算页
            return finish("completion", t0)
        time.sleep(0.3)
    return False, time.time() - t0, None


def advance():
    """按 A 前进：通常是直接进下一关；若回选关页则返回 False。"""
    ds.press("x", wait=2.6)
    if s18.is_select_ui():
        return False
    N.wait_start_anim()
    return True


def on_board():
    a = s18.bot_rgb()
    r = a[10:30, 150:252]
    # 实测：盘面 0.00~0.21（主题不同会有深浅差），选关页 0.39~0.41，难度选择 0.82
    return float((r.sum(axis=2) < 260).mean()) < 0.30


def to_select_of(diff):
    """切到指定难度的选关页：盘面先退出 -> B 回难度选择 -> 点难度。

    必须确保「真的离开了选关页」才能点难度按钮；否则 tap 只是点在格子上，
    会假成功（is_select_ui 仍 True）而实际停在原难度，录出错关。
    """
    ds.ensure_window()                          # 按键需要窗口焦点，漏了 B 会无效
    if on_board():
        N.leave_level()
    if s18.is_select_ui():
        ds.press("z", wait=1.8)                 # B：回难度选择
        time.sleep(0.6)
        if s18.is_select_ui():                  # B 没生效，点左下「B 戻る」兜底
            ds.tap(48, 165, hold=0.15, after=1.8)
    if s18.is_select_ui():
        print("  !! 无法离开选关页，难度切换不可靠", flush=True)
        return False
    for _ in range(4):
        ds.tap(*DIFFS[diff]["tap"], hold=0.12, after=1.8)
        time.sleep(0.4)
        if s18.is_select_ui():
            return True
    return False


def ensure_board(lvl, diff):
    """每关开场确保停在 **lvl 的干净盘面** 再采基线。

    实机：通关后按 A 只推进到「未クリア/クリア済 + ベストタイム + マス」的
    关卡成绩页（不是下一关净盘）。若直接开画，开头若干次触摸会被成绩页吞掉，
    丢十几条边导致判定失败（第8問 就是这样）。成绩页触摸一下即进净盘。
    """
    for i in range(6):
        if real_result():                      # 上一关真结算页残留，按 A 推进
            ds.press("x", wait=1.2)
            time.sleep(0.3)
            continue
        k = result_kind()
        if k is None and not completion_anim() and not s18.is_select_ui():
            return True
        if s18.is_select_ui():
            if not to_select_of(diff):
                return False
            N.goto_window(51 if lvl > 50 else 1)
            ok, _ = N.enter_level(lvl)
            if not ok:
                return False
            N.wait_start_anim()
        else:
            ds.tap(128, 96, hold=0.12, after=1.1)      # 成绩页：触摸确认
            time.sleep(0.3)
            if result_kind() is not None:
                ds.press("x", wait=1.1)
        time.sleep(0.3)
    return result_kind() is None


def run(lo, hi, dry, force, outdir, diff="yasashii", assume_board=False, retries=3):
    # 关键接线：让 slither18.go()/toggle() 每次点滑块前先查「是否已判定完成」。
    # 否则最后一条边补齐后弹出的 Completion!! / Please touch! 会被连续点掉，
    # 确认回标题，judge() 就永远看不到 Completion!!（ふつう 11/12/13 假过关根因）。
    s18.STOP_HOOK = settled
    os.makedirs(outdir, exist_ok=True)
    ds.ensure_window()
    base_idx = DIFFS[diff]["base"]
    label = DIFFS[diff]["label"]
    logpath = os.path.join(outdir, "record_log.json")
    merged = {}
    if os.path.exists(logpath):
        try:
            merged = {r["lvl"]: r for r in json.load(open(logpath, encoding="utf-8"))}
        except (ValueError, OSError):
            pass

    for lvl in range(lo, hi + 1):
        idx = base_idx + lvl
        out = os.path.join(outdir, f"数回_{label}18x10_第{lvl:02d}問.mp4")
        if not dry and not force and os.path.exists(out) and os.path.getsize(out) > 20000:
            print(f"第{lvl}問 已存在，跳过", flush=True)
            continue
        cleared = False
        for attempt in range(1, retries + 1):
            if attempt > 1:
                print(f"  ↻ 第{lvl}問 第{attempt}次重录（上次未过关，已删坏文件）", flush=True)
            # 每关/每次都重新导航进关，禁用 chained 连关：通关后按 A 从真结算页
            # 并不会进下一关，连关会录错关（第4問实测片尾 HUD 仍是「第3問」）。
            if assume_board and lvl == lo and attempt == 1:
                taps = 0
            else:
                if not to_select_of(diff):
                    print("  !! 无法回到目标难度选关页，重试", flush=True)
                    continue
                N.goto_window(51 if lvl > 50 else 1)
                ok, taps = N.enter_level(lvl)
                if not ok:
                    print(f"  !! 第{lvl}問 进关失败，重试", flush=True)
                    continue
            if not ensure_board(lvl, diff):
                print(f"  !! 第{lvl}問 无法进入干净盘面，重试", flush=True)
                continue
            cur = "A"
            base = {}
            ok1 = ok2 = False
            for _try in range(3):
                base["A"] = s18.shot()
                cur, ok1 = s18.toggle("A")
                base["B"] = s18.shot()
                cur, ok2 = s18.toggle("B")
                if ok1 and ok2:
                    cur = "A"
                    break
                time.sleep(2.5)          # START 演出未结束，等一下重来
            print(f"第{lvl}問 idx={idx} 尝试{attempt} 进关(tap{taps}) 基线={ok1}/{ok2} 档={cur}", flush=True)

            rec = None if dry else rl.rec_start(out)
            t0 = time.time()
            wall = 0.0
            left = fixed = 0
            cleared, waited, kind, went_next, rc = False, 0.0, None, False, None
            try:
                cur, stopped = draw_pass(idx, cur, base)
                cur, left, fixed = repair(idx, cur, base,
                                          deadline=t0 + MAX_LEVEL_S - 25, stopped=stopped)
                wall = time.time() - t0
                cleared, waited, kind = judge()
                rc = rl.rec_stop(rec) if rec else None  # 先停录，保证片尾停在结算页
                rec = None
                went_next = advance() if cleared else False
            finally:
                if rec:                                 # 异常兜底，保证 mp4 可播放
                    rl.rec_stop(rec)
                    rc = -9
            size = os.path.getsize(out) if (not dry and os.path.exists(out)) else 0
            merged[lvl] = dict(lvl=lvl, idx=idx, board="18x10", edges=len(s18.edges_of(idx)),
                               diff=diff, draw=round(wall, 1), missing_left=int(left), fixed=int(fixed),
                               cleared=bool(cleared), result=kind, next=bool(went_next),
                               judge_s=round(waited, 1), ff_rc=rc, size=size, attempt=attempt)
            print(f"第{lvl}問 画+修 {wall:.1f}s 缺{left} 补{fixed} 结算={kind} "
                  f"过关={cleared}({waited:.1f}s) →下一关={went_next} mp4={size}B", flush=True)
            json.dump([merged[k] for k in sorted(merged)], open(logpath, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
            if cleared:
                break
            # 失败：删掉坏 mp4，下一轮重新导航重录
            if not dry and os.path.exists(out):
                os.remove(out)
        if not cleared:
            print(f"  !! 第{lvl}問 {retries} 次仍未过关，停批", flush=True)
            break
    print("结束。日志", logpath, "共", len(merged), "关", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lo", type=int, default=95)
    ap.add_argument("--hi", type=int, default=100)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--outdir", default=None)
    ap.add_argument("--diff", choices=list(DIFFS), default="yasashii")
    ap.add_argument("--assume-board", action="store_true", help="已手工停在 --lo 的盘面上，跳过导航")
    ap.add_argument("--retries", type=int, default=3, help="单关最多尝试次数（顽固关可调大）")
    a = ap.parse_args()
    od = a.outdir or (OUTDIR if a.diff == "yasashii" else f"/workspace/vol5_recordings_{a.diff}_18x10")
    run(a.lo, a.hi, a.dry, a.force, od, a.diff, a.assume_board, a.retries)
