#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统一 TAS runner —— 三种模式（通常問題 / 認定問題）的唯一入口（用参数控制）。

把原先散落的选关/过关脚本收敛成一个入口：
  * 模式1 漢字ナンクロ：曾用 fill_fast_any.py + batch_fast_diff.sh / batch_scroll_51plus.py / run_chunk.sh；
  * 模式2 ひりどりナンクロ：曾用 run_mode2_easy1_fast.py + sweep_mode2.py / grind_mode2.py；
  * 模式3 ホワイトパズル：曾用 m3_batch.py + m3_run.sh。
本脚本把「导航 / 时序 / 难度按钮 / 关卡网格 / 结算 / 认定」全部参数化（MODE 表），
底层**复用已验证的实现**（模式1/3 → fill_fast_any.do_fill；模式2 → run_mode2_easy1_fast.run_fill）。

用法（单关 / 批量 / 认定）：
  python3 run.py --mode 1 --diff yasashii --level 3
  python3 run.py --mode 1 --diff muzukashii --from 51 --to 65     # 含选关页滚动（§S14/S15）
  python3 run.py --mode 2 --diff futsuu --from 1 --to 15
  python3 run.py --mode 3 --diff muzukashii --level 20
  python3 run.py --mode 1 --kentei silver                          # 认定問題
  python3 run.py --mode 2 --kentei platinum --evidence validation/mode2_4_certification
  python3 run.py --mode 1 --diff yasashii --level 3 --bgm 2        # 首关盘内🔧切 BGM=2（持久化）

环境：DISPLAY=:0（本沙箱）；--shot-dir 覆盖证据输出目录。
时序：--pace fast（默认，验证档）/ safe（录制档：手势抬到可靠下界）/ realtime（保守）。
      --retry N：单关失败先退回选关页再重打 N 次（录制建议 2，避免一次偶发掉键毁掉整段）。
