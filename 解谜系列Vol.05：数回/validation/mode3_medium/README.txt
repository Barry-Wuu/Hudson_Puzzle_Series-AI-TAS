# ふつう（mode3）· 逐关通关证据

规格：DeSmuME 原生双屏截图 256×384，P 模式调色板 PNG。
  上屏：完成盘面（答案环）+ LEVEL 第 NNN 問 + TIME；
  下屏：题面 + 橙黄色 "Completion!!!" 通关字样。

来源（两段拼接，编号连续 1~100）：
  l001~l064：/workspace/vol5_recordings_futsuu_18x10/数回_ふつう18x10_第01~64問.mp4（18×10）
  l065~l100：/workspace/vol5_recordings_futsuu_24x14/数回_ふつう24x14_第65~100問.mp4（24×14）

证据文件：l001_clear.png ~ l100_clear.png（编号 = 关内题号，与 Vol.11 约定一致）。
  每关取「下屏刚显示 Completion 大字、上屏已画出完整答案环」的第一帧。

抽取方法：4fps 流式抽帧 + Completion 艺术字模板匹配，取匹配峰分 90% 的首帧。
  逐关峰分 0.70~0.81，0 失败。

产出：2026-11-17，ai-tas 自动抽取。
