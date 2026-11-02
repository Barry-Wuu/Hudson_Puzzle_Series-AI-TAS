#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把游戏从任意状态带回选关页。"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ds
import play_akari_seg2 as P

for i in range(6):
    if P.in_select_page():
        print("已在选关页")
        break
    P.escape_to_select()
    time.sleep(0.5)
else:
    print("回选关页失败")
    sys.exit(1)
print("in_select_page =", P.in_select_page())
