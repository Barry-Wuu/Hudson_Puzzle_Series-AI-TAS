#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成《解谜系列Vol.12：美術館 / AKARI》全关卡攻略 Markdown。

答案来自 extract_akari.py 产物 validation/puzzles.json（300 题 AKARI 规则自检 300/300 零失败）。

渲染约定：
- 黑墙(无号)        = █
- 带号黑墙(相邻灯数) = 数字 0~4
- 白格有灯(答案)    = ●
- 白格无灯          = 全角空格 　
每个谜题一张等宽表格，行列与题目一致。
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '..', 'validation', 'puzzles.json')
DST = os.path.join(HERE, '攻略.md')

DIFFS = ['入門', 'やさしい', 'ふつう', 'むずかしい']
SUBTITLES = {
    '入門': '入門（20 关，6×6）',
    'やさしい': 'やさしい（100 关，10×10 / 18×10）',
    'ふつう': 'ふつう（110 关，10×10 / 18×10 / 24×14）',
    'むずかしい': 'むずかしい（70 关，24×14 / 36×20）',
}


def cell_char(puz, idx):
    """单格字符。puz 含 given/sol/numbered/bulbs。"""
    w = puz['w']
    c, r = idx % w, idx // w
    bulbs = set(tuple(b) for b in puz['bulbs'])
    numbered = set((nc, nr, n) for (nc, nr, n) in puz['numbered'])
    if (c, r) in bulbs:
        return '●'
    # 白格无灯
    # 查是否为带号墙
    if (c, r, 0) in numbered:
        for (nc, nr, n) in numbered:
            if (nc, nr) == (c, r):
                return str(n)
    # 无号墙：given 该格 = 0x58
    if puz['given'][idx] == 0x58:
        return '█'
    return '　'


def render_table(puz):
    w, h = puz['w'], puz['h']
    header = '| ' + ' | '.join('' for _ in range(w)) + ' |'
    sep = '| ' + ' | '.join('---' for _ in range(w)) + ' |'
    lines = [header, sep]
    for r in range(h):
        cells = [cell_char(puz, r * w + c) for c in range(w)]
        lines.append('| ' + ' | '.join(cells) + ' |')
    return '\n'.join(lines)


def main():
    data = json.load(open(SRC, encoding='utf-8'))
    out = []
    out.append('# 《解谜系列Vol.12：美術館 / AKARI（点灯）》全关卡攻略（官方解答）')
    out.append('')
    out.append('> 📌 **阅读提示**：本文件用 **Markdown 表格**展示每关解答。若在网页/App 预览中看到')
    out.append('> 表格列错位，属**渲染器问题**而非文件问题，请切换「源码模式 / Raw Data」或用纯文本编辑器打开。')
    out.append('>')
    out.append('> 图例：**`█`** = 黑墙（无号）；**数字 0~4** = 带号黑墙（该墙上下左右相邻的灯数）；')
    out.append('> **`●`** = 应放置的灯（答案）；**全角空格 `　`** = 普通白格（不放灯）。')
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
            out.append('')
            out.append(render_table(p))
            out.append('')
    text = '\n'.join(out).rstrip() + '\n'
    with open(DST, 'w', encoding='utf-8') as f:
        f.write(text)
    print('已写出', DST, len(text), 'bytes', '%.1f KB' % (len(text) / 1024))


if __name__ == '__main__':
    main()
