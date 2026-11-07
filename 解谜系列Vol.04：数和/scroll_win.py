# -*- coding: utf-8 -*-
"""7×7 视口滚动 + 「最少窗口」扫描的通用实现（13×21 / 11×19 共用）。

=== 背景（2026-11-07，见 RESEARCH.md 12.17）===
下屏 ▼/▲/◀/▶ 是【按住期间连续滚动】，滚多远由按住时长决定：慢速段约
11~15 格/秒 + 约 0.10 s 启动延迟，超过 ~0.5 s 进入二次加速（0.56 s 实测滚
12 格）。旧代码 `ds.click_touch(wait=.7)` 固定按住 0.18 s，每次只滚 2 格，
于是 22 行盘面要推 15 个视口才覆盖完。速率还会随模拟器实时负载漂移（同一个
0.38 s，一次滚 5 格、另一次滚 11 格），所以不能写死 hold → 格数 映射表。

本模块提供两样东西：

1. `Scroller`：预测 → 实测 → 修正 的闭环滚动。按 Δ 估算按住时长，滚完读回
   真实 (r0,c0)，用 EMA 修正速率；单次按压钳在 HOLD_MAX，不进入二次加速区
   （宁可欠几格再同向补一次短按，也不冲过头倒回来）。
2. `plan_windows` / `sweep_windows`：用最少的 7×7 窗口蛇形覆盖全盘。
   答案盘首行/首列是提示行列（全 0），答案格从 r=1 起 —— **行起点取 1 而不是
   0** 才能让 3 个行窗口吃下 21 行（13×21）/ 19 行（11×19），否则末行掉队。
   两档都是 3 行 × 2 列 = 6 窗口、5 次换屏，即几何下界。
"""
import subprocess
import time

import ds
import record_all as R

RATE0 = 13.0        # 慢速段初始估计（格/秒）
BASE0 = 0.10        # 启动延迟（秒）：短于它只滚 1 格
HOLD_MAX = 0.46     # 单次按压上限：超过 ~0.5 s 会二次加速，冲过头再倒回来很难看


