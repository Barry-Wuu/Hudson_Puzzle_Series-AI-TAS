#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vol.05 数回 36x20 大盘录制核心（由 slither_big.py 派生）。

★ 关键实机事实（むずかしい 第18問 idx1640，2026-11-12 逐档标定）：
  36x20 同样是「上屏全盘缩略图 + 下屏 16px 放大局部」，几何与 24x14 初始
  视口完全一致（X0=11, Y0=9, P=16，可见 14 列 x 9 行）。差异在全盘更大：
  顶点列 0..36、行 0..20，故横向 5 档、纵向 3 档，共 9 个可信绘制视口。
  * 横向档 col0 = 0/6/12/17/22 或 0/5/11/17/22，纵向档 row0 = 0/6/11，
    Y0 = 9/22/18；每档格线起点像素级漂移，15 步逐档实测 score 124~126。
  * 可画像素边界与 24x14 相同：x<=244 / y<=162。c=36 垂直边在
    (X0=20,c0=22) 视口落 x=244、r=20 水平边在 (Y0=18,r0=11) 视口
    落 y=162，实测差分 493.0 均可画。
  * 9 视口联合覆盖顶点列 0..36 / 行 0..20，静态验证 33 题未完全覆盖 = 0。
  * 滚动控件：右滑块 (250,86) / 左滑块 (4,86) / 底部滑块 (127,167)，
    纵向无反向，故按 row0=0/6/11 三层蛇形遍历。
