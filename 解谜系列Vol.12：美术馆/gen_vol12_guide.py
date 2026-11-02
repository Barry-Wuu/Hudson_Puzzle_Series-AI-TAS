#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成《解谜系列Vol.12：美術館／AKARI（点灯）》全关卡答案（紧凑字符矩阵版）。

格式（与 Vol.11 数墙攻略一致的紧凑矩阵）：
- 每关一个「紧凑字符矩阵」，一行 = 盘面一行，无表格竖线，便于 raw 直接阅读；
- 空白格（白格）= ⬜️；
- 墙（无数字的黑格）= 🟦（蓝色实心方块，与数字键帽同色系）；
- 带数字的墙 = emoji 0️⃣ 1️⃣ 2️⃣ 3️⃣ 4️⃣；
- 灯泡 = 💡。
- 每关盘面用 ``` 代码块包裹（前后各一行），手机/网页预览下也能保持等宽对齐，无需切 raw；
- 四类格子均为双宽 emoji，故代码块内每列宽度一致、不会错位。

数据源：validation/puzzles.json
  sol 取值编码（实测）：
    45 = 白格（无关灯与否）
    35 = 无数字墙
    64 = 灯泡
    0..4 = 带数字的墙（数字即该值）
"""
import json
import os
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'validation', 'puzzles.json')
DST = os.path.join(HERE, '答案.md')

MODES = ['入門', 'やさしい', 'ふつう', 'むずかしい']
TITLES = {
    '入門': '入門',
    'やさしい': 'やさしい',
    'ふつう': 'ふつう',
    'むずかしい': 'むずかしい',
}

NUM = ['0️⃣', '1️⃣', '2️⃣', '3️⃣', '4️⃣']

WALL, BLANK, LAMP = '🟦', '⬜️', '💡'  # 墙 = 蓝色实心方块


def cell(v):
    if v == 45:
        return BLANK
    if v == 35:
        return WALL
    if v == 64:
        return LAMP
    if 0 <= v <= 4:
        return NUM[v]
    raise ValueError('unknown cell code %r' % (v,))


def render(p):
    w, h, sol = p['w'], p['h'], p['sol']
    return '\n'.join(''.join(cell(sol[y * w + x]) for x in range(w)) for y in range(h))


def size_note(items):
    c = Counter('%d×%d' % (p['w'], p['h']) for p in items)
    if len(c) == 1:
        return list(c)[0]
    return ' / '.join(f'{k}（{n} 关）' if n != len(items) else k for k, n in c.items())


def main():
    data = json.load(open(SRC, encoding='utf-8'))
    out = []
    out.append('# 《解谜系列Vol.12：美術館／AKARI（点灯）》全关卡答案（官方答案盘面）')
    out.append('')
    out.append('> 📌 **阅读提示**：每关盘面都放在**代码块**里，网页与手机端预览都会按等宽字体渲染，'
               '行列对齐、无需切换「源码模式」。')
    out.append('>')
    out.append('> 说明：美術館（Akari／点灯）的规则是——在盘面放置灯泡，使**所有白格都被照亮**，'
               '且**灯泡之间不能互相直射**；墙会挡住光线，墙上的数字表示**该墙四周相邻格中必须放置的灯泡数量**。')
    out.append('> 以下盘面即**官方答案**——墙、数字墙原样保留，灯泡已标在正解位置。')
    out.append('>')
    out.append('> 图例：**`🟦`** = 墙（无数字，蓝色实心方块）；**`0️⃣`~`4️⃣`** = 带数字的墙（数字 = 相邻格中灯泡数量）；'
               '**`⬜️`** = 空白格（白格）；**`💡`** = 灯泡（答案位置）。')
    out.append('>')
    out.append('> 四类格子（`⬜️` ` ⃣` `0️⃣`~`4️⃣` `💡`）均占**两格宽**，'
               '代码块内每格宽度一致，不会出现单宽/双宽混排的错位。')
    out.append('>')
    out.append('> 题目顺序依仓库 `validation/` 目录的关卡顺序：入門 → やさしい → ふつう → むずかしい。')
    out.append('')

    total = 0
    for mode in MODES:
        items = data[mode]
        total += len(items)
        out.append(f'## {TITLES[mode]}')
        out.append('')
        out.append(f'{mode}（{len(items)} 关，{size_note(items)}）')
        out.append('')
        for p in items:
            out.append(f'### 第{p["rec"]:03d}問 rec{p["rec"]}（{p["w"]}×{p["h"]}）')
            out.append('```')
            out.append(render(p))
            out.append('```')
            out.append('')

    out.append(f'> 全 {total} 关。')
    text = '\n'.join(out).rstrip() + '\n'
    with open(DST, 'w', encoding='utf-8') as f:
        f.write(text)
    print('已写出', DST)
    print('关卡数:', {m: len(data[m]) for m in MODES}, '合计', total)
    print('大小: %.1f KB' % (len(text.encode('utf-8')) / 1024))


if __name__ == '__main__':
    main()