BGM：--bgm {1,2,3,4,none} 在首关进盘后经工具栏 🔧 → オプション 面板切换（§S60）。
"""
import argparse
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

# ---------------------------------------------------------------------------
# 时序预设：必须在 import TAS 模块前设定 AI_TAS_*（run_mode2_easy1_fast 在 import 期
#   读 env 并改写 kanji_common.F.TAP_HOLD）⇒ 先用 argv 预解析 --pace，再 import。
#   一组统一 env 覆盖三模式；值取自生产批处理（batch_fast_diff.sh / m3_run.sh §S31）。
#   ★ AI_TAS_PAGE_WAIT 不预设——模式1/3 默认 0.6、模式2 默认 0.15，各留各的下限。
# ---------------------------------------------------------------------------
_PACING = {
    'fast': dict(AI_TAS_TAP_HOLD='0.02', AI_TAS_MOVE_GAP='0.02', AI_TAS_TAP_AFTER='0.02',
                 AI_TAS_ARROW_AFTER='0.02', AI_TAS_KANJI_AFTER='0.02', AI_TAS_FILL_WAIT='0.02',
                 AI_TAS_HOP_AFTER='0.03', AI_TAS_BREATHE_EVERY='0', AI_TAS_PANEL_WAIT='0.6',
                 AI_TAS_SEIKAI_WAIT='0.1', AI_TAS_NAV_AFTER='1.5', AI_TAS_NAV_ENTER_WAIT='5.0'),
    # safe：**录制档**——只把 press 手势抬到 §S23 实测的可靠性下界（HOLD+GAP = 0.06；
    #   fast 只有 0.04，PITFALLS §S57.7 明载该档「偶发掉一个输入」）。
    #   徽章/箭头/翻页的间隔只微调，故填字耗时约为 fast 的 1.3 倍，换来录制少重试。
    'safe': dict(AI_TAS_TAP_HOLD='0.04', AI_TAS_MOVE_GAP='0.02', AI_TAS_TAP_AFTER='0.02',
                 AI_TAS_ARROW_AFTER='0.04', AI_TAS_KANJI_AFTER='0.03', AI_TAS_FILL_WAIT='0.03',
                 AI_TAS_HOP_AFTER='0.04', AI_TAS_BREATHE_EVERY='0', AI_TAS_PANEL_WAIT='0.7',
                 AI_TAS_SEIKAI_WAIT='0.5', AI_TAS_NAV_AFTER='1.5', AI_TAS_NAV_ENTER_WAIT='5.0'),
    'realtime': dict(AI_TAS_TAP_HOLD='0.06', AI_TAS_MOVE_GAP='0.04', AI_TAS_TAP_AFTER='0.12',
                     AI_TAS_ARROW_AFTER='0.05', AI_TAS_KANJI_AFTER='0.05', AI_TAS_FILL_WAIT='0.05',
                     AI_TAS_HOP_AFTER='0.05', AI_TAS_BREATHE_EVERY='10', AI_TAS_PANEL_WAIT='0.85',
                     AI_TAS_SEIKAI_WAIT='1.2', AI_TAS_NAV_AFTER='1.5', AI_TAS_NAV_ENTER_WAIT='5.0'),
}


def _preset_pace(argv, default='fast'):
    pace = default
    for i, a in enumerate(argv):
        if a == '--pace' and i + 1 < len(argv):
            pace = argv[i + 1]
        elif a.startswith('--pace='):
            pace = a.split('=', 1)[1]
    for k, v in _PACING.get(pace, _PACING[default]).items():
        os.environ.setdefault(k, v)
    return pace


PACE = _preset_pace(sys.argv)

import kanji_common as KC          # noqa: E402
import fill_fast_any as FF         # noqa: E402
import grind_mode2 as G            # noqa: E402

# ---------------------------------------------------------------------------
# 模式参数表：三模式的导航/几何/结算差异全部数据化（消掉 PRE_NAV / nav() / nav_to_m3_select 三份复制）
#   坐标均为下屏 NDS 相对坐标；来源见 PITFALLS §S30/§S50/§S52 与各 runner 实测。
# ---------------------------------------------------------------------------
GRID_COLS, GRID_DX, GRID_DY, GRID_X0 = 10, 24, 20, 19

MODES = {
    1: dict(
        name='漢字ナンクロ',
        game=(135, 51), game_clicks=1,           # ゲーム選択 スタート（单击即进）
        main_normal=(135, 57), main_kentei=(128, 96),
        diff={'yasashii': ((127, 59), 1), 'futsuu': ((127, 100), 2), 'muzukashii': ((127, 140), 2)},
        kentei_btn={'bronze': (128, 51), 'silver': (128, 82),
                    'gold': (128, 116), 'platinum': (128, 148)},
        grid_y=79, gaps=(0.0, 0.0, 0.0), scroll=True,
        exit_wrench=(40, 166),
        engine='design', settle='select', kentei_mode=1,
        folders=('mode1_1_easy', 'mode1_2_medium', 'mode1_3_hard'), evdir='mode1_4_certification',
    ),
    2: dict(
        name='ひりどりナンクロ',
        game=(136, 96), game_clicks=2,           # 模式2 スタート 必须两击
        main_normal=(135, 59), main_kentei=(135, 100),
        diff={'yasashii': ((135, 59), 1), 'futsuu': ((127, 100), 2), 'muzukashii': ((127, 140), 2)},
        kentei_btn={'bronze': (128, 52), 'silver': (128, 84),
                    'gold': (128, 116), 'platinum': (128, 148)},
        grid_y=83, gaps=(2.0, 2.0, 2.5), scroll=False,
        exit_wrench=(40, 166),
        engine='xbatch', settle='sleep', kentei_mode=2,
        folders=('mode2_1_easy', 'mode2_2_medium', 'mode2_3_hard'), evdir='mode2_4_certification',
    ),
    3: dict(
        name='ホワイトパズル',
        game=(135, 127), game_clicks=2,          # 第3行 スタート，非高亮项需两击
        main_normal=(135, 57), main_kentei=(128, 99),
        diff={'yasashii': ((127, 59), 1), 'futsuu': ((127, 100), 2), 'muzukashii': ((127, 140), 2)},
        kentei_btn={'bronze': (128, 51), 'silver': (128, 82),
                    'gold': (128, 116), 'platinum': (128, 148)},
        grid_y=79, gaps=(0.0, 0.0, 0.0), scroll=False,
        exit_wrench=(39, 164),                   # §S52.3：扳手比模式1 差 1px
        engine='design', settle='select', kentei_mode=3,
        folders=('mode3_1_easy', 'mode3_2_medium', 'mode3_3_hard'), evdir='mode3_4_certification',
    ),
}

DIFF_KEY = {'yasashii': 0, 'futsuu': 1, 'muzukashii': 2}

# ---------------------------------------------------------------------------
# BGM 切换（オプション 面板，设置持久化到 SRAM，主菜单⇄盘内共享同一值）。
#   入口两处：盘内工具栏 🔧（下排第2格，(33,167)）；ゲーム選択屏底部「オプション」。
#   面板布局：BGM 滑轨 1|2|3|4|なし（游戏 y≈71，黄块=当前档）；底部 問題選択/最初から/再開する。
#   坐标 §S60 像素实测：扳手 (33,167)、再開する (190,158)、黄块 y[258..269]（图像行）。
# ---------------------------------------------------------------------------
BGM_XY = {'1': 149, '2': 168, '3': 184, '4': 200, 'none': 220}
BGM_Y = 71
# 回读采样：滑轨在**图像行** 255..272（=游戏 y 63..80；⚠️ 截图是上下屏叠加 256x384，须 +192）。
_BGM_READ_ROWS = (255, 272)
# 各档 x 判读区间（图像坐标；由黄块 x[161..174]↔'2' 与等距档位标定）
_BGM_BOXES = [('1', 130, 158), ('2', 159, 175), ('3', 176, 191),
              ('4', 192, 209), ('none', 210, 235)]
BGM_WRENCH = (33, 167)      # 盘内工具栏 🔧（开オプション面板）
BGM_RESUME = (211, 184)     # 面板「再開する」（§S61 实测：底部按钮 y=184，非 158）
BGM_RESTART = (128, 184)    # 面板「最初から」
BGM_SELECT = (45, 184)      # 面板「問題選択」


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------
def _shot(name):
    return KC.shot(os.path.join(KC.DIAG_DIR, name))


def _is_board(mode, path):
    """填字界面判据：模式2 用 in_board（_top_is_board 对 8×8 失效），模式1/3 用 in_fill_interface。"""
    return G.in_board(path) if mode == 2 else KC.in_fill_interface(path)


def _on_select(mode, path):
    """选关页判据：模式2 用 on_select_page（返回按钮 + 非盘内），模式1/3 用 on_level_select。"""
    return G.on_select_page(path) if mode == 2 else KC.on_level_select(path)


def _set_shot_dir(shot_dir):
    """覆盖三模块的截图/诊断目录（在 import 之后设置模块全局，避免改动各模块默认）。"""
    KC.SHOT_DIR = shot_dir
    KC.DIAG_DIR = shot_dir
    G.SHOT = shot_dir                 # grind_mode2.settle 用其模块常量
    try:
        import run_mode2_easy1_fast as M2
        M2.SHOT = shot_dir
    except Exception:
        pass
    os.makedirs(shot_dir, exist_ok=True)


def default_folder(mode, diff):
    return MODES[mode]['folders'][DIFF_KEY[diff]]


def _cold_start():
    """干净重启模拟器并等标题页就绪（三模式共用入口）。"""
    subprocess.run(['pkill', '-x', 'desmume-cli'], check=False)
    time.sleep(2)
    subprocess.run(['bash', os.path.join(HERE, 'ensure_env.sh')],
                   check=False, capture_output=True)
    print('[导航] 冷启动 → 标题页就绪 %.1fs' % KC.wait_title(), flush=True)


# ---------------------------------------------------------------------------
# 导航（统一：冷启动 + 模式/难度/关卡，含模式1 选关页滚动）
# ---------------------------------------------------------------------------
def goto_select(mode, diff, warm=False):
    """把游戏导航到当前模式/难度的选关页。warm=True 假定已在选关页（只校验）。"""
    p = MODES[mode]
    if warm:
        chk = _shot('warm_check.png')
        if not _on_select(mode, chk):
            raise SystemExit('⚠️ --warm 假定已在选关页，但实测不在（截图 %s）' % chk)
        print('[导航] 热启动：已确认在选关页', flush=True)
        return
    _cold_start()
    _nav_to_main(mode)
    _, g2, g3 = p['gaps']
    KC.tap(*p['main_normal'], after=KC.NAV_TAP_AFTER)
    print('    -> 通常問題 %s' % (p['main_normal'],), flush=True)
    if g2:
        time.sleep(g2)
    btn, clicks = p['diff'][diff]
    for _ in range(clicks):
        KC.tap(*btn, after=KC.NAV_TAP_AFTER)
    print('    -> 難易度 %s ×%d' % (btn, clicks), flush=True)
    if g3:
        time.sleep(g3)
    chk = _shot('nav_select.png')
    if not _on_select(mode, chk):
        raise SystemExit('⚠️ 冷启动结束但未停在选关页（截图 %s）。检查 MODE[%d] 坐标。'
                         % (chk, mode))
    print('    ✅ 已到模式%d/%s 选关页（像素校验通过）' % (mode, diff), flush=True)


def _nav_to_main(mode):
    """冷启动后推进到该模式的「主菜单」（标题 → ファイル1 → 読込过场 → ゲーム選択）。"""
    p = MODES[mode]
    KC.tap(128, 100, after=KC.NAV_TAP_AFTER)      # タイトル → ファイル選択
    KC.tap(95, 76, after=KC.NAV_TAP_AFTER)        # ファイル1
    time.sleep(3.0)                              # 読み込み中 过场（会吃一次点击）
    for _ in range(p['game_clicks']):
        KC.tap(*p['game'], after=KC.NAV_TAP_AFTER)
    print('    -> ゲーム選択 %s ×%d' % (p['game'], p['game_clicks']), flush=True)
    if p['gaps'][0]:
        time.sleep(p['gaps'][0])


# ---------------------------------------------------------------------------
# BGM 切换：主菜单 オプション / 盘内 🔧 面板 两路入口，共享同一持久化设置
# ---------------------------------------------------------------------------
def read_bgm():
    """回读当前 BGM 档（必须在 オプション 面板打开时调用）。

    ⚠️ 截图是上下屏叠加 256x384，下屏游戏坐标要 +192：滑轨黄块在**图像行 258..269**
    （游戏 y 66..77）。对 5 档各自的 x 区间统计黄色像素，最多者即当前档。
    返回 '1'/'2'/'3'/'4'/'none'；看不到滑轨（面板未开）返回 None。
    """
    import numpy as np
    from PIL import Image
    path = _shot('bgm_read.png')
    a = np.array(Image.open(path).convert('RGB')).astype(int)
    y0, y1 = _BGM_READ_ROWS
    band = a[y0:y1]
    R, G, B = band[:, :, 0], band[:, :, 1], band[:, :, 2]
    yellow = (R > 210) & (G > 170) & (B < 110)
    best, best_n = None, -1
    for name, x0, x1 in _BGM_BOXES:
        n = int(yellow[:, x0:x1].sum())
        if n > best_n:
            best, best_n = name, n
    # 没有任何黄色高亮（面板未开 / 选择器不在预期位置）⇒ 返回 None 而非假阳性
    if best_n < 10:
        print('[BGM] 回读：滑轨无黄色高亮（面板未开？best_n=%d）→ None' % best_n, flush=True)
        return None
    print('[BGM] 回读当前档 = %s（黄像素 %d）' % (best, best_n), flush=True)
    return best


def _open_bgm_panel(mode=1):
    """盘内打开 オプション 面板：点工具栏 🔧（下排第2格，(33,167)）。

    打开后用 read_bgm() 校验（黄块出现=成功）；失败重试一次模式自带坐标。
    （另一处入口是 ゲーム選択屏底部「オプション」，见 PITFALLS §S60。）
    """
    for wx, wy in (BGM_WRENCH, MODES[mode]['exit_wrench']):
        KC.tap(wx, wy, after=1.2)
        time.sleep(0.5)
        if read_bgm() is not None:
            return True
    return False


def set_bgm(which, mode=1):
    """盘内切换 BGM 档（1/2/3/4/none）：🔧 → オプション面板选档 → 再開する 回盘内。

    ★ 必须已在填字界面（進盤後调用）。设置持久化到 SRAM，之后主菜单/其他盘共享。
    设置前后各回读一次；返回回读到的档（用于自检）。
    """
    if str(which) not in BGM_XY:
        raise SystemExit('无效 BGM %r（可选 1/2/3/4/none）' % which)
    if not _open_bgm_panel(mode):
        raise SystemExit('⚠️ オプション面板未打开（🔧 点击无效，看 diag/bgm_read.png）')
    before = read_bgm()
    KC.tap(BGM_XY[str(which)], BGM_Y, after=0.5)
    time.sleep(0.4)
    after = read_bgm()
    # 再開する：首击**常**只把焦点移到该按钮、二击才激活（§61.4）；之后有「再開!」大字过场 ~2.5s
    # ★★ 2026-10-18：首击偶尔直接激活（面板当场关闭）——此时**第二击会落到盘内**，
    #    在大盘上表现为后续的填字整体错位（模式1 ふつう/むずかしい 全关蓝 0.0% FAIL）。
    #    故第二击改为条件触发：面板已关就不要再点。
    KC.tap(*BGM_RESUME, after=0.8)
    if read_bgm() is not None:          # 面板仍在 ⇒ 首击只移了焦点，补第二击
        KC.tap(*BGM_RESUME, after=1.2)
    time.sleep(2.2)
    print('[BGM] set %s：%s → %s（已再開）' % (which, before, after), flush=True)
    return after


def _scroll_grid(diff):
    """模式1 No.51+ 选关网格滚到底（§S14/S15）：方向键 ↓，末行幂等，可重复调用。"""
    n = 14 if diff == 'muzukashii' else 8
    for _ in range(n):
        KC.key_press('Down', hold=0.05, after=0.12)


def _cell_xy(mode, diff, level, scrolled):
    """关卡 No.<level> 的选关页坐标；scrolled=True 用滚到底后的坐标（模式1 No.51+）。"""
    i = level - 1
    if not scrolled:
        r, c = divmod(i, GRID_COLS)
        return (GRID_X0 + c * GRID_DX, MODES[mode]['grid_y'] + r * GRID_DY)
    if level <= 60:                       # 51-60：滚动后依难度总行数落在不同行
        return (GRID_X0 + (i % GRID_COLS) * GRID_DX, 159 if diff == 'futsuu' else 139)
    return (GRID_X0 + (level - 61) * GRID_DX, 159)      # 61-65


def enter_board(mode, x, y):
    """点关进盘（一击 → 短检 → 必要时补击 → 轮询），并等「開始!」横幅消失。

    ★ 等横幅是必须的：`in_board`/`in_fill_interface` 在横幅期间就为真，此时点工具栏
      会被横幅**静默吞掉**（模式2 实测：面板没开 → 整盘填错位；§S24/§S50.4）。
    """
    def _landed():
        KC.wait_banner_gone(timeout=8.0)      # 開始! 横幅吞点击
        return True

    KC.tap(x, y, after=0.3)
    chk = _shot('enter_1.png')
    if _is_board(mode, chk):
        return _landed()
    KC.tap(x, y, after=KC.NAV_TAP_AFTER)
    t0 = time.time()
    while time.time() - t0 < max(KC.NAV_ENTER_WAIT, 3.0):
        chk = _shot('enter_2.png')
        if _is_board(mode, chk):
            return _landed()
        time.sleep(0.1)
    return False


# ---------------------------------------------------------------------------
# 填字分派
# ---------------------------------------------------------------------------
def fill_normal(mode, diff, level, rec, evidence):
    """按模式分派填字执行（底层复用已验证实现）。返回 True 若正解。

    ★ 模式1/3 一律按 **rec** 规划（`plan_by_rec` 读 plans.json）——rec 已由 `rec_for(mode,diff,level)`
      解析，避免 `do_fill(level)` 内部 `rec_for_level` 依赖 AI_TAS_DIFFICULTY 而误映射难度
      （曾把模式1 難51 当成 rec50，整盘填错）。
    """
    p = MODES[mode]
    if p['engine'] == 'xbatch':
        import run_mode2_easy1_fast as M2
        ev = evidence or (os.path.join(KC.SHOT_DIR, 'l%02d_fill_complete.png' % level)
                          if level else None)
        ok, _poll = M2.run_fill(rec=rec, evidence=ev)
        return ok
    # design 引擎（模式1/3）：按 rec 规划
    FF.do_fill(None, rec=rec)
    src = os.path.join(KC.SHOT_DIR, 'rec%d_fill_complete.png' % rec)
    if level is not None:
        dst = evidence or os.path.join(KC.SHOT_DIR, 'l%02d_fill_complete.png' % level)
    else:
        dst = evidence or src
    if os.path.exists(src) and os.path.abspath(src) != os.path.abspath(dst):
        shutil.move(src, dst)
    return True


def _judge(mode, x, y, tag):
    """按给定选关格坐标判通关（滚动后不能用 level_xy 的假坐标）。"""
    import numpy as np
    from PIL import Image
    p = _shot('judge_%s.png' % tag)
    a = np.array(Image.open(p).convert('RGB')).astype(int)[192:384]
    c = a[max(0, y - 5):y + 6, max(0, x - 9):x + 10]
    blue = float((np.abs(c - np.array(KC.CLEARED_BLUE)).max(2) <= 12).mean())
    gray = float((np.abs(c - np.array(KC.UNCLEARED_GRAY)).max(2) <= 12).mean())
    ok = blue > gray
    print('  通关判定(%d,%d)：蓝 %.1f%% / 灰 %.1f%%  ->  %s'
          % (x, y, blue * 100, gray * 100, '✅ 已通关' if ok else '❌ 未通关'), flush=True)
    return ok


def finish(mode, diff, level, rec, scrolled):
    """结算 + 通关判定。模式2 走盲点结算（on_level_select 对 7 格恒 False）。"""
    if MODES[mode]['settle'] == 'sleep':
        return G.settle('l%02d' % level)
    KC.settle(level)
    x, y = _cell_xy(mode, diff, level, scrolled)
    return _judge(mode, x, y, 'l%02d' % level)


# ---------------------------------------------------------------------------
# 认定問題
# ---------------------------------------------------------------------------
def run_kentei(mode, level, evdir, warm=False):
    """認定問題（四级）。模式2 委派给已验证的 run_mode2_cert；模式1/3 走通用进盘采集循环。"""
    p = MODES[mode]
    klevel = KC.KENTEI_ALIAS.get(str(level).lower(), str(level))
    if klevel not in p['kentei_btn']:
        raise SystemExit('未知认定级别 %r（可选 %s）' % (level, list(p['kentei_btn'])))
    if mode == 2:
        return _kentei_mode2(klevel, evdir, warm)
    return _kentei_generic(mode, klevel, evdir, warm)


def _kentei_mode2(level, evdir, warm):
    """委派 run_mode2_cert.py（2026-10-16 四级全清实证）：bronze 免梯度，silver+ 需大会话 --warm。"""
    env = dict(os.environ, AI_TAS_CERT_LEVEL=level, AI_TAS_EVDIR=evdir,
               AI_TAS_SHOT_DIR=os.path.join(KC.DIAG_DIR, 'cert2'))
    if warm:
        env['AI_TAS_CERT_NO_NAV'] = '1'
    rc = subprocess.run([sys.executable, os.path.join(HERE, 'run_mode2_cert.py')],
                        env=env).returncode
    print('[认定] 模式2 %s：run_mode2_cert rc=%d' % (level, rc), flush=True)
    return rc == 0


def _kentei_generic(mode, level, evdir, warm):
    """模式1/3 認定：进盘 → 盘面识别 rec → 按 rec 填字 → 存证 → 退出重摇（采全本）。

    坐标来源 §S50.4（模式1）/ §S52.3（模式3）；识别限本模式本级的 rec 段。
    """
    p = MODES[mode]
    os.makedirs(evdir, exist_ok=True)
    want = KC.kentei_recs(level, mode)
    print('[认定] 模式%d %s：题库 %s' % (mode, level, want), flush=True)
    if not warm:
        _cold_start()
        _nav_to_main(mode)
    KC.tap(*p['main_kentei'], after=1.2)
    print('    -> 認定問題 %s' % (p['main_kentei'],), flush=True)
    if not _cert_menu(mode, _shot('kentei_main.png')):
        KC.tap(*p['main_kentei'], after=1.5)
    if not _cert_menu(mode, _shot('kentei_main.png')):
        print('⚠️ 未进入認定级别菜单（看 diag）', flush=True)
        return False
    KC.tap(*p['kentei_btn'][level], after=1.3)          # 选级别
    have = set()
    for roll in range(1, 31):
        if have >= set(want):
            break
        print('--- 第 %d 轮进盘 ---' % roll, flush=True)
        if not _enter_kentei_board(mode, level):
            print('  ⚠️ 未进盘（仍菜单）', flush=True)
            continue
        KC.wait_banner_gone(timeout=7.0)                # 開始! 横幅吞点击（§S50.4）
        if not KC.list_panel_open():
            KC.tap(57, 136, after=0.5)                  # 工具栏 リスト（切列表选择）
            time.sleep(1.0)
        scores = _identify(mode, _shot('kentei_board.png'), want)
        rec = scores[0][1]
        print('  识别 rec%d（差 %d；次名 %s）' % (rec, scores[0][0], scores[1:2]), flush=True)
        if rec in have:
            print('  rec%d 已捕获 → 退出重摇' % rec, flush=True)
        else:
            FF.do_fill(None, rec=rec)
            src = os.path.join(KC.SHOT_DIR, 'rec%d_fill_complete.png' % rec)
            dst = os.path.join(evdir, '%s_clear_r%d.png' % (level, rec))
            if os.path.exists(src):
                shutil.move(src, dst)
                print('  ✅ 证据图 → %s' % dst, flush=True)
            have.add(rec)
        if have < set(want):
            _exit_kentei_board(mode)
            time.sleep(0.8)
    print('=== 模式%d %s 完成：捕获 %s / 目标 %s ==='
          % (mode, level, sorted(have), want), flush=True)
    return have >= set(want)


def _identify(mode, path, recs):
    """按模式识别进盘加载的 rec，返回 [(不匹配数, rec), …]（升序）。

    模式1 用 identify_kentei_board（按盘面**形状**掩码）；模式3 白パズル盘是满矩形、
      形状全同 ⇒ 换用「已给（蓝）格」签名（solve2 的 grid − badge_cells）。
    """
    if mode == 3:
        return _identify_white(path, recs)
    import identify_kentei_board as IK
    IK.RECS = recs
    _m, _geo, scores = IK.identify(path)
    return scores


def _identify_white(path, recs):
    """模式3 白パズル盘识别：以「已给（蓝）格」集合与 solve2 对齐，取不匹配最少者。

    identify_kentei_board 对满矩形白盘恒差 0（所有 rec 的「格/盘外」掩码相同），
    故改用「哪些格是已给（蓝）」做签名：solve2 的 `grid`(盘内) − `badge_cells`(待填) = 已给格。
    """
    import identify_kentei_board as IK
    import solve2
    m, _geo = IK.shot_map(path)
    best = []
    for rec in recs:
        r = solve2.solve(rec)
        if not r:
            continue
        filled = set()
        for v in r['badge_cells'].values():
            filled.update(v)
        given = set(r['grid']) - filled
        mm = sum(1 for (c, rr), cls in m.items()
                 if cls != '.' and (cls == 'b') != ((c, rr) in given))
        best.append((mm, rec))
    best.sort()
    return best


def _enter_kentei_board(mode, level):
    """认定级别菜单进盘（当前高亮单击即进；非高亮首击移高亮、二击才进，§S50.4）。"""
    x, y = MODES[mode]['kentei_btn'][level]
    KC.tap(x, y, after=1.3)
    if not _cert_menu(mode, _shot('kentei_enter_1.png')):
        return True
    KC.tap(x, y, after=1.6)
    return not _cert_menu(mode, _shot('kentei_enter_2.png'))


def _exit_kentei_board(mode):
    """盘内退出（弃答回级别菜单）：オプション → 問題選択×2 → はい×2。"""
    wx, wy = MODES[mode]['exit_wrench']
    KC.tap(wx, wy, after=1.2)
    KC.tap(53, 176, after=0.9)
    KC.tap(53, 176, after=1.1)
    KC.tap(86, 114, after=0.9)
    KC.tap(86, 114, after=1.4)


def _cert_menu(mode, path):
    """認定级别菜单签名（4 条粉色按钮带；模式1/2/3 同构，复用 run_mode2_cert 的判据）。"""
    import run_mode2_cert as C
    return C.cert_menu_visible(path)


def _recover_to_select(mode, diff, level, scrolled):
    """填字未通关后把游戏退回选关页，避免污染后续关卡的导航（§S60.6）。

    0.02 档偶发掉一个输入 → 该关徽章绑不全、settle 等不到选关页；
    若硬往下走，下一关会从「仍在盘内」的状态开始点格 → 连环失败（§S57.7 同源）。
    路径（实机标定）：盘内 🔧(33,167) 开オプション → Left×2 高亮「問題選択」→ A 弹确认
    （默认いいえ）→ Left 到「はい」→ A 退盘；兜底再走一次完整冷启动导航。
    """
    if _on_select(mode, _shot('recover_chk0.png')):
        return True
    # 开面板：先用已标定的 🔧(33,167)，read_bgm() 判据不过再试模式自带坐标
    opened = False
    for wx, wy in (BGM_WRENCH, MODES[mode]['exit_wrench']):
        KC.tap(wx, wy, after=1.2)
        time.sleep(0.5)
        if read_bgm() is not None:
            opened = True
            break
    if opened:
        for _ in range(2):
            KC.key_press('Left', hold=0.08, after=0.4)
        KC.key_press('x', hold=0.1, after=1.0)      # A → 确认弹窗（默认 いいえ）
        KC.key_press('Left', hold=0.08, after=0.4)
        KC.key_press('x', hold=0.1, after=1.5)      # はい → 退盘回选关页
        time.sleep(0.8)
    if _on_select(mode, _shot('recover_chk1.png')):
        print('  ↩ 已退回选关页（盘内退出路径）', flush=True)
        return True
    # ★ 不冷启动：冷启动会杀掉带声模拟器，整段录音从此静音（§S61 实机踩过）
    print('  ⚠️ 盘内退出未奏效（不冷启动，保留音频）；交由上层重试', flush=True)
    return False


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def play_one(mode, diff, level, rec, evidence, warm, no_settle, bgm=None, retry=0):
    """打一关：导航（首关冷启）→ 进盘 → （可选盘内🔧切 BGM）→ 填字 → 结算。

    retry>0 时：该关未通关则先退回选关页，再原地重打（最多 retry 次）。
    """
    p = MODES[mode]
    scrolled = bool(p['scroll'] and level > 50)
    x, y = _cell_xy(mode, diff, level, scrolled)
    print('############ 模式%d/%s No.%02d (rec%d) ############'
          % (mode, diff, level, rec), flush=True)
    attempt = 0
    while True:
        attempt += 1
        if attempt > 1:
            print('  ↻ No.%02d 第 %d 次重打（先退回选关页）' % (level, attempt - 1), flush=True)
            _recover_to_select(mode, diff, level, scrolled)
            time.sleep(0.6)
        if scrolled:
            _scroll_grid(diff)
        ok = False
        if not enter_board(mode, x, y):
            print('  ❌ 未能进入填字界面（截图 %s）' % os.path.join(KC.DIAG_DIR, 'enter_2.png'),
                  flush=True)
        else:
            if bgm is not None:
                # 关卡运行过程中经盘内 🔧 → オプション面板切 BGM（持久化，回盘内继续）
                set_bgm(bgm, mode=mode)
            ok = fill_normal(mode, diff, level, rec, evidence)
            if not no_settle:
                ok = finish(mode, diff, level, rec, scrolled) and ok
        if ok or no_settle or attempt > retry:
            return ok


def run_normal(args):
    mode, diff = args.mode, args.diff
    p = MODES[mode]
    # --rec：直接按记录号（假定已在填字界面，无导航）
    if args.rec is not None:
        _set_shot_dir(args.shot_dir or os.path.join(ROOT, 'validation', 'tmp_run'))
        rec = int(args.rec)
        if args.dry_run:
            _print_plan(mode, None, rec)
            return 0
        ok = fill_normal(mode, diff, None, rec, args.evidence)
        return 0 if ok else 1

    levels = list(range(args.frm, args.to + 1))
    shot_dir = args.shot_dir or os.path.join(ROOT, 'validation', default_folder(mode, diff))
    _set_shot_dir(shot_dir)
    if args.dry_run:
        for L in levels:
            _print_plan(mode, L, KC.rec_for(mode, diff, L))
        return 0

    # 冷启动导航一次到选关页（模式1/3 需先到目标难度；模式2 同）
    goto_select(mode, diff, warm=args.warm)

    results = []
    for L in levels:
        rec = KC.rec_for(mode, diff, L)
        ev = args.evidence if (args.evidence and len(levels) == 1) else None
        # --bgm：首关进盘后经 🔧 切 BGM（设一次即持久化，后续关卡沿用）
        bgm_now = args.bgm if L == levels[0] else None
        ok = play_one(mode, diff, L, rec, ev, warm=(L != levels[0]),
                      no_settle=args.no_settle, bgm=bgm_now, retry=args.retry)
        results.append((L, ok))
    print('================ DONE（模式%d/%s）================' % (mode, diff), flush=True)
    print('PASS: %s' % [L for L, ok in results if ok], flush=True)
    print('FAIL: %s' % [L for L, ok in results if not ok], flush=True)
    return 0 if all(ok for _, ok in results) else 1


def run_kentei_cmd(args):
    _set_shot_dir(args.shot_dir or os.path.join('/tmp', 'kentei'))
    evdir = args.evidence or os.path.join(ROOT, 'validation', MODES[args.mode]['evdir'])
    ok = run_kentei(args.mode, args.kentei, evdir, warm=args.warm)
    return 0 if ok else 1


def _print_plan(mode, level, rec):
    import plan_store as PS
    seq = PS.get(rec)
    if seq is None:
        print('  rec%d：plans.json 无计划' % rec)
        return
    import seq_codec as SC
    st = SC.seq_stats(seq)
    print('  %s rec%d：%d 步（触摸 %d + 箭头 %d + 跳跃 %d + 翻页 %d）'
          % (('No.%02d' % level) if level else '', rec, st['steps'],
             st['n_touch'], st['n_arrow'], st['n_hop'], st['n_page']))


def _setup_globals(args):
    """统一 DISPLAY / DIAG 目录（除非各脚本另有 --shot-dir）。"""
    os.environ.setdefault('DISPLAY', ':0')
    os.environ.setdefault('AI_TAS_DISPLAY', os.environ['DISPLAY'])


def main():
    ap = argparse.ArgumentParser(
        description='统一 TAS runner（模式1/2/3 通常問題 + 認定問題）',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--mode', type=int, choices=(1, 2, 3), default=1, help='游戏模式（默认 1）')
    ap.add_argument('--diff', default='yasashii',
                    help='难度：yasashii/futsuu/muzukashii（或 easy/normal/hard、日文、单字母）')
    ap.add_argument('--level', type=int, help='单关关卡号（1-based）')
    ap.add_argument('--from', dest='frm', type=int, default=1, help='批量起始关')
    ap.add_argument('--to', type=int, help='批量结束关（给出即批量）')
    ap.add_argument('--rec', type=int, help='直接按记录号（绕过难度映射，假定已在填字界面）')
    ap.add_argument('--kentei', help='認定問題级别：bronze/silver/gold/platinum')
    ap.add_argument('--warm', action='store_true', help='热启动（假定已在选关页/认定菜单）')
    ap.add_argument('--dry-run', action='store_true', help='只打印规划，不碰模拟器')
    ap.add_argument('--no-settle', action='store_true', help='填字后不结算')
    ap.add_argument('--evidence', help='证据图输出路径（单关）或目录（认定）')
    ap.add_argument('--shot-dir', dest='shot_dir', help='截图/诊断输出目录（覆盖默认 validation/…）')
    ap.add_argument('--pace', choices=('fast', 'safe', 'realtime'), default=PACE,
                    help='时序预设（默认 fast；录制建议 safe：手势抬到可靠下界）')
    ap.add_argument('--retry', type=int, default=0,
                    help='单关失败时退回选关页并重打的次数（默认 0；录制建议 2）')
    ap.add_argument('--bgm', choices=('1', '2', '3', '4', 'none'),
                    help='首关进盘后经盘内 🔧→オプション 切 BGM（持久化；ゲーム選択屏亦有オプション）')
    args = ap.parse_args()

    args.diff = KC.DIFF_ALIAS.get(str(args.diff).lower(), args.diff)
    if args.mode in (1, 2, 3) and args.diff not in DIFF_KEY:
        raise SystemExit('无效难度 %r（可选 yasashii/futsuu/muzukashii）' % args.diff)

    _setup_globals(args)
    if args.kentei:
        return run_kentei_cmd(args)
    if args.rec is not None:
        return run_normal(args)
    # level ↔ from/to 归一：单关即单次迭代的批量
    if args.level is not None:
        args.frm = args.to = args.level
    elif args.to is None:
        raise SystemExit('请给出 --level N（单关）或 --from/--to（批量），或用 --kentei/--rec')
    if args.to < args.frm:
        raise SystemExit('--to(%d) < --from(%d)' % (args.to, args.frm))
    return run_normal(args)


if __name__ == '__main__':
    sys.exit(main())