class Scroller:
    def __init__(self, origin_fn, rows, cols, win=7):
        """origin_fn(disk) -> ((r0,c0), off, frame, rate) 或 None。"""
        self.origin_fn = origin_fn
        self.rows = rows
        self.cols = cols
        self.win = win
        self.rate = RATE0
        self.base = BASE0
        self.n = 0                       # 累计按压次数（日志/评估用）

    # ---------- 低层：可控按住的触屏点击 ----------
    def hold_for(self, delta):
        if delta <= 1:
            return 0.10
        return max(0.12, min(HOLD_MAX, self.base + (delta - 1) / self.rate))

    def press(self, name, hold, wait=0.42):
        """按住方向键 hold 秒（ds.click_touch 固定 0.18 s，这里要可控）。"""
        x, y = R.V8_ARROW[name]
        g = ds.geom()
        sx = g['x'] + int(x * g['w'] / 256)
        sy = g['y'] + g['h'] // 2 + int(y * (g['h'] / 2) / 192)
        subprocess.run(['xdotool', 'mousemove', str(sx), str(sy)], env=ds.ENV)
        time.sleep(0.04)
        subprocess.run(['xdotool', 'mousedown', '1'], env=ds.ENV)
        time.sleep(hold)
        subprocess.run(['xdotool', 'mouseup', '1'], env=ds.ENV)
        time.sleep(wait)
        self.n += 1

    def sync(self, hold, moved, at_edge):
        """用一次实测样本修正速率估计（饱和/零位移样本丢弃）。"""
        if at_edge or moved <= 0:
            return
        eff = hold - self.base
        if eff < 0.05:
            return
        obs = min(28.0, max(6.0, moved / eff))
        self.rate = 0.65 * self.rate + 0.35 * obs

    # ---------- 高层：闭环滚到指定视口起点 ----------
    def to(self, tr, tc, disk, tag='', tries=18):
        """闭环滚到 (tr,tc)。带【防震荡/死锁】：连续 4 次落点只有 ≤2 个不同值
        时，两轴都还偏就改推另一轴一步打破（12.18 修复 039 在 (12,7)↔(15,7)
        死循环）；若只剩单轴差 1~2 格（短按必滚 2 格、目标恰好不可达），直接
        接受近似位置，交给 overlap 窗口兜底，不白烧按压（12.21 修复 061 在
        (4,5)↔(6,5) 间震荡 10 次）。

        === 为什么需要防死锁 ===
        方向键是「按住期间连续滚动」，速率随模拟器负载漂移（同 0.10s 实测过
        1 格与 3 格）。当目标格恰好落在两档可达位置之间（如 r0=14 介于 12/15），
        粗按会反复过冲，纯主轴推进永远到不了 —— 旧版 `to()` 在兜底里撞上这情况
        直接 320s 超时。现在：主轴卡住就切另一轴，无法精确命中也不阻塞
        （返回最后落点，交给 `sweep_windows` 按实读位置填 + 重叠窗口补）。
        """
        last = (None, None)
        hist = []
        for _ in range(tries):
            q = self.origin_fn(disk)
            if q is None:
                time.sleep(0.25)
                continue
            r0, c0 = q[0]
            last = (r0, c0)
            if (r0, c0) == (tr, tc):
                return last
            dr, dc = tr - r0, tc - c0
            axis_row = (abs(dr) >= abs(dc)) and dr != 0
            if not axis_row and dc == 0:
                axis_row = True
            name = ('D' if dr > 0 else 'U') if axis_row else ('R' if dc > 0 else 'L')
            delta = abs(dr) if axis_row else abs(dc)
            hist.append((r0, c0))
            # 防震荡/死锁：最近 4 次落点 ≤2 个不同 → 当前步进粒度下目标不可精确命中。
            if len(hist) >= 4 and len(set(hist[-4:])) <= 2:
                if dr != 0 and dc != 0:
                    # 两轴都还有偏差：改推另一轴一步打破（039 修复，保留）
                    name = ('R' if dc > 0 else 'L') if axis_row else ('D' if dr > 0 else 'U')
                    delta = abs(dc) if axis_row else abs(dr)
                    print('    [%s] 主轴(%s)震荡，改推另一轴 %s' %
                          (tag, '行' if axis_row else '列', name), flush=True)
                else:
                    # 只剩单轴差 1~2 格、短按必过冲（同 0.10s 实滚 2 格）：再推
                    # 只会在两档可达位置间来回。直接接受当前近似位置，由
                    # sweep_windows 按实读位置填 + overlap 窗口兜底（结果与
                    # 震荡到 tries 用尽完全相同，只是不白烧 10 次按压）。
                    print('    [%s] 目标(%d,%d)单轴震荡不可精确命中，停在(%d,%d)交重叠窗口兜底' %
                          (tag, tr, tc, r0, c0), flush=True)
                    return last
            hold = self.hold_for(delta)
            self.press(name, hold)
            q2 = self.origin_fn(disk)
            after = q2[0] if q2 else last
            moved = (abs(after[0] - r0) if name in 'DU' else abs(after[1] - c0))
            at_edge = (after[0] in (0, self.rows - self.win) if name in 'DU'
                       else after[1] in (0, self.cols - self.win))
            self.sync(hold, moved, at_edge)
            print('    [%s] %s%d hold=%.2f → (%d,%d)' %
                  (tag, name, delta, hold, after[0], after[1]), flush=True)
            last = after
        print('  [%s] !! 滚动未到 (%d,%d)，停在 %s（按实读位置填/重叠窗口补）' %
              (tag, tr, tc, last), flush=True)
        return last


def plan_windows(rows, cols, win=7, row_start=1, overlap=2):
    """把答案区切成「最少但有重叠」的窗口，返回蛇形访问顺序。

    * 行起点从 row_start 起、每 (win-overlap) 行一个；超出时钳到 rows-win
      （保证窗口不越界、且与上一窗口重叠 >=overlap 行/列）。
    * overlap 是抗漂移冗余：方向键按住期间连续滚动、落点随模拟器负载漂移
      1~2 格，紧贴平铺（overlap=0）会在接缝处漏格（039 实测漏掉 13~14 行、
      兜底朝非对齐目标死锁 320s）。overlap=2 时每个答案格至少落在 2 个窗口
      里，单窗漂移 ±2 仍被邻窗兜住。
    * 13×21（22×14, row_start=1）→ 行 1/6/11/15 × 列 0/5/7 = 12 窗口；
      11×19（20×12, row_start=0）→ 行 0/5/10/13 × 列 0/5 = 8 窗口。
      虽比几何下界（6）多，但确保零漏格、且不死锁，远优于旧版 15 视口。
    """
    step = max(1, win - overlap)
    starts_r, r = [], row_start
    while r < rows - 1:
        v = min(r, rows - win)
        if v not in starts_r:
            starts_r.append(v)
        r += step
    if (rows - win) not in starts_r:
        starts_r.append(rows - win)
    starts_c, c = [], 0
    while c < cols - 1:
        v = min(c, cols - win)
        if v not in starts_c:
            starts_c.append(v)
        c += step
    if (cols - win) not in starts_c:
        starts_c.append(cols - win)
    order = []
    for i, r0 in enumerate(starts_r):
        cs = starts_c if i % 2 == 0 else list(reversed(starts_c))
        for c0 in cs:
            order.append((r0, c0))
    return order


