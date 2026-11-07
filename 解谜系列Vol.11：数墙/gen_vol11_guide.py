#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成《解谜系列Vol.11：数墙》全关卡答案（紧凑字符矩阵版）。

格式：
- 每关一个紧凑字符矩阵，一行即盘面一行，用 ``` 代码块包裹（手机/网页预览下等宽对齐）；
- 墙 = █（全角实心方块）；
- 线索数字 = 带圈数字 ①〜㊿（1..50，单字符，保证每列等宽）；
- 空岛格（无线索的白格）= □；
- 每关一个矩阵，行列与题目尺寸一致，答案已含官方墙位置（wall=1）。

数据源：validation/puzzles.json（extract_nurikabe.py 产物，300 题全部 ok）。
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'validation', 'puzzles.json')
# 攻略产物与脚本同目录（仓库《解谜系列Vol.11：数墙/》）
DST = os.path.join(HERE, '答案.md')

DIFFS = ['入門', 'やさしい', 'ふつう', 'むずかしい']


def split_by_size(items, size_of):
    """按尺寸连续分段：[(尺寸, [关卡...]), ...]。
    难度相同、尺寸也相同的连续关卡归为一章（两者都相同算一章）。"""
    segs = []
    for it in items:
        s = size_of(it)
        if segs and segs[-1][0] == s:
            segs[-1][1].append(it)
        else:
            segs.append((s, [it]))
    assert len({s for s, _ in segs}) == len(segs), [s for s, _ in segs]
    return segs


def circled(n):
    """数字 -> 带圈数字（1..50 单字符）。"""
    if 1 <= n <= 20:
        return chr(0x2460 + n - 1)        # ①..⑳
    if 21 <= n <= 35:
        return chr(0x3251 + n - 21)       # ㉑..㉟
    if 36 <= n <= 50:
        return chr(0x32B1 + n - 36)       # ㊱..㊿
    return str(n)                          # 兜底（本库最大 40，不会到这）


def cell_text(clue, wall):
    """单格内容。墙=█；空岛=□；线索=带圈数字。"""
    if wall == 1:
        return '█'
    if clue >= 1:
        return circled(clue)
    return '□'


def render_table(p):
    """渲染一关为紧凑矩阵 + 代码块围栏（函数名沿用旧称）。"""
    w, h = p['w'], p['h']
    clue, wall = p['clue'], p['wall']
    lines = ['```']
    for r in range(h):
        lines.append(''.join(cell_text(clue[r * w + c], wall[r * w + c]) for c in range(w)))
    lines.append('```')
    return '\n'.join(lines)


def main():
    data = json.load(open(SRC, encoding='utf-8'))
    out = []
    out.append('# 《解谜系列Vol.11：数墙》全关卡答案（官方答案盘面）')
    out.append('')
    out.append('> 📌 **阅读提示**：每关盘面都放在**代码块**里，网页与手机端预览都会按等宽字体渲染，')
    out.append('> 行列对齐、无需切换「源码模式」。')
    out.append('>')
    out.append('> 图例：**`█`** = 墙（黑色格子，官方答案中涂黑的位置）；**带圈数字 ①〜㊿** = 线索数字')
    out.append('> （该数字表示此白色连通块（岛）应包含的格子数）；**全角空格 `　`** = 无线索的白格。')
    out.append('>')
    out.append('> 题目顺序依仓库 `validation/` 目录的关卡顺序：入門 → やさしい → ふつう → むずかしい。')
    out.append('')

    for diff in DIFFS:
        puzzles = data[diff]
        segs = split_by_size(puzzles, lambda p: '%d×%d' % (p['w'], p['h']))
        for size, seg in segs:
            out.append(f'## {diff} · {size}（{len(seg)} 关）')
            out.append('')
            for p in seg:
                out.append(f'**第{p["rec"]:02d}問 rec{p["rec"]}（{p["w"]}×{p["h"]}）**')
                out.append(render_table(p))
                out.append('')

    text = '\n'.join(out).rstrip() + '\n'
    os.makedirs(os.path.dirname(DST), exist_ok=True)
    with open(DST, 'w', encoding='utf-8') as f:
        f.write(text)
    print('已写出', DST, len(text), 'bytes', '%.1f KB' % (len(text) / 1024))


if __name__ == '__main__':
    main()