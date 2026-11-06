# -*- coding: utf-8 -*-
"""录「やさしい」档 9×9 关卡（やさしい第 k 問 → lv = 19+k，共 30 关）。

=== 坐标体系（实机标定，2026-11-07）===
* 上屏：完整 10×10 全盘（游戏标 9×9），格心 (79+16*(c+.5), 15+16*(r+.5))，
  格宽 16px。r0/c0 全 0 是斜线提示行列，答案格落在 r1..9 × c1..9。
* 红框：下屏 7×7 视口的指示器。红框左上角 (x0,y0) →
  视口全局起点 r0=(y0-15)/16、c0=(x0-79)/16，实测可达 0..3（16 个位置，
  点四边橙黄箭头逐格滚动，红框闭环可控）。
* 下屏视口：格心（触屏）= (8+24*(vc+.5), 10+24*(vr+.5))，格宽 24px；
  全局 (r,c) → 屏幕 (vr,vc) = (r-r0, c-c0)。
* 答案盘 = body[-100:]（10×10）；11×11 档为 body[-144:]（12×12），本脚本不涉及。

=== 4 视口分工 ===
视口起点只能到 3，故 9×9 需 4 个视口才能覆盖全部答案格：
  (0,0)→r0..6,c0..6  (0,3)→r0..6,c3..9  (3,0)→r3..9,c0..6  (3,3)→r3..9,c3..9
每格按「r<=6 → dr=0 否则 3；c<=6 → dc=0 否则 3」唯一归属，不重复填。
遍历顺序 (0,0)→(3,0)→(3,3)→(0,3) 只需 3+3+3=9 步滚动（比顺时针少 3 步）。

=== 两个已踩的坑 ===
1. 四边滚动箭头盖住视口最外圈中间格：
   ▶(下屏 x165..185,y73..108) ◀(x0..20,y73..108)
   ▼(x75..105,y163..186)      ▲(x75..105,y0..23)
   视口 (0,0) 时 ▼ 存在，答案格 (6,3) 格心 (92,166) 正落在 ▼ 框内，
   点它会滚动视口 → 之后所有坐标错位（首版 52/60 的根因）。
   修法：最外圈格心向内偏移 5px（safe_xy）。
2. 进关/复位的 START 演出余波会吞掉前 1~2 次触摸 → 留白 LEAD_IN_YA=2.0s，
   ensure_board9 要求连续 4 次无演出大字（这段在 ffmpeg 启动前，不占片长），
   且每视口填完立即读盘补点、全盘再统一补漏。

=== 批量必踩的坑：进错关 ===
通关后回选关层时存档/解锁演出余波会吞掉触摸，盲点关号后按 A 会进「上一关」
（日志特征：盘面模式不符，但实测白格数 = 上一关的白格数）。旧版每关 100% 中招，
白跑一轮重进关 +14s，是「单关用时突然变长」的真正原因。
故 select_level() 改为：点关号 → 读光标（按钮外圈深红描边）确认到位 → 才按 A。
"""
import os
import sys
import time
import json

import numpy as np

sys.path.insert(0, '/tmp')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ds
import record_all as R

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, 'validation', 'vol4_all.json')
OUTDIR = '/workspace/Vol.4_やさしい录播'

LV0 = 19                 # やさしい第 k 問 → lv = LV0 + k
GRID = 10                # 上屏全盘（含提示行列）
TOPX = lambda c: int(79 + 16 * (c + .5))
TOPY = lambda r: int(15 + 16 * (r + .5))
LEAD_IN_YA = 2.0
VIEWS = [(0, 0), (3, 0), (3, 3), (0, 3)]

# やさしい选关页是 4 行 × 10 列（每页 40 关），与入門的 2 行不同。
# 行距 24px，实测按钮浅色块：row1=75 / row2=99 / row3=123 / row4=147（触屏 y）。
SELC_COLS_Y = [26, 50, 75, 100, 124, 149, 173, 198, 222, 247]
SELC_ROWY_Y = [75, 99, 123, 147]

