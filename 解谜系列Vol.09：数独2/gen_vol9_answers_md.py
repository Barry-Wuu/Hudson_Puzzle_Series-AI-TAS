#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""由 validation/puzzles.json 生成《答案.md》—— 数字 emoji 盘面，9 行读完即完整解。

版式与 Vol.03（数独1）一致：同一个 3×3 宫内三格连写，宫与宫之间一个空格，
行间换行，每 3 行之间再空一行。
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'validation', 'puzzles.json')
OUT = os.path.join(HERE, '答案.md')

EMOJI = {i: '%d\ufe0f\u20e3' % i for i in range(1, 10)}


def grid_text(sol):
    rows = []
    for r in range(9):
        row = sol[r * 9:(r + 1) * 9]
        rows.append(' '.join(''.join(EMOJI[v] for v in row[c:c + 3]) for c in range(0, 9, 3)))
        if (r + 1) % 3 == 0 and r != 8:
            rows.append('')
    return '\n'.join(rows)


def main():
    data = json.load(open(SRC, encoding='utf-8'))
    diffs = []
    for r in data:
        if r['diff'] not in diffs:
            diffs.append(r['diff'])
    counts = {d: sum(1 for r in data if r['diff'] == d) for d in diffs}
    total = len(data)

    out = []
    out.append('# 《解谜系列Vol.09：数独2》全关卡答案（ROM 静态提取的官方答案盘面）\n')
    out.append('> 📌 **阅读提示**：每关答案盘面都放在**代码块**里，网页与手机端预览按等宽字体渲染，'
               '无需切换「源码模式」。每格用**数字 emoji**（1️⃣~9️⃣）表示：**同一个 3×3 宫内三格连写、'
               '宫内不留空格；宫与宫之间一个空格；行间回车换行，每 3 行之间再空一行**。9 行读完就是完整解。\n')
    out.append('> 说明：数独在 9×9 盘面上给出部分数字，空格填入 1~9，使每行、每列及每个 3×3 宫内都恰好是 '
               '1~9 各一次。以下盘面即**官方答案**——直接给出 9 行 × 9 格的**完整解**。\n')
    out.append('> 答案来自 ROM 内现成的题面/答案双平面数据（偏移 `0x323330` 起连续 %d 个 164 字节块，'
               '`[0:81]` 题面 / `[81:162]` 答案），**开录之前一次性全部静态提取**，不是现场求解、'
               '也不是逐关读屏；提取与自检见 `extract_vol9_answers.py`，结构化数据见 `validation/puzzles.json`。'
               '%d 关全部通过「题面合法 / 答案合法 / 覆盖给定 / 唯一解 / 与 ROM 答案一致」五项自检。\n'
               % (total, total))
    out.append('> 关卡分布（游戏选关页与录播实测）：%s，合计 %d 問；'
               '段位認定問題（ブロンズ/シルバー/ゴールド/プラチナ）**不在**这张表里，'
               'ROM 无独立题块，是进题时现场生成的。\n'
               % (' / '.join('%s %d 問' % (d, counts[d]) for d in diffs), total))
    out.append('> 题目顺序依 `validation/puzzles.json` 的全局关卡号：'
               + ' → '.join('%s %03d–%03d' % (d,
                                              sum(counts[x] for x in diffs[:i]) + 1,
                                              sum(counts[x] for x in diffs[:i + 1]))
                            for i, d in enumerate(diffs)) + '。\n')

    for d in diffs:
        start = sum(counts[x] for x in diffs[:diffs.index(d)]) + 1
        out.append('\n## %s · 9×9（%d 关，全局 %03d–%03d）\n' % (d, counts[d], start, start + counts[d] - 1))
        for r in [x for x in data if x['diff'] == d]:
            out.append('**第%03d問（%s No.%03d · 空格 %d）**\n' % (r['idx'], d, r['diff_idx'], r['blank']))
            out.append('```\n%s\n```\n' % grid_text(r['solution']))

    open(OUT, 'w', encoding='utf-8').write('\n'.join(out))
    print('已写出 %s（%d 关，%.0f KB）' % (OUT, total, os.path.getsize(OUT) / 1024))


if __name__ == '__main__':
    main()
