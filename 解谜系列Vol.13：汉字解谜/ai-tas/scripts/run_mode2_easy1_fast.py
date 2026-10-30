#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""模式2（ひりどりナンクロ／词语螺旋接龙）速通 runner v7（plans.json L/R 执行版 + 攒批发射 + 标题页轮询，全难度）。

やさしい/ふつう/むずかしい 三难度同管线（2026-10-15：R/C 转置修复后 rec270
ふつう No.01 实证通过，见 PITFALLS §S34）。自带冷启动：pkill desmume →
ensure_env → 标题页导航，故清扫驱动（sweep_mode2.py）无需做任何定位。

设计原则（与 fill_fast_any.py 同源，用户 2026-10-11 明确）：
  **先算后打**——动作序列 100% 由 datasheet + 规划器推导，主循环纯模型跟踪
  （Win：窗口原点 + 光标），**不读屏幕、不找橙框/蓝框、不做任何视觉闭环**；
  只有末尾「校验盘面尺寸 + 补填兜底」才用一次 ffmpeg 截图，与速度无关。

★★ 2026-10-16 v7：计划来源改为 **plans.json**（用户：「还在边算边规划？plans.json呢？」）。
  mode2 的 37 条计划本就是 `mode2_fill.build_lr` 产出的 §S45 L/R 动作串
  （map/hop/kanji/arrow/page，`PS.get(rec)` 透明解码），移动动作比 beam 版更少、
  带 L/R 跳跃；读取 ~0.1s，而 beam 现算 rec271 要 48.1s（旧版每关都算一遍）。
  * 翻页按 **§U 循环模型** 运行时重建：「前/次」循环翻页（到头回绕、无夹紧），
    开页页号由 `detect_page` **单截图实测**（格芯墨点计数、不按键：双页盘
    「满页⟺第0页」决定性；2026-10-16 四 rec 跨三难度实证面板恒开第0页，
    旧「停末页」假设+双截图按键判据已作废，见 PITFALLS §S57.2/§S57.4）；
    旧串里的线性 page 步全部丢弃，按窗口态模拟恢复的徽章重插
    （双向取近：正向「次」/反向「前」），从第0页出发 ⇒ 翻页=页数−1（下限）。
  * **窗口态模拟**：§S45 编码不存徽章 note，靠 arrow/map/hop 的模型规则
    （与 lr_plan.emit / beam walk_execute 同口径）恢复每个 kanji 步的徽章，
    并以「kanji 面板坐标 == 该徽章 li 推导坐标」自校验（37/37 dry-run 通过）。
  * 补填轮用 **hop→等效箭头** 变体：徽章已绑定（蓝）时 hop 跳不动（§S12），
    原样重打会窗口漂移；等效箭头把 org 从 map 后位置直推到我方模拟的 o_after。
    且每轮补填前 **remeasure_page 重测面板实际页**（§S57.7）：首轮若掉了翻页
    输入，模拟页与游戏实际页失同步，不重测则轮轮点错页（rec270/278 三轮全败根因）。
  * `AI_TAS_PLAN_SRC=beam` 回退旧 beam 现算路径（回归/对照用）。

相对 v3 的提速（v3 全清 7 关耗时 ~24s / 84 动作）：
  1) **组序用 beam 最优 + 复刻 walk_cost 执行**（plan_mode2_beam）：
     * 按 org 违反量方向 press，光标撞进目标组任一格即停（免点击），
       tgt 进窗才点该格——这就是 beam 预估 35 动作的核心；
     * v3 的 move_to 傻走到指定 tgt（同组格也可能绕远），实测 84 动作。
  2) **时序压到实测下界**（v6 复测，2026-10-15）：ARROW_AFTER 0.05 → 0.03；
     FILL_WAIT 0.12 → 0.06；PAGE_TURN_WAIT 0.25 → 0.15；点字 after 0.12 → 0.05
     （rec260/270/273/284 四关实证正解，勿单关通过就全量跑的教训见 §S46）。
  3) **填字动作攒批发射**（§S46，2026-10-15）：单动作 subprocess.run 开销 ≈0.1s/次
     （xdotool 裸进程仅 0.0027s），167 动作的ふつう关纯进程开销 ~16.7s。改为
     XBatch 攒批器：每组的「行走 press + 点字 + 翻页 + FILL_WAIT」全部内联进
     **一条** xdotool 命令链，组末一次 flush。时序与逐次调用逐位一致
     （move→gap→down→hold→up→after 不变，只是 sleep 改内联），
     游戏侧输入序列不变 ⇒ 不吞键、不丢绑定的风险只取决于时序参数本身。
     实测探针（AI_TAS_BATCH_DEBUG=1）：每批实际耗时 == 标称耗时（差 <5ms），
     即攒批后填字段耗时 100% 由时序常量决定，机制层已无优化空间。
  4) **冷启动改轮询标题页**（§S46）：on_title 像素判据（logo 暗像素 3164 +
     Vol.13 徽章 123 + 棕底 mean 157）替代 INIT_WAIT 30s 盲等，实测 ~5.6s 就绪。

机制前提（PITFALLS §S28 / §S29，已被 v3 七关全清验证）：
  * 方向按钮 ◀(4,56) ▲(64,8) ▼(69,124) ▶(118,62) 移动**光标** 1 格
    （滚动窗口盘面下：窗口原点 + 光标 board 坐标同 +1；窗口不滚时光标在窗内走）。
    本 runner 按此模型跟踪 w.org / w.cur，不理会视觉。
  * 点候选字绑到**光标当前所在格**，同槽号整组联动 ⇒ 每组只走一次；
    光标在组内任一格即可绑该组（免点击的依据）。
  * 进关后只重锚一次到 (0,0)；末尾未填满的组才动用重锚补填（兜底）。