def cells_in(remain, r0, c0, win=7):
    return [t for t in remain
            if r0 <= t[0] <= r0 + win - 1 and c0 <= t[1] <= c0 + win - 1]


def sweep_windows(cells, sc, disk, rows, cols, fill_window, tag,
                  filled0=None, win=7, row_start=1, overlap=2, log_prefix='窗口'):
    """按最少窗口蛇形扫描：一次滚动到一屏、填满再走下一屏。

    fill_window(todo, r0, c0, filled)：脚本各自实现（格子坐标、数字键盘、
    是否做字模读回校验都不一样）。返回累计 filled 集合。

    === 12.18 抗漂移 / 防死锁（修复 039）===
    1) 窗口加重叠（plan_windows overlap=2），单窗漂移 ±2 也被邻窗兜住，杜绝漏格。
    2) 主扫描后两轮回填兜底：第一轮重访【对齐】计划窗口（漂移落点也按实读填），
       第二轮逐格朝最近残留格的钳位位置滚（to() 已带防死锁，不会 320s 死循环）。
    """
    filled = set(filled0) if filled0 else set()
    remain = [(r, c, v) for r, c, v in cells if (r, c) not in filled]
    n0 = sc.n
    print('  [%s] %s扫描开始，待填 %d/%d' % (tag, log_prefix, len(remain), len(cells)),
          flush=True)
    plan = plan_windows(rows, cols, win, row_start, overlap)
    for i, (tr, tc) in enumerate(plan):
        if not remain:
            break
        if not cells_in(remain, tr, tc, win):
            continue
        r0, c0 = sc.to(tr, tc, disk, tag)
        todo = cells_in(remain, r0, c0, win)
        if not todo:
            print('  [%s] 窗口(%d,%d) 实到(%d,%d) 内无待填格，跳过' %
                  (tag, tr, tc, r0, c0), flush=True)
            continue
        print('  [%s] %s %d/%d (%d,%d)→(%d,%d) 待填 %2d 格 (累计 %d/%d)' %
              (tag, log_prefix, i + 1, len(plan), tr, tc, r0, c0, len(todo),
               len(filled), len(cells)), flush=True)
        fill_window(todo, r0, c0, filled)
        remain = [t for t in remain if (t[0], t[1]) not in filled]

    # 兜底第一轮：残留格重访【对齐】计划窗口（漂移落点也按实读位置填）。
    for (tr, tc) in plan:
        if not remain:
            break
        if not cells_in(remain, tr, tc, win):
            continue
        r0, c0 = sc.to(tr, tc, disk, tag)
        todo = cells_in(remain, r0, c0, win)
        if todo:
            print('  [%s] 兜底① 窗口(%d,%d)→(%d,%d) 补 %d 格' %
                  (tag, tr, tc, r0, c0, len(todo)), flush=True)
            fill_window(todo, r0, c0, filled)
            remain = [t for t in remain if (t[0], t[1]) not in filled]

    # 兜底第二轮：仍有残留（极少），逐格朝其钳位位置滚（to() 已带防死锁）。
    guard = 0
    while remain:
        guard += 1
        if guard > 90:
            print('  [%s] !! 兜底第二轮超 90 次仍未填满（残留 %d 格），收尾' %
                  (tag, len(remain)), flush=True)
            break
        q = sc.origin_fn(disk)
        if q is None:
            time.sleep(0.3)
            continue
        (r0, c0) = q[0]
        todo = cells_in(remain, r0, c0, win)
        if todo:
            fill_window(todo, r0, c0, filled)
            remain = [t for t in remain if (t[0], t[1]) not in filled]
            continue
        tr, tc = min(((t[0], t[1]) for t in remain),
                     key=lambda t: (max(0, t[0] - r0 - win + 1) + max(0, r0 - t[0])
                                    + max(0, t[1] - c0 - win + 1) + max(0, c0 - t[1])))
        sc.to(max(0, min(rows - win, tr)), max(0, min(cols - win, tc)), disk, tag)
    print('  [%s] %s扫描结束 %d/%d（本关按压 %d 次）' %
          (tag, log_prefix, len(filled), len(cells), sc.n - n0), flush=True)
    return filled
