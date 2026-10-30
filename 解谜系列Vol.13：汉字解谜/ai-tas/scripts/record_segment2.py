#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第二段实况录制：切 BGM2 → 模式1 むずかしい全 65 关 → 四级認定問題（ブロンズ→プラチナ）。

前置：第一段（record_segment1.py）已把 やさしい 35 + ふつう 60 全清（存档里），本段沿用同一存档。
管线同第一段：pulse 虚拟声卡（音频 wav）+ x11grab（视频 mp4）分进程采集，结束后合成
（3x 放大 + aac）。

用法：
  AI_TAS_DISPLAY=:0 python3 record_segment2.py                 # 全段（むずかしい + 认定）
  AI_TAS_DISPLAY=:0 python3 record_segment2.py --only cert --tag seg2b   # 只录认定（独立一段）
  SEG2_TEST=1 python3 record_segment2.py --only cert           # 认定只打 1 级（干跑）
"""
import os
import sys
import time
import shutil
import signal
import subprocess
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

os.environ.setdefault('AI_TAS_DISPLAY', ':0')
os.environ.setdefault('DISPLAY', ':0')
os.environ.setdefault('XDG_RUNTIME_DIR', '/tmp/xdg-pulse')
os.environ.setdefault('SDL_AUDIODRIVER', 'pulse')
os.environ.setdefault('LD_LIBRARY_PATH', '/usr/games:/usr/lib/x86_64-linux-gnu')
# safe 录制档（与 record_segment1 同）：press 手势 0.04+0.02 = §S23 可靠下界 0.06
_PACE = dict(AI_TAS_TAP_HOLD='0.04', AI_TAS_MOVE_GAP='0.02', AI_TAS_TAP_AFTER='0.02',
             AI_TAS_ARROW_AFTER='0.04', AI_TAS_KANJI_AFTER='0.03', AI_TAS_FILL_WAIT='0.03',
             AI_TAS_HOP_AFTER='0.04', AI_TAS_BREATHE_EVERY='0', AI_TAS_PANEL_WAIT='0.7',
             AI_TAS_SEIKAI_WAIT='0.5', AI_TAS_NAV_AFTER='1.5', AI_TAS_NAV_ENTER_WAIT='5.0')
for _k, _v in _PACE.items():
    os.environ.setdefault(_k, _v)

import kanji_common as KC          # noqa: E402
import fill_fast_any as FF         # noqa: E402
import run as R                    # noqa: E402

OUT = '/workspace/recordings'
WIN = ':0.0+384,192'
RETRY = 2
BGM = '2'                          # 第二段：切 BGM2
LEVELS = ('bronze', 'silver', 'gold', 'platinum')
LOG = lambda m: print('[%s] %s' % (time.strftime('%H:%M:%S'), m), flush=True)


# ---------------------------------------------------------------------------
# 采集
# ---------------------------------------------------------------------------
def start_ffmpeg(tag):
    os.makedirs(OUT, exist_ok=True)
    aud = subprocess.Popen(
        ['ffmpeg', '-y', '-f', 'pulse', '-i', 'auto_null.monitor',
         '-c:a', 'pcm_s16le', os.path.join(OUT, '%s_audio.wav' % tag)],
        stdout=open('/tmp/ff2_aud.log', 'w'), stderr=subprocess.STDOUT)
    time.sleep(0.6)
    vid = subprocess.Popen(
        ['ffmpeg', '-y', '-f', 'x11grab', '-video_size', '256x384', '-framerate', '30',
         '-i', WIN, '-c:v', 'libopenh264', '-b:v', '2M', '-pix_fmt', 'yuv420p',
         os.path.join(OUT, '%s_video.mp4' % tag)],
        stdout=open('/tmp/ff2_vid.log', 'w'), stderr=subprocess.STDOUT)
    time.sleep(0.6)
    LOG('录制已启动：aud=%s vid=%s' % (aud.pid, vid.pid))
    return aud, vid


def stop_ffmpeg(p):
    p.send_signal(signal.SIGINT)
    try:
        p.wait(timeout=20)
    except Exception:
        p.kill()


def mux(tag):
    """分进程采集的视频 + 音频 → 3x 放大 + aac 的成品。"""
    subprocess.run(
        ['ffmpeg', '-y', '-i', os.path.join(OUT, '%s_video.mp4' % tag),
         '-i', os.path.join(OUT, '%s_audio.wav' % tag),
         '-vf', 'scale=768:1152:flags=lanczos',
         '-c:v', 'libopenh264', '-b:v', '3M', '-pix_fmt', 'yuv420p',
         '-af', 'volume=-5dB', '-c:a', 'aac', '-b:a', '160k',
         '-shortest', os.path.join(OUT, '%s.mp4' % tag)],
        stdout=open('/tmp/ff2_mux.log', 'w'), stderr=subprocess.STDOUT)


def cold_start_with_sound():
    subprocess.run(['pkill', '-x', 'desmume-cli'], check=False)
    time.sleep(2)
    subprocess.Popen(
        ['setsid', '/usr/games/desmume-cli', '--cpu-mode=0', '--nojoy=1',
         '/workspace/Kanji/game.nds'],
        stdout=open('/tmp/desmume_rec2.log', 'a'), stderr=subprocess.STDOUT,
        start_new_session=True)
    LOG('冷启动（带声）…')
    KC.wait_title()
    LOG('标题页就绪')


# ---------------------------------------------------------------------------
# 导航
# ---------------------------------------------------------------------------
def enter_difficulty(diff, down_times):
    """从「難易度」菜单（高亮 やさしい）用 Up×3 夹顶 + Down×k 定位进入选关页。"""
    for i in range(3):
        for _ in range(3):
            KC.key_press('Up', hold=0.08, after=0.4)
        for _ in range(down_times):
            KC.key_press('Down', hold=0.08, after=0.5)
        KC.key_press('x', hold=0.1, after=2.0)
        if R._on_select(1, R._shot('seg2_nav_%s_%d.png' % (diff, i))):
            LOG('✅ 已到 %s 选关页' % diff)
            return True
        LOG('⚠️ 未到 %s 选关页（try%d）' % (diff, i))
    return False


def goto_cert_menu(from_select=False):
    """回到「漢字ナンクロ」模式菜单并进入「認定問題」级别菜单（_cert_menu 校验）。

    从模式菜单起：Up×3 夹到「通常問題」→ Down×1 = 「認定問題」→ A。
    变体法：B×k 先退层（k=0/1/2/3/4，过冲会被下一轮拉回），每轮都校验。
    """
    if R._cert_menu(1, R._shot('certmenu_pre.png')):
        return True
    variants = (2, 3, 4, 5) if from_select else (0, 1, 2, 3)
    for k in variants:
        for _ in range(k):
            KC.key_press('z', hold=0.1, after=1.0)
        for _ in range(3):
            KC.key_press('Up', hold=0.08, after=0.4)
        KC.key_press('Down', hold=0.08, after=0.5)
        KC.key_press('x', hold=0.1, after=1.5)
        time.sleep(0.6)
        if R._cert_menu(1, R._shot('certmenu_b%d.png' % k)):
            LOG('✅ 已到認定级别菜单（B×%d）' % k)
            return True
        LOG('⚠️ 未到認定级别菜单（B×%d）' % k)
    return False


def exit_board_kb():
    """盘内键盘退出：🔧 开面板 → Left×2 高亮「問題選択」→ A 弹确认 → Left → A。"""
    KC.tap(*R.BGM_WRENCH, after=1.2)
    for _ in range(2):
        KC.key_press('Left', hold=0.08, after=0.4)
    KC.key_press('x', hold=0.1, after=1.0)
    KC.key_press('Left', hold=0.08, after=0.4)
    KC.key_press('x', hold=0.1, after=1.5)
    time.sleep(0.8)


# ---------------------------------------------------------------------------
# 通常問題
# ---------------------------------------------------------------------------
def play_range(diff, lo, hi, bgm=None):
    R._set_shot_dir('/tmp/rec_seg2/%s' % diff)
    res = []
    for L in range(lo, hi + 1):
        rec = KC.rec_for(1, diff, L)
        LOG('===== %s No.%02d (rec%d) =====' % (diff, L, rec))
        try:
            ok = R.play_one(1, diff, L, rec, None, warm=(L > lo), no_settle=False,
                            bgm=(bgm if L == lo else None), retry=RETRY)
        except SystemExit as e:
            LOG('❌ play_one 异常：%s' % e)
            ok = False
        res.append((L, ok))
        LOG('%s No.%02d -> %s' % (diff, L, 'PASS' if ok else 'FAIL'))
    return res


# ---------------------------------------------------------------------------
# 認定問題（每级：进盘 → 识别 rec → 填字 → 等認定証 → 回级别菜单）
# ---------------------------------------------------------------------------
def is_certificate(path):
    """認定証签名（§S58.6）：下屏中央近白占比 > 0.45。"""
    import numpy as np
    from PIL import Image
    a = np.array(Image.open(path).convert('RGB')).astype(int)[192:384, 30:226]
    return float((a.min(2) > 200).mean()) > 0.45


def cert_dry_run(levels):
    """非破坏性验证：进每个认定盘 → 识别真实 rec → 退盘（**不填字**，不消耗首通証）。

    认定証只首次通关才发，正式录前必须先确认「进盘坐标 + 识别器 + 退盘」三段都通。
    """
    ok_all = True
    for lv in levels:
        want = KC.kentei_recs(lv, 1)
        if not R._enter_kentei_board(1, lv):
            LOG('  ❌ [dry] %s 未进盘（kentei_btn 坐标失效？）' % lv)
            ok_all = False
            continue
        KC.wait_banner_gone(timeout=8.0)
        time.sleep(0.8)
        if not KC.list_panel_open():
            KC.tap(57, 136, after=0.5)
            time.sleep(1.0)
        scores = R._identify(1, R._shot('dry_cert_%s.png' % lv), want)
        if not scores:
            LOG('  ⚠️ [dry] %s 识别失败（题库 %s）' % (lv, want))
            ok_all = False
        else:
            hit = scores[0][1] in want
            LOG('  ✅ [dry] %s 识别 rec%d（差 %d）%s'
                % (lv, scores[0][1], scores[0][0], '命中题库' if hit else '⚠️ 不在题库内'))
            ok_all = ok_all and hit
        exit_board_kb()
        if not R._cert_menu(1, R._shot('dry_certback_%s.png' % lv)):
            LOG('  ⚠️ [dry] %s 退盘后未回级别菜单' % lv)
            ok_all = False
    LOG('[dry] 认定链路自检：%s' % ('PASS' if ok_all else 'FAIL'))
    return ok_all


def kentei_one(level, evdir):
    """打一个认定级别：进盘→识别→填字→收証。返回 True 若出証/已回级别菜单。"""
    want = KC.kentei_recs(level, 1)
    LOG('--- 認定 %s（题库 %s）---' % (level, want))
    for attempt in range(1, 4):
        if not R._enter_kentei_board(1, level):
            LOG('  ⚠️ 未进盘（仍在级别菜单）try%d' % attempt)
            continue
        KC.wait_banner_gone(timeout=8.0)
        time.sleep(0.8)
        if not KC.list_panel_open():
            KC.tap(57, 136, after=0.5)                 # 工具栏 リスト（切列表选择）
            time.sleep(1.0)
        scores = R._identify(1, R._shot('cert_%s_board.png' % level), want)
        if not scores:
            LOG('  ⚠️ 识别失败 → 退盘重试')
            exit_board_kb()
            continue
        rec = scores[0][1]
        LOG('  识别 rec%d（差 %d）' % (rec, scores[0][0]))
        FF.do_fill(None, rec=rec)
        src = os.path.join(KC.SHOT_DIR, 'rec%d_fill_complete.png' % rec)
        if os.path.exists(src):
            shutil.move(src, os.path.join(evdir, '%s_clear_r%d.png' % (level, rec)))
        got = False
        for i in range(40):
            p = R._shot('cert_%s_settle_%02d.png' % (level, i))
            if not got and is_certificate(p):
                shutil.copy(p, os.path.join(evdir, '%s_certificate.png' % level))
                LOG('  🏅 %s 認定証到手' % level)
                got = True
            if R._cert_menu(1, p):
                if not got:
                    LOG('  （未截到認定証帧，但已回级别菜单）')
                return True
            KC.tap(*KC.CLEAR_DISMISS, after=0.4)
            time.sleep(0.4)
        LOG('  ⚠️ %s 未回到级别菜单' % level)
    return False


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', choices=('all', 'muzukashii', 'cert'), default='all')
    ap.add_argument('--dry', action='store_true',
                    help='认定链路自检：进盘→识别→退盘，不填字（不消耗首通証，不出录像）')
    ap.add_argument('--tag', default='seg2')
    args = ap.parse_args()
    test = os.environ.get('SEG2_TEST') == '1'

    if args.dry:
        R._set_shot_dir('/tmp/rec_seg2/dry')
        cold_start_with_sound()
        KC.tap(128, 100, after=1.5)
        KC.tap(95, 76, after=3.0)
        KC.key_press('x', hold=0.1, after=1.8)
        if not goto_cert_menu(from_select=False):
            LOG('❌ 未到認定级别菜单，dry 中止')
            return 1
        return 0 if cert_dry_run(LEVELS) else 1

    R._set_shot_dir('/tmp/rec_seg2/nav')
    cold_start_with_sound()
    aud, vid = start_ffmpeg(args.tag)
    t0 = time.time()
    allres = []
    try:
        # ---- 导航：标题 → ファイル1（读档）→ ゲーム選択 → 漢字ナンクロ（模式菜单）----
        KC.tap(128, 100, after=1.5)              # 标题 → ファイル選択
        KC.tap(95, 76, after=3.0)                # ファイル1（有档 → 読み込み中 ~3s）
        KC.key_press('x', hold=0.1, after=1.8)   # A：漢字ナンクロ → 模式菜单

        if args.only in ('all', 'muzukashii'):
            KC.key_press('x', hold=0.1, after=1.8)          # A：通常問題 → 難易度菜单
            if not enter_difficulty('muzukashii', 2):
                LOG('❌ 未到 むずかしい 选关页，中止（不冷启动以免断音）')
                return 1
            allres += play_range('muzukashii', 1, 65, bgm=BGM)

        if args.only in ('all', 'cert'):
            if not goto_cert_menu(from_select=(args.only == 'all')):
                LOG('❌ 未到認定级别菜单，中止')
                return 1
            evdir = os.path.join(ROOT, 'validation', 'mode1_4_certification')
            os.makedirs(evdir, exist_ok=True)
            levels = LEVELS[:1] if test else LEVELS
            for lv in levels:
                allres.append((lv, kentei_one(lv, evdir)))
    finally:
        stop_ffmpeg(vid)
        stop_ffmpeg(aud)
        LOG('录制停止，合成中…')
        mux(args.tag)

    npass = sum(1 for _, ok in allres if ok)
    LOG('=== 第二段完成：用时 %.1f 分钟，PASS %d / %d ==='
        % ((time.time() - t0) / 60, npass, len(allres)))
    LOG('FAIL: %s' % [x for x, ok in allres if not ok])
    return 0


if __name__ == '__main__':
    sys.exit(main())
