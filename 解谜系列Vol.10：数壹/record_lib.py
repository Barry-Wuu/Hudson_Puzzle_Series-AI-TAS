#!/usr/bin/env python3
"""数壹可靠自动涂黑：逐格独立点击 + 读盘纠错 + 结算识别。

- click_cell: move / click 分两次 xdotool 调用，中间真实 sleep，避免连点被合并成拖动/双击。
- read_board: 三态读盘（空 . / 黑 # / 白マス印 P），并识别「结算面板」。
- solve: 读盘后按「空→黑→P→空」循环补齐到答案；一旦识别到结算即停。
"""
import json
import subprocess
import sys
import time

sys.path.insert(0, '/tmp')
from PIL import Image
import ds

BX0, BY0, BSX, BSY = 46.0, 45.0, 48.67, 48.83
ENV = ds.ENV


def _xy(r, c):
    g = ds.geom()
    s = g['w'] / 512.0
    x = g['x'] + int((BX0 + BSX * (c + 0.5)) * s)
    y = g['y'] + g['h'] // 2 + int((BY0 + BSY * (r + 0.5)) * s)
    return x, y


def click_cell(r, c, pre=0.12, hold=0.09, post=0.14):
    """逐格点击：move→停留→按下→停留≥1帧→松开。分两次调用+真实 sleep，
    避免连点合并；不能用 `xdotool click`（按下/松开同帧，DS 采样抓不到）。"""
    x, y = _xy(r, c)
    subprocess.run(['xdotool', 'mousemove', str(x), str(y)], env=ENV)
    time.sleep(pre)
    subprocess.run(['xdotool', 'mousedown', '1'], env=ENV)
    time.sleep(hold)
    subprocess.run(['xdotool', 'mouseup', '1'], env=ENV)
    time.sleep(post)


def read_board(im=None):
    """返回 (board[6][6], cleared) 。cleared=True 表示已进入结算/非棋盘。"""
    im = im or ds.shot()
    iw, ih = im.size
    s = iw / 512.0
    board = []
    for r in range(6):
        row = ''
        for c in range(6):
            cx = (BX0 + BSX * (c + 0.5)) * s
            cy = (384 + BY0 + BSY * (r + 0.5)) * s
            blk = pink = tot = 0
            for yy in range(int(cy) - 6, int(cy) + 7):
                for xx in range(int(cx) - 6, int(cx) + 7):
                    if not (0 <= xx < iw and 0 <= yy < ih):
                        continue
                    R, G, B = im.getpixel((xx, yy))
                    tot += 1
                    sm = R + G + B
                    if sm < 340:
                        blk += 1
                    elif R > 160 and B > 130 and R - G > 60:
                        pink += 1
            st = '#' if tot and blk / tot > 0.33 else ('P' if tot and pink / tot > 0.33 else '.')
            row += st
        board.append(row)
    # 结算识别：中间行大量全黑 / 全盘几乎无浅色，都是结算面板特征
    mid_black = sum(board[r].count('#') for r in (1, 2, 3))
    light = sum(r.count('.') for r in board)
    cleared = (mid_black >= 14) or (light <= 6)
    return board, cleared


def taps_needed(cur, want):
    cyc = ['.', '#', 'P']
    return (cyc.index(want) - cyc.index(cur)) % 3


def load_mask(idx):
    data = json.load(open('/tmp/vol10_all.json'))
    rec = [x for x in data if x['diff'] == 0 and x['idx'] == idx][0]
    return [''.join('#' if rec['M'][r][c] else '.' for c in range(6)) for r in range(6)]


def solve(idx, maxit=8, log=print):
    mask = load_mask(idx)
    for it in range(maxit):
        board, cleared = read_board()
        if cleared:
            log(f'  iter{it}: 已结算 → 停')
            return True
        if board == mask:
            log(f'  iter{it}: 盘面已匹配')
            return True
        plan = []
        for r in range(6):
            for c in range(6):
                n = taps_needed(board[r][c], mask[r][c])
                plan += [(r, c)] * n
        log(f'  iter{it}: 需点 {len(plan)} 次')
        if not plan:
            return False
        for (r, c) in plan:
            click_cell(r, c)
        time.sleep(1.0)
    return False
