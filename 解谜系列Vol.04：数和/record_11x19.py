# -*- coding: utf-8 -*-
"""录「ふつう」11×19 关卡（第 61~120 問 → lv = 109 + k，lv170~229）。

=== 与 11×11 档的唯一结构差异（实机破译 2026-11-07，见 RESEARCH.md 12.12）===
* 选关页写「マス：11×19」；答案盘 = body[-240:]，形状 **20 行 × 12 列**，
  首行/首列全 0，取值 0..9（0=斜线格，1..9=该格应填数字），共 144 个数字格。
  （11×11 档是 body[-144:] = 12 行 × 12 列。）
* 上屏是 **12×12 的迷你全盘视图**，格心仍是 TOPX=63+16*(c+.5) / TOPY=16*(r+.5)；
  但全盘有 20 行，视图会整体下滚 offset ∈ 0..8（= 20-12）。
  以答案盘逐行 classify 匹配可唯一确定 offset（实测 rate=1.000）。
* 红框 = 下屏 7×7 视口在【当前上屏视图】中的位置 (r_view,c_view)。
  全局视口起点 r0 = offset + r_view；c0 = c_view（横向 12 列不滚动，同 11×11）。
  ▼ 序列可落在 r0 = 0/2/5/7/10/13，到底 13 = 20-7。
* 下屏 7×7 视口 + 1~9 数字键盘布局与 11×11 完全相同，Y.fill_cell / R.num_xy 可直接复用
  （实测试填 3/3 命中）。

=== 录制策略：动态视口扫描（不依赖精确滚动步数）===
纵向从 r0=0 单向按 ▼ 推到 r0=13，每个 r0 下横向从 c0=0 按 ▶ 推到 c0>=5；
每到一处读实际 (r0,c0)，把落在 [r0,r0+6]×[c0,c0+6] 内的未填答案格填掉，
按上屏 offset 平移判读补点。20 行 × 12 列全覆盖，无需精确到达指定视口。
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
import record_yasa as Y
import record_futsu11 as F

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, 'validation', 'vol4_all.json')
OUTDIR = '/workspace/Vol.4_ふつう11x19录播'

LV0 = 109                # 第 k 問 → lv = LV0 + k
ROWS, COLS = 20, 12      # 答案盘形状（含提示行列）
TOPX = lambda c: int(63 + 16 * (c + .5))
TOPY = lambda r: int(16 * (r + .5))
LEAD_IN = 2.0
TARGET_TOTAL = 60.0
HOLD_MIN, HOLD_MAX = 5.0, 15.0


def load_disk(lv):
    rep = json.load(open(DATA, encoding='utf-8'))
    body = bytes.fromhex(rep['levels'][lv]['body_hex'])
    disk = body[-(ROWS * COLS):]
    return disk


def view_off(im, disk):
    """上屏 12×12 视图对应的全局起始行 offset（0..8）。返回 (off, rate)。"""
    best = None
    for off in range(ROWS - 12 + 1):
        ok = jd = 0
        for r in range(12):
            for c in range(12):
                v = R.classify(im, TOPX(c), TOPY(r))
                if v < 0:
                    continue
                jd += 1
                if v == (1 if disk[(r + off) * COLS + c] else 0):
                    ok += 1
        if best is None or ok > best[0]:
            best = (ok, off, jd)
    return best[1], best[0] / max(1, best[2])


def origin(im, disk):
    """当前下屏视口的全局起点 (r0,c0) + 上屏视图偏移 off。"""
    o = F.red_origin_11(im)
    if o is None:
        return None
    off, rate = view_off(im, disk)
    return (off + o[0], o[1]), off, o, rate


def lit_global(im, todo, off):
    """按上屏视图偏移平移，判读 todo 中已出现深蓝数字的格。"""
    s = set()
    a = np.array(im.convert('RGB'))
    for r, c, v in todo:
        if not (off <= r <= off + 11):
            continue
        cx, cy = TOPX(c), TOPY(r - off)
        seg = a[cy - 6:cy + 7, cx - 6:cx + 7]
        rr, gg, bb = seg[:, :, 0].astype(int), seg[:, :, 1].astype(int), seg[:, :, 2].astype(int)
        if ((rr < 105) & (gg < 115) & (bb < 175)).sum() > 12:
            s.add((r, c))
    return s


def arrow(name):
    ds.click_touch(*R.V8_ARROW[name], wait=0.7)
    time.sleep(0.15)


def c0_now():
    o = F.red_origin_11(ds.shot())
    return o[1] if o else None


def to_c0(target):
    for _ in range(14):
        c = c0_now()
        if c is None:
            time.sleep(0.3)
            continue
        if c == target:
            return True
        arrow('R' if target > c else 'L')
    return False


def to_top(disk):
    for _ in range(16):
        q = origin(ds.shot(), disk)
        if q and q[0][0] == 0:
            return True
        arrow('U')
    return False


def fill_view(todo, r0, c0, disk, tag, filled):
    """填当前视口内 todo 格 + 最多 2 轮补点，累计 filled。"""
    if not todo:
        return
    for r, c, v in todo:
        Y.fill_cell(r - r0, c - c0, v)
    time.sleep(0.3)
    for rep_i in range(2):
        im = ds.shot()
        off2, _ = view_off(im, disk)
        lit = lit_global(im, todo, off2)
        miss = [(r, c, v) for r, c, v in todo if (r, c) not in lit]
        if not miss:
            break
        print('  [%s] 视口(%d,%d) 第%d轮补点 %d 格' %
              (tag, r0, c0, rep_i + 1, len(miss)), flush=True)
        for r, c, v in miss:
            Y.fill_cell(r - r0, c - c0, v, slow=True)
        time.sleep(0.35)
    im = ds.shot()
    off2, _ = view_off(im, disk)
    filled |= lit_global(im, todo, off2)


def sweep(cells, disk, tag):
    """纵向单向扫描 + 横向扫描，动态填满所有答案格。返回 filled 集合。"""
    filled = set()
    print('  [%s] 回顶 + 横向归零' % tag, flush=True)
    to_c0(0)
    to_top(disk)
    for vstep in range(24):
        q = origin(ds.shot(), disk)
        if q is None:
            time.sleep(0.3)
            continue
        (r0, c0), off, o, rate = q
        # 横向归零
        to_c0(0)
        for hstep in range(10):
            q2 = origin(ds.shot(), disk)
            if q2 is None:
                time.sleep(0.3)
                continue
            (r0, c0), off = q2[0], q2[1]
            todo = [(r, c, v) for r, c, v in cells
                    if r0 <= r <= r0 + 6 and c0 <= c <= c0 + 6
                    and (r, c) not in filled]
            if todo:
                print('  [%s] 视口(%2d,%d) off=%d 待填 %d 格 (累计 %d/%d)' %
                      (tag, r0, c0, off, len(todo), len(filled), len(cells)), flush=True)
                fill_view(todo, r0, c0, disk, tag, filled)
            if c0 >= 5:
                break
            arrow('R')
        q3 = origin(ds.shot(), disk)
        r_now = q3[0][0] if q3 else r0
        print('  [%s] 纵向第%d步 r0=%d 累计 %d/%d' %
              (tag, vstep, r_now, len(filled), len(cells)), flush=True)
        if len(filled) >= len(cells) or r_now >= 13:
            break
        arrow('D')
    return filled


def record(k):
    lv = LV0 + k
    tag = '%03d' % k
    disk = load_disk(lv)
    cells = [(r, c, disk[r * COLS + c])
             for r in range(ROWS) for c in range(COLS) if disk[r * COLS + c]]
    out = os.path.join(OUTDIR, 'Vol.4_数和_ふつう11x19_%s_256x384.mp4' % tag)
    os.makedirs(OUTDIR, exist_ok=True)
    print('\n=== ふつう11x19 %s (lv%d, %d行x%d列, %d 个数字格) ===' %
          (tag, lv, ROWS, COLS, len(cells)), flush=True)

    # 回选关层 → 建 S 模板 → 进关（ensure_board11 用答案盘前 12 行校验）
    R.ensure_select('boot')
    F.force_top._tmpl = F.build_s_templates()
    if not F.enter_level_11(k, disk[:144], tag):
        return False, '进关失败(盘面未就绪)'
    if not F.wait_input_ready(tag):
        return False, 'START演出未结束'
    q = origin(ds.shot(), disk)
    print('  [%s] 进关状态 off=%s rate=%s' %
          (tag, q[1] if q else None, round(q[3], 3) if q else None), flush=True)

    p = R.ffmpeg_proc(out)
    t_vid0 = time.time()
    time.sleep(R.FFMPEG_WARM)
    time.sleep(LEAD_IN)
    t0 = time.time()

    filled = sweep(cells, disk, tag)
    # 最多再补两轮（应对个别视口漏填）
    for rnd in range(2):
        if len(filled) >= len(cells):
            break
        print('  [%s] 第%d轮全盘补漏 (当前 %d/%d)' %
              (tag, rnd + 1, len(filled), len(cells)), flush=True)
        filled |= sweep(cells, disk, tag)
    print('  [%s] 填数耗时 %.2fs，最终命中 %d/%d' %
          (tag, time.time() - t0, len(filled), len(cells)), flush=True)

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
    print('  [%s] 已录 %.2fs → 定格 %.2fs' % (tag, elapsed, hold), flush=True)
    time.sleep(hold)
    ds.save(ds.shot(), '/tmp/fu11x19_end_%s.png' % tag)
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
        return False, '未进入结算页(%d KB, 已复位, 命中%d/%d)' % (kb, len(filled), len(cells))
    if not flow_ok:
        return False, '通关后未回选关层(%d KB)' % kb
    return True, '%d KB, 命中 %d/%d 格' % (kb, len(filled), len(cells))


def main():
    k = int(sys.argv[1]) if len(sys.argv) > 1 else 61
    ok, msg = record(k)
    print('\n=> ふつう11x19 %03d %s %s' % (k, 'OK' if ok else 'FAIL', msg), flush=True)


if __name__ == '__main__':
    main()
