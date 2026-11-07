#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vol.3 全关卡答案.md 生成器 —— 读 validation/puzzles.json（ROM 静态提取产物）。

分章规则（与其它卷一致）：**难度与尺寸都相同的连续关卡算一章**；
本卷 300 关全是 9×9，故等价于按难度分 3 章。
章标题 `## 难度 · 尺寸（N 关）`；关卡标题 `**第NNN問（9×9）**`（全局连续编号，
不带 # 前缀）；每关代码块给出 9 行 × 9 数字的**完整解**。

用法：python3.11 gen_vol3_guide.py
产出：脚本同目录 答案.md
"""
import os
import json

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'validation', 'puzzles.json')
OUT = os.path.join(HERE, '答案.md')

HEADER = """# 《解谜系列Vol.03：数独》全关卡答案（ROM 静态提取的官方答案盘面）

> 📌 **阅读提示**：每关答案盘面都放在**代码块**里，网页与手机端预览按等宽字体渲染，行列对齐、无需切换「源码模式」。
>
> 说明：数独在 9×9 盘面上给出部分数字，空格填入 1~9，使每行、每列及每个 3×3 宫内都恰好是 1~9 各一次。以下盘面即**官方答案**——直接给出 9 行 × 9 数字的**完整解**，行内不加空格。
>
> 答案来自 ROM 内现成的题面/答案双平面数据（NitroFS 资源包尾部 300 个 648 字节块），**开录之前一次性全部静态提取**，不是现场求解、也不是逐关读屏；提取与自检见 `extract_vol3_answers.py`，结构化数据见 `validation/puzzles.json`。300 关全部通过「题面合法 / 答案合法 / 覆盖给定 / 唯一解 / 与 ROM 答案一致」五项自检。
>
> 本卷**无入門难度**，最简单为「やさしい」。关卡分布（游戏选关页实测）：やさしい 70 問 / ふつう 140 問 / むずかしい 90 問，合计 300 問；「認定問題（段位認定）」复用这 300 問，ROM 无独立题库。
>
> 题目顺序依 `validation/puzzles.json` 的全局关卡号：やさしい 001–070 → ふつう 071–210 → むずかしい 211–300。
"""


def main():
    data = json.load(open(SRC, encoding='utf-8'))
    # 按 (难度, 尺寸) 连续分段
    chapters = []
    cur_key, cur_items = None, None
    for rec in data:
        key = (rec['diff'], '%d×%d' % (rec['w'], rec['h']))
        if key != cur_key:
            cur_key = key
            cur_items = []
            chapters.append((key, cur_items))
        cur_items.append(rec)

    lines = [HEADER.rstrip(), '']
    for (diff, size), recs in chapters:
        lines.append('## %s · %s（%d 关）' % (diff, size, len(recs)))
        lines.append('')
        for r in recs:
            lines.append('**第%03d問（%s）**' % (r['idx'], size))
            lines.append('')
            lines.append('```')
            sol = r['solution']
            for i in range(r['h']):
                lines.append(''.join(str(v) for v in sol[i * r['w']:(i + 1) * r['w']]))
            lines.append('```')
            lines.append('')
    text = '\n'.join(lines).rstrip() + '\n'
    open(OUT, 'w', encoding='utf-8').write(text)
    print('章节:', ['%s · %s（%d 关）' % (k[0], k[1], len(v)) for k, v in chapters])
    print('关卡数:', len(data), '已写出', OUT)


if __name__ == '__main__':
    main()
