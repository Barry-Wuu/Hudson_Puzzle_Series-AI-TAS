#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""《解谜系列Vol.13：漢字解謎》AI-TAS 公共底座：导航 / 结算 / 像素判定 / 关卡几何。

本模块是从原 `fill_any.py`（通用自动通关驱动）中抽出的**共用部分**：
  * 旧的「対応表 → リスト」慢速填字路径已废弃，由快通执行器 `fill_fast_any.py`
    （动作序列由 `plan_fast.py` 离线规划、先算后打）取代；
  * 但**导航**（冷启动 PRE_NAV / 热启动点关）、**结算过场推进**、**通关像素判定**、
    **选关网格几何**——这些对任何填字策略都通用，故独立成本模块，供
    `fill_fast_any.py` / `grid_verify.py` / `calib_arrows4.py` 复用。

★ 设计原则：本模块**不做任何填字**，只管两件事——
    1) 把游戏导航到「某关的填字界面」；
    2) 从结算后的选关页像素判定「该关是否已通关」。
  填字动作序列由调用方（plan_fast）提供。

坐标约定
--------
* 一律为「下屏 NDS 相对坐标」(0-255, 0-191)：屏幕左上为 (0,0)，窗口偏移由
  AI_TAS_WX / AI_TAS_WY 给出（本沙箱 384 / 192，原作者宿主机 192 / 48）。
* 设计坐标（按键精灵 1.5× 空间）= (下屏 x*1.5, 下屏 y*1.5 + 288)，换算见 plan_fast。

环境变量
--------
AI_TAS_DISPLAY    Xvfb 显示号，默认 :99
AI_TAS_WX / WY    DeSmuME 窗口左上角屏幕坐标，默认 384 / 192（本沙箱）
AI_TAS_INIT_WAIT  冷启动存档初始化等待秒数，默认 30
AI_TAS_DIFFICULTY 模式1 难度：yasashii(默认) / futsuu / muzukashii
AI_TAS_SHOT_DIR   通关证据截图输出目录，默认 /tmp
AI_TAS_DIAG_DIR   过场诊断截图目录，默认 /tmp（不进仓库）

