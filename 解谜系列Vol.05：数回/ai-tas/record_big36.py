#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vol.05 数回 —— 36x20 大盘连续录制（むずかしい 18~50）。

判定链路与 18x10（record18_v4.py）完全共用：
  Completion!!（下屏橙字模板）-> tap(128,96) 触摸确认 -> 真结算页
  （上屏绿色竹叶底 + 蓝色 クリアタイム/取得星数 横幅，real_result 三重判据）。

绘制链路改用 slither_big36：15 步蛇形 / 9 视口遍历逐边画 + 每视口净盘差分核查。
每关独立导航（禁用 chained 连关），失败自动删坏 mp4 整关重录。

用法:
    bash ai-tas/boot_audio.sh
    python3 ai-tas/record_big36.py --diff muzukashii --lo 18 --hi 50
    python3 ai-tas/record_big36.py --diff muzukashii --lo 18 --hi 18 --dry
"""
import argparse
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ds                      # noqa: E402
import nav18 as N              # noqa: E402
import record_levels as rl     # noqa: E402
import slither18 as s18        # noqa: E402
import record18_v4 as V        # noqa: E402  判据共用
import slither_big36 as SB       # noqa: E402  36x20 绘制核心

# 36x20 チェック 按钮（下屏 y=174..190 一排，チェック x≈175..214 中心 195,182）
CHECK_BTN = (195, 182)

DIFFS = {
    #   36x20 只用 muzukashii 档：idx = 1622 + 关号（第18問 idx1640）
    #   futsuu 档保留供 24x14 脚本复用，本脚本不使用
    "futsuu":     dict(label="ふつう",     tap=(176, 127), base=1522, total=100),
    "muzukashii": dict(label="むずかしい", tap=(176, 167), base=1622, total=50),
}
MISS_TH = 80
MAX_LEVEL_S = 900              # 36x20 边数翻倍，单关硬上限放大


def settled():
    return V.settled()


def _bottom():
    return np.asarray(ds.grab(None).convert("RGB")).astype(int)[192:384]


def _bright_sat(b):
    """下屏中部「亮饱和像素」数：Completion!! 大字（橙红+白描边）的量化特征。

    板面本身是淡绿（sat<110），题面数字是暗绿，所以大字一出现该值暴涨。
    实测第19問（RANDOM 主题）：点击前 2943 -> 出字 5285~5411（+2300）。
    """
    R, G, B = b[:, :, 0], b[:, :, 1], b[:, :, 2]
    mx = np.maximum(np.maximum(R, G), B)
    mn = np.minimum(np.minimum(R, G), B)
    m = ((mx - mn) > 110) & (mx > 170)
    return int(m[84:152, 50:250].sum())


def _result_page():
    """真结算页：上屏大面积纯绿成绩板（实测 0.615；盘面/Completion 页均 0）。"""
    a = np.asarray(ds.grab(None).convert("RGB")).astype(int)[0:192]
    R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    return float(((G > 120) & (R < 90) & (B < 90)).mean()) > 0.45


def judge(timeout=26.0):
    """36x20 判定（主题无关）。

    ★ 2026-11-13 根因：旧版靠 V.completion_anim()（24x14 那套固定模板 +
      橙色阈值）与 V.real_result()（要求上屏绿色>0.45 **且中部蓝色横幅**
      >0.18）。BGM / デザイン = RANDOM 会**每关换主题**，大字字体配色与
      成绩页配色都跟着变：第19問实测 Completion!! 明明已弹出并给出
      5 星 / クリアタイム 00:06:14，两个判据却全 False，于是把成功当失败、
      还删掉了已录好的 mp4（多轮「结算=None」都是假失败）。
      改法：只用**相对基准帧的差分**——点チェック前记下下屏中部亮饱和
      像素数，点击后该值暴涨 >800 即 Completion 出现；进结算页后用上屏
      绿色占比 >0.45 复核。两者都与主题无关。
    """
    def finish(tag, t0):
        # 点触离开 "Please touch!" -> 真结算页（让视频末帧停在成绩页）
        for _ in range(6):
            ds.tap(128, 96, hold=0.15, after=1.3)
            if _result_page() or V.real_result():
                break
        time.sleep(0.8)
        return True, time.time() - t0, tag

    time.sleep(1.2)                                  # 末条边触摸释放 / 动画稳定
    t0 = time.time()
    base = _bright_sat(_bottom())
    if V.completion_anim() or V.real_result() or _result_page():
        return finish("completion", t0)
    while time.time() - t0 < timeout:
        # ★ 2026-11-13 改成「单击 + 长等」：Completion!! 实测在点击后
        #   1.5~2.0s 才完整出现，旧版每 0.85s 补点一次会把刚弹出的大字
        #   立刻打断（判据永远抓不到），还可能在 Please touch! 页误触。
        ds.tap(*CHECK_BTN, hold=0.18, after=0.9)
        for _ in range(25):                          # ~5s 静观
            cur = _bright_sat(_bottom())
            if cur - base > 800 or V.completion_anim() or V.real_result():
                try:
                    ds.grab(None).save(f"/tmp/vol5_completion_{int(time.time())}.png")
                except Exception:
                    pass
                return finish("completion", t0)
            time.sleep(0.2)
    # 超时：留一张当时整屏截图供诊断（到底停在盘面 / まちがい / Completion），
    # 并输出「彩虹高亮错线段」的位置——判定为错时游戏会用它指出错线所在，
    # 这是与主题无关、也不依赖 measure 的**外部线索**，可反查哪条边画错。
    try:
        im = ds.grab(None)
        im.save(f"/tmp/vol5_judge_fail_{int(time.time())}.png")
        b = np.asarray(im.convert("RGB")).astype(int)[192:384]
        R, G, B = b[:, :, 0], b[:, :, 1], b[:, :, 2]
        mx = np.maximum(np.maximum(R, G), B)
        mn = np.minimum(np.minimum(R, G), B)
        rb = ((mx - mn) > 110) & (mx > 150) & ((G > 80) | (B > 80))
        ys, xs = np.where(rb)
        if len(ys) > 20:
            print(f"  · 错线彩虹高亮 bbox x={xs.min()}..{xs.max()} "
                  f"y={ys.min()}..{ys.max()} px={len(ys)}", flush=True)
    except Exception:
        pass
    return False, time.time() - t0, None


def on_board():
    return s18.bot_rgb() is not None and float(
        (s18.bot_rgb()[10:30, 150:252].sum(axis=2) < 260).mean()) < 0.30


def ensure_random(diff, lo, evidence_dir=None):
    """段首复验 BGM / デザイン = ランダム（与 record_levels.setup_random 同判据）。

    设置随 SRAM 持久化：若已是 RANDOM 红底则跳过点击，避免误切；
    否则补点两行「ランダム」。随后关面板回到干净盘面，供首关 assume_board 复用。
    """
    # ★ 2026-11-14 冷启动偶发时序重试：从 标题→主菜单→スタート 的过渡、
    #   或「关卡详情/成绩页」被 is_select_ui() 误判为选关页时，单次
    #   to_select_of/enter_level 会失败并让整批直接终止（实测批量 41/41b）。
    #   RANDOM 是 SRAM 全局设置，只要能进任一关的オプション面板即可校验，
    #   故最多重试 4 轮：每轮重新收敛到选关页并再进首关，失败就按 B /
    #   点「レベル選択に戻る」强制回退后再来，避免整批因导航抖动报废。
    entered = False
    for _att in range(1, 5):
        if to_select_of(diff):
            N.goto_window(51 if lo > 50 else 1)
            ok, _ = N.enter_level(lo)
            if ok:
                entered = True
                break
        print(f"  !! ensure_random: 第{_att}轮导航/进首关失败，回退重来", flush=True)
        ds.press("z", wait=0.8)                 # B(戻る)
        ds.tap(36, 170, hold=0.15, after=1.2)  # レベル選択に戻る / もどる
        time.sleep(1.0)
    if not entered:
        print("  !! ensure_random: 进首关失败（4 轮），RANDOM 未校验，禁止录制",
              flush=True)
        return False
    N.wait_start_anim()
    b = rl.bot()
    for k in range(4):
        ds.tap(235, 180, hold=0.20, after=2.0)   # オプション
        b = rl.bot()
        if rl.is_option(b):
            break
    else:
        print("  !! ensure_random: オプション面板未打开", flush=True)
        return False
    ok_rand, vals = rl.random_set(b)
    if not ok_rand:
        ds.tap(232, 66, hold=0.15, after=1.2)    # BGM -> ランダム
        ds.tap(232, 90, hold=0.15, after=1.2)    # デザイン -> ランダム
        b = rl.bot()
        ok_rand, vals = rl.random_set(b)
    print(f"  RANDOM 红底像素 BGM/デザイン={vals} 已持久化={ok_rand}", flush=True)
    if not ok_rand:
        print("  !! ensure_random: RANDOM 设置校验失败", flush=True)
        return False
    ds.tap(70, 172, hold=0.30, after=2.0)        # 問題を再開する -> 关面板
    # ★ 2026-11-13：返回值只以 ok_rand（オプション面板 BGM/デザイン 红底像素
    #   校验，主题无关）为准。rl.state() 的颜色判据在暖色(米黄)RANDOM 主题下
    #   会把**干净盘面**误报为 "completion"（实测第21問进关 TIME 00:00:00、
    #   下屏纯数字格无红线，却判 completion），旧版 return rl.state()=="board"
    #   会让暖色主题的关直接「ensure_random 失败」终止整批。
    #   RANDOM 是 SRAM 持久化全局设置，校验通过即生效；run() 随后会 leave_level
    #   清盘并由主循环逐关重新进关，ensure_board 再兜底净盘检查。
    print(f"  RANDOM 已设并校验（第{lo}問面板），画面状态 {rl.state()}（仅诊断）", flush=True)
    return ok_rand


def to_select_of(diff):
    """回到 むずかしい 选关页（36x20 只用 むずかしい，无需切换难度）。

    ★ 2026-11-13 重写：原逻辑在到达选关页后又按 B(戻る) 退回メインメニュー、
      再点难度按钮——而 むずかしい 选关页内并无难度切换按钮，导致永远返回
      False、整批停批。实测 むずかしい 选关页已是目标页，故直接复用
      goto_muzukashii_select 收敛到该页即可。
    """
    ds.ensure_window()
    ok = N.goto_muzukashii_select()
    if not ok:
        print("  !! to_select_of: 无法回到むずかしい选关页", flush=True)
        return False
    print("  · 已在むずかしい选关页", flush=True)
    return True


def _board_red_px():
    """下屏盘面区的红色像素数（排除底栏 / 右滚动条 / 顶部标签）。

    净盘实测 2~20（橙色 ×备忘 + 虚线光标框）；一旦带着上一轮半成品解答
    重进（实测 4377），重画会把已有线 toggle 擦掉，整关必废。
    """
    b = np.asarray(ds.grab(None).convert("RGB")).astype(int)[192:384]
    R, G, B = b[:, :, 0], b[:, :, 1], b[:, :, 2]
    m = (R > 190) & (G < 95) & (B < 95) & (R > G + 100)
    m[168:, :] = False
    m[:, 244:] = False
    m[:12, :] = False
    return int(m.sum())


def ensure_board(lvl, diff):
    """开场确保停在 lvl 的干净盘面（跳过进关成绩页 / 残留结算页 / 脏盘）。"""
    for i in range(6):
        if V.real_result():
            ds.press("x", wait=1.2)
            time.sleep(0.3)
            continue
        k = V.result_kind()
        if k is None and not V.completion_anim() and not s18.is_select_ui():
            # ★ 2026-11-13 净盘闸门：36x20 的解答会随「解答中データ」保留，
            #   上一轮被中断（超时/被杀）后重进会带着半成品线（实测 4377 px）。
            #   在脏盘上重画 = 把同名边 toggle 擦掉，必然缺边且判定失败。
            n = _board_red_px()
            if n < 300:
                return True
            print(f"  · 盘面残留 {n} 红像素，清盘重进", flush=True)
            N.leave_level()
            time.sleep(1.0)
            continue
        if s18.is_select_ui():
            if not to_select_of(diff):
                return False
            N.goto_window(51 if lvl > 50 else 1)
            ok, _ = N.enter_level(lvl)
            if not ok:
                return False
            N.wait_start_anim()
        else:
            ds.tap(128, 96, hold=0.12, after=1.1)
            time.sleep(0.3)
            if V.result_kind() is not None:
                ds.press("x", wait=1.1)
        time.sleep(0.3)
    return V.result_kind() is None


def run(lo, hi, dry, force, outdir, diff, assume_board=False, retries=3):
    SB.STOP_HOOK = settled
    os.makedirs(outdir, exist_ok=True)
    ds.ensure_window()
    # 段首复验 RANDOM（BGM / デザイン 始终 = ランダム），回到首关干净盘面
    if not ensure_random(diff, lo, os.path.join(HERE, "evidence")):
        print("!! ensure_random 失败：RANDOM 未设上，禁止录制非 RANDOM 视频，终止", flush=True)
        return {}
    # 36x20：RANDOM 面板检查用过的盘面可能被存档里的「解答中データ」污染
    # （实测 ensure_random 打印 completion），绝不复用到录制。强制清盘回选关页，
    # 由主循环逐关重新进关，保证每次都从净盘开始。
    if not s18.is_select_ui():
        N.leave_level()
    started_board = False
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
        out = os.path.join(outdir, f"数回_{label}36x20_第{lvl:02d}問.mp4")
        if not dry and not force and os.path.exists(out) and os.path.getsize(out) > 20000:
            print(f"第{lvl}問 已存在，跳过", flush=True)
            continue
        cleared = False
        for attempt in range(1, retries + 1):
            if attempt > 1:
                print(f"  ↻ 第{lvl}問 第{attempt}次重录（上次未过关，已删坏文件）", flush=True)
            if (assume_board or started_board) and lvl == lo and attempt == 1:
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
                N.wait_start_anim()
            if not ensure_board(lvl, diff):
                print(f"  !! 第{lvl}問 无法进入干净盘面，重试", flush=True)
                continue
            # 干净进关视口必须是逻辑 (0,0)；纵向无反向控件，否则无法遍历
            M0 = SB.measure(idx)
            v0 = (M0["r0"], M0["c0"])
            if v0 != (0, 0) or M0["score"] < 110:
                print(f"  !! 第{lvl}問 视口未复位 {v0} score={M0['score']}，整关重导航", flush=True)
                continue
            print(f"第{lvl}問 idx={idx} 尝试{attempt} 进关(tap{taps}) 视口={v0} "
                  f"原点=({M0['X0']},{M0['Y0']}) score={M0['score']} 边={len(SB.edges_of(idx))}", flush=True)

            rec = None if dry else rl.rec_start(out)
            t0 = time.time()
            wall = 0.0
            uncovered_n = miss_n = 0
            stopped = False
            visited = []
            cleared, waited, kind, rc = False, 0.0, None, None
            try:
                uncovered, miss_n, stopped, visited = SB.draw_all(idx, settled=settled)
                uncovered_n = len(uncovered)
                wall = time.time() - t0
                cleared, waited, kind = judge()
                if rec:
                    rc = rl.rec_stop(rec)
                    rec = None
            finally:
                if rec:
                    rl.rec_stop(rec)
                    rc = -9
            size = os.path.getsize(out) if (not dry and os.path.exists(out)) else 0
            merged[lvl] = dict(lvl=lvl, idx=idx, board="36x20", edges=len(SB.edges_of(idx)),
                               diff=diff, draw=round(wall, 1), uncovered=uncovered_n,
                               missing=int(miss_n), stopped=bool(stopped),
                               views=[list(v) for v in visited],
                               cleared=bool(cleared), result=kind, judge_s=round(waited, 1),
                               ff_rc=rc, size=size, attempt=attempt)
            print(f"第{lvl}問 画 {wall:.1f}s 未覆盖{uncovered_n} 仍缺{miss_n} "
                  f"结算={kind} 过关={cleared}({waited:.1f}s) mp4={size}B", flush=True)
            json.dump([merged[k] for k in sorted(merged)], open(logpath, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
            if cleared:
                break
            if not dry and os.path.exists(out):
                os.remove(out)
            # 36x20：删坏 mp4 后必须清盘，否则下一 attempt 进关会恢复
            # 本次残留的 600 条解答线，越画越乱（实测 attempt2 仍缺 378）。
            N.leave_level()
        if not cleared:
            print(f"  !! 第{lvl}問 {retries} 次仍未过关，停批", flush=True)
            break
    print("结束。日志", logpath, "共", len(merged), "关", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lo", type=int, default=18)
    ap.add_argument("--hi", type=int, default=50)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--outdir", default=None)
    ap.add_argument("--diff", choices=list(DIFFS), default="futsuu")
    ap.add_argument("--assume-board", action="store_true")
    ap.add_argument("--retries", type=int, default=3)
    a = ap.parse_args()
    od = a.outdir or f"/workspace/vol5_recordings_{a.diff}_36x20"
    run(a.lo, a.hi, a.dry, a.force, od, a.diff, a.assume_board, a.retries)
