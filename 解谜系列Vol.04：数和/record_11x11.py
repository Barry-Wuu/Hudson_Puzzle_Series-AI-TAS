# -*- coding: utf-8 -*-
"""录「やさしい」11×11 关卡（やさしい第 31~90 問 → lv = 19+k，共 60 关）。

=== 坐标体系（实机标定，2026-11-07，见 RESEARCH.md 十二章）===
* 上屏：完整 12×12 全盘（游戏标 11×11），格心 (63+16*(c+.5), 16*(r+.5))，格宽 16px。
   r0/c0 为斜线提示行列，答案格落在 r1..11 × c1..11。
* 红框：下屏 7×7 视口的指示器。红框左上角 (x0,y0) →
   视口全局起点 r0=y0/16、c0=(x0-63)/16，可达 0..5（共 36 个位置）。
* 下屏视口：格心（触屏）= (8+24*(vc+.5), 10+24*(vr+.5))，格宽 24px；
   全局 (r,c) → 屏幕 (vr,vc) = (r-r0, c-c0)。V8_* 完全复用入門/9×9 常量。
* 答案盘 = body[-144:]（12×12）；与全盘 classify 对照实测 rate=1.000（第31問）。

=== 选关滚动（关键）===
选关页是 4 行 × 10 列的可滚动列表，无「整页」，每点一次 ▼/▲ 整体平移 10 关：
  ▼ 触屏 (135,166) = S+10；▲ 触屏 (135,58) = S-10；无回卷 → ▲×6 必回顶(S=1)。
  6 档：S ∈ {1,11,21,31,41,51}，对应可见窗口 1~40/11~50/21~60/31~70/41~80/51~90。
  目标关 k 必在窗口内：t=max(0,-((40-k)//10)) 次 ▼，S=1+10t，格位 row=(k-S)//10,col=(k-S)%10。

=== 4 视口分工（覆盖 12×12 答案格，每格只归一个视口）===
  (0,0): r<=5,c<=5   (5,0): r>=6,c<=5   (0,5): r<=5,c>=6   (5,5): r>=6,c>=6
"""
import os
import sys
import time
import json

import numpy as np
from PIL import Image

sys.path.insert(0, '/tmp')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ds
import record_all as R
import record_yasa as Y

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, 'validation', 'vol4_all.json')
OUTDIR = '/workspace/Vol.4_やさしい11x11录播'

LV0 = 19                 # やさしい第 k 問 → lv = LV0 + k
GRID = 12                # 上屏全盘（含提示行列）
TOPX = lambda c: int(63 + 16 * (c + .5))
TOPY = lambda r: int(16 * (r + .5))
LEAD_IN_YA = 2.0
VIEWS = [(0, 0), (5, 0), (0, 5), (5, 5)]

# 选关滚动控件（触屏坐标）；下屏 y 需减 192
SCROLL_DOWN = (135, 166)     # ▼ S+10
SCROLL_UP = (135, 58)        # ▲ S-10
# 选关按钮（触屏坐标）：行距 24px，行中心 75/99/123/147
SELC_COLS_Y = [26, 50, 75, 100, 124, 149, 173, 198, 222, 247]
SELC_ROWY_Y = [75, 99, 123, 147]

# 成片定长控制（11×11 空格更多，初设上限 60s，按首关实测再压）
TARGET_TOTAL = 60.0
HOLD_MIN = 5.0
HOLD_MAX = 15.0
MISMATCH_WAIT = 2.0


# ---------- 起始关号 S 机器可读校验（背景相对 + 纵横比保持）----------

def _ink_bgrel(im, cx, cy, rad=8):
    """以单元格内部背景为参照提取数字笔画（兼顾「白底深蓝字」与「粉底白字」）。"""
    a = np.array(im.convert('RGB'))
    x0, x1 = cx - rad, cx + rad
    y0, y1 = cy - rad, cy + rad
    seg = a[y0:y1, x0:x1]
    if seg.size == 0:
        return None
    corners = []
    for (px, py) in [(2, 2), (seg.shape[1] - 3, 2), (2, seg.shape[0] - 3),
                     (seg.shape[1] - 3, seg.shape[0] - 3)]:
        corners.append(seg[py - 1:py + 2, px - 1:px + 2].reshape(-1, 3))
    bg = np.median(np.vstack(corners), axis=0)
    Rr, Gg, Bb = seg[:, :, 0].astype(int), seg[:, :, 1].astype(int), seg[:, :, 2].astype(int)
    dbg = np.sqrt(((Rr - bg[0]) ** 2 + (Gg - bg[1]) ** 2 + (Bb - bg[2]) ** 2))
    m = dbg > 70
    m[:1, :] = False; m[-1:, :] = False; m[:, :1] = False; m[:, -1:] = False
    return m