"""

import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ds                      # noqa: E402
import record18 as r18         # noqa: E402

# ---- 轻量抓屏（36x20 专用，不改共用 ds.py）----
# ds.grab 原本 `import -window root` 抓 1280x1024 全屏再 crop，与 ffmpeg
# x11grab 争抢 X 服务器，实测会让滚动 tap 被吞、档位漂移、后半段视口集中缺边。
# 改为只抓 DeSmuME 窗口（256x384），实测与 root-crop 平均绝对差 0.06px、
# 差异像素 0.05%，等价；单次 X 传输量降为 1/13。
import subprocess as _sp                        # noqa: E402
from PIL import Image as _Image                 # noqa: E402
_LIGHT_WID = None


def _light_grab(name=None, *_a, **_k):
    global _LIGHT_WID
    if _LIGHT_WID is None:
        _LIGHT_WID = _sp.check_output(
            ["xdotool", "search", "--name", "desmume"], env=ds.ENV, text=True
        ).split()[0]
    raw = "/tmp/_b36_light.png"
    _sp.run(["import", "-window", _LIGHT_WID, raw], env=ds.ENV, check=True)
    im = _Image.open(raw).convert("RGB")
    if name:
        im.save(os.path.join(ds.BASE, f"{name}.png"))
    return im


ds.grab = _light_grab

PJ = os.path.join(os.path.dirname(HERE), "validation", "puzzles.json")
_DATA = None

P = 16
XMAX, YMAX = 244, 162          # 可画像素上界（右侧滑块 / 底部工具栏死区之外）
TAPS = {"R": (250, 86), "L": (4, 86), "D": (127, 167)}
# 从干净进关 (0,0) 出发的蛇形滚动序列；纵向只能 +，故先走完 row0=0 全部横档
SCROLL_SEQ = [None, "R", "R", "R", "R", "D",
              "L", "L", "L", "L", "D",
              "R", "R", "R", "R"]

# ★ 15 个视口全部由「修好 measure() 搜索范围后」在真实 36x20 干净盘面
#   逐档实测（每步 score 125~126，静态验证 33 题未完全覆盖 = 0）。
#   关键修正：r0=6 层 Y0 原误设 22，实测为 14（差 8px），这是旧版
#   r0=6 层所有水平边系统性缺边的根因。中间横向档同样可信，全部纳入绘制。
#   联合覆盖顶点列 0..36 / 行 0..20。
DRAW_VIEWS = {
    0:  dict(X0=11, Y0=9,  r0=0,  c0=0),
    1:  dict(X0=18, Y0=9,  r0=0,  c0=6),
    2:  dict(X0=24, Y0=9,  r0=0,  c0=12),
    3:  dict(X0=14, Y0=9,  r0=0,  c0=17),
    4:  dict(X0=20, Y0=9,  r0=0,  c0=22),
    5:  dict(X0=20, Y0=14, r0=6,  c0=22),
    6:  dict(X0=14, Y0=14, r0=6,  c0=16),
    7:  dict(X0=24, Y0=14, r0=6,  c0=11),
    8:  dict(X0=18, Y0=14, r0=6,  c0=5),
    9:  dict(X0=11, Y0=14, r0=6,  c0=0),
    10: dict(X0=11, Y0=18, r0=11, c0=0),
    11: dict(X0=10, Y0=18, r0=11, c0=5),
    12: dict(X0=16, Y0=18, r0=11, c0=11),
    13: dict(X0=22, Y0=18, r0=11, c0=17),
    14: dict(X0=20, Y0=18, r0=11, c0=22),
}
MISS_TH = 50                   # 红线命中率阈值（%），见 score_edges

# 由录制器注入：每次点滑块前询问「是否已经判定完成」，防止 Completion!!
# 弹窗被连续点击误操作回标题。
STOP_HOOK = None


def _data():
    global _DATA
    if _DATA is None:
        _DATA = json.load(open(PJ, encoding="utf-8"))
    return _DATA


def bot_rgb():
    return np.asarray(ds.grab(None).convert("RGB")).astype(int)[192:384]


def top_rgb():
    return np.asarray(ds.grab(None).convert("RGB")).astype(int)[0:192]


def puzzle(idx):
    return next(x for x in _data() if x["idx"] == idx)


def edges_of(idx):
    p = puzzle(idx)
    return ([("h", r, c) for (r, c) in p["edges_h"]] +
            [("v", r, c) for (r, c) in p["edges_v"]])


# ---------- 逐视口实测 ----------
def _peaks(v, th, lo, hi):
    xs = [i for i, c in enumerate(v) if c > th and lo < i < hi]
    o = []
    for x in xs:
        if o and x - o[-1][-1] <= 1:
            o[-1].append(x)
        else:
            o.append([x])
    return [g[0] for g in o]


def detect_origin(a, x0_hint=None, y0_hint=None):
    """从下屏图找格线主序列起点 (X0, Y0)：连续 16px 间距最长的那条。

    ★ 红色解答线**必须并入**格线投影，而不是排除：线 (R≈255,G≈0,B≈0) 就画在
      格线上、把原本灰暗的格线像素覆盖掉，若用 `& ~red` 排除红线，等于把被覆盖
      的格线信息一并删掉，列投影会碎成 [4,150,166,246]，实测测出 X0=150 的
      离谱原点。改为 `| red` 把红线补回，投影立刻恢复完整 16px 序列。
    ★ 红线是粗线（3~4px），峰起点比格线中心早 1px，故串 16px 序列时允许
      `+16±1` 容差；净盘时精确 +16 优先命中，结果不变。
    ★ 带 ffmpeg + 密集红线时，下屏顶部标签栏 (y≈4) 会形成一条**完整的 16px
      伪序列**且比真序列还长，main() 若只选「最长」就会测出 Y0=4 / r0 减 1
      的「高分错误视口」（实测 #6/#7/#8 连续 6 次 score=122~125 但全错）。
      传入 hint（标定视口 X0/Y0）时，改为在长序列里**优先选起点最接近
      hint 的候选**，序列长度退为次要判据。净盘（hint=None）保持选最长。
    """
    R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    red = (R > 150) & (R > G + 60) & (R > B + 60) & (G < 130)
    d = (a.sum(axis=2) < 480) | red
    gx = _peaks(d[10:170, :].sum(axis=0), 110, 3, 250)
    gy = _peaks(d[:, 8:248].sum(axis=1), 100, 3, 180)

    def main(v, hint):
        vset = set(v)
        cands = []
        for s in v:
            seq = [s]
            while True:
                nxt = None
                for dd in (0, -1, 1):          # 优先精确 +16，再容 ±1
                    if seq[-1] + P + dd in vset:
                        nxt = seq[-1] + P + dd
                        break
                if nxt is None:
                    break
                seq.append(nxt)
            if len(seq) >= 4:
                cands.append((s, len(seq)))
        if not cands:
            return 11
        if hint is not None:
            cands.sort(key=lambda t: (abs(t[0] - hint), -t[1]))
        else:
            cands.sort(key=lambda t: -t[1])
        return cands[0][0]

    return main(gx, x0_hint), main(gy, y0_hint)


def measure(idx, a=None, tries=4, hint=None):
    """实测当前视口 -> dict(X0,Y0,r0,c0,score)。

    格线检测定像素原点，数字匹配定逻辑档位；score >= 110 视为动画已稳定。
    hint = 标定视口 dict(X0,Y0,r0,c0) 时，detect_origin 会在长序列里优先选
    接近 hint 的起点，避开带 ffmpeg + 密集红线时的标签栏伪序列（见 detect_origin）。
    净盘进关校验不传 hint，保持「选最长序列」原行为。
    """
    grid = puzzle(idx)["clue_grid"]
    H, W = len(grid), len(grid[0])
    last = None
    for _ in range(tries):
        im = bot_rgb() if a is None else a
        X0, Y0 = detect_origin(im,
                               hint["X0"] if hint else None,
                               hint["Y0"] if hint else None)
        m = np.zeros((9, 14), bool)
        for r in range(9):
            for c in range(14):
                x, y = X0 + P * c + 8, Y0 + P * r + 8
                if 0 <= x - 6 and x + 7 <= 256 and 0 <= y - 6 and y + 7 <= 192:
                    p = im[y - 6:y + 7, x - 6:x + 7]
                    pr, pg, pb = p[:, :, 0], p[:, :, 1], p[:, :, 2]
                    pred = (pr > 150) & (pr > pg + 60) & (pr > pb + 60) & (pg < 130)
                    # 只数「灰暗数字」像素，红线穿过格子中心不算有数字
                    m[r, c] = ((p.sum(axis=2) < 400) & ~pred).sum() > 8
        best_s, best_r0, best_c0, best_dist = -1, 0, 0, 10 ** 9
        # 36x20 全盘需覆盖 r0 到 H-9、c0 到 W-14（r0=11 / c0=22）。
        # 24x14 原版 min(H,7)/min(W,13) 会把中下层/右侧视口排除在搜索外，
        # 导致逻辑档位测错、数字匹配 score 只有 80~94。
        # ★ 数字匹配只比较「该格有无数字」，稀疏盘面常有多个窗口并列满分
        #   （净盘实测最右档 c0=22 会并列命中 c0=4 / c0=17/18，旧逻辑取遍历
        #   到的第一个即最小 c0，正是 #05/#08 画错档的来源）。hint 存在时，
        #   满分并列优先选离标定档位最近的 (r0,c0)；hint=None（净盘复位校验）
        #   距离恒 0，行为与旧版完全一致。
        for r0 in range(0, max(1, H - 8)):
            for c0 in range(0, max(1, W - 13)):
                s = 0
                for r in range(9):
                    for c in range(14):
                        if r0 + r < H and c0 + c < W:
                            s += int(m[r, c] == (grid[r0 + r][c0 + c] != "."))
                # ★ 2026-11-14 普遍启用「并列满分选离标定档位最近」加权。
                #   dry22e（idx=1644 稀疏盘）铁证：数字匹配在空白多的盘面会
                #   出现「多个窗口并列满分」的伪解，旧逻辑只对 c0>=17 的
                #   最右两档加权，中/左档并列时取遍历到的最小 c0，于是
                #   step2 实测 c0=0（标定 12）、step7 c0=1（标定 11）、
                #   step10/12 c0=0 —— use_measured=False 回退标定 M，而标定
                #   X0 与真实相位差半格（step2 实测 X0=16 / 标定 24），
                #   边画到相邻格线 -> step2 多余 11、step7 多余 23，共 34 条
                #   多余线 -> 错线彩虹高亮、结算=None。
                #   并列满分时按 dist 拉回离标定最近的档位后 c0 稳定，
                #   use_measured=True 走「完全实测 M」（X0/Y0 与 c0/r0 同源于
                #   一次测量，必然自洽），不再出现「标定 c0 + 实测/标定 X0」
                #   混用。唯一满分时 s 更大、dist 不参与比较，**真实滚动档位
                #   漂移（如 #08 实际 c0=0、标定 c0=5）仍原样保留**，不受影响。
                if hint is not None:
                    dist = abs(r0 - hint["r0"]) + abs(c0 - hint["c0"])
                else:
                    dist = 0
                if s > best_s or (s == best_s and dist < best_dist):
                    best_s, best_r0, best_c0, best_dist = s, r0, c0, dist
        last = dict(X0=X0, Y0=Y0, r0=best_r0, c0=best_c0, score=best_s)
        if best_s >= 110:
            return last
        a = None
        time.sleep(0.6)
    return last


# ---------- 上屏视口框（导航辅助 / 复位校验）----------
def frame_view(a=None):
    """上屏深绯红视口框左上角 -> 框档位 (row, col)，仅供复位检查。"""
    a = top_rgb() if a is None else a
    R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    m = (R > 170) & (R < 235) & (G < 60) & (B < 90)
    m[:20, :] = False
    colcnt, rowcnt = m.sum(axis=0), m.sum(axis=1)
    xs = np.where(colcnt >= 80)[0]
    ys = np.where(rowcnt >= 100)[0]
    if len(xs) < 2 or len(ys) < 2:
        return None
    return round((int(ys.min()) - 23) / 10), round((int(xs.min()) - 5) / 10)


# ---------- 边坐标（全部基于实测 M）----------
def endpts(kind, r, c):
    return [(r, c), (r, c + 1)] if kind == "h" else [(r, c), (r + 1, c)]


def _xy(rr, cc, M):
    return M["X0"] + P * (cc - M["c0"]), M["Y0"] + P * (rr - M["r0"])


def edge_px(kind, r, c, M):
    (x1, y1), (x2, y2) = (_xy(*v, M) for v in endpts(kind, r, c))
    return (x1, y1, x2, y2)


def visible(kind, r, c, M):
    """边的两个端点顶点都落在可画像素区内（避开滑块 / 工具栏死区）。"""
    for v in endpts(kind, r, c):
        x, y = _xy(*v, M)
        if not (M["X0"] <= x <= XMAX and M["Y0"] <= y <= YMAX):
            return False
    return True


def draw_line(kind, r, c, M):
    x1, y1, x2, y2 = edge_px(kind, r, c, M)
    # ★ 2026-11-13 端点内缩（根因修复）：上屏缩略图逐边比对
    #   （/tmp/top_line_cmp.py，答案 620/620 全命中）证明 c=20 列、
    #   ('v',9,c) 行等「答案里的空隙」被连上了 14 条多余线，且这些
    #   多余边**都与相邻答案边共顶点**。答案边端点落在格线交点(顶点)，
    #   拖拽起/止于顶点时游戏把相邻边一并画上 -> 回路多线 -> 点チェック
    #   后游戏高亮紫色错误框判「答案有误」（/tmp/clickdiag/03_12.png）。
    #   内缩 3px 后拖拽明确落在单条格线段内部，不再触发相邻边。
    # ★ 2026-11-13 撤回 INSET：微实验（_inset_test.py）实测 INSET=3 与 0
    #   自身红线都是 100%，但 INSET=3 那轮实测视口#5 反而「缺 38」；而
    #   「相邻边 82%」经 ASCII 像素图（_inset_test2.py）证明是 ±2 采样蹭到
    #   橙色 ×备忘 / 虚线光标框的伪影，不是真的连带画上。故回归端点=顶点。
    # ★ 2026-11-14 端点内缩实验（第41問根因）：
    #   step14 正常绘制 h(19,28)/h(19,30) 时，端点落在格线交点会把相邻空白
    #   h(19,27)/h(19,29) 一并画上（逐视口 trace + 游戏错线彩虹高亮双证据），
    #   且跨两个批量稳定复现 4 次。内缩让拖拽起止落在格线段内部，避开交点。
    #   ★ dry41_i2 验证（2026-11-14）：`SB36_H_INSET=2` 下 15 视口
    #   「多余=0」、step14 实机线 682=答案 682、未覆盖0 仍缺0
    #   结算=completion 过关=True，且未引入缺边；而 INSET=0 跨两个批量
    #   稳定复现 4 次「多余=2」。故**默认改为 2**，SB36_H_INSET=0 可回退。
    INSET = (int(os.environ.get("SB36_H_INSET", "2"))
             if kind == "h" else 0)
    # ★ 2026-11-14 补录第41問：带 ffmpeg 的正式录制里，底行(r>=19) h 边
    #   端点仍会落在格线交点、连带画出相邻空白 h 边（step14 多余=2；
    #   dry 无 ffmpeg 时不复现，dry41_i2 的 step13/14 M 与正式完全一致）。
    #   故仅底行可用 SB36_H_INSET_BOTTOM 单独加大内缩；默认与 INSET 相同，
    #   不设置时行为完全不变，其它 h 边保持已验证的 INSET=2
    #   （42~50 全部一次过，不动它们）。
    if kind == "h" and r >= 19:
        INSET = int(os.environ.get("SB36_H_INSET_BOTTOM", str(INSET)))
    if kind == "h":
        pts = [(x1 + INSET, y1), (x2 - INSET, y1)]
    else:
        pts = [(x1, y1 + INSET), (x1, y2 - INSET)]
    r18.drag(pts, step=3, gap=0.02,
             head=0.12, down=0.10, tail=0.10, settle=0.12)


def score_edges(base, cur, edges, M):
    """★ 红线命中率判据（替代「画前 base vs 画后 cur」RGB 差分）。

    旧差分判据在两种情况会系统性误判「缺」：
      * 盘面残留上一次 attempt / 前面视口画出的红线：base 已经是红色，
        画完 cur 还是红色，差分≈0 -> 误判缺；
      * 实测原点差 1px：采样点错过 3px 粗红线 -> 差分≈0 -> 误判缺。
    误判缺会把**已画上的边**放回 pending 重画 -> toggle 擦除 -> 真断口，
    这正是 36x20 判定不过、缺边全是水平边的恶性循环根源。

    改为直接检查「该边中间像素当前是否为红色解答线」（R>190,G<95,B<95），
    与 base 无关、不受残留线影响。返回 0~100 命中率，>=MISS_TH 视为已画。
    """
    out = {}
    for (k, r, c) in edges:
        x1, y1, x2, y2 = edge_px(k, r, c, M)
        L = max(abs(x2 - x1), abs(y2 - y1))
        hit = n = 0
        for t in range(3, L - 2):
            x = int(round(x1 + (x2 - x1) * t / L))
            y = int(round(y1 + (y2 - y1) * t / L))
            if 0 <= x < 256 and 0 <= y < 192:
                # ★ 采样 ±9px 邻域（exp36_calib_stability 实测，2026-11-13）：
                #   36x20 每次进关滚动吸附点随机漂 ±8px（净盘两遍 off 仅
                #   9/15 一致），实测 M 的端点因此比真实格线偏 8px；游戏把
                #   拖拽起点 floor 回真实格线画线，于是「线在真实格线、
                #   采样点在偏 8px 处」，单像素判据会把整条边误判「缺」。
                #   误判触发就地补画 / 放回 pending 跨视口重画，而数回同一
                #   格线段再拖一次即 toggle 擦除 -> 回路随机破损（v8/v9
                #   未覆盖0 仍缺0 也判不过的根因）。邻域搜索让采样偏 8px
                #   仍能命中真实红线，消除误判、避免无谓 toggle。
                #   水平边偏移在 y、垂直边偏移在 x；相邻平行边相距 16px
                #   > 9，不会串扰。
                found = False
                # ★ 2026-11-13 收紧为 ±2px：原 ±9px 会把「线画偏 8px、
                #   落在相邻格线」误判为已画（相位分析实测 #06 整视口偏
                #   8px），于是那条边被 pending.discard 后永不重画 -> 答案
                #   线集与题库不一致 -> 点チェック不弹 Completion。红线粗
                #   3~4px，±2 足以命中正确画的线；相邻平行边相距 16px，
                #   不会串扰。
                for d in range(-2, 3):
                    xx = x + (d if k == "v" else 0)
                    yy = y + (d if k == "h" else 0)
                    if 0 <= xx < 256 and 0 <= yy < 192:
                        R, G, B = cur[yy, xx]
                        if R > 190 and G < 95 and B < 95 and R > G + 100:
                            found = True
                            break
                if found:
                    hit += 1
                n += 1
        out[(k, r, c)] = 100.0 * hit / max(n, 1)
    return out


# ---------- 上屏缩略图线集（收尾校验 / 诊断）----------
_TOP_CAL = (2, 26, 7.0)   # (x0, y0, step)：36x20 上屏缩略图固定 7px/格，实机标定


def top_line_set(a=None):
    """用「格线段正中心 4 像素」从上屏缩略图提取实机线集，不膨胀、离两端
    顶点 >=2px，天然排除相邻边在顶点处的采样串扰。

    实机验证（2026-11-13）：
      * 净盘上屏 5011 个静态红像素 -> 本判据判出 0 条格线段（0 误判）；
      * 残留 2 条线盘面 -> 判出恰好那 2 条；
      * 第20問判定失败画面 -> 答案 664 条 100% 命中、0 缺失、5 条真多余线。
    故可用作「实机线集 == 答案线集」的可靠判据。
    """
    a = top_rgb() if a is None else a
    R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    # ★ デザイン=RANDOM 主题每关随机：冷色(浅青)与暖色(橙黄)背景都要可靠。
    #   loose (G<160) 会把暖色背景吃成「全盘 1496 条线」；strict (G<95) 在
    #   浅青判定画面漏 10 条偏暗红线。实测 mid1 在两种主题下均 0 漏 0 误：
    #   浅青 664 命中/0 缺/5 多余，暖色 329 命中/0 多余。
    red = (R > 170) & (R > G + 80) & (R > B + 80) & (G < 130)
    x0, y0, S = _TOP_CAL

    def hit(k, r, c):
        if k == "h":
            y = int(round(y0 + S * r))
            xs = [int(round(x0 + S * c + t)) for t in (2, 3, 4, 5)]
            return sum(1 for x in xs if 0 <= y < 192 and 0 <= x < 256 and red[y, x]) > 2
        x = int(round(x0 + S * c))
        ys = [int(round(y0 + S * r + t)) for t in (2, 3, 4, 5)]
        return sum(1 for y in ys if 0 <= y < 192 and 0 <= x < 256 and red[y, x]) > 2

    allseg = set([("h", r, c) for r in range(21) for c in range(36)] +
                 [("v", r, c) for r in range(20) for c in range(37)])
    return {e for e in allseg if hit(*e)}


# ---------- 绘制主流程 ----------
def _red_mask(a):
    R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    return (R > 185) & (G < 100) & (B < 100) & (R > G + 90)


def _pick_probe(group, M):
    """挑一条离视口中心最近、四周留白足够的边作探测（必属该视口答案）。"""
    cx, cy = (M["X0"] + XMAX) / 2.0, (M["Y0"] + YMAX) / 2.0
    best, bestd = None, 1e9
    for e in group:
        k, r, c = e
        x1, y1, x2, y2 = edge_px(k, r, c, M)
        if not (M["X0"] + 10 <= min(x1, x2) and max(x1, x2) <= XMAX - 10):
            continue
        if not (M["Y0"] + 10 <= min(y1, y2) and max(y1, y2) <= YMAX - 10):
            continue
        d = abs((x1 + x2) / 2.0 - cx) + abs((y1 + y2) / 2.0 - cy)
        if d < bestd:
            best, bestd = e, d
    return best


def _phase_delta(probe, M, base, cur):
    """由「探测边画完后新增的红线像素」反推 X0/Y0 真实相位偏差 (dx, dy)。

    只比较 base 与 cur 的红色差集，天然排除盘面上已有的线 / 橙色备忘 /
    虚线光标框 / 滚动箭头。返回 (dx, dy, ok)；ok=False 表示这条线根本没画上。
    """
    k, r, c = probe
    x1, y1, x2, y2 = edge_px(k, r, c, M)
    new = _red_mask(cur) & ~_red_mask(base)
    if k == "h":
        sx0, sx1 = max(0, x1 + 2), min(256, x2 - 2)
        sy0, sy1 = max(0, y1 - 9), min(192, y1 + 10)
    else:
        sx0, sx1 = max(0, x1 - 9), min(256, x1 + 10)
        sy0, sy1 = max(0, y1 + 2), min(192, y2 - 2)
    sub = new[sy0:sy1, sx0:sx1]
    ys, xs = np.where(sub)
    if len(ys) < 8:
        return 0, 0, False
    if k == "h":
        dy = int(round(np.median(ys))) + sy0 - y1
        dx = int(xs.min()) + sx0 - x1
    else:
        dx = int(round(np.median(xs))) + sx0 - x1
        dy = int(ys.min()) + sy0 - y1
    if abs(dx) > 9 or abs(dy) > 9:
        return 0, 0, False
    # 只接受 >=5px 的修正：红线本身 3~4px 粗，median/min 会有 1~2px 线宽偏差，
    # 那属于噪声；真正需要修的是「整档偏半格 = 8px」。
    if abs(dx) < 5:
        dx = 0
    if abs(dy) < 5:
        dy = 0
    return dx, dy, True


def _assign_best_views(edges):
    """为每条答案边挑一个「最居中」的可见视口 step（基于标定 DRAW_VIEWS 几何）。

    ★ 2026-11-13 根因修复：36x20 蛇形 15 视口各自只覆盖盘面一部分，一条边
       若落在它「第一次可见」的视口边缘（如底行 h 边 r=7/8/20 落在视口可见区
       下沿），拖拽端点贴近工具栏死区 -> 偶发画不上；而蛇形滚动后该边在后续
       视口 visible()=False，score_edges 判缺却永远补不上 -> 回路缺边 ->
       结算=None（第20問 3 次都缺 ('h',7,13)/('h',8,18)/('h',20,28)）。
       改为：每条边只在「离视口中心最近的可视视口」画，边缘边被挪到更居中的
       视口，避开死区。draw_all 内对实测 M 仍做 visible 兜底（漂移导致最佳
       视口不可见时允许任何可见视口 fallback），避免漏画。
    """
    best = {}
    for e in edges:
        k, r, c = e
        bstep, bdist = None, 1e18
        for step in DRAW_VIEWS:
            M = DRAW_VIEWS[step]
            if not visible(*e, M):
                continue
            x1, y1, x2, y2 = edge_px(k, r, c, M)
            cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
            vcx, vcy = (M["X0"] + XMAX) / 2.0, (M["Y0"] + YMAX) / 2.0
            d = abs(cx - vcx) + abs(cy - vcy)
            if d < bdist:
                bdist, bstep = d, step
        if bstep is not None:
            best[e] = bstep
    return best


def draw_all(idx, settled=None, verbose=True, audit_dir=None):
    """按蛇形滚动序列逐视口绘制；每视口实测参数、净盘差分核查。

    缺边**不就地补画**（18x10 教训：补边会把已完成回路 toggle 坏），
    而是放回 pending，让后续视口（不同坐标系）重画；仍缺则交 run() 整关重试。
    返回 (未画完边集合, 累计仍缺数, 是否中途结算, 视口实测记录)。

    诊断开关：设置环境变量 SB36_AUDIT_DIR=<目录> 即等价于传入 audit_dir，
    生产不设置时行为完全不变（不额外抓屏、不写文件）。
    """
    if audit_dir is None:
        audit_dir = os.environ.get("SB36_AUDIT_DIR") or None
    edges = edges_of(idx)
    best_step = _assign_best_views(edges)
    pending = set(edges)
    miss_total = 0
    stopped = False
    visited = []
    _trace_prev = set()
    # ★ 2026-11-13：从 still 回流的「仍缺边」不再受 best_step 排他限制。
    #   第20問 ('h',1,34) 的 best_step=#4，#4 实测 M 下 score_edges 误判缺且
    #   后续 10 个视口因 best_step!=step 一律不画 -> 未覆盖1 回路断口。
    #   回流边允许在蛇形后续任意可见视口补画，正常边仍按最佳视口分配。
    reflow = set()
    for step, action in enumerate(SCROLL_SEQ):
        if settled is not None and settled():
            stopped = True
            break
        if action is not None:
            if STOP_HOOK is not None and STOP_HOOK():
                stopped = True
                break
            ds.tap(*TAPS[action], hold=0.18, after=1.2)
            time.sleep(0.7)
            # ★ 2026-11-13 横向边界档补偿：吸附点每次进关随机漂 ±1 列，
            #   4 次 L 后可能只到 c0=1（标定 0）-> c=0 最左列全不可见
            #   「未覆盖4」；4 次 R 后可能只到 c0=21（标定 22）-> c=36 最右列
            #   超出 XMAX 不可见「未覆盖5」（第21問两次实测，静态复现一致）。
            #   在每个方向序列的**最后一档**多按一次：游戏在左右边界会钳制，
            #   c0 稳定到 0 / 22；本来已到位的进关多按一次无副作用。
            #   step4(R末) 后是 D(不改 c0)，step9(L末) 后是 D，
            #   step14(R末) 是序列终点，故后续档位与标定一致。
            if step in (4, 14):
                ds.tap(*TAPS["R"], hold=0.18, after=1.2)
                time.sleep(0.7)
            elif step == 9:
                ds.tap(*TAPS["L"], hold=0.18, after=1.2)
                time.sleep(0.7)
        if settled is not None and settled():
            stopped = True
            break
        # 中间两档坐标不可靠，仅作滚动过渡，不画边
        if step not in DRAW_VIEWS:
            if verbose:
                print(f"  视口#{step} 过渡档，跳过绘制", flush=True)
            continue
        # ★ 每视口实测当前视口：36x20 滚动吸附点不固定（c0 步长 5/6 交替），
        #   带 ffmpeg 时还会 X0 偏 8px / c0 偏 1 漂移，硬编码 DRAW_VIEWS 会让
        #   后半段边落在错格（实测集中缺 12~30）。exp18c 靠「每视口实测」
        #   拿到 未覆盖=0 仍缺=0 cleared=True，是已验证的正解。
        #   measure() 已对红色解答线免疫（detect_origin 与数字检测都排除
        #   红色线像素），故可在「已有线」盘面上继续实测；仅当 score 偏低或
        #   量纲越界时回退标定值，避免拿脏测值画线。
        want = DRAW_VIEWS[step]
        mm = measure(idx, hint=want)
        # ★ 36x20 滚动吸附点每次进关随机漂（净盘实测两套：c0=5/11/16/22
        #   X0=10/16/14/20 与 c0=6/12/17/22 X0=18/24/14/20），甚至某步多滚/
        #   少滚一整档（jprobe 第19問 step8 实际 c0=0、标定 c0=5）。旧容差
        #   abs(c0-want)<=2 会把这类**真实漂移**判为不可信并回退标定 M，
        #   按错档位画边 -> 多余/缺失线段 -> 点チェック永不弹 Completion。
        #   改为：score 高 + X0/Y0 在真实格线相位范围内就无条件信任实测 M
        #   （M 描述的就是当前真实视口，用它画边一定正确，档位漂到哪都无所谓）；
        #   c0/r0 容差放宽到能容纳一整档漂移，仍能挡住 c0=4/X0=5 这类
        #   标签栏伪序列（真实格线相位 X0>=9，伪序列 X0=5）。
        xy_trust = (mm["score"] >= 110 and
                    # ★ 2026-11-13 X0 下限从 9 放宽到 4：实测视口#6 真值
                    #   就是 X0=6（score=125），旧下限 9 会误退回标定。
                    # ★ 2026-11-14 第49問根因：视口#13 实测 X0 可达 29~30
                    #   （score=126，真实格线相位；标签栏伪序列的特征是
                    #   X0<=5 / 低分，不是大 X0）。旧上限 26 会把这类可信
                    #   实测 M 一刀切「回退标定 M」（标定 X0=22/c0=17，
                    #   实测 c0=18），该视口 17 条边画不上、末视口#14
                    #   补不回 -> 仍缺17 结算=None。第40問 X0=29 同源，
                    #   当时仅靠 --retries 重掷吸附点偶然绕开。
                    #   默认仍 26，既有行为完全不变；SB36_XY_XMAX=32 放行。
                    4 <= mm["X0"] <= int(os.environ.get("SB36_XY_XMAX", "26"))
                    and 8 <= mm["Y0"] <= 22)
        use_measured = (
            xy_trust and
            abs(mm["c0"] - want["c0"]) <= 8 and
            abs(mm["r0"] - want["r0"]) <= 2
        )
        if use_measured:
            M = mm
        elif (xy_trust and abs(mm["X0"] - want["X0"]) <= 2
              and abs(mm["r0"] - want["r0"]) <= 2):
            # ★ 2026-11-13 精准版：c0 数字匹配出伪解（多个窗口并列满分）
            #   但 r0 测对、实测 X0 与标定 X0 一致时，**只保留实测 Y0**。
            #   纵向吸附点每关随机漂（r0=6 层实测 Y0=13 或 21，标定 14），
            #   回退标定 Y0 会偏 7px；旧版 + 相位自校准更修到 Y0=9，
            #   #6/#7 一次缺 13/18 共 25 条。
            # ★ 绝不能连 X0 一起换成实测值：dry22 实测 #11 X0=18 / 标定 10、
            #   #12 X0=24 / 标定 16（c0 伪解连带 X0 偏一整列 16px），
            #   「标定 c0 + 实测 X0」不自洽，step11/12 画出 40 条错位多余线
            #   -> 结算=None。加 X0/r0 一致性门槛后 #10~#12 回退标定 M。
            M = dict(want, Y0=mm["Y0"])
        else:
            M = want
        # ★ 2026-11-13 孤儿边兜底：best_step 基于标定 M 分配，若该视口实测 M
        #   因吸附点漂移使这条边 visible()=False，它既进不了 group、也不会进
        #   still，reflow 收不到 -> 永久「未覆盖」。把「本视口本该画却不可见」
        #   的边放进 reflow，允许后续任意可见视口补画。与 step9 的 L 补偿
        #   配合：前者让 c=0 列重新可见，后者让可见时一定能画。
        for _e in pending:
            if best_step.get(_e) == step and not visible(*_e, M):
                reflow.add(_e)
        if verbose:
            print(f"  视口#{step} 实测 c0={mm['c0']} r0={mm['r0']} X0={mm['X0']} "
                  f"Y0={mm['Y0']} score={mm['score']} -> "
                  f"{'实测' if use_measured else '回退标定'} M", flush=True)
        # ★ 2026-11-13 修正：删除 Y0_BY_R0 硬映射，完全信任 measure 实测 Y0。
        #   旧版依据「净盘两遍 15/15 恒为 9/14/18」把 r0=6 层 Y0 固定为 14，
        #   但带 ffmpeg 的实机录制中**纵向吸附点会漂到 21/22**：本轮验证
        #   r0=6 层 5 个视口一致实测 Y0=21/22 且 score=122~126（用它采样
        #   数字全部正确，是真实格线相位，不是标签栏伪序列）。硬映射 14
        #   把线画偏 8px 半格 -> 游戏 floor 到相邻格线 -> r0=6 层水平边
        #   系统性判缺（#5~#9 各缺 33~38、仍缺 30~35，全是 h 边），
        #   回路不完整 -> 结算=None。r0=0 层实测 9、r0=11 层实测 18 与
        #   标定一致，故只有中间层崩，与日志完全吻合。
        #   use_measured 已保证 score>=110 且 8<=Y0<=22，实测 Y0 可直接用。
        visited.append((M["r0"], M["c0"], M["X0"], M["Y0"],
                        mm["score"] if use_measured else -1))
        group = [e for e in edges if e in pending and visible(*e, M)
                 and (best_step.get(e) == step or best_step.get(e) is None
                      or e in reflow)]
        if not group:
            if verbose:
                print(f"  视口#{step} 逻辑({M['r0']},{M['c0']}) 原点({M['X0']},{M['Y0']}) 无新边", flush=True)
            continue
        base = bot_rgb()
        # ★ 2026-11-13 相位自校准（根治「预测相位不可靠」）：
        #   实测视口#6 因实测 X0=6 被 X0>=9 下限拒绝、回退标定后整体偏 8px，
        #   一次缺 15 条；视口#8（X0=10）同样缺 15。说明 measure() 给出的
        #   X0/Y0 偶发偏半格，而错 8px 会让该视口近半数边画不上。
        #   改为：先画**一条探测边**（取离视口中心最近、四周留白足够者），
        #   只取「与画前基准帧的红色差集」定位这条线真正落在哪个像素，
        #   由此反推 dx/dy 修正 X0/Y0，再按修正后的 M 画其余边。
        #   探测边本身属于该视口答案，不会画多余线；不再重复画（避免 toggle）。
        # ★ 2026-11-13 禁用相位自校准（第22問根因）：统计第21問成功录像
        #   触发 0 次，第22問失败录像触发 3 次且每次都把 Y0 越修越错
        #   （dy=-5 -> Y0=9，真实格线相位是 21），#6/#7 一次缺 13/18 共
        #   25 条。measure() 已能实测真实 X0/Y0（见上方 xy_trust 分支），
        #   不再需要「探测边反推相位」这套遗留逻辑。probe=None 时下面的
        #   `if probe is not None` 整块跳过，group 所有边正常绘制。
        probe = None
        if probe is not None:
            M0 = dict(M)
            draw_line(*probe, M0)
            time.sleep(0.18)
            dx, dy, pok = _phase_delta(probe, M0, base, bot_rgb())
            pending.discard(probe)
            if pok and (dx or dy):
                # 相位偏 >=5px 说明这条探测边**落在了相邻格线**，本身已是错线：
                # 先用旧坐标原路再拖一次把它 toggle 掉，再用修正坐标画正确那条。
                draw_line(*probe, M0)
                time.sleep(0.15)
                M = dict(M, X0=M["X0"] + dx, Y0=M["Y0"] + dy)
                draw_line(*probe, M)
                time.sleep(0.15)
                if verbose:
                    print(f"  视口#{step} 相位自校准 dx={dx} dy={dy} -> "
                          f"X0={M['X0']} Y0={M['Y0']}（已擦掉错位线重画）", flush=True)
            elif not pok and verbose:
                print(f"  视口#{step} 探测边未上屏（可能拖拽丢失），按原 M 继续", flush=True)
        for e in group:
            if e == probe:
                continue
            draw_line(*e, M)
            pending.discard(e)
        # settled() 内部会抓 1280x1024 全屏（completion_anim/real_result 各一次）。
        # 逐边检查 = 600 次全屏抓屏，与 ffmpeg x11grab 争抢 X 服务器，
        # 实测后半段（视口 #11 起）拖拽开始集中丢失、缺边 12~30。
        # 回路只有补齐最后一条边才闭合，改为每组结束后查一次即可，
        # 既保留 Completion 自动停手，又把抓屏次数从 600 降到 15。
        if settled is not None and settled():
            stopped = True
            break
        cur1 = bot_rgb()
        sc = score_edges(base, cur1, group, M)
        miss = [e for e, s in sc.items() if s < MISS_TH]
        # ★ 2026-11-13 就地复查补画（离线审计 /tmp/miss_check.py 铁证）：
        #   /tmp/verify19_audit2 的 39 条 miss 边里 33 条命中率<10%
        #   （该格线段真的没有红线），只有 3 条是 82%/100% 的误判。
        #   这些真空白边在蛇形滚动后续视口大多 visible()=False，
        #   「交后续视口重画」等于永远补不上 -> 回路缺数十条边 ->
        #   点チェック后游戏无任何弹窗级响应（结算=None）。这与第18問
        #   「仍缺8 全是误判、线其实画上了却能过关」完全自洽。
        #   故仅对「复查仍<10%」的真空白边就地再画一次；10~50% 的
        #   模糊边视为已画，绝不补（避免对已画边 toggle 擦除）。
        really = [e for e in miss if sc[e] < 10]
        # ★ 2026-11-13 上屏缩略图复核（根治第20問 5 条多余线）：
        #   score_edges 的 ±2px 采样偶发把「已在别的视口画对」的边误判为
        #   <10% 真空白；就地补画会用当前视口 M 在相邻格线再画一条 ->
        #   r=19 多出 5 条 h 边 -> 回路多分支、点チェック判错线（结算=None）。
        #   监视实验（/tmp/monitor_extra.py）铁证：多余线 5 条恰好在最后一个
        #   视口 #14（该视口「缺 5」）出现。上屏缩略图 7px/格中心像素法
        #   （mid1 判据、主题无关）能可靠判定该边是否真的有线：已有线则跳过
        #   补画，避免制造多余线；确实无线才补，不误伤真缺边。
        if really and os.environ.get("SB36_TOPGUARD", "1") != "0":
            top_real = top_line_set()
            before = len(really)
            really = [e for e in really if e not in top_real]
            if verbose and before != len(really):
                print(f"  视口#{step} 上屏复核：跳过 {before - len(really)} 条误判补画",
                      flush=True)
        if really:
            for e in really:
                draw_line(*e, M)
            time.sleep(0.3)
        cur2 = bot_rgb() if really else cur1
        sc2 = score_edges(base, cur2, really, M) if really else {}
        still = [e for e in really if sc2.get(e, 100.0) < 10]
        pending.update(still)
        reflow.update(still)
        miss_total += len(still)
        # ★ 仅诊断用：audit_dir 非 None 时保存该视口画完后的下屏图与实测 M，
        #   供离线盘点「红线是否落在答案格线」；生产调用不传，行为完全不变。
        if audit_dir:
            try:
                os.makedirs(audit_dir, exist_ok=True)
                _Image.fromarray(bot_rgb().astype("uint8")).save(
                    os.path.join(audit_dir, f"step{step:02d}.png"))
                with open(os.path.join(audit_dir, f"step{step:02d}.json"),
                          "w", encoding="utf-8") as _f:
                    json.dump(dict(step=step, M=M,
                                   group=[list(e) for e in group],
                                   miss=[list(e) for e in miss],
                                   still=[list(e) for e in still]), _f)
            except Exception as _e:
                print(f"  audit save failed step{step}: {_e}", flush=True)
        # ★ 2026-11-14 就地擦除「答案外多余线」实验分支（默认关闭）：
        #   第35問 idx=1657 曾稳定复现 step14 连上底行空隙 h(20,28~31) 4 条，
        #   点チェック 后「错线彩虹高亮」、结算=None。原设想用当前视口 M
        #   对答案外边再拖一次 toggle 取消（游戏对已画格线再拖 = 取消）。
        #   ★ 实战结论（第41問 idx=1663）：两次触发均为「2->2」「4->4」，
        #   多余线数量纹丝不动（疑似 top_line_set 在该主题下误判，toggle
        #   只是画了又擦），两关仍结算=None。既未证明有效、又多出抓屏与
        #   拖拽干预，故**默认关闭**，仅保留为可选实验。
        #   启用：SB36_CLEAN_EXTRA=1；诊断：SB36_TRACE_EXTRA=1。
        #   默认（两者都不设）时本段零抓屏、零干预，与修复前行为完全一致。
        if os.environ.get("SB36_TRACE_EXTRA") or os.environ.get("SB36_CLEAN_EXTRA", "0") == "1":
            _real = top_line_set()
            _extra = _real - set(edges)
            _new = _extra - _trace_prev
            if os.environ.get("SB36_TRACE_EXTRA"):
                print(f"  [trace] step{step}: 实机线={len(_real)} 多余={len(_extra)} "
                      f"本视口新增={sorted(_new)[:12]}", flush=True)
                if _new and os.environ.get("SB36_TRACE_DETAIL"):
                    print(f"     [detail] M={M} group底行={[e for e in group if e[1] >= 19][:14]} "
                          f"really={sorted(really)[:12]} still={sorted(still)[:12]}", flush=True)
            if _extra and os.environ.get("SB36_CLEAN_EXTRA", "0") == "1":
                for _p in range(2):
                    _cur = top_line_set() - set(edges)
                    _todo = [e for e in sorted(_cur) if visible(*e, M)]
                    if not _todo:
                        break
                    _before = len(_cur)
                    for e in _todo:
                        draw_line(*e, M)
                        time.sleep(0.12)
                        if e in top_line_set():
                            draw_line(*e, M)
                            time.sleep(0.12)
                    _real = top_line_set()
                    _extra = _real - set(edges)
                    _after = len(_extra)
                    if verbose:
                        print(f"  视口#{step} 多余线擦除 pass{_p+1}: {_before} -> {_after} "
                              f"处理 {len(_todo)} 条 {sorted(_todo)[:8]}", flush=True)
                    if os.environ.get("SB36_TRACE_EXTRA"):
                        print(f"  [trace] step{step} 擦除后: 实机线={len(_real)} "
                              f"多余={_after} 答案缺={len(set(edges) - _real)}", flush=True)
                    if _after >= _before:
                        break
            _trace_prev = set(_extra)
        if verbose:
            print(f"  视口#{step} 逻辑({M['r0']},{M['c0']}) 原点({M['X0']},{M['Y0']}) "
                  f"画 {len(group)} 边 缺 {len(miss)} 交后续视口 {len(still)} {still[:4]}",
                  flush=True)
    return pending, miss_total, stopped, visited


if __name__ == "__main__":
    idx = int(sys.argv[1]) if len(sys.argv) > 1 else 1587
    M = measure(idx)
    print("idx", idx, "measure", M, "边数", len(edges_of(idx)))
    print("可见边", sum(1 for e in edges_of(idx) if visible(*e, M)))