解答表：datasheet 记录（rec260=易1 … rec250=易6, rec251=易7，见 §S29 锚定表）。

用法：
  AI_TAS_REC=260 AI_TAS_DIFF2=yasashii   AI_TAS_LEVEL=1 python3 run_mode2_easy1_fast.py
  AI_TAS_REC=270 AI_TAS_DIFF2=futsuu     AI_TAS_LEVEL=1 python3 run_mode2_easy1_fast.py
  AI_TAS_REC=285 AI_TAS_DIFF2=muzukashii AI_TAS_LEVEL=1 python3 run_mode2_easy1_fast.py
  AI_TAS_SEIKAI_SHOT=/path/l01_fill_complete.png   # 抓正解!横幅证据图（默认不抓）
  AI_TAS_ARROW_AFTER=0.03 AI_TAS_FILL_WAIT=0.06 AI_TAS_PAGE_WAIT=0.15 ... # 时序扫参
"""
import math
import os
import shutil
import struct
import subprocess
import sys
import time

os.environ.setdefault('DISPLAY', ':99')
sys.path.insert(0, '/workspace/Kanji/ai-tas/scripts')
import kanji_common as F                      # noqa: E402
import numpy as np                            # noqa: E402
import plan_fast as P                         # noqa: E402
import plan_store as PS                       # noqa: E402
import seq_codec as SC                        # noqa: E402
from PIL import Image                         # noqa: E402
from plan_mode2_beam import (beam_plan, load_plan as beam_load, Win)  # noqa: E402

DATA = '/workspace/Kanji/validation/datasheet.bin'
REC_IDX = int(os.environ.get('AI_TAS_REC', '260'))
LEVEL = int(os.environ.get('AI_TAS_LEVEL', '1'))

ICON_LIST = (57, 136)
RIGHT, LEFT, UP, DOWN = (118, 62), (4, 56), (64, 8), (69, 124)
LIS_X0, LIS_Y0, LIS_COLS, LIS_STEP = 152, 32, 6, 16
LIS_ROWS = 8
CANDS_PER_PAGE = LIS_COLS * LIS_ROWS
PAGE_NEXT, PAGE_PREV = (220, 163), (157, 163)
WIN_STEP = 24
SHOT = os.environ.get('AI_TAS_SHOT_DIR', '/tmp/m2f')
# 模式2 难度（nav 用）：やさしい默认高亮单击即进；ふつう/むずかしい 需单击选中再单击进入
DIFF2 = os.environ.get('AI_TAS_DIFF2', 'yasashii')
DIFF2_BTN = {'yasashii': (135, 59), 'futsuu': (127, 100), 'muzukashii': (127, 140)}
DIFF2_CLICKS = {'yasashii': 1, 'futsuu': 2, 'muzukashii': 2}
BOARD = [8, 8]     # [rows, cols]，load_plan() 后填真实值（重锚次数按它算）
# 时序（env 可调）
# ★★ §S55（2026-10-16）：上一版的 0.03/0.05/0.06 是**伪下界**——用户指出「同尺寸关卡的
#   过关计时比模式1/3 慢」后查明：模式1/3 的 batch（batch_fast_diff.sh / m3_run.sh）长期
#   跑在 TAP_HOLD=MOVE_GAP=TAP_AFTER=0.02 档（§S25 实测 0.087s/步），而模式2 用 0.06/0.04，
#   每动作 0.13~0.15s ⇒ 实测 0.26~0.29s/动作，是模式1/3 的 2~3 倍。
#   现把模式2 拉到同档；三档规模实证正解（rec260 8x8 / rec270 20x25 / rec281 20x25 最大 344 步）：
#   0.149 / 0.127 / 0.134 s/动作，填字段 9.30→4.78s、35.93→17.18s。
ARROW_AFTER = float(os.environ.get('AI_TAS_ARROW_AFTER', '0.02'))
FILL_WAIT = float(os.environ.get('AI_TAS_FILL_WAIT', '0.02'))   # 连续填字时每组点字后的等待
PAGE_TURN_WAIT = float(os.environ.get('AI_TAS_PAGE_WAIT', '0.15'))  # リスト翻页动画等待（翻页无可靠像素签名，缺它会静默吞点字）
# 点候选字后的间隔：模式2 自有时序（不动 kanji_common 全局以免波及模式1/3 的默认值）
KANJI_AFTER = float(os.environ.get('AI_TAS_KANJI_AFTER', '0.02'))
# §S55：press 手势总时长 TAP_HOLD+MOVE_GAP 由 0.06+0.04 压到 0.02+0.02（与模式1 同档）。
#   只在本 runner 进程内覆盖（模式1/3 走各自 batch 的 env / 默认，不受影响）。
F.TAP_HOLD = float(os.environ.get('AI_TAS_TAP_HOLD', '0.02'))
F.TAP_MOVE_GAP = float(os.environ.get('AI_TAS_MOVE_GAP', '0.02'))
SEIKAI_SHOT = os.environ.get('AI_TAS_SEIKAI_SHOT')
# §S56：进关后「重锚到 (0,0)」默认关闭——差分实验证明初始态本就是 (0,0),(0,0)，
#   那段 LEFT×(C-1)+UP×(R-1) 全被边缘夹取、纯空按（详见 main() ② 处注释）。
REANCHOR = os.environ.get('AI_TAS_REANCHOR', '0')
B = F.XBatch()          # 填字动作攒批器（§S46：每组末 flush，省 per-action 进程开销）
# ★ v7（§S57）：§S45 L/R 动作串执行相关
ARROW_BY_DESIGN = {(P.ARROW[k][0], P.ARROW[k][1]): k for k in P.ARROW}   # 设计坐标 → 方向
BTN = {'U': UP, 'D': DOWN, 'L': LEFT, 'R': RIGHT}                        # 方向 → 底屏坐标
HOP_AFTER = float(os.environ.get('AI_TAS_HOP_AFTER', '0.03'))   # 跳跃后缓冲（T_HOP≈0.079=hold0.05+after0.03）
# 候选面板墨块区（整屏坐标 y≥192 是底屏；与 mode2_fill_paged 同款标定）
PANEL_Y0, PANEL_Y1, PANEL_X0, PANEL_X1 = 10, 160, 135, 250


def load_plan(idx=REC_IDX):
    """从 datasheet 读解答表（相对定位，见 PITFALLS §S29）。"""
    D = open(DATA, 'rb').read()
    off = list(struct.unpack_from('<300I', D, 0))
    # ★ 偏移表恰好 300 项（1200B）；最后一条记录（rec299）无尾偏移，延伸到文件尾
    rec = D[off[idx]:off[idx + 1] if idx + 1 < len(off) else len(D)]
    rl, cnt = struct.unpack_from('<HH', rec, 0)
    i = 4
    for _ in range(cnt):
        i += 2
        while i + 1 < len(rec) and rec[i:i + 2] != b'\xff\xff':
            i += 2
        i += 2
    C, R = rec[i], rec[i + 1]              # ★ 首字节=列数、次字节=行数（§S29 修正）
                                           #   旧写法 `R, C = rec[i], rec[i+1]` 把矩形盘整体
                                           #   转置；方盘（8×8/15×15/16×16）无差别故易关全过，
                                           #   ふつう/むずかしい 的 25×20 矩形盘必错。
    base = i + 2                           # 解盘起点
    sol = [rec[base + 2 * k: base + 2 * k + 2].decode('cp932', 'replace') for k in range(R * C)]
    sb = base + 2 * R * C + 2              # 槽位区
    slots = [rec[sb + k] & 0x7f for k in range(R * C)]
    hdr = sb + R * C
    n_cand = rec[hdr]
    cands = [rec[hdr + 1 + 2 * k: hdr + 1 + 2 * k + 2].decode('cp932', 'replace')
             for k in range(n_cand)]
    by_slot = {}
    for k in range(R * C):
        if slots[k]:
            by_slot.setdefault(slots[k], []).append((k // C, k % C))
    plan = []
    for n in sorted(by_slot):
        cells = by_slot[n]
        kanji = sol[cells[0][0] * C + cells[0][1]]
        assert all(sol[r * C + c] == kanji for r, c in cells), '槽%d 解不一致' % n
        assert kanji in cands, '槽%d 的 %s 不在候选表' % (n, kanji)
        li = cands.index(kanji)
        plan.append({'slot': n, 'kanji': kanji, 'cells': cells, 'li': li,
                     'lx': LIS_X0 + LIS_STEP * (li % LIS_COLS),
                     'ly': LIS_Y0 + LIS_STEP * (li // LIS_COLS)})
    slots_mat = [[slots[r * C + c] != 0 for c in range(C)] for r in range(R)]
    return plan, (R, C), slots_mat


def nav():
    F.tap(128, 100, after=F.NAV_TAP_AFTER)
    F.tap(95, 76, after=F.NAV_TAP_AFTER)
    time.sleep(3.0)
    F.tap(136, 96, after=F.NAV_TAP_AFTER)
    F.tap(136, 96, after=F.NAV_TAP_AFTER)   # 模式2 的「スタート」必须两下
    time.sleep(2.0)
    F.tap(135, 59, after=F.NAV_TAP_AFTER)   # 通常問題
    time.sleep(2.0)
    dbx, dby = DIFF2_BTN[DIFF2]
    for _ in range(DIFF2_CLICKS[DIFF2]):    # やさしい单击进；ふつう/むずかしい 需两击
        F.tap(dbx, dby, after=F.NAV_TAP_AFTER)
    time.sleep(2.5)
    col, row = (LEVEL - 1) % 10, (LEVEL - 1) // 10   # 选关页 10 列/行（15 关两行）
    lx, ly = 19 + 24 * col, 83 + 20 * row
    F.tap(lx, ly, after=F.NAV_TAP_AFTER)     # 选关页第 LEVEL 关：点两下
    F.tap(lx, ly, after=F.NAV_TAP_AFTER)
    time.sleep(3.5)


def verify_board(shot, slots_mat):
    """校验进关后的盘面尺寸与解答表一致（只做范围 sanity）。

    ★ 盘面像素宽度不规范：8×8 为 16px/列（宽 130），25×20 约 12.6px/列（宽 251）——
      旧版按 `16*C+2` 估宽会把大盘误报成「关卡不对」。这里改为范围检查。
    """
    R, C = len(slots_mat), len(slots_mat[0])
    a = np.array(Image.open(shot).convert('L')).astype(int)[0:192]
    dark = a < 100
    cols = [x for x in range(256) if dark[:, x].sum() > 40]
    if not cols:
        return False, '未找到棋盘边框'
    x0, x1 = min(cols), max(cols)
    w = x1 - x0 + 1
    return 100 <= w <= 256, '棋盘宽 %d px（%d×%d 盘）' % (w, R, C)


def press(btn):
    B.tap(*btn, after=ARROW_AFTER)      # 入队；每组末随 B.flush() 一次性发出


def tap_kanji(li, cur_page):
    """翻到候选字所在页并点字（窗口状态不受影响；返回新页号）。

    ★ 翻页后必须等动画播完再点字——翻页无可靠像素签名，紧跟其后的点字会被静默吞掉
      （fill_fast_any §S24 / v3 实证：65 候选大盘不等待时绑不上、不出正解）。
      §S46：等待改为攒批内联 sleep，与逐次 time.sleep 时序一致。
    """
    want, idx = divmod(li, CANDS_PER_PAGE)
    while cur_page < want:
        B.tap(*PAGE_NEXT, after=KANJI_AFTER); cur_page += 1
        B.sleep(PAGE_TURN_WAIT)
    while cur_page > want:
        B.tap(*PAGE_PREV, after=KANJI_AFTER); cur_page -= 1
        B.sleep(PAGE_TURN_WAIT)
    B.tap(LIS_X0 + LIS_STEP * (idx % LIS_COLS),
          LIS_Y0 + LIS_STEP * (idx // LIS_COLS), after=KANJI_AFTER)
    return cur_page


def walk_execute(w, tgt, cells, cnt):
    """复刻 beam.walk_cost 的执行版（纯模型，不读屏幕）：
    按 org 违反量方向 press，光标撞进目标组任一格即停（免点击）；
    tgt 进窗则停（返回 False，由调用方点该格）。返回是否免点击（free）。
    """
    cells_set = set(cells)
    if tuple(w.cur) in cells_set:
        return True
    n = 0
    while tuple(w.cur) not in cells_set:
        if w.in_win(tgt):
            break
        rv = tgt[0] - (w.org[0] + 3)        # >0：目标在窗下方 ⇒ DOWN
        cv = tgt[1] - (w.org[1] + 3)        # >0：目标在窗右方 ⇒ RIGHT
        if abs(rv) >= abs(cv):
            step = 1 if rv > 0 else -1
            if 0 <= w.org[0] + step <= w.R - 4:
                w.org[0] += step
            w.cur[0] = min(max(w.cur[0] + step, 0), w.R - 1)
            press(DOWN if rv > 0 else UP); cnt[0] += 1
        else:
            step = 1 if cv > 0 else -1
            if 0 <= w.org[1] + step <= w.C - 4:
                w.org[1] += step
            w.cur[1] = min(max(w.cur[1] + step, 0), w.C - 1)
            press(RIGHT if cv > 0 else LEFT); cnt[0] += 1
        n += 1
        if n > 4 * (w.R + w.C):
            raise SystemExit('walk 死锁：tgt %s org %s cur %s' % (tgt, w.org, w.cur))
    return tuple(w.cur) in cells_set


def reanchor_to(w, tgt, cnt):
    """重锚到 (0,0) 再走到 tgt（兜底用；边缘夹取，丢键不影响终点）。"""
    for _ in range(BOARD[1] - 1):
        press(LEFT); cnt[0] += 1
    for _ in range(BOARD[0] - 1):
        press(UP); cnt[0] += 1
    w.org, w.cur = [0, 0], [0, 0]
    walk_execute(w, tgt, [tgt], cnt)        # 走到 tgt（此时 tgt 即单目标格）


# ==================== v7：plans.json L/R 动作串执行（§S57） ====================

def load_plan_seq(idx=None):
    """计划来源：plans.json（§S45 L/R 串，PS.get 透明解码）优先；
    AI_TAS_PLAN_SRC=beam 回退 beam 现算（回归/对照用）。返回 (seq, 来源, 耗时)。

    idx: 记录号（None → 模块 REC_IDX）。
    """
    idx = REC_IDX if idx is None else int(idx)
    src = os.environ.get('AI_TAS_PLAN_SRC', 'json')
    if src == 'json':
        t0 = time.time()
        seq = PS.get(idx)
        dt = time.time() - t0
        if seq is not None and all(isinstance(s, (list, tuple)) and len(s) == 4
                                   for s in seq):
            return seq, 'json', dt
        print('⚠️ plans.json rec%d 无 §S45 字符串计划 → 回退 beam 现算' % idx, flush=True)
    t0 = time.time()
    seq, _st = beam_plan(idx)
    return seq, 'beam', time.time() - t0


def ds_tap(a, b, after):
    """设计坐标（按键精灵 1.5× 空间）→ 底屏相对（fill_fast_any.click_design 同口径）。"""
    B.tap(a / 1.5, b / 1.5 - 192, after=after)


def count_inked_cells(path):
    """候选面板 6×8 格**芯墨点计数**（内容无关，取代旧墨块连通域判据）。

    旧判据（墨块连通域）在**两页皆满**时失效：rec281 三页盘实测起点墨块 62、
    按次后 66（两页都是满页 48 字），连通域数只反映笔画碎片数、分不出满/满
    ⇒ 把开在第0页误判成末页，整关点字全打错页（2026-10-16 实测失败）。
    改为按格芯数：每格中心 11×11 窗口内墨像素（mean<120）≥2 即记 1 字。
    满页=48、末页=ncand%48（<48）；37 个 mode2 rec 无一 ncand%48==0
    ⇒ 判据全库决定性（空/字区分度实测：有字格 ≥10 点 vs 阈值 2）。
    """
    im = np.array(Image.open(path).convert('RGB')).astype(int)[192:]
    ink = im.mean(2) < 120
    n = 0
    for r in range(LIS_ROWS):
        for c in range(LIS_COLS):
            y, x = LIS_Y0 + LIS_STEP * r, LIS_X0 + LIS_STEP * c
            if int(ink[y - 5:y + 6, x - 5:x + 6].sum()) >= 2:
                n += 1
    return n


def detect_page(ncand):
    """实测面板开页页号（**单截图**格芯计数，不按任何翻页键；「前/次」循环翻页）。

    2026-10-16 实测（rec270/250/285 双页 + rec281 三页，跨三难度）：列表面板
    进关**恒开第0页**（§U 旧「停末页」作废，见 PITFALLS §S57.2）。本函数只
    截图数有字格、不按键——旧版按一次「次」做双页比对，把面板停在第1页，
    升序计划因此先多翻一次回第0页（双页盘 2 次、三页盘 3 次，达不到
    「每关至多一次翻页」）；不按键则重建从第0页出发 = npages-1 次（下限）。
      有字格 <48 ⇒ 开的是不满页 = 末页（唯一可不满的页）⇒ now=页数-1
      有字格 =48 ⇒ 满页 ⇒ now=0（双页盘决定性：第0页是唯一满页；
                      三页盘 0/1 皆满，按实测恒 0 处理；万一真开在第1页，
                      也只多 1 次翻页、不影响正确性——li→页映射是绝对的）
    单页盘不截图直接返回 (0,1)。
    """
    npages = max(1, int(math.ceil(ncand / float(CANDS_PER_PAGE))))
    if npages == 1:
        return 0, 1
    s0 = os.path.join(SHOT, '_pg0.png')
    F.shot(s0)
    n0 = count_inked_cells(s0)
    now = 0 if n0 >= CANDS_PER_PAGE else npages - 1
    print('  面板页数=%d 开页墨点=%d ⇒ 开在第%d页（不按键，直接重建）'
          % (npages, n0, now), flush=True)
    return now, npages


def remeasure_page(ncand):
    """补填轮前**重测**面板当前页（按一次「次」双页比对；对 2/3 页盘都决定性）。

    为什么需要：首轮填充若掉了**翻页输入**（0.02 时序档的已知边缘风险，§S55），
    我方模拟的页号会与游戏实际页失同步；旧代码补填轮按模拟的 endpage 重建，
    之后每一轮的翻页目标全错 ⇒ 轮轮点错页。实测 rec270/rec278 首轮+2 轮补填
    **三轮全败**（2026-10-16 清扫），根因即此——不是补填序列错，是起点页错。
    重测一次即断级联（补填是恢复路径，可靠性优先，不惜 1 次翻页 + 0.9s）。
    判定（按次后比较两页有字格数，37 rec 无 ncand%48==0 ⇒ 全库决定性）：
      起点 <48            ⇒ 起点=末页，按次绕回第0页 ⇒ now=0
      起点 =48 且按次后 <48 ⇒ 起点=倒数第2页 ⇒ now=页数-1
      两页都 =48           ⇒ 起点=第0页 ⇒ now=1
    """
    npages = max(1, int(math.ceil(ncand / float(CANDS_PER_PAGE))))
    if npages == 1:
        return 0, 1
    s0 = os.path.join(SHOT, '_rp0.png')
    F.shot(s0)
    n0 = count_inked_cells(s0)
    F.tap(*PAGE_NEXT, after=F.TAP_AFTER)
    time.sleep(0.9)
    s1 = os.path.join(SHOT, '_rp1.png')
    F.shot(s1)
    n1 = count_inked_cells(s1)
    if n0 < CANDS_PER_PAGE:
        now = 0
    elif n1 < CANDS_PER_PAGE:
        now = npages - 1
    else:
        now = 1
    print('  补填重测面板：页数=%d 墨点=%d→%d ⇒ 现位于第%d页'
          % (npages, n0, n1, now), flush=True)
    return now, npages


def rebuild_pages_sim(seq, plan_local, R, C, start_page, npages):
    """循环翻页重建 + 窗口态模拟恢复徽章（§S45 编码不存徽章 note）。

    模拟规则（与 lr_plan.emit / beam walk_execute 同口径；dry-run 37/37 校验）：
      初始 窗口(0,0)/光标(0,0)（§S56 实证）；
      arrow：org/cur 同向 ±1（org 夹 [0,R-4]×[0,C-4]，cur 夹 [0,R-1]×[0,C-1]）；
      map(i,j)：光标 = org+(i,j)（点格即选中该格所属徽章，org 不变）；
      hop(w/q)：光标 = 当前徽章读序下一/上一格，org = clamp(光标)（§S12）；
      kanji/page：不影响窗口态。
    翻页（§U 循环模型，双向取近）：正向按「次」/反向按「前」，次数取
    min((tgt-cur)%n, (cur-tgt)%n)；旧线性模型的 page 步全部丢弃重插。
    自校验：每个 kanji 步的面板坐标必须等于所恢复徽章的 li 推导坐标，
    否则说明串与解答表不同源 ⇒ 直接中止（防静默错字）。
    同时产出无跳变体 nohop（hop→等效箭头）：补填轮用——徽章已绑定（蓝）
    时 hop 跳不动（§S12），原样重打会窗口漂移。
    返回 (fixed, 翻页次数, 结束页号, nohop)。
    """
    by_slot = {p['slot']: sorted(p['cells']) for p in plan_local}
    cell2slot = {}
    for s, cs in by_slot.items():
        for cell in cs:
            cell2slot[cell] = s
    kanji_of = {p['slot']: p['kanji'] for p in plan_local}
    slot_page = {p['slot']: p['li'] // CANDS_PER_PAGE for p in plan_local}
    slot_kpos = {p['slot']: ((p['li'] % CANDS_PER_PAGE) // LIS_COLS,
                             (p['li'] % CANDS_PER_PAGE) % LIS_COLS)
                 for p in plan_local}
    fixed, nohop = [], []
    curpage = start_page
    npress = 0
    org = [0, 0]
    cur = [0, 0]
    slot = None
    for s in seq:
        k = s[0]
        if k == 'arrow':
            d = ARROW_BY_DESIGN.get((s[1], s[2]))
            if d is None:
                raise SystemExit('❌ 未知箭头坐标 %r（ARROW 表外）' % ((s[1], s[2]),))
            if d in ('U', 'D'):
                stp = 1 if d == 'D' else -1
                org[0] = min(max(org[0] + stp, 0), R - 4)
                cur[0] = min(max(cur[0] + stp, 0), R - 1)
            else:
                stp = 1 if d == 'R' else -1
                org[1] = min(max(org[1] + stp, 0), C - 4)
                cur[1] = min(max(cur[1] + stp, 0), C - 1)
            fixed.append(s); nohop.append(s)
        elif k == 'map':
            i, j = s[1], s[2]
            cur = [org[0] + i, org[1] + j]
            slot = cell2slot.get(tuple(cur))
            if slot is None:
                raise SystemExit('❌ map 步指向非徽章格 org=%s+(%d,%d)——串与解答表不同源？'
                                 % (org, i, j))
            note = 'm%d=%s' % (slot, kanji_of.get(slot, '?'))
            fixed.append(('map', i, j, note)); nohop.append(('map', i, j, note))
        elif k == 'hop':
            cs = by_slot[slot]
            idx = cs.index(tuple(cur))
            stp = 1 if s[1] == 'w' else -1
            cur = list(cs[(idx + stp) % len(cs)])
            o_after = [min(max(cur[0], 0), R - 4), min(max(cur[1], 0), C - 4)]
            fixed.append(s)
            o = list(org)                   # nohop：等效箭头把 org 直推到我方模拟的 o_after
            while o[0] != o_after[0]:
                dd = 'D' if o_after[0] > o[0] else 'U'
                o[0] += 1 if dd == 'D' else -1
                nohop.append(('arrow', P.ARROW[dd][0], P.ARROW[dd][1], 'hop等效%s' % dd))
            while o[1] != o_after[1]:
                dd = 'R' if o_after[1] > o[1] else 'L'
                o[1] += 1 if dd == 'R' else -1
                nohop.append(('arrow', P.ARROW[dd][0], P.ARROW[dd][1], 'hop等效%s' % dd))
            org = o_after
        elif k == 'kanji':
            if slot is None:
                raise SystemExit('❌ kanji 步前无 map（slot 未恢复）')
            row, col = s[1], s[2]
            exp = slot_kpos[slot]
            if (row, col) != exp:
                raise SystemExit('❌ kanji 坐标 (%d,%d) != 徽章%d 期望 %s——串与解答表不同源'
                                 % (row, col, slot, exp))
            tgt = slot_page[slot]
            fwd = (tgt - curpage) % npages
            bwd = (curpage - tgt) % npages
            if fwd and fwd <= bwd:
                for _ in range(fwd):
                    fixed.append(('page', P.LIST_NEXT_D[0], P.LIST_NEXT_D[1], 'リスト次'))
                    nohop.append(('page', P.LIST_NEXT_D[0], P.LIST_NEXT_D[1], 'リスト次'))
                npress += fwd
            elif bwd:
                for _ in range(bwd):
                    fixed.append(('page', P.LIST_PREV_D[0], P.LIST_PREV_D[1], 'リスト前'))
                    nohop.append(('page', P.LIST_PREV_D[0], P.LIST_PREV_D[1], 'リスト前'))
                npress += bwd
            curpage = tgt
            note = 'k%d=%s' % (slot, kanji_of.get(slot, ''))
            fixed.append(('kanji', row, col, note))
            nohop.append(('kanji', row, col, note))
        elif k == 'page':
            continue                      # 丢弃旧线性模型翻页，上面按循环模型重插
        else:
            raise SystemExit('❌ 未知动作 kind=%r' % (k,))
    return fixed, npress, curpage, nohop


def exec_seq(seq, cnt, tag=''):
    """执行 §S45 L/R 动作串（map/kanji/arrow/page/hop；纯模型，无视觉闭环）。

    map/kanji 的 (行,列) 用 runner 自有标定常量（与 beam 版同按钮）；
    arrow/page 是设计坐标（ds_tap 换算）；hop 走 XBatch.key（§S18 防丢键时序）。
    每组（kanji 步）末 flush 一次（§S46 攒批）。
    """
    for n, (kind, a, b, note) in enumerate(seq, 1):
        if kind == 'map':                 # 缩略图窗口格 (行,列)
            B.tap(26 + WIN_STEP * b, 24 + WIN_STEP * a, after=ARROW_AFTER)
        elif kind == 'kanji':             # 列表面板格 (行,列)
            B.tap(LIS_X0 + LIS_STEP * b, LIS_Y0 + LIS_STEP * a, after=KANJI_AFTER)
            B.sleep(FILL_WAIT)
        elif kind == 'page':              # 列表翻页（等动画播完，§S24）
            ds_tap(a, b, KANJI_AFTER)
            B.sleep(PAGE_TURN_WAIT)
        elif kind == 'hop':               # L/R 肩键跳跃（§S12：窗口重锚到 clamp(光标)）
            B.key(a, hold=F.KEY_HOLD, after=HOP_AFTER)
        elif kind == 'arrow':
            d = ARROW_BY_DESIGN.get((a, b))
            if d is None:
                raise SystemExit('❌ 未知箭头坐标 %r' % ((a, b),))
            B.tap(*BTN[d], after=ARROW_AFTER)
        else:
            raise SystemExit('❌ 未知动作 kind=%r' % (kind,))
        cnt[0] += 1
        if kind == 'kanji':
            B.flush()                     # §S46：每组末一次性发出
        if n % 10 == 0:
            print('  %3d/%d %s%s' % (n, len(seq), note, tag), flush=True)
    B.flush()


def run_fill(rec=None, evidence=None, plan_src=None, reanchor=None, detect_only=False):
    """模式2 单盘填字：规划 → 开リスト → 执行 §S45 L/R 串 → 正解判定 → 失败补填 3 轮。

    ★ 假定游戏**已停在填字界面**（冷启动/导航由调用方负责，见 run.py）。
    返回 (ok: bool, poll_path)。evidence 非空时把正解帧按 §S37 量化存到该路径。

    rec: 记录号（None → 模块 REC_IDX，即 import 期 AI_TAS_REC）。
    plan_src: 'json'（plans.json）/ 'beam'（现算）；None → env AI_TAS_PLAN_SRC。
    reanchor: 进关后是否重锚 (0,0)；None → env AI_TAS_REANCHOR（默认关，§S56）。
    detect_only: 只测「面板开在第几页」就退（探针，不执行）；返回 (True, None)。
    """
    global REC_IDX
    if rec is not None:
        REC_IDX = int(rec)
    plan_src = plan_src or os.environ.get('AI_TAS_PLAN_SRC', 'json')
    if reanchor is None:
        reanchor = (os.environ.get('AI_TAS_REANCHOR', '0') != '0')
    ev = SEIKAI_SHOT if evidence is None else evidence

    seq, plan_src, plan_dt = load_plan_seq(REC_IDX)
    _, _, _, cands = beam_load(REC_IDX)
    if plan_src == 'json':
        st = SC.seq_stats(seq)
        print('计划 plans.json rec%d：%d 步（触摸 %d + 箭头 %d + 跳跃 %d + 翻页 %d；读取 %.2fs）'
              % (REC_IDX, st['steps'], st['n_touch'], st['n_arrow'], st['n_hop'],
                 st['n_page'], plan_dt), flush=True)
    else:
        print('beam 规划 %s rec%d（现算 %.1fs）' % (DIFF2, REC_IDX, plan_dt), flush=True)

    plan_local, (R, C), slots_mat = load_plan(REC_IDX)
    BOARD[0], BOARD[1] = R, C
    print('解答表 %d 组 / 盘面 %dx%d：%s' % (len(plan_local), R, C,
          ' '.join(p['kanji'] for p in plan_local)), flush=True)

    os.makedirs(SHOT, exist_ok=True)
    t0 = time.time()
    # 切 リスト（打开候选面板）；★ 带校验重试——「開始!」横幅可能吞掉首击（进盘过早时），
    #   面板没开会令 detect_page 误判开页、整盘填错位（run.py 统一入口下实测偶发）。
    F.tap(*ICON_LIST, after=F.TAP_AFTER)
    time.sleep(1.2)                           # 面板动画 + 输入就绪
    for _ in range(2):
        if F.list_panel_open():
            break
        print('  [warn] リスト 面板未开，补点 LISTMODE', flush=True)
        F.tap(*ICON_LIST, after=F.TAP_AFTER)
        time.sleep(1.0)
    cnt = [1]
    base = '%s/base.png' % SHOT
    F.shot(base)
    ok, desc = verify_board(base, slots_mat)
    print('进关盘面校验：%s %s' % (desc, '✅' if ok else '⚠️ 关卡不对，结果不可信！'), flush=True)

    # ② 进关后重锚到 (0,0)——★ 2026-10-16 差分实验（PITFALLS §S56）证明：
    #   初始态本就是 窗口(0,0)/光标(0,0)（§S12 L1074 亦载），故这段 LEFT×(C-1)+UP×(R-1)
    #   全被边缘夹取 = 纯空按。实证：开列表面板后连拍 A(重锚前)/B(重锚后)，
    #   全屏 diff 22665 ≈ 无输入噪声基线 23394；三个结构区（放大窗/上屏左上窗/整棋盘）
    #   diff 全部 ≤ 基线 ⇒ 重锚零状态变化。默认跳过，省 C-1+R-1 次空按
    #   （8×8 省 14、15×15 省 28、20×25 省 43；小盘/密盘收益占比最高，正对「易慢于尺寸」）。
    #   ⚠️ 补填循环里的重锚仍保留——补填时光标已走遍全盘，回 (0,0) 再重走是必要的。
    #   换游戏/盘面起点会变的场合用 AI_TAS_REANCHOR=1（或 run_fill(reanchor=True)）恢复。
    if reanchor:
        for _ in range(C - 1):
            press(LEFT); cnt[0] += 1
        for _ in range(R - 1):
            press(UP); cnt[0] += 1

    # ③ 执行
    if plan_src == 'json':
        # 实测面板页 + 循环翻页重建（§U 循环模型 + 窗口态模拟恢复徽章）
        now_page, npages = detect_page(len(cands))
        if detect_only:
            # 探针：只测「进关后面板开在第几页」就退（不执行、不判定），
            # 用于确认开页页号（实测恒第0页 ⇒ 重规划用页升序）
            print('探针 detect_only：rec%d 开页页号=%d（%d 页盘）→ 退出'
                  % (REC_IDX, now_page, npages), flush=True)
            return True, None
        fixed, npress, endpage, nohop = rebuild_pages_sim(
            seq, plan_local, R, C, now_page, npages)
        print('  循环翻页重建：%d → %d 步（翻页 %d 次；无跳变体 %d 步）'
              % (len(seq), len(fixed), npress, len(nohop)), flush=True)
        exec_seq(fixed, cnt)
        fill_dt = time.time() - t0
        print('填字段 %.2fs / %d 动作（%.3fs/动作）'
              % (fill_dt, cnt[0], fill_dt / cnt[0]), flush=True)
    else:
        # 旧 beam 路径（AI_TAS_PLAN_SRC=beam）：walk_execute（撞组即停/免点击）
        w = Win((0, 0), (0, 0), R, C)
        cur_page = 0
        for i, (k, tgt) in enumerate(seq):
            p = plan_local[k]
            tgt = tuple(tgt)
            free = walk_execute(w, tgt, p['cells'], cnt)
            if not free:
                # tgt 进窗但光标不在组内 → 点 tgt 窗内格（光标跳到 tgt）
                wi, wj = tgt[0] - w.org[0], tgt[1] - w.org[1]
                B.tap(26 + WIN_STEP * wj, 24 + WIN_STEP * wi, after=ARROW_AFTER)
                cnt[0] += 1
                w.cur = list(tgt)
            cur_page = tap_kanji(p['li'], cur_page)
            B.sleep(FILL_WAIT)
            B.flush()                   # §S46：每组末一次性发出（省 per-action 进程开销）
        fill_dt = time.time() - t0
        print('填字段 %.2fs / %d 动作（%.3fs/动作）'
              % (fill_dt, cnt[0], fill_dt / cnt[0]), flush=True)

    # ④ 完成判定：轮询「正解!」横幅 = 本关通过的权威信号（选关页判定不可用：
    #    mode2 选关页仅 7 格，on_level_select 的 dark_mid>3000 判据恒 False）。
    #    正解后流程实测：正解!横幅 → セーブ中です…（+1.5s 仍在存档）→ 自动回选关页。
    poll = '%s/seikai_poll.png' % SHOT
    F.wait_seikai_shot(poll, timeout=8.0)
    ok = False
    if F.banner_visible(poll):
        ok = True
        if ev:
            os.makedirs(os.path.dirname(ev) or '.', exist_ok=True)
            # §S37 调色板量化：NDS 画面实际色数 ≤127，256 色调色板完全容纳、
            # 像素差 0.00（数学无损），与模式1/3 证据图口径一致（原 raw PNG 偏大、加载慢）
            _im = Image.open(poll).convert('RGB')
            _im = _im.quantize(colors=256, dither=Image.NONE)
            _im.save(ev)
            print('  ✅ 正解! 确认 → 证据图(量化) %s' % ev, flush=True)
        else:
            print('  ✅ 正解! 确认 → 本关通过', flush=True)
        time.sleep(5.0)                     # セーブ中です… 落盘后自动回选关页
    else:
        print('  ⚠️ 8s 未见正解! → 仍在关内，重走全序列补填', flush=True)
        for rnd in range(1, 4):
            if plan_src == 'json':
                # 徽章已绑定（蓝）时 hop 跳不动（§S12）⇒ 用无跳变体（hop→等效箭头）。
                # ★ 补填轮前**重测面板实际页**（§S57.7）：首轮若掉了翻页输入，模拟页
                #   与游戏实际页失同步，按模拟 endpage 重建会轮轮点错页（rec270/278
                #   三轮全败根因）；重测后从实测页重建，级联立断。
                now_page, _np = remeasure_page(len(cands))
                fixed2, _, _, nohop2 = rebuild_pages_sim(
                    seq, plan_local, R, C, now_page, _np)
                for _ in range(BOARD[1] - 1):
                    press(LEFT); cnt[0] += 1
                for _ in range(BOARD[0] - 1):
                    press(UP); cnt[0] += 1
                exec_seq(nohop2, cnt, tag='（补填轮%d）' % rnd)
            else:
                # 重锚到 (0,0) 后重走 beam 全序列（纯模型，不限盘面尺寸）
                for _ in range(BOARD[1] - 1):
                    press(LEFT); cnt[0] += 1
                for _ in range(BOARD[0] - 1):
                    press(UP); cnt[0] += 1
                w.org, w.cur = [0, 0], [0, 0]
                cur_page = 0
                for (k, tgt) in seq:
                    p = plan_local[k]; tgt = tuple(tgt)
                    free = walk_execute(w, tgt, p['cells'], cnt)
                    if not free:
                        wi, wj = tgt[0] - w.org[0], tgt[1] - w.org[1]
                        B.tap(26 + WIN_STEP * wj, 24 + WIN_STEP * wi, after=ARROW_AFTER)
                        cnt[0] += 1
                        w.cur = list(tgt)
                    cur_page = tap_kanji(p['li'], cur_page)
                    B.sleep(FILL_WAIT)
                    B.flush()
            F.wait_seikai_shot(poll, timeout=8.0)
            if F.banner_visible(poll):
                ok = True
                if ev:
                    os.makedirs(os.path.dirname(ev) or '.', exist_ok=True)
                    _im = Image.open(poll).convert('RGB')
                    _im = _im.quantize(colors=256, dither=Image.NONE)
                    _im.save(ev)
                print('     轮%d：正解! 确认，补填成功 ✅' % rnd, flush=True)
                time.sleep(5.0)
                break
            print('     轮%d：仍未见正解!，重试' % rnd, flush=True)

    total = time.time() - t0
    print('=== 合计 %.2fs / %d 动作（ARROW_AFTER=%.3f FILL_WAIT=%.3f KANJI_AFTER=%.3f）'
          % (total, cnt[0], ARROW_AFTER, FILL_WAIT, KANJI_AFTER), flush=True)
    return ok, poll


def main():
    """独立运行（向后兼容旧命令）：冷启动 → 导航 → run_fill。"""
    # 冷启动 + 导航（模式2 专用路径）；填字交给 run_fill。
    subprocess.run(['pkill', '-x', 'desmume-cli'], check=False)
    time.sleep(2)
    subprocess.run(['bash', '/workspace/Kanji/ai-tas/scripts/ensure_env.sh'],
                   check=False, capture_output=True)
    wt = F.wait_title()        # §S46：轮询标题页就绪（实测 ~8s），替代 INIT_WAIT 30s 盲等
    print('冷启动 → 标题页就绪 %.1fs' % wt, flush=True)
    nav()
    run_fill(rec=REC_IDX, evidence=SEIKAI_SHOT,
             detect_only=(os.environ.get('AI_TAS_DETECT_ONLY') == '1'))
    time.sleep(1.2)
    F.shot('/tmp/M2F_final.png')
    print('成品截图 /tmp/M2F_final.png', flush=True)


if __name__ == '__main__':
    main()