def cap_top_left(im):
    cx = SELC_COLS_Y[0]
    cy = 192 + SELC_ROWY_Y[0]
    m = _ink_bgrel(im, cx, cy, rad=8)
    if m is None or m.sum() < 4:
        return None
    ys, xs = np.where(m)
    sub = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = sub.shape
    nh = 18
    nw = max(1, round(w * nh / h))
    im2 = Image.fromarray((sub * 255).astype('uint8')).resize((nw, nh))
    canvas = np.zeros((18, 24), dtype=bool)
    iw = min(nw, 24)
    canvas[:, (24 - iw) // 2:(24 - iw) // 2 + iw] = (np.array(im2) > 127)[:, :iw]
    return canvas


def build_s_templates():
    """滚动过 6 档，捕获左上格指纹（S 已知），返回 {S: bitmap}。"""
    force_top()
    tmpl = {}
    S = 1
    for _ in range(6):
        im = ds.shot()
        tmpl[S] = cap_top_left(im)
        if S < 51:
            ds.click_touch(*SCROLL_DOWN, wait=0.85)
        S += 10
    force_top()
    return tmpl


def top_left_S(im, templates):
    q = cap_top_left(im)
    if q is None:
        return None
    best, bd = None, 1e9
    for S, ref in templates.items():
        if ref is None or ref.shape != q.shape:
            continue
        d = int((ref != q).sum())
        if d < bd:
            bd, best = d, S
    return best if bd < 90 else None


# ---------- 选关滚动导航 ----------

def _read_cursor(tries=3):
    for _ in range(tries):
        c = Y.cursor_cell(ds.shot())
        if c is not None:
            return c
        time.sleep(0.2)
    return None


def force_top():
    """连续点 ▲ 直到左上格 = 1（无回卷 → 最多 12 次必到顶）。"""
    tmpl = getattr(force_top, '_tmpl', None)
    for _ in range(12):
        if tmpl is not None:
            S = top_left_S(ds.shot(), tmpl)
            if S == 1:
                return True
        else:
            # 无模板时仅靠多次点击（6 次足够）
            pass
        ds.click_touch(*SCROLL_UP, wait=0.8)
    # 末次再读核验
    if tmpl is not None and top_left_S(ds.shot(), tmpl) != 1:
        return False
    return True


def scroll_to_show(k):
    """从任意滚动位置，确定性滚动使关 k 落在窗口内；返回 (row,col,S)。

    强制回顶后用 t=max(0,-((40-k)//10)) 次 ▼，S=1+10t 必含 k。
    """
    tmpl = getattr(force_top, '_tmpl', None)
    force_top()
    t = max(0, -((40 - k) // 10))
    S = 1
    for _ in range(t):
        ds.click_touch(*SCROLL_DOWN, wait=0.8)
        S += 10
        if tmpl is not None:
            cur = top_left_S(ds.shot(), tmpl)
            if cur is not None:
                S = cur
    if tmpl is not None:
        S = top_left_S(ds.shot(), tmpl) or S
    row = (k - S) // 10
    col = (k - S) % 10
    return row, col, S


def select_level_11(row, col, tag):
    """点窗口内 (row,col) 关号并读光标确认；到位才返回。"""
    sx, sy = SELC_COLS_Y[col], SELC_ROWY_Y[row]
    for _ in range(8):
        if _read_cursor() == (row, col):
            return True
        ds.click_touch(sx, sy, wait=0.45)
        time.sleep(0.25)
    print('  [%s] !! 光标未到位 (期望 %s, 实际 %s)' % (tag, (row, col), _read_cursor()), flush=True)
    return False


# ---------- 上屏 12×12 判读 ----------

def red_origin_11(im):
    """红框左上角 → (r0,c0,x0,y0)；无红框返回 None。"""
    a = np.array(im.convert('RGB'))
    r = a[0:192, :, 0].astype(int)
    g = a[0:192, :, 1].astype(int)
    b = a[0:192, :, 2].astype(int)
    m = (r > 170) & (g < 95) & (b < 95) & (r > g + 80) & (r > b + 80)
    ys, xs = np.where(m)
    if len(xs) < 30:
        return None
    x0, y0 = int(xs.min()), int(ys.min())
    return (round(y0 / 16.0), round((x0 - 63) / 16.0), x0, y0)


def match12(im, disk):
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


def lit_cells_11(im, cells):
    """11×11 版已填格判读：用本模块 TOPX/TOPY(63/0) + 深蓝笔画阈值>12。

    9×9 的 Y.lit_cells 用 TOPX=79/TOPY=15，在 11×11 上屏(63/0)会系统性
    错位一格，导致大量误判 missing → 补点把盘面越补越乱，切勿复用。
    亮红红框(R>170)不满足 rr<105，天然被排除，抗视口滚动干扰。
    """
    s = set()
    a = np.array(im.convert('RGB'))
    for r, c, v in cells:
        cx, cy = TOPX(c), TOPY(r)
        seg = a[cy - 6:cy + 7, cx - 6:cx + 7]
        rr, gg, bb = seg[:, :, 0].astype(int), seg[:, :, 1].astype(int), seg[:, :, 2].astype(int)
        if ((rr < 105) & (gg < 115) & (bb < 175)).sum() > 12:
            s.add((r, c))
    return s


def ensure_board11(disk, tag):
    """进关后确保到达【空白】可玩 12×12 盘面（且与目标关答案盘吻合）。"""
    stable = 0
    bad_since = None
    for attempt in range(40):
        im = ds.shot()
        ok, jd, white, bad = match12(im, disk)
        rate = ok / max(1, jd)
        if jd >= 86 and white >= 40 and rate >= 0.85:
            bad_since = None
            if R._orange_low(im) > 120:      # START/入力開始 演出中，触摸会被吞
                stable = 0
                time.sleep(0.35)
                continue
            stable += 1
            if stable < 4:
                time.sleep(0.35)
                continue
            print('  [%s] 空白盘面就绪 (attempt=%d, %d/%d=%.3f, 白格%d)' %
                  (tag, attempt, ok, jd, rate, white), flush=True)
            return True
        stable = 0
        if jd < 86:                          # 教学页/START演出 → 按 A 推进
            bad_since = None
            ds.key('x', wait=0.5)
            time.sleep(0.35)
            continue
        now = time.time()
        if bad_since is None:
            bad_since = now
        if now - bad_since < MISMATCH_WAIT:
            time.sleep(0.25)
            continue
        print('  [%s] 盘面模式不符 (%d/%d=%.3f, 白格%d) 不一致 %s' %
              (tag, ok, jd, rate, white, bad[:6]), flush=True)
        return False
    ds.save(ds.shot(), '/tmp/ya11_fail_board_%s.png' % tag)
    print('  [%s] !! 盘面就绪失败' % tag, flush=True)
    return False


def scroll_to_11(tr, tc, tag):
    """用四边箭头把视口滚到全局起点 (tr,tc)，红框闭环校验（11×11 版）。"""
    for _ in range(16):
        o = red_origin_11(ds.shot())
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
    print('  [%s] !! 视口未到 (%d,%d)，当前 %s' % (tag, tr, tc, red_origin_11(ds.shot())), flush=True)
    return False


def enter_level_11(k, disk, tag):
    """回选关层 → 滚动到含 k 的窗口 → 点关号（读光标确认）→ A 进关 → 校验盘面。"""
    for attempt in range(3):
        if not R.ensure_select(tag):
            continue
        time.sleep(0.8)
        row, col, S = scroll_to_show(k)
        if not select_level_11(row, col, tag):
            continue
        ds.key('x', wait=1.0)
        time.sleep(1.0)
        if ensure_board11(disk, tag):
            return True
        print('  [%s] 第%d次进关盘面不符 → 重试' % (tag, attempt + 1), flush=True)
    return False


def wait_input_ready(tag, need=10, gap=0.3, max_iter=120):
    """开录前二次兜底：START/入力開始 演出大字会闪烁(11×11 周期更长)，
    ensure_board11 的短窗口可能恰好卡在横幅熄灭间隙而误判就绪。
    这里要求连续 need 次采样都无大字才返回，放在 ffmpeg 启动前，不占片长。
    """
    stable = 0
    for i in range(max_iter):
        o = R._orange_low(ds.shot())
        stable = stable + 1 if o < 120 else 0
        if stable >= need:
            print('  [%s] 输入就绪 (连续%d次无演出大字, 采样%d次)' % (tag, need, i + 1), flush=True)
            return True
        time.sleep(gap)
    print('  [%s] !! 演出大字未收敛(stable=%d)' % (tag, stable), flush=True)
    return False


# ---------- 单关录制 ----------

def record_level_11(k):
    lv = LV0 + k
    tag = '%03d' % k
    with open(DATA, encoding='utf-8') as fp:
        rep = json.load(fp)
    body = bytes.fromhex(rep['levels'][lv]['body_hex'])
    disk = body[-(GRID * GRID):]
    cells = [(r, c, disk[r * GRID + c])
             for r in range(GRID) for c in range(GRID) if disk[r * GRID + c]]
    out = os.path.join(OUTDIR, 'Vol.4_数和_やさしい11x11_%s_256x384.mp4' % tag)
    print('\n=== やさしい11x11 %s (lv%d, 12×12, %d 格) ===' % (tag, lv, len(cells)), flush=True)

    if not enter_level_11(k, disk, tag):
        return False, '进关失败(盘面未就绪)'
    if not wait_input_ready(tag):
        return False, 'START演出未结束'

    # 4 视口分工
    assign = {v: [] for v in VIEWS}
    for r, c, v in cells:
        assign[(0 if r <= 5 else 5, 0 if c <= 5 else 5)].append((r, c, v))
    assert sum(len(v) for v in assign.values()) == len(cells)
    print('  [%s] 视口分工: %s' % (tag, {str(k2): len(v) for k2, v in assign.items()}), flush=True)

    os.makedirs(OUTDIR, exist_ok=True)
    p = R.ffmpeg_proc(out)
    t_vid0 = time.time()
    time.sleep(R.FFMPEG_WARM)
    time.sleep(LEAD_IN_YA)
    t0 = time.time()

    for view in VIEWS:
        if not scroll_to_11(*view, tag=tag):
            print('  [%s] !! 视口 %s 未就绪' % (tag, view), flush=True)
            break
        o = red_origin_11(ds.shot())
        print('  [%s] 视口 %s 到位 (红框 %d,%d)' % (tag, view, o[2], o[3]), flush=True)
        for r, c, v in assign[view]:
            Y.fill_cell(r - view[0], c - view[1], v)
        # 即时补点（最多 2 轮，每轮先回位防止视口漂移）
        for rep_i in range(2):
            im = ds.shot()
            lit = lit_cells_11(im, assign[view])
            miss = [(r, c, v) for r, c, v in assign[view] if (r, c) not in lit]
            if not miss:
                break
            print('  [%s] 视口 %s 第%d轮补点 %d 格' % (tag, view, rep_i + 1, len(miss)), flush=True)
            scroll_to_11(*view, tag=tag)
            for r, c, v in miss:
                Y.fill_cell(r - view[0], c - view[1], v, slow=True)
        print('  [%s] 视口 %s 完成 (%d 格)' % (tag, view, len(assign[view])), flush=True)

    print('  [%s] 填数耗时 %.2fs' % (tag, time.time() - t0), flush=True)

    # 全盘统一核对 + 按视口补漏
    for rnd in range(2):
        time.sleep(0.6)
        lit = lit_cells_11(ds.shot(), cells)
        miss = [(r, c, v) for r, c, v in cells if (r, c) not in lit]
        print('  [%s] 全盘核对 %d/%d，空格 %d %s' %
              (tag, len(cells) - len(miss), len(cells), len(miss), miss[:10]), flush=True)
        if not miss:
            break
        byview = {v: [] for v in VIEWS}
        for r, c, v in miss:
            byview[(0 if r <= 5 else 5, 0 if c <= 5 else 5)].append((r, c, v))
        for view, sub in byview.items():
            if not sub:
                continue
            scroll_to_11(*view, tag=tag)
            for r, c, v in sub:
                Y.fill_cell(r - view[0], c - view[1], v, slow=True)

    # 等自动 CLEAR
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

    elapsed = time.time() - t_vid0
    hold = max(HOLD_MIN, min(HOLD_MAX, TARGET_TOTAL - elapsed))
    print('  [%s] 已录 %.2fs → 定格 %.2fs（目标总长 %.1fs）' %
          (tag, elapsed, hold, TARGET_TOTAL), flush=True)
    time.sleep(hold)
    ds.save(ds.shot(), '/tmp/ya11_end_%s.png' % tag)
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
    # 构建 S 指纹模板（需先确保在选关层）
    R.ensure_select('boot')
    force_top._tmpl = build_s_templates()
    lo = int(sys.argv[1]) if len(sys.argv) > 1 else 31
    hi = int(sys.argv[2]) if len(sys.argv) > 2 else 90
    os.makedirs(OUTDIR, exist_ok=True)
    results = []
    for k in range(lo, hi + 1):
        try:
            ok, msg = record_level_11(k)
        except Exception as e:
            ok, msg = False, 'EXC %s: %s' % (type(e).__name__, e)
        print('  => やさしい11x11%03d %s %s' % (k, 'OK' if ok else 'FAIL', msg), flush=True)
        results.append((k, ok, msg))
    print('\n=== 汇总 ===', flush=True)
    for k, ok, msg in results:
        print('  やさしい11x11%03d  %-4s  %s' % (k, 'OK' if ok else 'FAIL', msg), flush=True)
    print('  成功 %d / %d' % (sum(1 for _, o, _ in results if o), len(results)), flush=True)


if __name__ == '__main__':
    main()
