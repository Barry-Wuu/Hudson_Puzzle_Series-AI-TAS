#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""⛔ **结论已作废的工具**（保留作诊断参考）——曾用于验证「新存档题序重排」假设。

→ PITFALLS §S60.5.1：**「新档题库重排」是误判**。盘面直接核对已证 `futsuu No.N = rec(54+N)`
  本来就是对的（No.01 最大编号 73 = rec55.nbadge；No.04 = 62 = rec58.nbadge）；
  初次录制 ふつう No.04–07 连续 FAIL 的真因是 **0.02 档偶发掉一个输入**（§S57.7 同源），
  单关重跑与 `--from 1 --to 10` 连打均 10/10 PASS。
→ 本脚本对**大盘**（ふつう 级）的 `IK.identify` 会失准（几何一致但可见行数 9 vs 10，
  报「差 19–37」），**其输出的 L→rec 映射不要采信**。

原始用途（历史）：逐关进盘 → 盘面形状识别 → 输出 L→rec 映射。

用法：
  python3 identify_map.py --diff futsuu --from 1 --to 6
"""
import os, sys, time, json, argparse
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, HERE); sys.path.insert(0, ROOT)
os.environ.setdefault('AI_TAS_DISPLAY', ':0')
os.environ.setdefault('DISPLAY', ':0')
for _k, _v in dict(AI_TAS_TAP_HOLD='0.02', AI_TAS_MOVE_GAP='0.02', AI_TAS_TAP_AFTER='0.02',
                   AI_TAS_ARROW_AFTER='0.02', AI_TAS_KANJI_AFTER='0.02', AI_TAS_FILL_WAIT='0.02',
                   AI_TAS_HOP_AFTER='0.03', AI_TAS_BREATHE_EVERY='0', AI_TAS_PANEL_WAIT='0.6',
                   AI_TAS_SEIKAI_WAIT='0.1', AI_TAS_NAV_AFTER='1.5', AI_TAS_NAV_ENTER_WAIT='5.0').items():
    os.environ.setdefault(_k, _v)

import kanji_common as KC          # noqa: E402
import run as R                    # noqa: E402
import identify_kentei_board as IK # noqa: E402

ALL_RECS = None          # 延迟构建：只留可解 rec（solve2.solve 返回 None 的跳过）


def solvable_recs():
    global ALL_RECS
    if ALL_RECS is None:
        import solve2
        ok = []
        for r in range(300):
            try:
                if solve2.solve(r) is not None:
                    ok.append(r)
            except Exception:
                pass
        ALL_RECS = ok
        print('[识别] 可解 rec 共 %d 个' % len(ALL_RECS), flush=True)
    return ALL_RECS


def exit_board():
    """盘内退出：🔧(33,167) → Left×2(問題選択高亮) → A(弹确认,默认いいえ) → Left(はい) → A。"""
    KC.tap(33, 167, after=1.2)              # 🔧 オプション面板（再開する默认高亮）
    for _ in range(2):
        KC.key_press('Left', hold=0.08, after=0.4)
    KC.key_press('x', hold=0.1, after=1.0)  # A → 确认弹窗（いいえ 高亮）
    KC.key_press('Left', hold=0.08, after=0.4)
    KC.key_press('x', hold=0.1, after=1.5)  # はい → 回选关页
    time.sleep(0.8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--diff', required=True)
    ap.add_argument('--from', dest='frm', type=int, required=True)
    ap.add_argument('--to', type=int, required=True)
    ap.add_argument('--out', default=None)
    args = ap.parse_args()
    diff = args.diff

    R.goto_select(1, diff)
    mapping = {}
    for L in range(args.frm, args.to + 1):
        scrolled = bool(R.MODES[1]['scroll'] and L > 50)
        if scrolled:
            R._scroll_grid(diff)
        x, y = R._cell_xy(1, diff, L, scrolled)
        if not R.enter_board(1, x, y):
            print('[识别] No.%02d 进盘失败，跳过' % L, flush=True)
            mapping[str(L)] = None
            continue
        KC.wait_banner_gone(timeout=8.0)
        time.sleep(0.8)
        p = R._shot('imap_%s_%02d.png' % (diff, L))
        IK.RECS = solvable_recs()
        try:
            _m, _geo, scores = IK.identify(p)
        except Exception as e:
            print('[识别] No.%02d 识别异常：%s' % (L, e), flush=True)
            scores = []
        best = scores[0] if scores else None
        second = scores[1] if len(scores) > 1 else None
        rec = best[1] if best and best[0] <= 8 else None
        mapping[str(L)] = dict(rec=rec, diff=best[0] if best else None,
                               second='%s(%d)' % (second[1], second[0]) if second else None)
        print('[识别] %s No.%02d -> rec%s (差%s；次名 %s)' %
              (diff, L, rec, best[0] if best else '?', second), flush=True)
        exit_board()
        # 确认回选关页
        chk = R._shot('imap_back_%02d.png' % L)
        if not R._on_select(1, chk):
            print('[识别] ⚠️ 未回选关页，重导航', flush=True)
            R.goto_select(1, diff, warm=False)
    if args.out:
        json.dump(mapping, open(args.out, 'w'), ensure_ascii=False, indent=1)
        print('映射已存 ->', args.out, flush=True)
    print('=== 映射摘要 ===')
    for L in range(args.frm, args.to + 1):
        v = mapping.get(str(L))
        print('  No.%02d -> rec%s (差%s)' % (L, v['rec'] if v else '?',
                                            v['diff'] if v else '?'), flush=True)


if __name__ == '__main__':
    sys.exit(main())
