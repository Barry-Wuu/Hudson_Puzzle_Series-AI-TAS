# 入門（mode1）· 逐关通关证据

规格：DeSmuME 原生双屏截图 256×384，P 模式调色板 PNG。
  上屏：完成盘面（6×6 环路）+ 入門 第 NNN 問 + TIME；
  下屏：题面 + 橙黄色 "Completion!!!" 通关字样。

来源：本地实机录像 /workspace/vol5_recordings/数回_入門_第01~20問.mp4（原生 256×384@30fps）。

证据文件：l001_clear.png ~ l020_clear.png（编号 = 关内题号，与 Vol.11 约定一致）。
  每关取「下屏刚显示 Completion 大字、上屏已画出完整答案环」的第一帧。

抽取方法：4fps 流式抽帧 + Completion 艺术字模板匹配，取匹配峰分 90% 的首帧。
  字样跨尺寸为统一 UI（下屏 x≈30,y≈262），模板匹配对入門/10x10/18x10/24x14/36x20 全尺寸通用。
  逐关峰分 0.70~0.94，均远高于误报阈值 0.5，0 失败。

产出：2026-11-17，ai-tas 自动抽取（脚本 /tmp/extract_v5_validation.py，日志见 validation/_extract_log.csv）。