# ---- 成片定长控制 ----
# 各关空格数不同（56~64）→ 填数耗时天然差 1.5~2.5s，结算出现时刻也有 1s 级抖动。
# 若结尾定格固定 5s，成片时长就会 38~43s 参差。改为「录到结算后补足到目标总长」：
#   定格 = clamp(TARGET_TOTAL - 已录, HOLD_MIN, HOLD_MAX)
# HOLD_MIN 保证 4 星延迟点亮全过程（第 3/4 颗最多晚 2~3s 亮）。
TARGET_TOTAL = 42.0
HOLD_MIN = 5.0
HOLD_MAX = 9.5

# 进关后盘面有淡入/展开动画，顶部 1~3 行会短暂全黑 → 匹配率假性偏低。
# 「模式不符」不立刻判死，给 MISMATCH_WAIT 秒轮询窗口（实测 1.29s 即完全就绪）。
MISMATCH_WAIT = 2.0


# ---------- 基础读取 ----------

def sel_xy_yasa(k):
    """やさしい 1-based 关号 → 选关按钮触屏坐标（4 行 × 10 列，每页 40 关）。"""
    idx = k - 1
    return SELC_COLS_Y[idx % 10], SELC_ROWY_Y[idx // 10]


def cursor_cell(im):
    """选关层：靠按钮外圈「深红描边」定位光标 → (row, col)；无光标返回 None。

    实测：选中按钮 = 粉红底 + 白色内描边 + 深红外描边；未选中按钮只有粉红底，
    直接与深蓝背景相接。故用深红像素数（r>140, g<55, b<55）即可干净区分：
    光标位 96，相邻按钮仅 48（采样窗重叠），其余行 ≤22。
    """
    a = np.array(im.convert('RGB'))[192:384]
    r = a[:, :, 0].astype(int)
    g = a[:, :, 1].astype(int)
    b = a[:, :, 2].astype(int)
    deep = (r > 140) & (g < 55) & (b < 55)
    best = (0, -1, -1)
    second = 0
    for ri, cy in enumerate(SELC_ROWY_Y):
        for ci, cx in enumerate(SELC_COLS_Y):
            n = int(deep[max(0, cy - 12):cy + 13, max(0, cx - 14):cx + 15].sum())
            if n > best[0]:
                second = best[0]
                best = (n, ri, ci)
            elif n > second:
                second = n
    if best[0] < 60 or best[0] < 1.5 * second:
        return None
    return (best[1], best[2])


def select_level(k, tag):
    """点目标关号并【读光标确认】，确认到位才返回。

    ★ 这是消除「每关白跑一次重进关」的关键：通关后回选关层时存档/解锁演出
    余波会吞掉触摸，旧版盲点 2 次后直接按 A，结果进了光标所在的**上一关**
    （日志特征：盘面不符但白格数 = 上一关）。改为点击后逐次读光标，
    到位才按 A，点击被吞也能自愈。

    光标框会闪烁，单帧可能落到「描边不可见」的相位 → 读 3 次再放弃。
    """
    idx = k - 1
    want = (idx // 10, idx % 10)
    sx, sy = sel_xy_yasa(k)
    for _ in range(8):
        if _read_cursor() == want:
            return True
        ds.click_touch(sx, sy, wait=0.45)
        time.sleep(0.25)
    print('  [%s] !! 光标未到位 (期望 %s, 实际 %s)' % (tag, want, _read_cursor()), flush=True)
    return False


def _read_cursor(tries=3):
    for _ in range(tries):
        c = cursor_cell(ds.shot())
        if c is not None:
            return c
        time.sleep(0.2)
    return None


def _arr():
    return np.array(ds.shot().convert('RGB'))


def red_origin(im):
    """红框左上角 → (r0, c0, x0, y0)；无红框返回 None。"""
    a = np.array(im.convert('RGB'))
    r = a[0:192, :, 0].astype(int)
    g = a[0:192, :, 1].astype(int)
    b = a[0:192, :, 2].astype(int)
    m = (r > 170) & (g < 95) & (b < 95) & (r > g + 80) & (r > b + 80)
    ys, xs = np.where(m)
    if len(xs) < 30:
        return None
    x0, y0 = int(xs.min()), int(ys.min())
    return (round((y0 - 15) / 16.0), round((x0 - 79) / 16.0), x0, y0)


def match9(im, disk):
    """上屏 10×10 全盘 classify 与答案盘白格模式对照 → (吻合, 可判定, 白格, 不一致格)。"""
    ok = jd = white = 0
    bad = []
    for r in range(GRID):
        for c in range(GRID):
            v = R.classify(im, TOPX(c), TOPY(r))
            if v < 0:
                continue
            jd += 1
            if v == 1:
                white += 1
            ans = 1 if disk[r * GRID + c] else 0
            if v == ans:
                ok += 1
            else:
                bad.append((r, c, v, ans))
    return ok, jd, white, bad


def dark_at(im, r, c):
    """上屏格子 (r,c) 内深色笔画像素数（白格空格=0，填入大数字=25~43）。"""
    a = np.array(im.convert('RGB'))
    cx, cy = TOPX(c), TOPY(r)
    s = a[cy - 6:cy + 7, cx - 6:cx + 7]
    rr, gg, bb = s[:, :, 0].astype(int), s[:, :, 1].astype(int), s[:, :, 2].astype(int)
    return int(((rr < 105) & (gg < 115) & (bb < 175)).sum())


def lit_cells(im, cells):
    s = set()
    a = np.array(im.convert('RGB'))
    for r, c, v in cells:
        cx, cy = TOPX(c), TOPY(r)
        seg = a[cy - 6:cy + 7, cx - 6:cx + 7]
        rr, gg, bb = seg[:, :, 0].astype(int), seg[:, :, 1].astype(int), seg[:, :, 2].astype(int)
        if ((rr < 105) & (gg < 115) & (bb < 175)).sum() > 12:
            s.add((r, c))
    return s


# ---------- 视口滚动 ----------

def scroll_to(tr, tc, tag):
    """用四边箭头把视口滚到全局起点 (tr,tc)，红框闭环校验。"""
    for _ in range(14):
        o = red_origin(ds.shot())
        if o is None:
            return False
        cr, cc = o[0], o[1]
        if (cr, cc) == (tr, tc):
            return True
        if cr != tr:
            name = 'D' if tr > cr else 'U'
        else:
            name = 'R' if tc > cc else 'L'
        ds.click_touch(*R.V8_ARROW[name], wait=0.7)
    print('  [%s] !! 视口未到 (%d,%d)，当前 %s' % (tag, tr, tc, red_origin(ds.shot())), flush=True)
    return False


def safe_xy(vr, vc):
    """视口格心，最外圈向内偏移 5px 避开四边滚动箭头。"""
    tx = 8 + 24 * (vc + .5)
    ty = 10 + 24 * (vr + .5)
    if vr == 0:
        ty += 5
    elif vr == 6:
        ty -= 5
    if vc == 0:
        tx += 5
    elif vc == 6:
        tx -= 5
    return int(tx), int(ty)


def fill_cell(vr, vc, v, slow=False):
    tx, ty = safe_xy(vr, vc)
    nx, ny = R.num_xy(v)
    if slow:
        ds.click_touch(tx, ty, wait=0.32)
        ds.click_touch(nx, ny, wait=0.32)
    else:
        R.fast_tap(tx, ty)
        R.fast_tap(nx, ny)


# ---------- 进关 ----------

def ensure_board9(disk, tag):
    """进关后确保到达【空白】可玩盘面：上屏 10×10 全盘匹配 + 无演出大字。"""
    stable = 0
    bad_since = None
    for attempt in range(30):
        im = ds.shot()
        ok, jd, white, bad = match9(im, disk)
        rate = ok / max(1, jd)
        if jd >= 60 and white >= 25 and rate >= 0.85:
            bad_since = None
            if R._orange_low(im) > 120:      # START/入力開始 演出中，触摸会被吞
                stable = 0
                time.sleep(0.35)
                continue
            stable += 1
            if stable < 4:                   # 连续 4 次无演出大字才真的可点（约 1.4s，
                time.sleep(0.35)             # 这段在 ffmpeg 启动之前，不影响成片时长）
                continue
            print('  [%s] 空白盘面就绪 (attempt=%d, %d/%d=%.3f, 白格%d)' %
                  (tag, attempt, ok, jd, rate, white), flush=True)
            return True
        stable = 0
        if jd < 60:                          # 不是盘面（教学页/演出/菜单）→ 按 A 推进
            bad_since = None
            ds.key('x', wait=0.5)
            time.sleep(0.35)
            continue
        # 判定得到但模式不符：多半是盘面展开动画的中间态，窗口内轮询重判；
        # 持续不符才是真进错关，交给外层重试。
        now = time.time()
        if bad_since is None:
            bad_since = now
        if now - bad_since < MISMATCH_WAIT:
            time.sleep(0.25)
            continue
        print('  [%s] 盘面模式不符 (%d/%d=%.3f, 白格%d) 不一致 %s' %
              (tag, ok, jd, rate, white, bad[:6]), flush=True)
        return False
    ds.save(ds.shot(), '/tmp/ya_fail_board_%s.png' % tag)
    print('  [%s] !! 盘面就绪失败' % tag, flush=True)
    return False


def enter_level(k, disk, tag):
    """回选关层 → 点关号（读光标确认到位）→ A 进关 → 校验盘面。最多 3 次。"""
    for attempt in range(3):
        if not R.ensure_select(tag):
            continue
        time.sleep(0.8)                     # 存档/解锁演出余波
        if not select_level(k, tag):
            continue
        ds.key('x', wait=1.0)
        time.sleep(1.0)
        if ensure_board9(disk, tag):
            return True
        print('  [%s] 第%d次进关盘面不符 → 重试' % (tag, attempt + 1), flush=True)
    return False


# ---------- 单关录制 ----------

def record_level(k):
    lv = LV0 + k
    tag = '%03d' % k
    with open(DATA, encoding='utf-8') as fp:
        rep = json.load(fp)
    body = bytes.fromhex(rep['levels'][lv]['body_hex'])
    disk = body[-(GRID * GRID):]
    cells = [(r, c, disk[r * GRID + c])
             for r in range(GRID) for c in range(GRID) if disk[r * GRID + c]]
    out = os.path.join(OUTDIR, 'Vol.4_数和_やさしい%s_256x384.mp4' % tag)
    print('\n=== やさしい%s (lv%d, 9×9, %d 格) ===' % (tag, lv, len(cells)), flush=True)

    if not enter_level(k, disk, tag):
        return False, '进关失败(盘面未就绪)'

    # 4 视口分工
    assign = {v: [] for v in VIEWS}
    for r, c, v in cells:
        assign[(0 if r <= 6 else 3, 0 if c <= 6 else 3)].append((r, c, v))
    assert sum(len(v) for v in assign.values()) == len(cells)
    print('  [%s] 视口分工: %s' % (tag, {str(k2): len(v) for k2, v in assign.items()}), flush=True)

    os.makedirs(OUTDIR, exist_ok=True)
    p = R.ffmpeg_proc(out)
    t_vid0 = time.time()                    # 录像起点（用于成片定长补足）
    time.sleep(R.FFMPEG_WARM)
    time.sleep(LEAD_IN_YA)
    t0 = time.time()

    for view in VIEWS:
        if not scroll_to(*view, tag=tag):
            print('  [%s] !! 视口 %s 未就绪' % (tag, view), flush=True)
            break
        o = red_origin(ds.shot())
        print('  [%s] 视口 %s 到位 (红框 %d,%d)' % (tag, view, o[2], o[3]), flush=True)
        for r, c, v in assign[view]:
            fill_cell(r - view[0], c - view[1], v)
        # 即时补点（最多 2 轮，每轮先回位防止视口漂移）
        for rep_i in range(2):
            im = ds.shot()
            lit = lit_cells(im, assign[view])
            miss = [(r, c, v) for r, c, v in assign[view] if (r, c) not in lit]
            if not miss:
                break
            print('  [%s] 视口 %s 第%d轮补点 %d 格' % (tag, view, rep_i + 1, len(miss)), flush=True)
            scroll_to(*view, tag=tag)
            for r, c, v in miss:
                # 补点必须用 slow：滚动刚结束时 fast_tap 会被吞，补不上等于白补
                fill_cell(r - view[0], c - view[1], v, slow=True)
        print('  [%s] 视口 %s 完成 (%d 格)' % (tag, view, len(assign[view])), flush=True)

    print('  [%s] 填数耗时 %.2fs' % (tag, time.time() - t0), flush=True)

    # 全盘统一核对 + 按视口补漏（不整盘重填，视频里不留重填痕迹）
    for rnd in range(2):
        time.sleep(0.6)
        lit = lit_cells(ds.shot(), cells)
        miss = [(r, c, v) for r, c, v in cells if (r, c) not in lit]
        print('  [%s] 全盘核对 %d/%d，空格 %d %s' %
              (tag, len(cells) - len(miss), len(cells), len(miss), miss[:10]), flush=True)
        if not miss:
            break
        byview = {v: [] for v in VIEWS}
        for r, c, v in miss:
            byview[(0 if r <= 6 else 3, 0 if c <= 6 else 3)].append((r, c, v))
        for view, sub in byview.items():
            if not sub:
                continue
            scroll_to(*view, tag=tag)
            for r, c, v in sub:
                fill_cell(r - view[0], c - view[1], v, slow=True)

    # 等自动 CLEAR（实测填完后 4~7s；窗口 14s）
    for _ in range(28):
        if R.in_result_screen():
            break
        time.sleep(0.5)
    cleared = R.in_result_screen()
    if not cleared:
        ds.key('x', wait=0.8)
        for _ in range(20):
            if R.in_result_screen():
                cleared = True
                break
            time.sleep(0.5)
    print('  [%s] 结算页 = %s' % (tag, cleared), flush=True)

    # 尾部定格：补足到 TARGET_TOTAL，保证每关成片用时一致（HOLD_MIN 兜住 4 星点亮）
    elapsed = time.time() - t_vid0
    hold = max(HOLD_MIN, min(HOLD_MAX, TARGET_TOTAL - elapsed))
    print('  [%s] 已录 %.2fs → 定格 %.2fs（目标总长 %.1fs）' %
          (tag, elapsed, hold, TARGET_TOTAL), flush=True)
    time.sleep(hold)
    ds.save(ds.shot(), '/tmp/ya_end_%s.png' % tag)
    p.terminate()
    try:
        err = p.communicate(timeout=8)[1]
        if err:
            print('  [%s] ffmpeg stderr: %s' % (tag, err.decode('utf-8', 'ignore')[:200]), flush=True)
    except Exception:
        p.kill()

    if not os.path.exists(out) or os.path.getsize(out) < 5000:
        return False, '视频未生成/过小'
    time.sleep(0.6)
    flow_ok = R.ensure_select(tag)
    kb = os.path.getsize(out) // 1024
    if not cleared:
        return False, '未进入结算页(%d KB, 已复位)' % kb
    if not flow_ok:
        return False, '通关后未回选关层(%d KB)' % kb
    return True, '%d KB, %d 格' % (kb, len(cells))


def main():
    lo = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    hi = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    os.makedirs(OUTDIR, exist_ok=True)
    results = []
    for k in range(lo, hi + 1):
        try:
            ok, msg = record_level(k)
        except Exception as e:
            ok, msg = False, 'EXC %s: %s' % (type(e).__name__, e)
        print('  => やさしい%03d %s %s' % (k, 'OK' if ok else 'FAIL', msg), flush=True)
        results.append((k, ok, msg))
    print('\n=== 汇总 ===', flush=True)
    for k, ok, msg in results:
        print('  やさしい%03d  %-4s  %s' % (k, 'OK' if ok else 'FAIL', msg), flush=True)
    print('  成功 %d / %d' % (sum(1 for _, o, _ in results if o), len(results)), flush=True)


if __name__ == '__main__':
    main()
