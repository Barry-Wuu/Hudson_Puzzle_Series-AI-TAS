#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成《解谜系列Vol.12：美術館／AKARI（点灯）》全关卡攻略（紧凑字符矩阵版）。

格式（用户指定，与 Vol.11 数墙攻略一致）：
- 每关一个「紧凑字符矩阵」，一行 = 盘面一行，无表格竖线，便于 raw 直接阅读；
- 空白格（白格）= □（与数墙攻略相同）；
- 墙（无数字的黑格）= █（与数墙攻略相同）；
- 带数字的墙 = emoji 0️⃣ 1️⃣ 2️⃣ 3️⃣ 4️⃣；
- 灯泡 = 💡。

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
DST = os.path.join(HERE, '攻略.md')

MODES = ['入門', 'やさしい', 'ふつう', 'むずかしい']
TITLES = {
    '入門': '入門',
    'やさしい': 'やさしい',
    'ふつう': 'ふつう',
    'むずかしい': 'むずかしい',
}

NUM = ['0️⃣', '1️⃣', '2️⃣', '3️⃣', '4️⃣']

WALL, BLANK, LAMP = '█', '□', '💡'


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
    out.append('# 《解谜系列Vol.12：美術館／AKARI（点灯）》全关卡攻略（官方答案盘面）')
    out.append('')
    out.append('> 📌 **阅读提示**：本文件的盘面是**紧凑字符矩阵**，一行即盘面一行、无表格竖线，'
               '为「源码模式 / Raw Data」直接阅读而设计。若在渲染后的预览里看到格子错位，属**渲染器问题**而非文件问题。')
    out.append('>')
    out.append('> 说明：美術館（Akari／点灯）的规则是——在盘面放置灯泡，使**所有白格都被照亮**，'
               '且**灯泡之间不能互相直射**；墙会挡住光线，墙上的数字表示**该墙四周相邻格中必须放置的灯泡数量**。')
    out.append('> 以下盘面即**官方答案**——墙、数字墙原样保留，灯泡已标在正解位置。')
    out.append('>')
    out.append('> 图例：**`█`** = 墙（无数字）；**`0️⃣`~`4️⃣`** = 带数字的墙（数字 = 相邻格中灯泡数量）；'
               '**`□`** = 空白格（白格）；**`💡`** = 灯泡（答案位置）。')
    out.append('>')
    out.append('> ⚠️ `💡` 与 `0️⃣`~`4️⃣` 是**双宽 emoji**，而 `█`/`□` 是单宽字符，'
               '因此在等宽字体下同一行的格子列宽会略有参差（emoji 占两格）。这是字符宽度差异，不是盘面错位；'
               '逐行按顺序读即为正确盘面。')
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
            out.append('')
            out.append(render(p))
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
