# -*- coding: utf-8 -*-
"""生成《解谜系列Vol.4：数和》全 310 关 答案.md（格式照 Vol.12 美术馆）。

格子映射（用户指定）：
  * 答案盘 0 = 斜线格 → ⬛（纯斜线格与带提示数字的斜线格统一，不区分）
  * 答案盘 1..9 = 答案格 → 1️⃣~9️⃣
  * 首行 / 首列若无答案格（整行/整列全 0）就不画该行/列 → 提示行列被裁掉

答案盘 = body[-(cols*rows):]，cols/rows 由 body 头部 byte2/byte3 给出，
共 6 种尺寸：6×6 / 8×8 / 10×10 / 12×12 / 12×20 / 14×22（cols×rows）。
"""
import os
import json
import collections

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, 'validation', 'vol4_all.json')
OUT = os.path.join(HERE, '答案.md')

EMO = ['⬛', '1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣']
BANDS = [('入門', 0, 20), ('やさしい', 20, 110),
         ('ふつう', 110, 230), ('むずかしい', 230, 310)]


def render(disk, C, R):
    grid = [[disk[r * C + c] for c in range(C)] for r in range(R)]
    if all(grid[0][c] == 0 for c in range(C)):
        grid = grid[1:]
        R -= 1
    if all(grid[r][0] == 0 for r in range(R)):
        grid = [row[1:] for row in grid]
        C -= 1
    return [''.join(EMO[v] for v in row) for row in grid], C, R


def main():
    levels = json.load(open(DATA, encoding='utf-8'))['levels']
    lines = []
    A = lines.append
    A('# 《解谜系列Vol.4：数和》全关卡答案（官方答案盘面）')
    A('')
    A('> 📌 **阅读提示**：每关盘面都放在**代码块**里，网页与手机端预览都会按等宽字体渲染，行列对齐、无需切换「源码模式」。')
    A('>')
    A('> 说明：数和在斜线格上给出提示数，白格填入 1~9，使每段白格的数字之和等于提示数。以下盘面即**官方答案**——斜线格原样保留，白格已标上应填的数字。')
    A('>')
    A('> 图例：**`⬛`** = 斜线格（纯斜线格与带提示数字的斜线格，统一记作 ⬛）；**`1️⃣`~`9️⃣`** = 答案格（该格应填的数字）。')
    A('>')
    A('> `⬛` 与 `1️⃣`~`9️⃣` 均为**双宽 emoji**，代码块内每格宽度一致，不会出现单宽/双宽混排的错位。')
    A('>')
    A('> 首行 / 首列为提示行列，若整行 / 整列没有答案格就不画：故 6×6 盘呈 5×5、8×8 呈 7×7、10×10 呈 9×9、12×12 呈 11×11、20×12 呈 11×19、22×14 呈 13×21。')
    A('>')
    A('> 题目顺序依仓库 `validation/vol4_all.json` 的关卡顺序：入門 → やさしい → ふつう → むずかしい。')
    A('')
    for name, a, z in BANDS:
        A('## %s' % name)
        A('')
        cnt = collections.Counter()
        for lv in range(a, z):
            b = bytes.fromhex(levels[lv]['body_hex'])
            cnt['%d×%d' % (b[2] - 1, b[3] - 1)] += 1
        desc = ' / '.join('%s（%d 关）' % (k, v)
                         for k, v in sorted(cnt.items(), key=lambda x: -x[1]))
        A('%s（%d 关，%s）' % (name, z - a, desc))
        A('')
        for lv in range(a, z):
            b = bytes.fromhex(levels[lv]['body_hex'])
            C, R = b[2], b[3]
            disk = b[-(C * R):]
            rows, W, H = render(disk, C, R)
            n = lv - a + 1
            A('### 第%03d問 rec%d（%d×%d）' % (n, n, W, H))
            A('```')
            lines.extend(rows)
            A('```')
            A('')
    A('> 全 %d 关。' % len(levels))
    with open(OUT, 'w', encoding='utf-8') as fp:
        fp.write('\n'.join(lines) + '\n')
    print('wrote %s, %d lines' % (OUT, len(lines)))


if __name__ == '__main__':
    main()
