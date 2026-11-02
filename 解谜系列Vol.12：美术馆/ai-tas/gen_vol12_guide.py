#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成《解谜系列Vol.12：美術館 / AKARI》全关卡答案 Markdown。

答案来自 extract_akari.py 产物 validation/puzzles.json（300 题 AKARI 规则自检 300/300 零失败）。

渲染约定（与根目录 gen_vol12_guide.py 的紧凑矩阵版完全一致）：
- 黑墙(无号)        = ⬛️
- 带号黑墙(相邻灯数) = 0️⃣ ~ 4️⃣
- 白格有灯(答案)    = 💡
- 白格无灯          = ⬜️
每关一个紧凑矩阵，并用 ``` 代码块包裹（前后各一行），手机/网页预览下保持等宽对齐。
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '..', 'validation', 'puzzles.json')
DST = os.path.join(HERE, '答案.md')

NUM = ['0️⃣', '1️⃣', '2️⃣', '3️⃣', '4️⃣']

DIFFS = ['入門', 'やさしい', 'ふつう', 'むずかしい']
SUBTITLES = {
    '入門': '入門（20 关，6×6）',
    'やさしい': 'やさしい（100 关，10×10 / 18×10）',
    'ふつう': 'ふつう（110 关，10×10 / 18×10 / 24×14）',
    'むずかしい': 'むずかしい（70 关，24×14 / 36×20）',
}


def cell_char(puz, idx):
    """单格字符，直接读 sol（与根目录紧凑矩阵版同源，避免 numbered 字段的错位）。

    sol 编码（实测）：45=白格、35=无号墙、64=灯泡、0..4=带号墙（数字即该值）。
    """
    v = puz['sol'][idx]
    if v == 45:
        return '⬜️'
    if v == 35:
        return '⬛️'
    if v == 64:
        return '💡'
    if 0 <= v <= 4:
        return NUM[v]
    raise ValueError('unknown cell code %r' % (v,))


def render_table(puz):
    """紧凑矩阵 + 代码块围栏（函数名沿用旧称）。"""
    w, h = puz['w'], puz['h']
    lines = ['```']
    for r in range(h):
        lines.append(''.join(cell_char(puz, r * w + c) for c in range(w)))
    lines.append('```')
    return '\n'.join(lines)


def main():
    data = json.load(open(SRC, encoding='utf-8'))
    out = []
    out.append('# 《解谜系列Vol.12：美術館 / AKARI（点灯）》全关卡答案（官方解答）')
    out.append('')
    out.append('> 📌 **阅读提示**：每关盘面都放在**代码块**里，网页与手机端预览都会按等宽字体渲染，')
    out.append('> 行列对齐、无需切换「源码模式」。')
    out.append('>')
    out.append('> 图例：**`⬛️`** = 黑墙（无号）；**`0️⃣`~`4️⃣`** = 带号黑墙（该墙上下左右相邻的灯数）；')
    out.append('> **`💡`** = 应放置的灯（答案）；**`⬜️`** = 普通白格（不放灯）。')
    out.append('>')
    out.append('> 题目顺序依仓库 `validation/` 目录：入門 → やさしい → ふつう → むずかしい。')
    out.append('')
    for diff in DIFFS:
        out.append('## %s' % diff)
        out.append('')
        out.append(SUBTITLES[diff])
        out.append('')
        for p in data[diff]:
            out.append('### 第%02d問（%d×%d）' % (p['rec'], p['w'], p['h']))
            out.append(render_table(p))
            out.append('')
    text = '\n'.join(out).rstrip() + '\n'
    with open(DST, 'w', encoding='utf-8') as f:
        f.write(text)
    print('已写出', DST, len(text), 'bytes', '%.1f KB' % (len(text) / 1024))


if __name__ == '__main__':
    main()