产出截图
--------
每关**只留一张**通关证据（由调用方在填字完成后抓）：`<SHOT_DIR>/l<NN>_fill_complete.png`。
结算过场（弹窗/保存/选关页）的诊断截图一律写 `<DIAG_DIR>`，默认 /tmp，不污染仓库。
"""
import os
import shutil
import subprocess
import time

# --- 环境 --------------------------------------------------------------------
DISPLAY = os.environ.get('AI_TAS_DISPLAY', ':99')
ENV = dict(os.environ, DISPLAY=DISPLAY)
WX = int(os.environ.get('AI_TAS_WX', 384))
WY = int(os.environ.get('AI_TAS_WY', 192))
INIT_WAIT = int(os.environ.get('AI_TAS_INIT_WAIT', 30))
SHOT_DIR = os.environ.get('AI_TAS_SHOT_DIR', '/tmp')
# 过场诊断截图目录（默认 /tmp，不进仓库）——仓库里每关只留一张通关截图
DIAG_DIR = os.environ.get('AI_TAS_DIAG_DIR', '/tmp')

# --- 时序参数（env 可调，便于在沙箱实测中扫参）-------------------------------
# ★ 2026-10-12 实测下界（中1，248 次点按压测，见 sweep_driver.py）：
#   * TAP_AFTER：默认 0.12 偏保守，实测压到 0.02（甚至 0.005）仍稳定通关；
#     历史上「0.10 失败」并非 click 间隔本身，而是别处时序耦合问题，已排除。
#   * TAP_HOLD + TAP_MOVE_GAP（press 手势总时长）才是硬约束：≥~0.06s 可靠，
#     低至 0.04~0.05s 时 248 次点按中偶发绑定丢失 → 不出正解。故保留 HOLD=0.06/GAP=0.04
#     作为生产默认（余量充足），但理论上 HOLD=0.04/GAP=0.03（手势 0.07）已实测 2× 稳定。
#   * 想全量提速请用 env 覆盖，并在多关上验证，勿单关通过就全量跑。
TAP_HOLD = float(os.environ.get('AI_TAS_TAP_HOLD', 0.06))
TAP_AFTER = float(os.environ.get('AI_TAS_TAP_AFTER', 0.12))
# 物理按键（方向键 / L·R 肩键）保键时长：瞬时 xdotool key 会概率性丢键（§S18 实测），
# 0.04 是可靠下界，生产默认给 0.05 留余量；单价 ≈ hold + ~0.03s xdotool 开销。
KEY_HOLD = float(os.environ.get('AI_TAS_KEY_HOLD', 0.05))
# mousemove 与 mousedown 之间的固定间隔（xdotool 内联 sleep）。
# 历史注释称此间隔「必须 ~40ms，否则 press 落在上一坐标」；但本扫参实验
# 验证 0.02/0.01/0.0 在中1（248 次点按）下仍可通关，故改为可配置。
TAP_MOVE_GAP = float(os.environ.get('AI_TAS_MOVE_GAP', 0.04))
# 面板切换（対応表<->リスト 图标）带约 0.3s 动画，必须等够；
PANEL_AFTER = float(os.environ.get('AI_TAS_PANEL_AFTER', 0.5))
SETTLE_POLL = float(os.environ.get('AI_TAS_SETTLE_POLL', 0.4))
NAV_TAP_AFTER = float(os.environ.get('AI_TAS_NAV_AFTER', 1.5))
# 非空则结算阶段只抓帧不点弹窗（用于观察过场、标定 is_popup）
OBSERVE = os.environ.get('AI_TAS_OBSERVE')
XBATCH_DEBUG = bool(os.environ.get('AI_TAS_BATCH_DEBUG'))

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
import sys
sys.path.insert(0, REPO)

# --- 难度（模式1 通常問題 的第1/2/3难度）---------------------------------------
# 关卡↔datasheet 记录映射（实机锚定，见 PITFALLS §H3 / §E6）：
#   やさしい  : No.N = rec(N-1)                  → rec0-34    (35 关)
#   ふつう    : No.N = rec(54+N)                 → rec55-114  (60 关，全部可解)
#   むずかしい: No.1-40  = rec(114+N)  → rec115-154  (39/40 可解，rec119 解析失败)
#             No.41-55 = rec(189+N)  → rec230-244  (14/15 可解，rec238 解析失败)
#             No.56-60 = rec(209+N)  → rec265-269  (5/5 可解，2026-10-12 实机口の数定位)
#             No.61-65 = rec(N+94)   → rec155-159  (5/5 可解，口の数 337-341)
# 注：关卡几何（level_xy）对三难度**完全相同**（同一 10 列网格），差异只在难度按钮。
# 难度按钮坐标（下屏 NDS 相对坐标，像素实测粉色带 RGB(255,131,131) 中心）：
#   やさしい y≈59 / ふつう y≈100 / むずかしい y≈140，x 中心≈127（粉钮横跨 x 42-213）。
DIFFS = {
    'yasashii':   dict(name='やさしい',  base=0,   n=35, btn=(127, 59), expect=35),
    'futsuu':     dict(name='ふつう',    base=54,  n=60, btn=(127, 100), expect=60),
    'muzukashii': dict(name='むずかしい', base=114, n=65, btn=(127, 140), expect=65),
}
DIFF_ALIAS = {'yasashii': 'yasashii', 'futsuu': 'futsuu', 'muzukashii': 'muzukashii',
              'y': 'yasashii', 'f': 'futsuu', 'm': 'muzukashii',
              'easy': 'yasashii', 'normal': 'futsuu', 'hard': 'muzukashii',
              'やさしい': 'yasashii', 'ふつう': 'futsuu', 'むずかしい': 'muzukashii'}
DIFF = DIFF_ALIAS.get(os.environ.get('AI_TAS_DIFFICULTY', 'yasashii').lower(), 'yasashii')


def level_to_rec(diff, level):
    """难度 diff 的关卡 level(1-based) → datasheet 记录号。"""
    level = int(level)
    if diff == 'yasashii':
        return level - 1
    if diff == 'futsuu':
        return 54 + level
    if diff == 'muzukashii':
        if 1 <= level <= 40:
            return 114 + level          # rec115-154
        if 41 <= level <= 55:
            return 189 + level          # rec230-244
        if 56 <= level <= 60:
            return 209 + level          # rec265-269（实机 口の数 交叉比对定位）
        if 61 <= level <= 65:
            return level + 94           # rec155-159 (61->155 ... 65->159)
        raise SystemExit('难度 %s 无关卡 %s 的映射' % (diff, level))
    raise SystemExit('难度 %s 无关卡 %s 的映射' % (diff, level))


# --- 模式2「ひりどりナンクロ」/ 模式3「ホワイトパズル」通常問題 rec 表 -------------
# 2026-10-14 逐关实机标定（口径：选关页切选中框 → 读上屏「口の数」→ datasheet 反查，
# 取唯一连续段匹配；方法/全表见 REPORT.md §8b 与 PITFALLS.md §S29）：
#   模式2 ひりどりナンクロ 通常問題：
#     やさしい   No.01-05 = rec260-264（8×8）、No.06 = rec250（15×15）、No.07 = rec251（16×16）
#     ふつう     No.01-15 = rec270-284（全 25×20）
#     むずかしい No.01-15 = rec285-299（全 25×20）
#   模式3 ホワイトパズル 通常問題：
#     やさしい   No.01-15 = rec160-174（全 8×8）
#     ふつう     No.01-15 = rec195-209（全 25×20）
#     むずかしい No.01-20 = rec210-229、No.21-25 = rec245-249（全 25×20，尾 5 关特别大盘）
MODE2_REC = {
    'yasashii':   [260, 261, 262, 263, 264, 250, 251],
    'futsuu':     list(range(270, 285)),
    'muzukashii': list(range(285, 300)),
}
MODE3_REC = {
    'yasashii':   list(range(160, 175)),
    'futsuu':     list(range(195, 210)),
    'muzukashii': list(range(210, 230)) + list(range(245, 250)),
}
MODE_REC = {2: MODE2_REC, 3: MODE3_REC}

# --- 模式1「認定問題」随机题库 rec 表（2026-10-15 实测，见 PITFALLS §S50）--------
# 認定题库 = rec35-54（20 题），按 rec 号**连续切 4 段、每段 5 题**，一段对应一级。
# ★ 每级**进盘时从本段随机抽 1 题（有放回）**——不是固定轮转；要看全 5 题须反复「进盘→退出→再进盘」。
#   级别↔段：ブロンズ=35-39 / シルバー=40-44 / ゴールド=45-49 / プラチナ=50-54。
# 免进盘预筛：级别菜单上屏「ロの数」= 下一题徽章格总数（口径见 PITFALLS §S50.1/§S30.8）。
KENTEI_REC = {
    'bronze':   list(range(35, 40)),
    'silver':   list(range(40, 45)),
    'gold':     list(range(45, 50)),
    'platinum': list(range(50, 55)),
}
# 模式3 ホワイトパズル 認定問題（2026-10-15 实测，见 PITFALLS §S52）：
# 题库 = rec175-194（原「模式3 额外段/无登场关卡」20 条），同样按号连续切 4 段、每段 5 题。
KENTEI_REC_M3 = {
    'bronze':   list(range(175, 180)),
    'silver':   list(range(180, 185)),
    'gold':     list(range(185, 190)),
    'platinum': list(range(190, 195)),
}
# 模式2 ひりどりナンクロ 認定問題（2026-10-16 实测，见 PITFALLS §S58）：
# ★ 与模式1/3 不同——**每级只有 2 个变体**（不切 5 题段），进盘从本对随机抽 1 题、有放回。
KENTEI_REC_M2 = {
    'bronze':   [252, 253],
    'silver':   [254, 255],
    'gold':     [256, 257],
    'platinum': [258, 259],
}
# 模式号 → 認定题库表（1/2/3）
KENTEI_TABLE = {1: KENTEI_REC, 2: KENTEI_REC_M2, 3: KENTEI_REC_M3}
# 级别别名（英文/单字母/日文）→ KENTEI_REC 键
KENTEI_ALIAS = {'bronze': 'bronze', 'b': 'bronze', 'ブロンズ': 'bronze',
                'silver': 'silver', 's': 'silver', 'シルバー': 'silver',
                'gold': 'gold', 'g': 'gold', 'ゴールド': 'gold',
                'platinum': 'platinum', 'p': 'platinum', 'プラチナ': 'platinum'}


def kentei_recs(level, mode=1):
    """「認定問題」某级别的题库（rec 列表）。level 支持别名（见 KENTEI_ALIAS）。

    mode=1 漢字ナンクロ（rec35-54，四级各 5 题，§S50）；
    mode=2 ひりどりナンクロ（rec252-259，四级各 2 变体，§S58）；
    mode=3 ホワイトパズル（rec175-194，四级各 5 题，§S52）。

    >>> kentei_recs('ブロンズ'), kentei_recs('platinum')
    ([35, 36, 37, 38, 39], [50, 51, 52, 53, 54])
    >>> kentei_recs('bronze', 3), kentei_recs('p', 3)
    ([175, 176, 177, 178, 179], [190, 191, 192, 193, 194])
    >>> kentei_recs('silver', 2)
    [254, 255]
    """
    table = KENTEI_TABLE.get(int(mode))
    if table is None:
        raise SystemExit('模式 %s 无認定問題题库（可选 1/2/3）' % mode)
    key = KENTEI_ALIAS.get(str(level).lower(), str(level))
    if key not in table:
        raise SystemExit('未知认定级别 %r（可选 %s）' % (level, list(table)))
    return list(table[key])


def rec_for(mode, diff, level):
    """(模式号 1/2/3, 难度, 关卡 1-based) → datasheet 记录号。

    模式1 走 level_to_rec（分段公式见上）；模式2/3「通常問題」查 MODE2_REC / MODE3_REC。
    diff 支持别名（easy/normal/hard 或日文/单字母），见 DIFF_ALIAS。

    >>> rec_for(2, 'yasashii', 1), rec_for(2, 'futsuu', 1), rec_for(3, 'muzukashii', 25)
    (260, 270, 249)
    """
    mode, level = int(mode), int(level)
    diff = DIFF_ALIAS.get(str(diff).lower(), diff)
    if mode == 1:
        return level_to_rec(diff, level)
    table = MODE_REC.get(mode)
    if not table or diff not in table:
        raise SystemExit('模式 %s 的难度 %s 无 rec 映射' % (mode, diff))
    seq = table[diff]
    if not (1 <= level <= len(seq)):
        raise SystemExit('模式 %s/%s 无关卡 %s（该难度共 %d 关）'
                         % (mode, diff, level, len(seq)))
    return seq[level - 1]


def rec_for_level(level):
    return level_to_rec(DIFF, level)

# --- 关卡几何（选关网格）-------------------------------------------------------
# 选关网格（下屏相对坐标，像素级实测）：列中心 x = 19/43/.../235（10 列，步长 24）；
# 行中心 y = 79/99/119/139（步长 20）。
# ★ やさしい 共 35 关，第 4 行（y=139）是 No.31~35。旧代码曾把第四行误标成 81~85。
# ★ 三难度共用同一网格几何：ふつう 60 关（6 行）、むずかしい 65 关（7 行），
#   第 6/7 行需先滚动（▼）才能点到，见 PITFALLS §S。
LEVEL_COLS, LEVEL_DX, LEVEL_DY, LEVEL_X0, LEVEL_Y0 = 10, 24, 20, 19, 79
# 选关页点两下后等「開始!」横幅消失再填。
# ★ 2026-10-11 旧注释称「5.0 不能缩短、⚠️别调小」——**经 2026-10-12 实测已推翻**：
#   中1 上 NAV_ENTER_WAIT 压到 1.5（配合 NAV_TAP_AFTER=0.3）仍稳定通关。
#   真正的硬约束是「进关手势总时长」= NAV_TAP_AFTER + NAV_ENTER_WAIT ≥ ~1.8s
#   （游戏载入关卡棋盘的固有时间）：NT=1.5+NE=0.3=1.8 ✅，但 NT=1.5+NE=0.2=1.7 ❌；
#   同理 NT=0.3+NE=1.5=1.8 ✅。两参数可互换分配，但和不能低于 ~1.8s。
#   5.0 作为生产默认保留（余量足、不冒险），提速请用 env 覆盖并多关验证。
NAV_ENTER_WAIT = float(os.environ.get('AI_TAS_NAV_ENTER_WAIT', 5.0))


def level_xy(n):
    """关卡 No.N 在选关网格中的下屏坐标（10 列 × N 行，三难度同一几何）。"""
    n = int(n)
    i = n - 1
    r, c = divmod(i, LEVEL_COLS)
    return (LEVEL_X0 + c * LEVEL_DX, LEVEL_Y0 + r * LEVEL_DY)


# --- 冷启动必经序列 ------------------------------------------------------------
# 每个元素是 (x, y, after) 三次组，或 ('wait', 秒数) 表示只等待不点。
#   标题画面 → ファイル選択 → [読み込み中 过场，自动推进、会吃掉一次点击] →
#   ゲーム選択 → 模式(通常問題) → 難易度 → 选关页
# ★★★ 2026-10 重大修正：选完「ファイル1」后游戏会播一段「読み込み中」过场并
#   **自动**推进到ゲーム選択，期间任何点击都会被吞。旧版 PRE_NAV 没有这段等待，
#   导致下一击 (135,51) 打在过场上、整条序列错位 —— 实测 No.28 冷启动误进 No.33。
#   现插入 ('wait', 3.0) 等过场播完，再点后续按钮；点完难度钮后再等让关卡网格就绪。
# ★ 难度按钮点击次数（2026-10-11 实机）：やさしい 是默认高亮项，**单击即进**选关页；
#   ふつう/むずかしい 需**单击选中再单击进入**（第一下只高亮、不进入）。故按 DIFF 追加。
_DIFF_BTN = DIFFS[DIFF]['btn']
_DIFF_STEPS = [(_DIFF_BTN[0], _DIFF_BTN[1], NAV_TAP_AFTER)]
if DIFF != 'yasashii':
    _DIFF_STEPS.append((_DIFF_BTN[0], _DIFF_BTN[1], NAV_TAP_AFTER))
PRE_NAV = [
    (128, 100, NAV_TAP_AFTER),   # ① 标题画面：任意点 → ファイル選択
    ( 95,  76, NAV_TAP_AFTER),   # ② ファイル選択：选「ファイル1」
    ('wait', 3.0),               # ③ 等「読み込み中」过场自动推进完（关键！否则整条错位）
    (135,  51, NAV_TAP_AFTER),   # ④ ゲーム選択：漢字ナンクロ「スタート」
    (135,  57, NAV_TAP_AFTER),   # ⑤ 模式菜单：「通常問題」
    *_DIFF_STEPS,                # ⑥/⑦ 難易度：当前 DIFF → 选关页
]


# --- 基础动作 -----------------------------------------------------------------
def tap(x, y, hold=None, after=None):
    """按压式触摸到下屏相对坐标 (x,y)。瞬时 click 游戏不识别。

    ★ 时序铁律：mousemove 与 mousedown 之间必须留 ~40ms 间隔。2026-10 曾把
      tap 改成「单次 xdotool 调用（move+down+up 一气呵成）」想提速，结果连续
      快速绑定时游戏把 press 落在「上一坐标」、整批绑定失效（单关填字 delta=0、
      永不出现 正解）。本版在**单进程**里用 xdotool 内联 `sleep 0.04` 精确复刻
      那段间隔：既保住进程数减半的提速，又不被 SDL 吞掉 press。
    """
    hold = TAP_HOLD if hold is None else hold
    after = TAP_AFTER if after is None else after
    ax, ay = WX + int(x), WY + 192 + int(y)
    subprocess.run(['xdotool', 'mousemove', str(ax), str(ay),
                    'sleep', ('%.3f' % TAP_MOVE_GAP), 'mousedown', '1',
                    'sleep', ('%.3f' % hold), 'mouseup', '1'],
                   env=ENV, check=False)
    time.sleep(after)


def key_press(name, hold=None, after=None):
    """物理按键（DeSmuME SDL 前端：方向键 = NDS D-pad，`q`/`w` = L/R 肩键）。

    ★ 实测铁律（PITFALLS §S18，2026-10-12）：`xdotool key` **瞬时按键会概率性丢键**
      （约一半命中，实测：w 瞬时无反应、q 瞬时命中；D-pad 瞬时 27 次只走 ~8 步）。
      必须 `keydown → hold(≥0.04) → keyup`。可靠单价 ≈ 0.079s（hold 0.05）。
    """
    hold = KEY_HOLD if hold is None else hold
    after = TAP_AFTER if after is None else after
    subprocess.run(['xdotool', 'keydown', name], env=ENV, check=False)
    time.sleep(hold)
    subprocess.run(['xdotool', 'keyup', name], env=ENV, check=False)
    time.sleep(after)


def hop(key, hold=None, after=None):
    """L/R 肩键跳跃（`w` = R 向前 / `q` = L 向后）。

    §S12：hop 会在**当前所选徽章的待填格之间按读序循环**，且**每次都把缩略图窗口
    重锚到 clamp(光标格)**；光标在已绑定（蓝）格上时跳不动。
    """
    key_press(key, hold=hold, after=after)


class XBatch:
    """xdotool 动作攒批器：把多个动作合并进**一次** xdotool 子进程调用。

    动机（2026-10-15 实测，PITFALLS §S46）：单动作 `subprocess.run(['xdotool', ...])`
    的机制开销 ≈0.1s/次（xdotool 裸进程仅 0.0027s，余下是 Python fork/exec/管道等待）；
    模式2 ふつう一关 167 动作 ⇒ 纯进程开销 ~16.7s，占填字段 1/3。
    攒批后**时序与逐次调用逐位一致**：每个动作仍是 move→gap→down→hold→up→after，
    只是 sleep 全部内联进同一条 xdotool 命令链，游戏侧看到的输入序列不变。

    用法：
        B = XBatch()
        B.tap(118, 62, after=0.05)      # 入队，不发射
        B.sleep(0.12)                   # 入队一段内联等待
        B.flush()                       # 一次子进程发出全部；返回本批动作数
    注意：flush 前游戏不会收到任何输入 ⇒ **读屏幕判定之前必须先 flush**。
    """

    def __init__(self):
        self.cmd = ['xdotool']
        self.n = 0
        self.nom = 0.0            # 本批累计标称睡眠（用于诊断实际 vs 标称）

    def tap(self, x, y, hold=None, after=None):
        """入队一次按压（时序同 kanji_common.tap）。"""
        hold = TAP_HOLD if hold is None else hold
        after = TAP_AFTER if after is None else after
        ax, ay = WX + int(x), WY + 192 + int(y)
        self.cmd += ['mousemove', str(ax), str(ay),
                     'sleep', ('%.3f' % TAP_MOVE_GAP), 'mousedown', '1',
                     'sleep', ('%.3f' % hold), 'mouseup', '1']
        if after > 0:
            self.cmd += ['sleep', ('%.3f' % after)]
        self.n += 1
        self.nom += TAP_MOVE_GAP + hold + max(after, 0)
        return self

    def key(self, name, hold=None, after=None):
        """入队一次物理按键（keydown → hold → keyup，§S18 防丢键）。"""
        hold = KEY_HOLD if hold is None else hold
        after = TAP_AFTER if after is None else after
        self.cmd += ['keydown', name, 'sleep', ('%.3f' % hold), 'keyup', name]
        if after > 0:
            self.cmd += ['sleep', ('%.3f' % after)]
        self.n += 1
        self.nom += hold + max(after, 0)
        return self

    def sleep(self, t):
        """入队一段内联等待（不占动作数）。"""
        if t > 0:
            self.cmd += ['sleep', ('%.3f' % t)]
            self.nom += t
        return self

    def flush(self):
        """发射队列（一次子进程）。返回本批动作数。

        AI_TAS_BATCH_DEBUG=1 时打印「实际 vs 标称」耗时——用来诊断游戏侧
        输入处理是否跟不上（实际 >> 标称 ⇒ DeSmuME/SDL 在节拍我们的输入）。
        """
        n = self.n
        if n:
            _t0 = time.time() if XBATCH_DEBUG else None
            subprocess.run(self.cmd, env=ENV, check=False)
            if XBATCH_DEBUG:
                _d = time.time() - _t0
                print('    [batch] %d 动作 实际 %.3fs / 标称 %.3fs（差 %+.3fs）'
                      % (n, _d, self.nom, _d - self.nom), flush=True)
        self.cmd = ['xdotool']
        self.n = 0
        self.nom = 0.0
        return n

    def __len__(self):
        return self.n


# --- 快进（turbo）--------------------------------------------------------------
# ⚠️ 本沙箱的 desmume-cli 构建**没有快进热键**（2026-10-13 实测 27 个候选键全部 1×，
#    也没有速度控制台命令）；只有 --frameskip（无用：CPU 受限，且会打坏点按）与
#    --disable-limiter（启动期选项，会把肩键/方向键的保键窗口整体缩小）。
#    但在**自己的 DeSmuME（wx 版）**上快进键是有的（Config→Hotkeys 可查/改）。
# 用法：设 AI_TAS_FAST_KEY=<你的快进键名>，则在 nav 与 settle 段按住它。
FAST_KEY = os.environ.get('AI_TAS_FAST_KEY', '')


def turbo(on):
    """按住/松开快进键。未配置 AI_TAS_FAST_KEY 时是 no-op。

    ★ 只应在 nav / settle 段用：这两段是**纯触摸点按**，快进不影响注册；
      填字段有方向键/肩键输入，快进会让「保键 = 1 步」的窗口整体缩小 ⇒ 会错步。

    ★ 2026-10-15 实测结论（§S37）：**desmume-cli 0.9.11 不注册任何 host 倍速
      快捷键**——GUI 版默认的 Tab 快进在 CLI 版不存在（实测 Tab/space/f/t
      按住时 CPU 增速与基线持平 ≈1.0x）；`--disable-limiter` 是全程生效的
      命令行参数，无法「按住加速、松开恢复」，且会破坏填字段输入节奏。
      故本流水线在 CLI 版下是 no-op；换 GUI 版 DeSmuME 时设
      AI_TAS_FAST_KEY=Tab 即可在 nav/settle 段启用。
      结算段提速改走「砍固定睡 + import 快抓屏」路线（settle 11.2s→4.4s），
      「连点 A/B 跳过结算过场」亦实测无效（3.90s vs 3.2s，游戏动画刚性）。
    """
    if not FAST_KEY:
        return
    subprocess.run(['xdotool', 'keydown' if on else 'keyup', FAST_KEY],
                   env=ENV, check=False)


def _win_id():
    """DeSmuME 窗口 ID（Xvfb 重启后会变，故每次现找；找不到返回 None）。"""
    try:
        out = subprocess.run(['xdotool', 'search', '--name', 'desmume'],
                             env=ENV, capture_output=True, text=True, check=False)
        ids = out.stdout.split()
        return ids[0] if ids else None
    except Exception:
        return None


def shot(path):
    """抓 NDS 画面（256x384）。

    ★ 2026-10-15：ffmpeg x11grab 单帧实测 **477ms/张**（进程冷启 + 采集初始化），
      而 `import -window` 仅 **14ms/张**（快 34 倍）；抓图内容两者一致
      （尺寸相同、平均像素差 3.45/255、差异>30 的像素仅 2.96%，
      全是光标闪烁/动画噪声，不影响 on_level_select 等大面积结构判据）。
      import 失败（窗口找不到等）时回退 ffmpeg x11grab。
    ⚠️ import 依赖 desmume 窗口尺寸 = 256x384（实测无边框正好）；
       换前端/加边框后需回归本函数与各屏幕判据。
    """
    wid = _win_id()
    if wid:
        r = subprocess.run(['import', '-window', wid, path],
                           env=ENV, check=False, capture_output=True)
        if r.returncode == 0 and os.path.exists(path) \
                and os.path.getsize(path) > 0:
            return path
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'x11grab',
                    '-draw_mouse', '0',
                    '-video_size', '256x384', '-i', '%s+%d,%d' % (DISPLAY, WX, WY),
                    '-update', '1', '-frames:v', '1', path], env=ENV, check=False)
    return path


# --- 屏幕判别 ------------------------------------------------------------------
def _top_is_board(top):
    """上屏是否满屏谜题棋盘（供 on_level_select / in_fill_interface 复用）。

    填字界面的上屏是完整棋盘；选关页的上屏是标题/难度/预览，不是满棋盘。
    棋盘有两种视觉状态，任一满足即判定为棋盘：
      * 灰|蓝格多（已填/固定字多时）：阈值 >1200；
      * 黑网格线 + 白格多（刚进入时棋盘空白，只有格线与固定字）：
        黑>7000 且 白>3000（2026-10-11 实测 No.03 填字界面 黑≈8583/白≈6502，
        选关页上屏 黑≈5355，区分可靠；此前只查灰|蓝导致小盘空白棋盘被误判）。
      * **小盘分支（2026-10-15 模式3 やさしい 8×8 实测补）**：8×8 棋盘只有 64 格，
        黑网格线总量远低于大盘——实测填字界面 黑≈4770/白≈9471，够不到 7000 线，
        导致 in_fill_interface 恒 False、模式3 批量「进关失败」5/5。故加
        黑>3000 且 白>6000。已用全量样本回归：
          8×8 填字 4770/9471 ✓；8×8 选关预览 4428/6880（也判 True，但被
          in_fill_interface 的 dark_top>1500 排除）；難易度選択 4798/2864 ✗（白不够）；
          模式1 易/中/难填字图、模式3 导航 8 步画面 均无反转（原 False 仍 False）。
    """
    import numpy as np
    black = int((top.max(2) < 100).sum())
    white = int((top.min(2) > 200).sum())
    gray_blue = int((np.abs(top - np.array(UNCLEARED_GRAY)).max(2) <= 28).sum()
                    + (np.abs(top - np.array(CLEARED_BLUE)).max(2) <= 28).sum())
    return (gray_blue > 1200 or (black > 7000 and white > 3000)
            or (black > 3000 and white > 6000))   # 小盘（模式3 やさしい 8×8）


def on_level_select(path):
    """粗判当前是否停在选关页（**模式1 或 模式3「ホワイトパズル」**）。

    ★ 2026-10-11 重写（大难度实证）：旧版靠「蓝|灰格数 + 上屏非棋盘」判定，
      但 ふつう/むずかしい 的**选关页**：(a) 格子是黑色缩略图/数字（几无蓝|灰底），
      (b) 上屏是高亮关卡的**预览棋盘**（_top_is_board 也判为『棋盘』）——双重失效。
    新判据基于**下屏的疏密结构**：
      * 选关页下屏顶部（nds-y 5~60）是**稀疏**的标题/计数文字（「クリアした問題 NN/60」）；
      * 填字界面下屏同区是**密**的缩略图/リスト面板。
      实测 dark_top：选关页 ≈1062，填字界面 ≈2705~3490。故用比值 dark_top < dark_mid*0.3。
    通关过场并非固定：正解! → (★獲得数 弹窗) → 「セーブ中です…」 → 选关页，
    每关出现的环节/时长都可能不同，所以结算阶段用「检测 + 点击」的循环而非固定 sleep。

    ★ 2026-10-15 补模式3 分支：模式3 选关页**不满足**上面的「dark_mid>3000」——
      它的下屏是「難易度 + クリアした問題 NN/25」表头 + **2~3 行编号按钮**，
      dark_top≈1017~1209、dark_mid≈1900(15关)~3517(25关)。故新增一条独立强签名：
      **上屏是高亮关卡的预览棋盘（白格铺满）**，white≈6563(8×8)~22305(25×20)，
      而导航途中的 ファイル選択/ゲーム選択/通常問題/難易度選択 等画面 white≤2864
      （上屏是列表/按钮，非预览棋盘）——用 white>5000 干净分开；再用 dark_top 绝对分带
      (800~1600) 排除填字界面（其 dark_top≈2289+）与 正解 画面（≈3352+）。
      全量实测（导航 8 步画面 + 三难度选关页 + 填字界面 + 三种正解图 + 獲得数弹窗）无冲突。
    """
    try:
        from PIL import Image
        import numpy as np
        full = np.array(Image.open(path).convert('RGB')).astype(int)
        a = full[192:384, :, :]
        dark = (a.max(2) < 110)
        dark_top = int(dark[5:60].sum())      # 下屏顶部：选关页=稀疏表头
        dark_mid = int(dark[70:160].sum())    # 下屏中部：选关页=编号网格
        # ★ 2026-10-13 补 dark_top 下界：标题画面（漢字パズル KANJI PUZZLE）下屏顶部
        #   无暗像素（实测 dark_top=0、dark_mid≈3033），旧式 `dark_mid>3000 and
        #   dark_top<dark_mid*0.3` 会把标题屏误判成选关页（ratio=0 恒过），导致
        #   冷启动/自愈后在标题屏就"幂等返回"、后续点关全打空。选关页表头
        #   「クリアした問題 NN/35」实测 dark_top≈1062~1134，故 >400 可干净区分，
        #   不影响填字界面（dark_top≈2705+，本就靠 ratio>0.3 排除）。
        if dark_mid > 3000 and 400 < dark_top < dark_mid * 0.3:
            return True                      # —— 模式1 选关页（原判据，未改动）——
        # —— 模式3 选关页（2026-10-15 新增，见 docstring）——
        top_white = int((full[0:192].min(2) > 200).sum())
        return top_white > 5000 and 800 < dark_top < 1600
    except Exception:
        return False


def in_fill_interface(path):
    """判定是否停在「填字界面」：上屏是铺满的谜题棋盘，且下屏顶部是密的面板区。

    ★ 2026-10-11 补强（大难度）：原版还要求下屏 [120:180] 有「灰格」，但 ふつう/むずかしい
      的 縮略图/リスト 面板并非灰底 → bot_gray 常不达标、被误判「未进入」。改用与
      on_level_select 互补的 dark_top（填字界面下屏顶部密 ≈2705+，选关页稀疏 ≈1062）。
    """
    try:
        from PIL import Image
        import numpy as np
        full = np.array(Image.open(path).convert('RGB')).astype(int)
        top = full[0:192]
        if not _top_is_board(top):      # 上屏不是满棋盘 → 不是填字界面
            return False
        a = full[192:384]
        dark_top = int((a.max(2) < 110)[5:60].sum())
        return dark_top > 1500          # 下屏顶部密 = 面板（非选关页稀疏表头）
    except Exception:
        return False


def on_title(path=None):
    """判定是否停在**标题页**（漢字パズル logo / Puzzle Series Vol.13）。

    2026-10-15 冷启动实测标定（PITFALLS §S46）：desmume 冷启动到标题页就绪
    实测 ~8s（firmware 白屏 → 黑 → 标题），而 INIT_WAIT 盲等 30s ⇒ 每关白等
    ~22s。像素签名（上屏）：
      * 主标题文字带 y70-115 / x25-230 暗像素 ≈3164（阈值 >2500）
      * 左上 Vol.13 徽章带 y8-30 / x8-120 暗像素 ≈123（阈值 >60）
      * 整屏 mean ≈156.7（棕底，阈值 130~185）
    三者同时满足才认——白屏 firmware（mean 240）与黑屏过渡（mean 0）均排除。
    """
    if path is None:
        path = shot(os.path.join(DIAG_DIR, '_titlechk.png'))
    try:
        from PIL import Image
        import numpy as np
        a = np.array(Image.open(path).convert('L')).astype(int)[0:192]
        logo = a[70:115, 25:230]
        badge = a[8:30, 8:120]
        return (int((logo < 90).sum()) > 2500 and int((badge < 90).sum()) > 60
                and 130 < a.mean() < 185)
    except Exception:
        return False


def wait_title(timeout=25.0, poll=0.25):
    """冷启动后轮询等标题页就绪（替代 INIT_WAIT 盲等，§S46）。

    返回实际等待秒数；超时也放行（由 nav 首击 + 后续校验兜底）。
    """
    t0 = time.time()
    while time.time() - t0 < timeout:
        if on_title():
            return time.time() - t0
        time.sleep(poll)
    return time.time() - t0


def is_popup(path):
    """粗判是否处于通关结算弹窗（★獲得数 等）：下屏中央区域近白像素占比。"""
    try:
        from PIL import Image
        import numpy as np
        a = np.array(Image.open(path).convert('RGB'))[192:384, :, :].astype(int)
        region = a[40:150, 30:230]
        white = (region.max(2) > 220) & (region.min(2) > 175)
        return float(white.mean()) > 0.22
    except Exception:
        return False


# --- 通关判定（像素级实测标定）------------------------------------------------
# 选关页格子的**底色**就是通关状态本身：
#     已通关 = 蓝色底 RGB(65,164,255)      未通关 = 灰色底 RGB(148,148,148)
#   实测标定：已通关格 蓝 28.9%~39.5% / 灰 0%；未通关格 蓝 0.0% / 灰 8%~34%。
#   光标高亮不会把未通关格染蓝（No.30 带光标实测 蓝 0.0%），故判定安全。
CLEARED_BLUE = (65, 164, 255)
UNCLEARED_GRAY = (148, 148, 148)


def level_cleared(level, path=None):
    """实测某关在选关页是否已通关，返回 (bool, 蓝占比, 灰占比)。"""
    if path is None:
        path = shot(os.path.join(DIAG_DIR, '_clearchk.png'))
    from PIL import Image
    import numpy as np
    img = np.array(Image.open(path).convert('RGB')).astype(int)[192:384]
    x, y = level_xy(level)
    c = img[y - 5:y + 6, x - 9:x + 10]   # 格约 24x13，取中心小块避免串行
    blue = float((np.abs(c - np.array(CLEARED_BLUE)).max(2) <= 12).mean())
    gray = float((np.abs(c - np.array(UNCLEARED_GRAY)).max(2) <= 12).mean())
    return blue > gray, blue, gray


# --- 横幅 / 列表面板 像素判别（2026-10-13 实测标定，PITFALLS §S24）--------------------
# 進关「開始!」与过关「正解!」横幅：下屏中部 (y240-305, x55-205) 红色像素，
#   横幅挂起 ≈900，无横幅 ≈0 —— 两者同签名，banner_visible 通吃。
# リスト 面板：右面板 (y205-260, x140-245) 暗像素，
#   列表开 ≈1518（汉字笔画），入力 手写态 ≈758（空点阵）—— 阈值 1100 可判。
# 用途：① 進关后等横幅消失（**游戏内计时器从横幅消失起算**，实测见 §S24）；
#       ② 正解横幅出现即截证据图（计时器≈fill 耗时）；
#       ③ 校验 LISTMODE 切换真的生效（被吞则会静默涂胶到手写面板）。
BANNER_REGION = (240, 305, 55, 205)
PANEL_REGION = (205, 260, 140, 245)
BANNER_RED_MIN = 400
LIST_DARK_MIN = 1100


def _region_px(path, region):
    from PIL import Image
    import numpy as np
    y0, y1, x0, x1 = region
    return np.array(Image.open(path).convert('RGB')).astype(int)[y0:y1, x0:x1]


def banner_visible(path=None):
    """下屏中部横幅（開始!/正解!）是否挂着。"""
    if path is None:
        path = shot(os.path.join(DIAG_DIR, '_banner.png'))
    px = _region_px(path, BANNER_REGION)
    n = int(((px[:, :, 0] > 150) & (px[:, :, 1] < 110) & (px[:, :, 2] < 110)).sum())
    return n > BANNER_RED_MIN


def list_panel_open(path=None):
    """リスト 面板是否已打开（暗像素判别）。"""
    if path is None:
        path = shot(os.path.join(DIAG_DIR, '_listchk.png'))
    px = _region_px(path, PANEL_REGION)
    return int((px.max(2) < 100).sum()) > LIST_DARK_MIN


def wait_banner_gone(timeout=6.0, poll=0.1, settle_extra=0.1, appear_wait=1.5):
    """等「開始!」横幅出现再消失。

    返回时刻 ≈ 游戏内计时器起点（计时器从横幅消失起算，§S24 实测）。
    若 appear_wait 内横幅一直没出现（时序漂移/已过），也放行——由调用方
    的 list_panel_open 校验兜底。返回 False 表示超时仍见横幅。
    """
    t0 = time.time()
    seen = False
    while time.time() - t0 < timeout:
        p = shot(os.path.join(DIAG_DIR, '_bwait.png'))
        if banner_visible(p):
            seen = True
        elif seen or time.time() - t0 > appear_wait:
            time.sleep(settle_extra)   # 横幅末帧仍可能吞输入，留极小余量
            return True
        time.sleep(poll)
    return False


def wait_seikai_shot(out_path, timeout=3.0, poll=0.1):
    """等「正解!」横幅出现并立刻截图（证据图计时器 ≈ fill 耗时）。

    超时（如填字失败、永远不出正解）则直接截当前屏，交由 settle 诊断。
    """
    t0 = time.time()
    dbg = os.environ.get('AI_TAS_SEIKAI_DEBUG')
    k = 0
    while time.time() - t0 < timeout:
        p = shot(os.path.join(DIAG_DIR, '_seikaiwait.png'))
        vis = banner_visible(p)
        if dbg:
            k += 1
            shutil.copy(p, os.path.join(
                DIAG_DIR, '_seikaitrace_%03d_%s.png' % (k, 'Y' if vis else 'N')))
            print('    [seikai-trace] #%d t=%.2f banner=%s' % (k, time.time() - t0, vis), flush=True)
        if vis:
            # ★ 2026-10-13（§S26）：正解!横幅窗口极短（<0.3s），检测到后再 shot(out_path)
            #   二次抓取经常扑空（扑到黑场）——medium56/hard11/30/50 四张全黑图根因。
            #   直接把检测到横幅的这一帧复制为证据图，零重抓、零竞态。
            shutil.copy(p, out_path)
            return out_path
        time.sleep(poll)
    return shot(out_path)


# --- 结算 ---------------------------------------------------------------------
# 通关后会弹「★獲得数」结算框，位于**下屏 y≈130~190 的中央**；点它推进：
#   弹窗 → 「セーブ中です…」 → 选关页。
CLEAR_DISMISS = (128, 163)


def settle(level):
    """等待自动结算并推进过场，返回 True 若检测到已回到选关页。

    逻辑：正解! → (★獲得数 弹窗) → 点 (128,163) → セーブ中 → 选关页。
    过场环节/时长不固定，故用「检测到选关页即停，否则点击推进」的循环。
    正解后题盘已锁定，点击不会误填，安全；OBSERVE 模式只抓帧不点。

    ★ 2026-10-15：删固定 `sleep(3.0)`——实测该 3.0s **纯属浪费**：
      难1 实测「正解横幅 → 回选关页」整段过场仅 ~3.2s（★獲得数 + セーブ中，
      游戏动画时长刚性：连点 A/B 跳过实测无效，3.90s vs 3.2s 基线），
      固定睡结束时早已回到选关页、白躺 3s。且 §S24 实证过「预点不注册」，
      弹窗未出时点击落在已锁定题盘上无害，故直接零固定睡眠进轮询。
      叠加 shot() 换 `import`（477ms→14ms），结算段总耗时 11.2s → ~4s。
    """
    tag = 'l%02d' % level
    popup = os.path.join(DIAG_DIR, '%s_clear_popup.png' % tag)
    p = shot(popup)
    if on_level_select(p):
        print('  已退回选关页（无弹窗环节）')
        return True
    for i in range(30):
        p = shot(os.path.join(DIAG_DIR, '%s_settle_%02d.png' % (tag, i)))
        if on_level_select(p):
            print('  已退回选关页（第 %d 次检测确认）' % (i + 1))
            return True
        if not OBSERVE:
            tap(*CLEAR_DISMISS, after=0.4)   # 点掉 ★獲得数 弹窗 / 推进过场
        time.sleep(SETTLE_POLL)
    print('  ⚠️ 未检测到选关页——多半是徽章没绑全（未通关），'
          '请核对 l%02d_fill_complete.png' % level)
    return False


# --- 导航 ---------------------------------------------------------------------
def nav_to_fill(level, warm=False):
    """把游戏导航到 No.<level> 的填字界面（不填字）。

    warm=False（冷启动）：等 INIT_WAIT → 逐屏推进 PRE_NAV → 校验停在选关页 →
                          点关两次 → 等横幅消失 → 校验进入填字界面。
    warm=True（热启动续关）：假定已停在选关页（上一关结算后的常态），
                          仅校验选关页 → 点关两次 → 校验进入填字界面。
    任一步自校验失败即抛 SystemExit（宁可中止也不乱点）。
    """
    tag = 'l%02d' % level
    if warm:
        chk = shot(os.path.join(DIAG_DIR, '%s_warm_check.png' % tag))
        if not on_level_select(chk):
            raise SystemExit(
                '⚠️ --warm-nav 假定游戏已停在选关页，但实测不在（截图 %s）。\n'
                '   请先手工把游戏点到选关页再重跑。' % chk)
        print('[导航] 热启动：已确认在选关页，跳过 %ds 初始化与 %d 步冷启动导航'
              % (INIT_WAIT, len(PRE_NAV)))
    else:
        print('[导航] 等待游戏启动 %ds ...' % INIT_WAIT)
        time.sleep(INIT_WAIT)
        for step in PRE_NAV:
            if step[0] == 'wait':
                print('      导航 [等待 %.1fs 过场]' % step[1])
                time.sleep(step[1])
                continue
            x, y, after = step
            print('      导航 -> 下屏(%d,%d)  (after=%.1fs)' % (x, y, after))
            tap(x, y, after=after)
        nav_chk = shot(os.path.join(DIAG_DIR, '%s_navchk.png' % tag))
        if not on_level_select(nav_chk):
            raise SystemExit(
                '⚠️ 冷启动导航结束但未停在选关页（截图 %s）。\n'
                '   多半是 PRE_NAV 与当前游戏版本/存档对不上，别硬跑，先标定坐标系。' % nav_chk)
        print('      已到选关页（像素校验通过）')

    # 选关页需点**两下**才进关（第 1 下只是移光标 + 上屏显示该关信息）
    x, y = level_xy(level)
    print('      点关 No.%02d 两次 -> 下屏(%d,%d)' % (level, x, y))
    tap(x, y, after=NAV_TAP_AFTER)
    tap(x, y, after=NAV_TAP_AFTER)
    # ★ 2026-10-13：原为固定 sleep(NAV_ENTER_WAIT)（默认 5s，全计进游戏内计时器）。
    # 现改为「填字界面出现即返回」的轮询：进关瞬态（横幅前）就已 in_fill，
    # 尽早返回让调用方（fill_fast_any）抢在横幅消失前点 LISTMODE，
    # 把 0.85s 面板就绪延迟与横幅重叠（§S24：计时器从横幅消失起算）。
    # NAV_ENTER_WAIT 退化为超时上限，不再参与计时器。
    t_enter = time.time()
    enter_chk = None
    while time.time() - t_enter < max(NAV_ENTER_WAIT, 3.0):
        enter_chk = shot(os.path.join(DIAG_DIR, '%s_enterchk.png' % tag))
        if in_fill_interface(enter_chk):
            break
        time.sleep(0.1)
    if not in_fill_interface(enter_chk):
        raise SystemExit(
            '⚠️ 点关后未进入填字界面（截图 %s）。\n'
            '   可能 level_xy(%d)=(%d,%d) 落点漂移，或关卡网格还没就绪。'
            % (enter_chk, level, x, y))
    print('      已进入 No.%02d 填字界面（像素校验通过，+%.1fs）' % (level, time.time() - t_enter))
