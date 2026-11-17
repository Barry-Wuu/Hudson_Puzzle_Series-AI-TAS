# むずかしい（mode4）· 逐关通关证据

规格：DeSmuME 原生双屏截图 256×384，P 模式调色板 PNG。
  上屏：完成盘面（答案环）+ LEVEL 第 NNN 問 + TIME；
  下屏：题面 + 橙黄色 "Completion!!!" 通关字样。

来源（两段拼接，编号连续 1~50）：
  l001~l017：/workspace/vol5_recordings_muzukashii_24x14/数回_むずかしい24x14_第01~17問.mp4（24×14）
  l018~l050：/workspace/vol5_recordings_muzukashii_36x20/数回_むずかしい36x20_第18~50問.mp4（36×20）

证据文件：l001_clear.png ~ l050_clear.png（编号 = 关内题号，与 Vol.11 约定一致）。
  每关取「下屏刚显示 Completion 大字、上屏已画出完整答案环」的第一帧。

抽取方法：4fps 流式抽帧 + Completion 艺术字模板匹配，取匹配峰分 90% 的首帧。
  逐关峰分 0.79~0.88，0 失败。
  注：l035、l036 主目录录像（重录版）末尾停在「あと6か所」未完成态，改用
      /workspace/vol5_recordings_muzukashii_36x20_baseline_375s/ 的同关旧版完成录像抽取
      （峰分 0.858 / 0.788），上屏答案环与题解一致。

段位认定（無段→5級）不属主线关卡，无 Completion 画面，其全过程录像单独存于：
  /workspace/nintei_one/段位认定_实机全过程_無段到5級.mp4，未纳入本 validation。

产出：2026-11-17，ai-tas 自动抽取。
