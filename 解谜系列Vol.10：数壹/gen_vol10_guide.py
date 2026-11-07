#!/usr/bin/env python3
import unicodedata
"""把 /tmp/vol10_all.json 渲染成 Vol.10 数壹 答案.md（①=未涂，❶=涂黑）。"""
import json

DIFF = {0: '入門', 1: 'やさしい', 2: 'ふつう', 3: 'むずかしい'}


def circled(n):
    """未涂色：带圈数字 ①..⑳"""
    return chr(0x2460 + n - 1)


def filled(n):
    """涂黑：负片带圈数字 ❶..❿（U+2776..）、⓫..⓴（U+24EB..）"""
    if n <= 10:
        return chr(0x2776 + n - 1)
    return chr(0x24EA + (n - 10))


def dwidth(s):
    """显示宽度：全角/宽字符按 2 计。"""
    return sum(2 if unicodedata.east_asian_width(c) in 'WF' else 1 for c in s)


def pad(s, width, gap=3):
    return s + ' ' * max(0, width - dwidth(s) + gap)


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


def compact(recs):
    """每关压成一行：关号 + 用 | 切开的各行，一屏看完。"""
    out = []
    for rec in recs:
        w, h, sol = rec['w'], rec['h'], rec['M']
        rows = [''.join((filled if sol[r][c] else circled)(rec['G'][r][c])
                        for c in range(w)) for r in range(h)]
        out.append(f"{rec['idx']:03d} " + '|'.join(rows))
    return out


def main():
    data = json.load(open('/tmp/vol10_all.json'))
    by = {}
    for rec in data:
        by.setdefault(rec['diff'], []).append(rec)

    L = []
    L.append('# 《解谜系列Vol.10：ひとりにしてくれ／数壹（Hitori）》全关卡答案（官方答案盘面）')
    L.append('')
    L.append('> 📌 **阅读提示**：每关盘面都放在**代码块**里，网页与手机端预览都会按等宽字体渲染，行列对齐、无需切换「源码模式」。')
    L.append('>')
    L.append('> 说明：数壹（ひとりにしてくれ／Hitori）的规则是——把盘面中**一部分数字涂黑**，要求：① 涂黑的格子**不能上下左右相邻**；② 每一行、每一列中，**未涂黑**的数字**不得重复**；③ 所有**未涂黑**的格子必须**连成一片**。')
    L.append('>')
    L.append('> 以下盘面即**官方答案**——数字原样保留，涂黑位置用**实心（负片）带圈数字**标出。')
    L.append('>')
    L.append('> 图例：**`①`~`⑳`** = 未涂色的数字；**`❶`~`❿`、`⓫`~`⓴`** = 需要**涂黑**的数字（负片带圈数字，字号与正片一致）。两种字符在代码块内均为单宽、逐格对齐。')
    L.append('>')
    L.append('> 题目顺序即 ROM 内关卡表顺序：入門（6×6，20 关）→ やさしい（8×8，100 关）→ ふつう（8×8／12×12，100 关）→ むずかしい（12×12／17×17，80 关），合计 300 关。')
    L.append('')
    for diff in (0, 1, 2, 3):
        recs = by[diff]
        segs = split_by_size(recs, lambda r: '%d×%d' % (r['w'], r['h']))
        for si, (size, seg) in enumerate(segs):
            L.append(f'## {DIFF[diff]} · {size}（{len(seg)} 关）')
            L.append('')
            if diff == 0 and si == 0:
                L.append('> 🗺️ **速览**：入門 20 关压成 20 行，一屏看完。每行 = 一关，`|` 切开即为自上而下的 6 行，每组 6 格即一行。')
                L.append('')
                L.append('```')
                L.extend(compact(recs))
                L.append('```')
                L.append('')
                L.append('> 下面是逐关单列版，供手机上放大查看。')
                L.append('')
            for rec in seg:
                w, h, sol = rec['w'], rec['h'], rec['M']
                L.append(f"### 第{rec['idx']:03d}問（{w}×{h}）")
                L.append('```')
                for r in range(h):
                    line = ''.join((filled if sol[r][c] else circled)(rec['G'][r][c])
                                   for c in range(w))
                    L.append(line)
                L.append('```')
                L.append('')
        L.append('---')
        L.append('')
    out = '/workspace/hudson_tas/解谜系列Vol.10：数壹/答案.md'
    open(out, 'w').write('\n'.join(L).rstrip() + '\n')
    print('written', out, len(L), 'lines')


if __name__ == '__main__':
    main()
