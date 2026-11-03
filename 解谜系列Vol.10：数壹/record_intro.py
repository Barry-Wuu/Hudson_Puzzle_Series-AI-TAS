#!/usr/bin/env python3
"""入門关批量录制：输出 256×384 + 系统声 + alimiter + 无光标。

交互在 512×768（2×）进行，落格更稳；ffmpeg 抓 512×768 后再缩放为 256×384。
每关：选关→进入→（选项→リトライ→はい 复位）→等 START→逐格可靠点击涂黑
→读盘纠错兜底（并识别结算）→A 存档回选关。

用法：python3 record_intro.py [起始关] [结束关]
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '/tmp')
import ds
import record_lib as R

COLS = [19, 44, 67, 91, 116, 139, 163, 188, 211, 235]
OUT = '/workspace/Vol.10_入門录播'
WIN_X, WIN_Y = 400, 120


def level_touch(idx):
    if idx <= 10:
        return COLS[idx - 1], 88
    return COLS[idx - 11], 104


def ffmpeg_proc(path):
    cmd = [
        'ffmpeg', '-y', '-loglevel', 'error',
        '-thread_queue_size', '512',
        '-f', 'x11grab', '-video_size', '512x768', '-framerate', '30',
        '-i', f':99+{WIN_X},{WIN_Y}',
        '-thread_queue_size', '512',
        '-f', 'pulse', '-i', 'rec.monitor',
        '-af', 'alimiter=limit=0.9:asc=1',
        '-vf', 'scale=256:384:flags=lanczos',
        '-c:v', 'libopenh264', '-b:v', '1200k', '-r', '30',
        '-c:a', 'aac', '-b:a', '128k',
        '-fflags', '+genpts',
        path,
    ]
    env = dict(os.environ, DISPLAY=':99')
    return subprocess.Popen(cmd, env=env, stderr=subprocess.DEVNULL)


def mask_cells(idx):
    mask = R.load_mask(idx)
    return [(r, c) for r in range(6) for c in range(6) if mask[r][c] == '#']


def record_level(idx):
    path = f'{OUT}/Vol.10_数壹_入門{idx:03d}_256x384.mp4'
    p = ffmpeg_proc(path)
    time.sleep(0.6)

    tx, ty = level_touch(idx)
    ds.click_touch(tx, ty, wait=0.8)        # 选关
    ds.key('x', wait=1.7, hold=0.12)        # A 进入
    ds.key('Return', wait=0.7, hold=0.12)   # 选项
    ds.click_touch(145, 179, wait=0.8)      # リトライ
    time.sleep(0.7)
    ds.click_touch(95, 148, wait=0.6)       # はい（复位计时）
    time.sleep(3.5)                          # 等 START 完全淡出(略加长, 防首点被 START 吃掉)

    # —— 稳健填法(修「开头误触」): 以入场读盘为基准, 把每个格直接设成答案掩码。
    # 多余格(#/P→.) 与缺格(.→#) 一次到位, 再 solve() 兜底(正常 board==mask 零迭代)。
    # 这样无论入场有无误触, 一遍即干净, 结算前不再出现可见的额外矫正。
    board, _ = R.read_board()
    mask = R.load_mask(idx)
    for r in range(6):
        for c in range(6):
            for _ in range(R.taps_needed(board[r][c], mask[r][c])):
                R.click_cell(r, c)
    # 校验补齐: 再读一次, 把连续快点漏掉的格补上(通常 0~2 格)
    time.sleep(0.6)
    b2, _ = R.read_board()
    for r in range(6):
        for c in range(6):
            if b2[r][c] != mask[r][c]:
                for _ in range(R.taps_needed(b2[r][c], mask[r][c])):
                    R.click_cell(r, c)
    time.sleep(0.6)
    R.solve(idx, log=lambda *a: None)        # 正常情况下 board==mask 直接返回
    time.sleep(2.5)                          # 等结算稳定

    p.terminate()                            # 停在结算画面，存档动作不入镜
    try:
        p.wait(timeout=5)
    except subprocess.TimeoutExpired:
        p.kill()

    ds.key('x', wait=3.6, hold=0.12)         # A 存档 → 回选关（不录制）
    time.sleep(0.6)

    print(f'  ✓ 入門{idx:03d}  {os.path.getsize(path)//1024} KB', flush=True)


def main():
    lo = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    hi = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    os.makedirs(OUT, exist_ok=True)
    for idx in range(lo, hi + 1):
        print(f'录制入門{idx:03d} …', flush=True)
        record_level(idx)


if __name__ == '__main__':
    main()
