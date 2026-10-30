#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成《解谜系列Vol.11：数墙》全关卡攻略 Markdown 表格版（2026-10-19）。

格式（用户指定）：
- 用 Markdown 表格展示每关答案盘面；
- 墙 = █（全角实心方块）；
- 线索数字 = 带圈数字 ①〜㊿（1..50，单字符，保证每列等宽）；
- 空岛格（无线索的白格）= 全角空格 　；
- 每关一个表格，行列与题目尺寸一致，答案已含官方墙位置（wall=1）。

数据源：validation/puzzles.json（extract_nurikabe.py 产物，300 题全部 ok）。
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '..', '_vol11', 'puzzles.json')
# 攻略产物与脚本同目录（仓库《解谜系列Vol.11：数墙/》）
DST = os.path.join(HERE, '攻略.md')

DIFFS = ['入門', 'やさしい', 'ふつう', 'むずかしい']
SUBTITLES = {
    '入門': '入門（20 关，6×6）',
    'やさしい': 'やさしい（100 关，10×10 / 18×10）',
    'ふつう': 'ふつう（100 关，18×10 / 24×14）',
    'むずかしい': 'むずかしい（80 关，24×14 / 36×20）',
}


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
    """单格内容。墙=█；空岛=全角空格；线索=带圈数字。"""
    if wall == 1:
        return '█'
    if clue >= 1:
        return circled(clue)
    return '　'


def render_table(p):
    """渲染一关为 Markdown 表格。返回多行字符串。"""
    w, h = p['w'], p['h']
    clue, wall = p['clue'], p['wall']
    header = '| ' + ' | '.join('' for _ in range(w)) + ' |'
    sep = '| ' + ' | '.join('---' for _ in range(w)) + ' |'
    lines = [header, sep]
    for r in range(h):
        cells = [cell_text(clue[r * w + c], wall[r * w + c]) for c in range(w)]
        lines.append('| ' + ' | '.join(cells) + ' |')
    return '\n'.join(lines)


def main():
    data = json.load(open(SRC, encoding='utf-8'))
    out = []
    out.append('# 《解谜系列Vol.11：数墙》全关卡攻略（官方答案盘面）')
    out.append('')
    out.append('> 📌 **阅读提示**：本文件用 **Markdown 表格**展示每关答案。若在网页/App 的预览中看到')
    out.append('> 表格列错位、或 `█` 与数字不等宽，属**渲染器问题**而非文件问题。请切换右上角「**源码模式** / **Raw Data**」')
    out.append('> 查看，或用记事本、VS Code 等纯文本/代码编辑器打开，格式即为正确效果。')
    out.append('>')
    out.append('> 图例：**`█`** = 墙（黑色格子，官方答案中涂黑的位置）；**带圈数字 ①〜㊿** = 线索数字')
    out.append('> （该数字表示此白色连通块（岛）应包含的格子数）；**全角空格 `　`** = 无线索的白格。')
    out.append('>')
    out.append('> 题目顺序依仓库 `validation/` 目录的关卡顺序：入門 → やさしい → ふつう → むずかしい。')
    out.append('')

    for diff in DIFFS:
        out.append(f'## {diff}')
        out.append('')
        out.append(f'{SUBTITLES[diff]}')
        out.append('')
        puzzles = data[diff]
        for p in puzzles:
            out.append(f'### 第{p["rec"]:02d}問 rec{p["rec"]}（{p["w"]}×{p["h"]}）')
            out.append('')
            out.append(render_table(p))
            out.append('')

    text = '\n'.join(out).rstrip() + '\n'
    os.makedirs(os.path.dirname(DST), exist_ok=True)
    with open(DST, 'w', encoding='utf-8') as f:
        f.write(text)
    print('已写出', DST, len(text), 'bytes', '%.1f KB' % (len(text) / 1024))


if __name__ == '__main__':
    main()