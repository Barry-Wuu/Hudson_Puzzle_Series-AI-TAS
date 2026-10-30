#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分段实况录制器（模式1 易/中/难+认定、模式2 全、模式3 全）。

设计要点（2026-10-17 用户要求）：
  * 每难度/每 BGM 段独立一个视频文件；后一段的**第一帧 = 前一段的最后一帧**：
    冷启动后先导航到「上一段结尾所在画面」，**再**启动 ffmpeg，故开头天然衔接。
  * BGM 分配：模式1 易+中=BGM1；模式1 难+认定=BGM2；模式2=BGM3；模式3=BGM4。
    每段冷启动后会重切一次（BGM 不单独落盘，跨会话会回默认）。
  * 视频用 fragmented MP4（+frag_keyframe+empty_moov）：进程被杀也不会丢 moov。
  * fast 时序（**不可用 safe**：TAP_HOLD=0.04 会让大盘箭头/跳跃错位，实测全败）。

用法：
  python3 record_series.py --list
  python3 record_series.py --seg seg1a
  SEG_TEST=1 python3 record_series.py --seg seg1a     # 只打 1 关（管线自检）
"""
import os
import sys
import time
import signal
import argparse
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

os.environ.setdefault('AI_TAS_DISPLAY', ':0')
os.environ.setdefault('DISPLAY', ':0')
os.environ.setdefault('XDG_RUNTIME_DIR', '/tmp/xdg-pulse')
os.environ.setdefault('SDL_AUDIODRIVER', 'pulse')
os.environ.setdefault('LD_LIBRARY_PATH', '/usr/games:/usr/lib/x86_64-linux-gnu')
# 时序分档（依据 PITFALLS §S57.7 / §S60.5.2 / §S60.5.3）：
#   press 手势长度 = TAP_HOLD + MOVE_GAP，§S57.7 实测**可靠下界 0.06s**。
#   fast 档只有 0.02+0.02=0.04s ⇒ 录制环境（desmume 带声 + 两路 ffmpeg）下
#   **偶发掉一个输入** ⇒ 填字耗时与成功时几乎相同却绑不全（リスト剩十几个字）判 FAIL，
#   且失败后若不退回选关页就往下走会**连环 FAIL**（§S60.5.3）。
#   故按盘面大小而非模式号分档：
#     · 模式1 大盘（ふつう/むずかしい 20x25、200+ 步）→ safe 档（0.04+0.02=0.06s 达下界）
#     · 模式2/3 大盘（25x20、678 步）                → realtime 档（0.06+0.04=0.10s）
#     · 小盘（模式1 やさしい 8x8，实测 35/35 PASS）   → fast 档（0.02+0.02）
_SAFE_SEGS = ('seg1b', 'seg2a')
_SLOW_SEGS = ('seg3b', 'seg3c', 'seg4a', 'seg4b', 'seg4c', 'seg3d', 'seg4d')
if any(k in ' '.join(sys.argv) for k in _SLOW_SEGS):
    _PACE = dict(AI_TAS_TAP_HOLD='0.06', AI_TAS_MOVE_GAP='0.04', AI_TAS_TAP_AFTER='0.12',
                 AI_TAS_ARROW_AFTER='0.05', AI_TAS_KANJI_AFTER='0.05', AI_TAS_FILL_WAIT='0.05',
                 AI_TAS_HOP_AFTER='0.05', AI_TAS_BREATHE_EVERY='10', AI_TAS_PANEL_WAIT='0.85',
                 AI_TAS_SEIKAI_WAIT='1.2', AI_TAS_NAV_AFTER='1.5', AI_TAS_NAV_ENTER_WAIT='5.0')
elif any(k in ' '.join(sys.argv) for k in _SAFE_SEGS):
    _PACE = dict(AI_TAS_TAP_HOLD='0.04', AI_TAS_MOVE_GAP='0.02', AI_TAS_TAP_AFTER='0.02',
                 AI_TAS_ARROW_AFTER='0.04', AI_TAS_KANJI_AFTER='0.03', AI_TAS_FILL_WAIT='0.03',
                 AI_TAS_HOP_AFTER='0.04', AI_TAS_BREATHE_EVERY='0', AI_TAS_PANEL_WAIT='0.7',
                 AI_TAS_SEIKAI_WAIT='0.5', AI_TAS_NAV_AFTER='1.5', AI_TAS_NAV_ENTER_WAIT='5.0')
else:
    _PACE = dict(AI_TAS_TAP_HOLD='0.02', AI_TAS_MOVE_GAP='0.02', AI_TAS_TAP_AFTER='0.02',
                 AI_TAS_ARROW_AFTER='0.02', AI_TAS_KANJI_AFTER='0.02', AI_TAS_FILL_WAIT='0.02',
                 AI_TAS_HOP_AFTER='0.03', AI_TAS_BREATHE_EVERY='0', AI_TAS_PANEL_WAIT='0.6',
                 AI_TAS_SEIKAI_WAIT='0.1', AI_TAS_NAV_AFTER='1.5', AI_TAS_NAV_ENTER_WAIT='5.0')
for _k, _v in _PACE.items():
    os.environ.setdefault(_k, _v)

import kanji_common as KC          # noqa: E402
import fill_fast_any as FF         # noqa: E402
import run as R                    # noqa: E402

OUT = '/workspace/recordings'
WIN = ':0.0+384,192'
BACK = (218, 173)                  # 各层「戻る」按钮（§S61 实测）
LOG = lambda m: print('[%s] %s' % (time.strftime('%H:%M:%S'), m), flush=True)

# tag, mode, kind, start(diff|None), diff, lo, hi, bgm
SEGS = [
    dict(tag='seg1a', mode=1, kind='new',    start=None,           diff='yasashii',   lo=1, hi=35, bgm=None),
    dict(tag='seg1b', mode=1, kind='normal', start='yasashii',     diff='futsuu',     lo=1, hi=60, bgm='1'),
    dict(tag='seg2a', mode=1, kind='normal', start='futsuu',       diff='muzukashii', lo=1, hi=65, bgm='2', end_gamesel=True),
    dict(tag='seg2b', mode=1, kind='cert',   start='gamesel',      diff=None,         lo=0, hi=0,  bgm='2'),
    dict(tag='seg3a', mode=2, kind='normal', start='mode1menu',    diff='yasashii',   lo=1, hi=7,  bgm='3'),
    dict(tag='seg3b', mode=2, kind='normal', start='cold',         diff='futsuu',     lo=1, hi=15, bgm='3'),
    dict(tag='seg3c', mode=2, kind='normal', start='cold',         diff='muzukashii', lo=1, hi=15, bgm='3', end_gamesel=True),
    dict(tag='seg3d', mode=2, kind='cert',   start='gamesel',      diff=None,         lo=0, hi=0,  bgm='3'),
    dict(tag='seg4a', mode=3, kind='normal', start='cold',         diff='yasashii',   lo=1, hi=15, bgm='4'),
    dict(tag='seg4b', mode=3, kind='normal', start='cold',         diff='futsuu',     lo=1, hi=15, bgm='4'),
    dict(tag='seg4c', mode=3, kind='normal', start='cold',         diff='muzukashii', lo=1, hi=25, bgm='4'),
    # seg4d：起点 = seg4c 结尾（模式3 むずかしい 25/25 选关页），录制中再退到模式菜单进認定
    dict(tag='seg4d', mode=3, kind='cert',   start='m3hard',       diff=None,         lo=0, hi=0,  bgm='4'),
]
CERT_LEVELS = ('bronze', 'silver', 'gold', 'platinum')
RETRY = 3


# ---------------------------------------------------------------------------
# 采集（fragmented MP4：被杀也不丢 moov）
# ---------------------------------------------------------------------------
def start_ffmpeg(tag):
    os.makedirs(OUT, exist_ok=True)
    aud = subprocess.Popen(
        ['ffmpeg', '-y', '-f', 'pulse', '-i', 'auto_null.monitor',
         '-c:a', 'pcm_s16le', os.path.join(OUT, '%s_audio.wav' % tag)],
        stdout=open('/tmp/ff_%s_aud.log' % tag, 'w'), stderr=subprocess.STDOUT)
    time.sleep(0.6)
    vid = subprocess.Popen(
        ['ffmpeg', '-y', '-f', 'x11grab', '-video_size', '256x384', '-framerate', '30',
         '-draw_mouse', '0',
         '-i', WIN, '-c:v', 'libopenh264', '-b:v', '2M', '-pix_fmt', 'yuv420p',
         '-movflags', '+frag_keyframe+empty_moov+default_base_moof',
         os.path.join(OUT, '%s_video.mp4' % tag)],
        stdout=open('/tmp/ff_%s_vid.log' % tag, 'w'), stderr=subprocess.STDOUT)
    time.sleep(0.6)
    LOG('录制已启动 %s：aud=%s vid=%s' % (tag, aud.pid, vid.pid))
    return aud, vid


def stop_ffmpeg(p):
    if p is None:
        return
    p.send_signal(signal.SIGINT)
    try:
        p.wait(timeout=25)
    except Exception:
        p.kill()


def mux(tag):
    subprocess.run(
        ['ffmpeg', '-y', '-i', os.path.join(OUT, '%s_video.mp4' % tag),
         '-i', os.path.join(OUT, '%s_audio.wav' % tag),
         # 原生分辨率封装：采集本就 256x384，不再任何放大
         '-c:v', 'libopenh264', '-b:v', '1M', '-pix_fmt', 'yuv420p',
         '-af', 'volume=-5dB', '-c:a', 'aac', '-b:a', '160k',
         '-shortest', os.path.join(OUT, '%s.mp4' % tag)],
        stdout=open('/tmp/ff_%s_mux.log' % tag, 'w'), stderr=subprocess.STDOUT)


# ---------------------------------------------------------------------------
# 导航
# ---------------------------------------------------------------------------
def cold_start_with_sound():
    subprocess.run(['pkill', '-x', 'desmume-cli'], check=False)
    time.sleep(2.0)
    subprocess.Popen(
        ['setsid', '/usr/games/desmume-cli', '--cpu-mode=0', '--nojoy=1',
         '/workspace/Kanji/game.nds'],
        stdout=open('/tmp/desmume_series.log', 'a'), stderr=subprocess.STDOUT,
        start_new_session=True)
    LOG('冷启动（带声）…')
    KC.wait_title()


_BGM_PREWARMED = False


def prewarm_bgm(mode, cur_diff, bgm):
    """★ 2026-10-18 关键修复：在**本段不会去打**的一个盘里先把 BGM 设好。

    PITFALLS §60.4：「录制宜在同一模拟器会话内先设 BGM 再开打」。但实测发现，
    在**目标盘内**调 `set_bgm()`（🔧 → オプション面板 → 再開する 回盘内）会扰动大盘的
    视口/入力状态，使随后 plan 的坐标整体错位——模式1 ふつう/むずかしい 表现为
    填字耗时正常、入力リスト却剩十几个字、徽章蓝 0.0%（§S60.5.2 断为「0.02 档掉输入」
    是误判：换 safe 档、条件二击、退出重进均无效）；同一批关卡不调 set_bgm 时 3/3 PASS。
    小盘（やさしい 8×8 完全可见）不受影响，故 seg1a/旧录制均未暴露。

    解法：污染留在一个不参与本段的盘里（避开本段要打的难度，否则会误伤首关），
    目标盘保持进盘时的干净状态。
    """
    # 避开本段要打的难度：本段打 やさしい 就改用 ふつuu 做宿主，反之亦然
    host = 'futsuu' if (cur_diff == 'yasashii' or cur_diff is None) else 'yasashii'
    try:
        to_gamesel()
        enter_mode(mode)
        enter_normal_menu()
        enter_diff(mode, host)
        x, y = R._cell_xy(mode, host, 1, False)
        if not R.enter_board(mode, x, y):
            LOG('⚠️ BGM 预热：未能进入 模式%d/%s No.01' % (mode, host))
            return False
        R.set_bgm(bgm, mode=mode)
        R._recover_to_select(mode, host, 1, False)
        time.sleep(0.5)
        LOG('BGM 预热完成 = %s（宿主盘：模式%d/%s No.01）' % (bgm, mode, host))
        # ★ 必须把画面退回标题页：后续 main() 的 to_gamesel() 假设从标题开始。
        #   ⚠️ 不能靠重启模拟器复位——BGM 是**会话级**设置，重启即丢（§60.4）。
        if not back_to_title():
            LOG('⚠️ 预热后未能回到标题页，后续导航可能错位')
        return True
    except SystemExit as e:
        LOG('⚠️ BGM 预热失败：%s —— 本段退回「盘内切 BGM」' % e)
        return False


def back_to_title(max_press=10):
    """选关页/菜单 → 逐层按 B（键 z）退回标题页，每步用像素判据检测。

    ⚠️ 用于 BGM 预热之后复位画面。不能用重启模拟器代替——BGM 是会话级设置，重启即丢。
    """
    for i in range(max_press):
        if KC.on_title(R._shot('prewarm_title_%d.png' % i)):
            LOG('✅ 已回到标题页')
            return True
        KC.key_press('z', hold=0.12, after=1.6)
        time.sleep(0.4)
    return KC.on_title(R._shot('prewarm_title_final.png'))


def to_gamesel():
    """标题 → ファイル1 → ゲーム選択（停在主菜单，不选游戏）。"""
    KC.tap(128, 100, after=KC.NAV_TAP_AFTER)
    KC.tap(95, 76, after=KC.NAV_TAP_AFTER)
    time.sleep(3.0)


def enter_mode(mode):
    """ゲーム選択：Down×(mode-1) → A 进模式菜单。

    ⚠️ 该屏触摸分区比视觉按钮偏下（§S60），且菜单高亮**循环**（Up 会绕到末项），
       故不做 Up 夹顶，直接按冷启动默认高亮（漢字ナンクロ）向下定位。
    """
    for _ in range(mode - 1):
        KC.key_press('Down', hold=0.08, after=0.5)
    KC.key_press('x', hold=0.1, after=1.8)
    time.sleep(0.5)


def enter_normal_menu():
    """模式菜单：直接 A（冷启动默认高亮 = 通常問題；不做 Up 夹顶，否则绕到認定）。"""
    KC.key_press('x', hold=0.1, after=1.6)
    time.sleep(0.5)


def enter_diff(mode, diff):
    """难度菜单：触摸点难度按钮（与 goto_select 同路径，已验证）。

    ⚠️ 不用 _on_select 校验：模式2 下它会把「难度菜单」误判成「选关页」（§S61），
       校验反而导致提前返回/死循环。点完即走，真进不去由 enter_board 暴露。
    """
    p = R.MODES[mode]
    btn, clicks = p['diff'][diff]
    time.sleep(0.8)
    for _ in range(clicks):
        KC.tap(*btn, after=1.2)
    time.sleep(1.0)
    return True


def to_select(mode, diff):
    """从ゲーム選択一路到指定难度的选关页。"""
    enter_mode(mode)
    enter_normal_menu()
    enter_diff(mode, diff)
    if not R._on_select(mode, R._shot('nav_%s_%s.png' % (mode, diff))):
        raise SystemExit('❌ 未到 模式%d/%s 选关页' % (mode, diff))
    LOG('✅ 已到 模式%d/%s 选关页' % (mode, diff))


def find_back(path):
    """自动定位「戻る」按钮中心：按钮是亮粉 (255,131,131)，背景棕粉 G>B，可区分。

    位置随页面内容变化（やすしい页 y≈165、ふつう 25x20 大盘 y≈179），不能写死。
    """
    import numpy as np
    from PIL import Image
    a = np.array(Image.open(path).convert('RGB')).astype(int)
    R_, G_, B_ = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    btn = ((R_ > 235) & (G_ > 95) & (G_ < 175) & (B_ > 95) & (B_ < 175)
           & (np.abs(G_ - B_) < 30))
    # 原图 256x384：右下角区域 y 320..384 / x 120..256
    sub = btn[320:384, 120:256]
    ys, xs = np.where(sub)
    if len(ys) < 200:
        return None
    return (int(np.median(xs) + 120), int(np.median(ys) + 320) - 192)


def nav_difficulty(mode, diff):
    """从上一难度选关页切到目标难度。

    ★★ 2026-10-18 修复：旧实现「点戻る → enter_diff」**没有到达校验**，导致后续
    各关填字全部错位（模式1 ふつう/むずかしい 全关蓝 0.0% FAIL，耗时却与成功时相同），
    seg1b/seg2a 是仅有的两段走此路径的段。改为：先逐层退回ゲーム選択，
    再走 `to_select`（内部含 `_on_select` 像素校验）。
    """
    exit_to_gamesel(mode)
    to_select(mode, diff)
    return True


def is_gamesel(path):
    """ゲーム選択 屏判据：底部 3 个按钮行（データ削除/オプション/戻る）密集粉带。"""
    import numpy as np
    from PIL import Image
    a = np.array(Image.open(path).convert('RGB')).astype(int)
    R_, G_, B_ = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    pink = (R_ > 200) & (G_ > 90) & (G_ < 190) & (B_ > 90) & (B_ < 190)
    prof = pink[192:, :].sum(1)
    bands, s = 0, None
    for j, v in enumerate(prof):
        if v > 60 and s is None:
            s = j
        elif v <= 60 and s is not None:
            if j - s >= 8:
                bands += 1
            s = None
    return bands >= 6


def is_mode_menu(path):
    """模式菜单判据：上屏是纯背景 + 标题条，**没有盘面网格**（§S62 实拍标定）。

    选关页/难度菜单上屏都有网格或通关小格（暗像素 0.09~0.18），模式菜单为 0.000。
    """
    import numpy as np
    from PIL import Image
    a = np.array(Image.open(path).convert('RGB')).astype(int)[:192]
    dark = float((a.max(2) < 90).mean())
    blue = float(((a[:, :, 2] > 180) & (a[:, :, 2] - a[:, :, 0] > 60)).mean())
    return dark < 0.02 and blue < 0.02


def cert_tap_entry(mode):
    """在模式菜单点「認定問題」进级别菜单（单击未高亮项只移高亮，故点后校验再补击）。"""
    btn = R.MODES[mode]['main_kentei']
    for i in range(2):
        KC.tap(*btn, after=1.4)
        time.sleep(0.5)
        if R._cert_menu(mode, R._shot('certmenu_tap%d.png' % i)):
            return True
    return False


def cert_nav_from_select(mode):
    """从本模式「むずかしい」选关页：B 逐层退到模式菜单（检测上屏无网格）→ 認定問題。

    ⚠️ B 键有 ~1 帧延迟/偶发吞键，且退过头会到ゲーム選択——故每轮先检测、再按 B，
       等 3s 再判；误退到ゲーム選択则重新进模式（最多 8 轮）。
    """
    for i in range(8):
        p = R._shot('cert_back_%d.png' % i)
        if is_mode_menu(p):
            LOG('✅ 已退到模式%d菜单（B×%d）' % (mode, i))
            return cert_tap_entry(mode)
        if is_gamesel(p):
            LOG('  ↺ 退过头到ゲーム選択 → 重新进模式%d' % mode)
            enter_mode(mode)
            time.sleep(0.8)
            continue
        KC.key_press('z', hold=0.12, after=2.5)
        time.sleep(0.8)
    LOG('⚠️ 未退到模式菜单')
    return False


def exit_to_gamesel(mode):
    """逐层 B 回ゲーム選択（选关页→难度→模式→ゲーム選択），每步检测。

    ⚠️ 不用固定点「戻る」：选关页的戻る y≈151、难度/模式菜单 y≈173，位置不同；
       而 B 键在每一层都能退，且一步一检测不会点过头（点过头会退到标题屏）。
    """
    for i in range(6):
        if is_gamesel(R._shot('gs_chk_%d.png' % i)):
            LOG('✅ 已回到ゲーム選択')
            return True
        KC.key_press('z', hold=0.12, after=1.6)
        time.sleep(0.5)
    ok = is_gamesel(R._shot('gs_chk_final.png'))
    LOG('返回ゲーム選択：%s' % ('OK' if ok else 'FAIL'))
    return ok


# ---------------------------------------------------------------------------
# 内容
# ---------------------------------------------------------------------------
def play_range(mode, diff, lo, hi, bgm=None):
    R._set_shot_dir('/tmp/rec_%s' % diff)
    res = []
    for L in range(lo, hi + 1):
        rec = KC.rec_for(mode, diff, L)
        LOG('===== 模式%d/%s No.%02d (rec%d) =====' % (mode, diff, L, rec))
        try:
            ok = R.play_one(mode, diff, L, rec, None, warm=(L > lo), no_settle=False,
                            bgm=(bgm if L == lo else None), retry=RETRY)
        except SystemExit as e:
            LOG('❌ 异常：%s' % e)
            ok = False
        res.append((L, ok))
        LOG('%s No.%02d -> %s' % (diff, L, 'PASS' if ok else 'FAIL'))
        if not ok:
            # 单关彻底失败也要退回选关页，避免污染后续
            R._recover_to_select(mode, diff, L, bool(R.MODES[mode]['scroll'] and L > 50))
    return res


def cert_all(mode, bgm=None):
    """四级認定：每级进盘 → 识别 → 填字 → 收証（打一题即出証，不必打满题库）。"""
    R._set_shot_dir('/tmp/rec_cert')
    res = []
    for lv in CERT_LEVELS:
        LOG('===== 認定 %s =====' % lv)
        ok = cert_one(mode, lv, bgm)
        res.append((lv, ok))
        LOG('認定 %s -> %s' % (lv, 'PASS' if ok else 'FAIL'))
    return res


def is_certificate(path):
    import numpy as np
    from PIL import Image
    a = np.array(Image.open(path).convert('RGB')).astype(int)[192:384, 30:226]
    return float((a.min(2) > 200).mean()) > 0.45


def exit_board_kb():
    KC.tap(*R.BGM_WRENCH, after=1.2)
    for _ in range(2):
        KC.key_press('Left', hold=0.08, after=0.4)
    KC.key_press('x', hold=0.1, after=1.0)
    KC.key_press('Left', hold=0.08, after=0.4)
    KC.key_press('x', hold=0.1, after=1.5)
    time.sleep(0.8)


def cert_one(mode, level, bgm=None):
    """四级認定单级：模式2 走独立识别/填字管线（リスト有字格/墨迹判别变体）。"""
    if mode == 2:
        return cert_one_mode2(level, bgm)
    return cert_one_design(mode, level, bgm)


def ensure_cert_menu(mode):
    """确保停在認定级别菜单；若上一级通关把游戏送去「おめでとう」/标题页，先点掉再导航回来。"""
    for _ in range(3):
        p = R._shot('ensure_%s.png' % time.strftime('%H%M%S'))
        if R._cert_menu(mode, p):
            return True
        if KC.on_title(p):
            break
        KC.tap(*KC.CLEAR_DISMISS, after=1.2)      # 推进「おめでとう」祝贺页
        time.sleep(0.8)
    p = R._shot('ensure_title.png')
    if R._cert_menu(mode, p):
        return True
    if KC.on_title(p):
        LOG('  ↺ 已回标题页 → 重新载入存档导航到認定菜单')
        to_gamesel()
        enter_mode(mode)
        KC.key_press('Down', hold=0.08, after=0.5)
        KC.key_press('x', hold=0.1, after=1.6)
        time.sleep(0.6)
        if R._cert_menu(mode, R._shot('ensure_menu_post.png')):
            return True
    return cert_tap_entry(mode)


def cert_one_mode2(level, bgm=None):
    """模式2 認定单级（rec252-259，同级两变体随机）。

    识别：リスト面板有字格数（两变体必不同）；bronze 同数 → 与 rec252 实拍做墨迹 XOR。
    填字：v7 管线（run_mode2_cert.fill_rec，含面板页重建/补填）。
    証：首次通关才出现，轮询 12s + 白卡占比 0.45。
    ⚠️ 该级若是本模式最后一证（プラチナ），正解后会先播「全問正解」成绩滚动 ~25s 再出証，
       故轮询窗口放到 60s；証后还有「おめでとう」→ 淡出 → **回标题页**。
    """
    import shutil
    import run_mode2_cert as C
    import run_mode2_easy1_fast as V7
    evdir = os.path.join(ROOT, 'validation', R.MODES[2]['evdir'])
    os.makedirs(evdir, exist_ok=True)
    C.SHOT = KC.SHOT_DIR
    os.makedirs(C.SHOT, exist_ok=True)
    for attempt in range(1, 4):
        ensure_cert_menu(2)
        if not R._enter_kentei_board(2, level):
            LOG('  ⚠️ 未进盘 try%d' % attempt)
            continue
        KC.wait_banner_gone(timeout=8.0)
        time.sleep(0.8)
        if bgm is not None:
            R.set_bgm(bgm, mode=2)
            bgm = None
        if not KC.list_panel_open():
            KC.tap(*V7.ICON_LIST, after=0.5)
            time.sleep(1.2)
        board = R._shot('cert2_%s_board.png' % level)
        try:
            rec, why = C.identify(board, level)
        except Exception as e:
            LOG('  ⚠️ 识别异常：%s → 退盘重试' % e)
            R._exit_kentei_board(2)
            continue
        LOG('  识别 %s' % why)
        # 面板读数与两变体都对不上 ⇒ 面板没开好/盘面异常，别硬填
        n = V7.count_inked_cells(board)
        lo, hi = C.CERT_VARIANTS[level]
        nl = len(C.beam_load(lo)[3])
        nh = len(C.beam_load(hi)[3])
        if nl != nh and min(abs(n - nl), abs(n - nh)) > 4:
            LOG('  ⚠️ リスト有字格 %d 与两变体(%d/%d) 均不符 → 退盘重试' % (n, nl, nh))
            R._exit_kentei_board(2)
            continue
        poll = C.fill_rec(rec)
        if poll is None:
            LOG('  ⚠️ 填字未正解 → 退盘重试')
            R._exit_kentei_board(2)
            continue
        from PIL import Image
        Image.open(poll).convert('RGB').quantize(
            colors=256, dither=Image.NONE).save(
                os.path.join(evdir, '%s_clear_r%d.png' % (level, rec)))
        got = False
        for i in range(120):                      # 最长 60s（末级成绩滚动 ~25s）
            time.sleep(0.5)
            p = R._shot('cert2_%s_poll_%02d.png' % (level, i))
            if C.cert_like(p):
                shutil.copy(p, os.path.join(evdir, '%s_certificate.png' % level))
                LOG('  🏅 %s 認定証到手' % level)
                got = True
                time.sleep(1.0)
                KC.tap(128, 150, after=1.5)
                break
            if R._cert_menu(2, p):
                LOG('  ℹ️ 未见認定証（已认定/非首次）')
                return True
        for i in range(12):                       # 証后的「おめでとう」/淡出/回标题
            p = R._shot('cert2_%s_after_%02d.png' % (level, i))
            if R._cert_menu(2, p):
                return True
            if KC.on_title(p):
                LOG('  🏁 全模式通关演出结束，已回标题页')
                return True
            if i % 2 == 1:
                KC.tap(*KC.CLEAR_DISMISS, after=1.2)   # 「おめでとう」页需要再点一次
            time.sleep(0.8)
        if not got:
            LOG('  ℹ️ 未见認定証（可能已认定/非首次）')
        if R._cert_menu(2, R._shot('cert2_%s_menu.png' % level)):
            return True
        if C.back_to_cert_menu():
            LOG('  ↩︎ 已回認定级别菜单')
            return True
        LOG('  ⚠️ 未能回認定级别菜单 try%d' % attempt)
    return False


def cert_one_design(mode, level, bgm=None):
    evdir = os.path.join(ROOT, 'validation', R.MODES[mode]['evdir'])
    os.makedirs(evdir, exist_ok=True)
    want = KC.kentei_recs(level, mode)
    for attempt in range(1, 4):
        ensure_cert_menu(mode)
        if not R._enter_kentei_board(mode, level):
            LOG('  ⚠️ 未进盘 try%d' % attempt)
            continue
        KC.wait_banner_gone(timeout=8.0)
        time.sleep(0.8)
        if bgm is not None:
            R.set_bgm(bgm, mode=mode)
            bgm = None
        if not KC.list_panel_open():
            KC.tap(57, 136, after=0.5)
            time.sleep(1.0)
        try:
            scores = R._identify(mode, R._shot('cert_%s_board.png' % level), want)
        except Exception as e:                     # IK.identify 对异常盘面会 IndexError
            LOG('  ⚠️ 识别异常：%s → 退盘重试' % e)
            R._exit_kentei_board(mode)
            continue
        if not scores:
            LOG('  ⚠️ 识别失败 → 退盘重试')
            R._exit_kentei_board(mode)
            continue
        rec = scores[0][1]
        LOG('  识别 rec%d（差 %d）' % (rec, scores[0][0]))
        FF.do_fill(None, rec=rec)
        src = os.path.join(KC.SHOT_DIR, 'rec%d_fill_complete.png' % rec)
        if os.path.exists(src):
            import shutil
            shutil.move(src, os.path.join(evdir, '%s_clear_r%d.png' % (level, rec)))
        got = False
        # 前 6s 盲点推进「正解→★獲得数→認定証」；之后只轮询（末级可能有成绩滚动，
        #   乱点会把証点掉）。最长 60s。
        for i in range(120):
            p = R._shot('cert_%s_settle_%02d.png' % (level, i))
            if not got and is_certificate(p):
                import shutil
                shutil.copy(p, os.path.join(evdir, '%s_certificate.png' % level))
                LOG('  🏅 %s 認定証到手' % level)
                got = True
                time.sleep(1.0)
                KC.tap(*KC.CLEAR_DISMISS, after=1.5)
                break
            if R._cert_menu(mode, p):
                return True
            if KC.on_title(p):
                LOG('  🏁 全模式通关演出结束，已回标题页')
                return got
            if i < 12 or KC.is_popup(p):
                KC.tap(*KC.CLEAR_DISMISS, after=0.4)
            time.sleep(0.5)
        for i in range(12):                        # 証后的「おめでとう」/淡出/回标题
            p = R._shot('cert_%s_after_%02d.png' % (level, i))
            if R._cert_menu(mode, p):
                return True
            if KC.on_title(p):
                LOG('  🏁 全模式通关演出结束，已回标题页')
                return got
            if i % 2 == 1:
                KC.tap(*KC.CLEAR_DISMISS, after=1.2)
            time.sleep(0.8)
        LOG('  ⚠️ 未回認定级别菜单 try%d' % attempt)
    return False


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seg', help='段标签（见 --list）')
    ap.add_argument('--list', action='store_true')
    args = ap.parse_args()
    if args.list:
        for s in SEGS:
            print('%-6s 模式%d %-10s %s%s BGM=%s'
                  % (s['tag'], s['mode'], s['kind'],
                     (s['diff'] or ''), (' No.%d-%d' % (s['lo'], s['hi'])) if s['kind'] == 'normal' else '',
                     s['bgm']))
        return 0
    seg = next((x for x in SEGS if x['tag'] == args.seg), None)
    if not seg:
        raise SystemExit('未知段 %r' % args.seg)
    test = os.environ.get('SEG_TEST') == '1'
    tag, mode, kind = seg['tag'], seg['mode'], seg['kind']

    R._set_shot_dir('/tmp/rec_%s/nav' % tag)
    cold_start_with_sound()

    # ★ BGM 预热：先在一个「本段不打的盘」里把 BGM 设好（详见 prewarm_bgm 文档），
    #   之后 play_range 就不必在目标盘内调 set_bgm —— 否则大盘填字会整体错位。
    global _BGM_PREWARMED
    _BGM_PREWARMED = False
    # 注：BGM 预热方案 prewarm_bgm 曾为绕开一个误判而写（真因实为 nav_difficulty
    #     缺到达校验），已不再需要。正常走 play_range/cert_one 里的盘内 set_bgm。

    # ---- 录制前把画面导航到「上一段结尾」的画面 ----
    if kind == 'new':
        pass                                   # 新档：从标题开始录（含开场）
    elif seg['start'] == 'gamesel':
        to_gamesel()
    elif seg['start'] == 'cold':
        to_gamesel()
        to_select(mode, seg['diff'])       # 直接导航到本段难度（每段独立，progress 连续）
    elif seg['start'] == 'mode1menu':
        to_gamesel()
        enter_mode(1)                      # 模式1 的模式菜单（= 上一段结尾画面）
    elif seg['start'] == 'm3hard':
        to_gamesel()
        to_select(3, 'muzukashii')         # 模式3 むずかしい选关页（= seg4c 结尾画面）
    elif seg['start']:
        to_gamesel()
        to_select(mode, seg['start'])

    aud, vid = start_ffmpeg(tag)
    t0 = time.time()
    res = []
    try:
        if kind == 'new':
            # 标题 → 文件1（空档）→ ゲーム選択 → 模式菜单 → 通常問題 → やさしい
            # ⚠️ 空档首次进难度菜单，单击可能只移高亮不进入（2026-10-17 实测），
            #    故点后校验，未到选关页则补击同钮（同 cert_tap_entry 模式）。
            KC.tap(128, 100, after=1.5)
            KC.tap(95, 76, after=2.5)
            enter_mode(mode)
            enter_normal_menu()
            _btn = R.MODES[mode]['diff'][seg['diff']][0]
            enter_diff(mode, seg['diff'])
            _ok = R._on_select(mode, R._shot('new_select.png'))
            for _try in range(3):
                if _ok:
                    break
                LOG('  ↺ 未到选关页 try%d → 补击难度按钮 %s' % (_try + 1, _btn))
                KC.tap(*_btn, after=1.2)
                time.sleep(0.8)
                _ok = R._on_select(mode, R._shot('new_select.png'))
            if not _ok:
                raise SystemExit('❌ 新档未到选关页')
            res += play_range(mode, seg['diff'], seg['lo'], 1 if test else seg['hi'],
                              bgm=seg['bgm'])
        elif kind == 'normal':
            if seg['start'] == 'cold':
                pass                        # 已在目标难度选关页（录制前已导航）
            elif seg['start'] in ('gamesel', 'mode1menu'):
                if seg['start'] == 'mode1menu':
                    exit_to_gamesel(1)     # 模式1 模式菜单 → ゲーム選択（衔接上一段结尾）
                enter_mode(mode)
                enter_normal_menu()
                enter_diff(mode, seg['diff'])
                if not R._on_select(mode, R._shot('jump_select.png')):
                    raise SystemExit('❌ 未到 %s 选关页' % seg['diff'])
            else:
                order = ('yasashii', 'futsuu', 'muzukashii')
                k = order.index(seg['diff'])
                if not nav_difficulty(mode, seg['diff']):
                    raise SystemExit('❌ 未能切到 %s' % seg['diff'])
            res += play_range(mode, seg['diff'], seg['lo'], 1 if test else seg['hi'],
                              bgm=seg['bgm'])
            if seg.get('end_gamesel'):
                exit_to_gamesel(mode)
        elif kind == 'cert':
            # 起点两种：
            #   gamesel  → A（模式菜单，默认通常問題）→ Down×1 = 認定問題 → A
            #   m3hard   → 已在むずかしい选关页：B 退到模式菜单 → 点認定問題（seg4d 衔接 seg4c）
            if seg['start'] == 'm3hard':
                if not cert_nav_from_select(mode):
                    raise SystemExit('❌ 未能从选关页进入認定级别菜单')
            else:
                enter_mode(mode)
                KC.key_press('Down', hold=0.08, after=0.5)
                KC.key_press('x', hold=0.1, after=1.6)
                time.sleep(0.6)
                if not R._cert_menu(mode, R._shot('certmenu_new.png')):
                    if not cert_tap_entry(mode):     # 兜底：直接点「認定問題」
                        raise SystemExit('❌ 未到認定级别菜单')
            res += [(lv, cert_one(mode, lv, seg['bgm'] if i == 0 else None))
                    for i, lv in enumerate(CERT_LEVELS[:1] if test else CERT_LEVELS)]
            # 末级（プラチナ）通关会播全模式通关演出并回标题页，此时不再退到ゲーム選択
            if not KC.on_title(R._shot('cert_end.png')):
                exit_to_gamesel(mode)
            else:
                time.sleep(3.0)      # 末帧别停在「セーブ中です」，让标题页露出来
    finally:
        stop_ffmpeg(vid)
        stop_ffmpeg(aud)
        LOG('停止采集，合成中…')
        mux(tag)

    npass = sum(1 for _, ok in res if ok)
    LOG('=== %s 完成：%.1f 分钟，PASS %d/%d ===' % (tag, (time.time() - t0) / 60, npass, len(res)))
    LOG('FAIL: %s' % [x for x, ok in res if not ok])
    return 0 if npass == len(res) else 1


if __name__ == '__main__':
    sys.exit(main())
