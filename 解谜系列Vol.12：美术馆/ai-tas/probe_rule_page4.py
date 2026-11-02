#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探针 4：规则页（绿标题栏）翻页到结束，看最终落到哪。"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ds
import play_akari_seg2 as P

GREEN = (65, 90, 57)


def is_rule_page(im=None):
    """上屏顶部 y=0..26, x=215..256 绿底 ⇒ 规则页。"""
    if im is None:
        im = ds.grab("")
    a = np.asarray(im.convert("RGB")).astype(int)
    reg = a[0:26, 215:256]
    g = ((np.abs(reg[:, :, 0] - 65) < 25) & (np.abs(reg[:, :, 1] - 90) < 25)
         & (np.abs(reg[:, :, 2] - 57) < 25)).sum()
    return int(g) > 250


def main():
    for i in range(12):
        im = ds.grab("")
        r = is_rule_page(im)
        s = P.in_select_page(im)
        print(f"  iter{i}: rule_page={r} select_page={s}")
        if not r:
            break
        ds.press("x", wait=1.0)
    ds.grab("rule_end")
    print("end: rule_page=", is_rule_page(), " select=", P.in_select_page())


main()
