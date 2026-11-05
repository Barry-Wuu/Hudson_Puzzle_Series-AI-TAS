#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vol.4（数和 / Kakuro）入門关「实况」录制。

答案来源（用户定调：答案本来就在 bin 里，玩的时候挖出，不是现场推算）：
  validation/vol4_all.json —— ROM `CPQ.` 数据块静态提取的 310 关记录表。
  每条关卡「记录体最后 36 字节」= 6x6 答案数字盘（行优先）：
    0    = 提示格 / 黑格（不填）
    1..9 = 该白格的正确答案数字

结构与验证（全部实测，勿臆断）：
  * 入門第1問(level 0)：答案盘 13 个非零格与屏幕白格逐格吻合；
    段描述 4 字节组 [提示格坐标, 段长, 段和] 也全量对上（如 [0,2,3,7] → r2 的 2+4+1=7）。
  * 入門第2問(level 1)：16 个非零格与屏幕白格逐格吻合（含 r3c3、r5c5 为提示格）。
  * 填完第1問 13 格即自动出现「CLEAR」，无需按 A 决定。

交互（与 Vol.10 数壹的「涂黑」完全不同）：
  点下屏缩略盘白格 → 选中；点右侧数字键盘 1-9 → 填入该格；填满自动结算。
  下屏缩略盘 6x6 格心（触屏 256x192 坐标）: (13+25*(c+.5), 20+25.5*(r+.5))
  数字键盘格心: (203+19.5*((n-1)%3), 65+23.5*((n-1)//3))

前置条件：Xvfb :99 上的 desmume-cli 已运行、且**已停在目标关的空白盘面**
（导航链见 RESEARCH.md §三：标题→初期化→Logo→スタート→选关→A 进关）。
音频：当前 pulse 无 desmume sink-input，故录静音 AAC 轨保持与 Vol.10 录播格式一致，
后期可按既有「cover + 音频叠加」流程补 BGM。

用法：python3.11 record_intro.py [0-based 关号=1] [输出目录]
"""
import os
import sys
import json
import time
import subprocess

sys.path.insert(0, '/tmp')
import ds

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, 'validation', 'vol4_all.json')
DEFAULT_OUT = '/workspace/Vol.4_入門录播'


def cell_touch(r, c):
    """下屏缩略盘 (r,c) 格心，返回 NDS 触屏坐标。"""
    return int(13 + 25 * (c + 0.5)), int(20 + 25.5 * (r + 0.5))


def num_touch(n):
    """右侧数字键盘上数字 n 的格心，返回 NDS 触屏坐标。"""
    return int(203 + 19.5 * ((n - 1) % 3)), int(65 + 23.5 * ((n - 1) // 3))


def answer_grid(level):
    """0-based 关号 → 6x6 答案盘（0=提示格，1..9=答案）。"""
    with open(DATA, encoding='utf-8') as fp:
        report = json.load(fp)
    body = bytes.fromhex(report['levels'][level]['body_hex'])
    disk = body[-36:]
    return [[disk[r * 6 + c] for c in range(6)] for r in range(6)]


def ffmpeg_proc(path):
    g = ds.geom()
    cmd = [
        'ffmpeg', '-y', '-loglevel', 'error',
        '-thread_queue_size', '512',
        '-f', 'x11grab', '-video_size', '%dx%d' % (g['w'], g['h']),
        '-framerate', '30', '-draw_mouse', '0',
        '-i', ':99+%d,%d' % (g['x'], g['y']),
        '-thread_queue_size', '512',
        '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=stereo',
        '-af', 'alimiter=limit=0.9:asc=1',
        '-c:v', 'libopenh264', '-b:v', '1200k', '-r', '30',
        '-c:a', 'aac', '-b:a', '128k',
        '-fflags', '+genpts',
        path,
    ]
    env = dict(os.environ, DISPLAY=':99')
    return subprocess.Popen(cmd, env=env, stderr=subprocess.DEVNULL)


def record(level, out):
    grid = answer_grid(level)
    cells = [(r, c, grid[r][c]) for r in range(6) for c in range(6) if grid[r][c]]
    print('入門%03d 答案格 %d 个:' % (level + 1, len(cells)), cells, flush=True)

    p = ffmpeg_proc(out)
    time.sleep(1.0)          # 等 ffmpeg 起来
    time.sleep(2.0)          # 开头留白：让观众看清题目与提示数字

    for r, c, v in cells:    # 按行优先逐格填，视觉上自上而下、从左到右
        x, y = cell_touch(r, c)
        nx, ny = num_touch(v)
        ds.click_touch(x, y, wait=0.35)     # 选中格
        ds.click_touch(nx, ny, wait=0.45)   # 输入数字

    time.sleep(4.5)          # 等最后一格触发 CLEAR 演出 + 停在结算画面
    p.terminate()
    try:
        p.wait(timeout=6)
    except subprocess.TimeoutExpired:
        p.kill()
    return len(cells)


def main():
    level = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    outdir = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OUT
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, 'Vol.4_数和_入門%03d_256x384.mp4' % (level + 1))
    n = record(level, out)
    print('录制完成: %s  (%d KB, %d 格)' % (out, os.path.getsize(out) // 1024, n), flush=True)


if __name__ == '__main__':
    main()
