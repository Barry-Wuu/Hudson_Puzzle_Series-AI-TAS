#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第一段实况录制：新存档 + BGM1（新档默认）→ 模式1 やさしい全35关 + ふつう全60关。

管线：pulse 虚拟声卡（音频 wav）+ x11grab（视频 mp4）分进程实时采集，结束后合成
（3x 放大 + aac）。冷启动→标题画面即开场画面，录制从标题开始。
用法：AI_TAS_DISPLAY=:0 python3 record_segment1.py
测试：SEG1_TEST=1 只打 やさしい 第1关（验证集成，测试后需删 .dsv 还原新档）。
"""
import os, sys, time, signal, subprocess, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

os.environ.setdefault('AI_TAS_DISPLAY', ':0')
os.environ.setdefault('DISPLAY', ':0')
os.environ.setdefault('XDG_RUNTIME_DIR', '/tmp/xdg-pulse')
os.environ.setdefault('SDL_AUDIODRIVER', 'pulse')
os.environ.setdefault('LD_LIBRARY_PATH', '/usr/games:/usr/lib/x86_64-linux-gnu')
# safe 录制档（run.py --pace safe）：press 手势 0.04+0.02 = §S23 实测可靠下界 0.06。
# fast 档是 0.02+0.02 = 0.04，PITFALLS §S57.7 明载「偶发掉一个输入」——录 95 关必翻车。
_PACE = dict(AI_TAS_TAP_HOLD='0.04', AI_TAS_MOVE_GAP='0.02', AI_TAS_TAP_AFTER='0.02',
             AI_TAS_ARROW_AFTER='0.04', AI_TAS_KANJI_AFTER='0.03', AI_TAS_FILL_WAIT='0.03',
             AI_TAS_HOP_AFTER='0.04', AI_TAS_BREATHE_EVERY='0', AI_TAS_PANEL_WAIT='0.7',
             AI_TAS_SEIKAI_WAIT='0.5', AI_TAS_NAV_AFTER='1.5', AI_TAS_NAV_ENTER_WAIT='5.0')
RETRY = 2                       # 单关失败 → 退回选关页 → 原地重打（最多 2 次）
for _k, _v in _PACE.items():
    os.environ.setdefault(_k, _v)

import kanji_common as KC          # noqa: E402
import run as R                    # noqa: E402

OUT = '/workspace/recordings'
WIN = ':0.0+384,192'
LOG = lambda m: print('[%s] %s' % (time.strftime('%H:%M:%S'), m), flush=True)


def start_ffmpeg(tag='seg1'):
    os.makedirs(OUT, exist_ok=True)
    aud = subprocess.Popen(
        ['ffmpeg', '-y', '-f', 'pulse', '-i', 'auto_null.monitor',
         '-c:a', 'pcm_s16le', os.path.join(OUT, '%s_audio.wav' % tag)],
        stdout=open('/tmp/ff_aud.log', 'w'), stderr=subprocess.STDOUT)
    time.sleep(0.6)
    vid = subprocess.Popen(
        ['ffmpeg', '-y', '-f', 'x11grab', '-video_size', '256x384', '-framerate', '30',
         '-i', WIN, '-c:v', 'libopenh264', '-b:v', '2M', '-pix_fmt', 'yuv420p',
         os.path.join(OUT, '%s_video.mp4' % tag)],
        stdout=open('/tmp/ff_vid.log', 'w'), stderr=subprocess.STDOUT)
    time.sleep(0.6)
    LOG('录制已启动：aud=%s vid=%s' % (aud.pid, vid.pid))
    return aud, vid


def stop_ffmpeg(p):
    p.send_signal(signal.SIGINT)
    try:
        p.wait(timeout=20)
    except Exception:
        p.kill()


def cold_start_with_sound():
    subprocess.run(['pkill', '-x', 'desmume-cli'], check=False)
    time.sleep(2)
    subprocess.Popen(
        ['setsid', '/usr/games/desmume-cli', '--cpu-mode=0', '--nojoy=1',
         '/workspace/Kanji/game.nds'],
        stdout=open('/tmp/desmume_rec.log', 'a'), stderr=subprocess.STDOUT,
        start_new_session=True)
    LOG('冷启动（带声）…')
    KC.wait_title()
    LOG('标题页就绪')


def ensure_select(tag, tries=2):
    """确认在选关页；不行则重试一次导航。"""
    for i in range(tries):
        p = R._shot('rec_nav_%s_%d.png' % (tag, i))
        if R._on_select(1, p):
            LOG('✅ 选关页就绪（%s）' % tag)
            return True
        LOG('⚠️ 不在选关页（%s try%d），再试' % (tag, i))
        KC.key_press('x', hold=0.1, after=1.8)      # 高亮通常在当前项，A 激活
        time.sleep(0.8)
    return False


def play_range(diff, lo, hi):
    # 诊断/证据图一律写 /tmp（不污染仓库里已提交的 validation 证据图）
    R._set_shot_dir('/tmp/rec_seg1/%s' % diff)
    res = []
    for L in range(lo, hi + 1):
        rec = KC.rec_for(1, diff, L)
        LOG('===== %s No.%02d (rec%d) =====' % (diff, L, rec))
        try:
            ok = R.play_one(1, diff, L, rec, None, warm=(L > lo), no_settle=False,
                            retry=RETRY)
        except SystemExit as e:
            LOG('❌ play_one 异常：%s' % e)
            ok = False
        res.append((L, ok))
        LOG('%s No.%02d -> %s' % (diff, L, 'PASS' if ok else 'FAIL'))
    return res


def nav_difficulty(diff, down_times):
    """从上一难度的选关页切到 diff 的选关页（纯键盘，不冷启动 → 保住有声模拟器）。

    难度菜单项序：やさしい / ふつう / むずかしい。用「Up×3 夹到顶 + Down×k」锚定，
    丢一次键也不会错位（边缘夹取，同 §S25 的重锚思想）。B 次数给两档变体重试。
    """
    for i, b_press in enumerate((2, 1)):
        for _ in range(b_press):
            KC.key_press('z', hold=0.1, after=1.0)          # B → 難易度菜单
        for _ in range(3):
            KC.key_press('Up', hold=0.08, after=0.4)        # 夹到 やさしい
        for _ in range(down_times):
            KC.key_press('Down', hold=0.08, after=0.5)      # 落到目标难度
        KC.key_press('x', hold=0.1, after=2.0)              # A → 进选关页
        if R._on_select(1, R._shot('rec_nav_%s_%d.png' % (diff, i))):
            LOG('✅ 已到 %s 选关页（B×%d）' % (diff, b_press))
            return True
        LOG('⚠️ 未到 %s 选关页（B×%d 失败）' % (diff, b_press))
    return False


def enter_difficulty(diff, down_times):
    """从「難易度」菜单（高亮 やさしい）用 Up×3 夹顶 + Down×k 定位进入选关页。"""
    for i in range(3):
        for _ in range(3):
            KC.key_press('Up', hold=0.08, after=0.4)
        for _ in range(down_times):
            KC.key_press('Down', hold=0.08, after=0.5)
        KC.key_press('x', hold=0.1, after=2.0)
        if R._on_select(1, R._shot('rec_nav_%s_%d.png' % (diff, i))):
            LOG('✅ 已到 %s 选关页' % diff)
            return True
        LOG('⚠️ 未到 %s 选关页（try%d）' % (diff, i))
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=OUT)
    ap.add_argument('--tag', default='seg1')
    ap.add_argument('--start', choices=('yasashii', 'futsuu'), default='yasashii',
                    help='从哪个难度开录（断点续录用）')
    ap.add_argument('--from', dest='frm', type=int, default=1,
                    help='起始关（该难度内，1-based；断点续录用）')
    args = ap.parse_args()
    test = os.environ.get('SEG1_TEST') == '1'

    R._set_shot_dir('/tmp/rec_seg1/nav')
    cold_start_with_sound()
    aud, vid = start_ffmpeg(args.tag)
    t0 = time.time()
    allres = []
    try:
        # ---- 导航：标题 → ファイル1（空档）→ ゲーム選択 → 漢字ナンクロ → 通常問題 → 難易度 ----
        KC.tap(128, 100, after=1.5)          # 标题 → ファイル選択
        KC.tap(95, 76, after=2.5)            # ファイル1（空档→直接ゲーム選択）
        KC.key_press('x', hold=0.1, after=1.5)   # A：漢字ナンクロ（默认高亮）→ 模式菜单
        KC.key_press('x', hold=0.1, after=1.5)   # A：通常問題 → 難易度菜单

        down = 0 if args.start == 'yasashii' else 1
        if not enter_difficulty(args.start, down):
            LOG('❌ 未能到达 %s 选关页，中止' % args.start)
            return 1

        if test:
            allres += play_range('yasashii', 1, 1)
        elif args.start == 'yasashii':
            allres += play_range('yasashii', args.frm, 35)
            # ---- 切 ふつう：B×2 退回難易度菜单 → Down → A（不冷启动，保住有声模拟器）----
            if not nav_difficulty('futsuu', 1):
                LOG('❌ 未能切到 ふつう，中止（不冷启动以免断音）')
                return 1
            allres += play_range('futsuu', 1, 60)
        else:
            allres += play_range('futsuu', args.frm, 60)
    finally:
        stop_ffmpeg(vid)
        stop_ffmpeg(aud)
        LOG('录制停止，合成中…')
        subprocess.run(
            ['ffmpeg', '-y', '-i', os.path.join(args.out, '%s_video.mp4' % args.tag),
             '-i', os.path.join(args.out, '%s_audio.wav' % args.tag),
             '-vf', 'scale=768:1152:flags=lanczos',
             '-c:v', 'libopenh264', '-b:v', '3M', '-pix_fmt', 'yuv420p',
             '-af', 'volume=-5dB', '-c:a', 'aac', '-b:a', '160k',
             '-shortest', os.path.join(args.out, '%s.mp4' % args.tag)],
            stdout=open('/tmp/ff_mux.log', 'w'), stderr=subprocess.STDOUT)

    npass = sum(1 for _, ok in allres if ok)
    LOG('=== 第一段完成：用时 %.1f 分钟，PASS %d / %d ==='
        % ((time.time() - t0) / 60, npass, len(allres)))
    LOG('FAIL: %s' % [L for L, ok in allres if not ok])
    return 0


if __name__ == '__main__':
    sys.exit(main())
