# ARM7 驱动逆向进度（2026-10-23 晚）

## 环境与文件
- ROM: /home/z/my-project/boom_ball/downloads/kanji.nds
- **ARM7 = ROM offset 0x5B200, size 0x289C0 (166KB), VMA 0x2380000**（注意 header 布局：0x20/24/28/2C=ARM9 off/entry/load/size；0x30/34/38/3C=ARM7）
- /tmp/arm7.bin 已提取；capstone 5.0.7 可用；ARM 主体 = ARM 模式，部分 Thumb
- /tmp/SSEQPlayer = kode54 版（已打 codecvt 补丁），main_render.cpp 离线渲染已跑通

## 已确证（源码级）
- 0x7330 = SND_SetTimer(ch, timer, fmt)：strh [0x04000400 + ch*16]（timer+fmt 高8位）；调用者 0x8910（命令应用）/0xaf40
- 0x87b4 = 命令分发器：每声道 0x54 字节结构，[+0x24]=timer, [+0x26]=pan/vol 包, [+0x39]=格式
- 0x9a4c = sound-tick IRQ 核心：release 计数 [player+0x1c] >= 0xF0 时减 0xF0；tempoCount [player+0x18]=tempo(0x78)、[+0x1A]=rate(0x100)、[+0x1C]=count(初值 0xF0)
- 0x8b08 = 每音轨 tick → 0x8b88 = SSEQ 解释器主循环（0x9f28 取字节，0xA2/0xA1/0xA0 特殊操作码）
- 0x9bb8 区域 = player 初始化（tempo=0x78, rate=0x100, count=0xF0, ch 表清 0xFF）
- GetPitchTable SWI 包装在 0xc708，**无人调用** → 驱动不用 BIOS pitch 表（音高计算另行）
- 无 0x040004xx 字面量：寄存器地址 = 0x04000000 + add #0x400 + ch<<4 运行时算出
- 无硬编码 tick reload 值（运行时计算）；实证 96Hz sound tick（scale 1.0）
- 0xffb8 附近 = __aeabi_uidiv 类库函数；0x10040+ = literal pool（0x1000000/0x400000/0x20000/0x80000）

## 10-24 破案：ADPCM nibble 顺序反了（重大修复）
- 能量占比测量发现渲染 <300Hz 占 96%（实录 60%），细分出 DC-10Hz 占 71% → 逐层定位到波形本身
- **根因：adpcm_decode 高半字节在前是错的**。NDS ADPCM 低半字节先行（GBATEK/melonDS 双证）
  + 表索引须 mask 0x3F（bits6-7=predictor）。已修入渲染器
- 证据：27/40 波形 DC 异常 → 修复后 2/40；wave14 DC/峰 0.152→0.010
- 教训：旧 0.782 相似度被 DC 吹高（渲染 RMS 0.144 中 DC 0.108，音乐 AC 只占 65%）；修复后分数
  降为 0.746/0.752 属预期——旧度量被 DC 污染，新旧分数不可直接比，**听感为最终裁决**
- 注意 loop 波形 data 尾部含循环头未处理（次要，后续可修）
- 交付：BGM07_修复版/修复前.ogg（q6）供耳朵 A/B

## 10-24 包络/编解码/混叠三连否
- **指数包络**（decay/release 平方律，RENDER_ADR=exp）：0.782/0.785，与线性持平 → 包络形状非差异源
- **编解码天花板排除**：渲染→mp3@192k 对比 mp3 录音，分数与 wav 版完全一致（0.782/0.785）→ 差距真实
- **分频段分解**（关键定位）：低频<300Hz 0.877 / 300-1k 0.874 / 1k-3k 0.721 / 3k-8k 0.606 / **>8k 0.491**
  → 差异集中在高频，低中频已接近实录
- **抗混叠滤波**（pitch-up Nyquist 低通，RENDER_LP=1）：首版只切超声段，无效果；且注意——
  高频带相似度对瞬时对齐/微小时移极敏感，0.49 可能部分是度量伪影，听感需耳朵裁决
- **下一步方向**：① 让用户耳朵裁决当前 pan 修正版是否更接近 ② 若要继续量化，
  先做对齐谱音分+高频能量比测量再下结论（防度量伪影）③ DeSmuME SPU 链路（32768→44100 重采样器）对照

## 10-23 深夜渲染试验结果
- **NN 无插值假设被否**：RENDER_INTERP=nn RENDER_SR=32768 版 vs 实录 0.763/0.768，
  低于 Hermite44k 的 0.782/0.785（DeSmuME 录音端自带插值平滑，硬件 sample-hold 反而更糙）
- **Pan 硬件律已修入渲染器**：旧公式（±0.7 线性衰减，硬边 30% 串音+2×增益不一致）→
  gl=(128-P)/64·g, gr=P/64·g（melonDS/驱动双证）。单声道度量下分数持平（度量对 pan 不敏感），属正确性修正
- 渲染器新增开关：RENDER_INTERP=nn|hermite、RENDER_SR、RENDER_OUT
- 下一步：包络定点区（0x23000-0x23700）attack/decay 曲线；音量 IWRAM 表公式反推

## 10-23 晚二轮（「继续」轮）新发现
- **NoteOn key 路径**（0x8d5c-0x8d80）：key = SSEQ key + 轨道移调 [sb+0x13]，clamp 0..127 → bl 0x9554（NoteOn setup）
- **timer 公式埋在运行时 SDK 层**：0x9554 → 0xa714（程序/波形解析）→ 更深，无静态常数；
  硬件语义（FSS/melonDS 一致）：播放率 = 2.0946MHz/(65536−TimerReload)，pitch 换算走 ×(表+0x10000)>>16
- **音量表 = 运行时生成**：0x7730 veneer 指向 IWRAM 0x0380455C（0x7738 字面量），静态 dump 不到；
  桶结构（60/120/240 边界 + ×16/×8/×4/×1）保证增益连续 → 音量链≈线性，非主要听感差异源
- **头号听感嫌疑改为：硬件无插值（sample-hold）**——我们的 Hermite 对 8/16kHz 波形会明显"更亮/更滑"，
  与实录（模拟器输出）的音色差异吻合；下一步渲染试验：最近邻 + 32768Hz 输出

## 待挖（按听感影响排序）
1. **NoteOn timer（音高）计算**：写入点 [ch+0x24]：0x7ccc / 0x856c / 0x8698 / 0x86fc（interpreter 内），
   timer 值经 [sp+4]/[sp+8]/[sp+c] 由上游算出——还没追到公式源头
2. **音量表 dump**：0x76b8=音量桶转换：|amp|≥240→sel3、≥120→sel2、≥60→sel1、否则 sel0；
   0x7730 = veneer（ldr ip,[pc]; bx ip，真表址在 0x7738 字面量）→ 0x76e0 处 ldr=[pc,#0x4c]→字面量在 0x772c。
   **上一轮读表基址读错了（0x2d3 是代码）**：需按 veneer 链重追真实表地址再 dump
3. tick timer reload 运行时计算（写 0x04000104 处）
4. 包络 step：0x23000-0x23700 ARM 定点区（×16 = ror#28），release=0x1E00/(126-r) 已定

## 已确证：硬件混音精确语义（melonDS 源码 + 驱动 RE 双证）
- SNDxCNT（0x04000400+ch*16，0x7330 写它，**不是 timer**！）：
  - bits0-6 Volume：7-bit，**127 会 ++ 成 128**（drv/melonds 一致）
  - bits8-9 VolumeShift select：硬件 shift 表 = **{sel0→<<4, sel1→<<3, sel2→<<2, sel3→<<0}**
    （melonDS volshift[4]={4,3,2,0}，val<<=shift × Volume）
  - 驱动 0x76b8 选桶：|amp|≥240→sel3(×1)、≥120→sel2(×4)、≥60→sel1(×8)、else sel0(×16)，
    表值与 shift 配合还原 11-bit 振幅 → 7-bit 量化有阶梯
- Pan：**out_L = in×(128-Pan)>>10, out_R = in×Pan>>10**（注意 128 不是 127！Pan 0-127，127→128）
- MasterVolume：out×MV>>7；混音求和后饱和到 16bit
- 硬件插值（无声卡插值）：melonDS 可选 none/linear/cubic/gauss；用户实录为 DeSmuMe（其默认?）

## 反汇编工具
- /tmp/arsmdis.py START END [thumb]：ARM7 反汇编小工具
- ARM halfword STRH/LDRH 立即数编码：imm = ((w>>8)&0xF)<<4 | (w&0xF)（bit7-4=1011 是 opcode 部分，不是 imm！）

## 结构速记
- ch 结构 stride=0x54；[+3]=flags(bit0=active,bit1=vol dirty,bit2-6=fmt/pan区)、[+0x22]=fmt、
  [+0x24]=timer、[+0x26]=vol/pan 包、[+0x39]=格式2、[+0x3c]=TimerReload初值、[+0x48]=hook fn
- player：[+0x18]=tempo(0x78)、[+0x1A]=rate(0x100)、[+0x1C]=tempoCount(0xF0)；阈值 240
- 解释器：0x8b88-0x9544；取字节 0x9f28；参数读取 0x9d70（4类操作数）；varlen 0x9ed8

## 方法教训
- 反汇编前先确认模式：ARM 区段用 CS_MODE_ARM，偶有 Thumb；函数头=push {..,lr} (E92D..40)
- literal pool 会打断线性反汇编（bl 目标越界=碰到 pool/数据，跳过即可）
- ROM header 别读错：0x30/34/38/3C 才是 ARM7（第一次误取了 ARM9）
- bash heredoc 用 `python3 /dev/stdin << 'EOF'` 更稳；veneer（ldr ip,[pc];bx ip）会骗 literal 追踪

## 10-24 配对更正（用户澄清）
- rec_menu 对应 SEQ_BGM00（此前误用 BGM07，跨曲对比分数作废）；BGM00 修复版已交付耳朵验证

## 10-24 gate 拉长 bug（耳朵反馈：旋律节奏偏慢，鼓点对）
- 根因：gate/total_len = dur*SR/factor——输出样本数除以重采样因子，低采样率旋律波(8k) gate 放大 5.5 倍级，
  音符压过休止糊掉；鼓组因短包络不受影响 → 完美解释"鼓对旋律慢"
- 已修为 dur*SR；修复版已交付，待耳朵裁决

## 10-24 gate 单位破案（RE 驱动源码）
- 用户反馈旋律节奏仍不对 → 停止猜测，反汇编驱动：0x8ba4 循环遍历 voice 链([+0x50])，
  递减 [voice+0x34] = **note gate 按 sound tick(96Hz) 计数**；rest 按 seq tick(48Hz)。
  渲染器此前 gate=ticks/48 → 音符长 2 倍 → 旋律糊。鼓组一次性波形包络自衰减不受影响（与耳朵反馈吻合）
- Call(0x95) 无重复参数、0xD4 才带 count（BGM00 未用）；Call/Return/Jump 语义与解析器一致；
  全轨 poly(bit1=0) notes 不推进游标 ✓；RawData=0xFF 结尾标记无害
- gate96 版已交付耳朵裁决；低音周期度量(实录1.138/渲染0.755→0.499)对断音敏感不可靠

## 10-24 晚 FD 破案（旋律节奏真根因）
- SDAT 原始字节流解码（绕开 ndspy eventsData 重编码）：旋律短语 N62g11 R96 N60g11 R36 N60g11 R36 N62g11 R24 FD
- **0xFD = 返回并跳过调用者的 R192**（短语链式衔接，间隔仅 R24）；ndspy 把 Call 内联展开时
  合并成 R216（4.5s 空洞）→ 实录旋律无 >2.3s 间隔、周期4s vs 渲染8s → "节奏偏慢"真身
- R216×11 仅 track4/5 短语 joints ✓ 零误伤；已修 R216→24；gate 单位复核 = seq tick(48Hz)
  （RE 0x8bc4: [voice+0x14] 每解释器调用+1 vs gate[voice+0x18]，解释器每 seq tick 跑一次 RE 0x9a4c）
- 驱动细节：Tempo=0xE1 写 player+0x18；rate=player+0x1A(0x100)；seq tick=sound tick×tempo/240
- 已交付 FD 修复版耳朵裁决

## 10-25 凌晨 全局节拍破案（耳朵:间隔不对+错误音符）
- R216→24 hack 回滚（track4 raw 证实 R216=[80 81 58] 真实存在）
- **真根因: seq tick = 96Hz 非 48Hz**（sound tick=192Hz；旧"96Hz sound tick"系循环验证错误）
- 决定性证据: 实录全部 gap 无一漏网地对上 rest×1/96s: R216→2.25✓ R96→1.0✓ R120→1.25✓
  R36+R36→0.75✓ R192→2.0✓ R168→1.75✓（48Hz 时 R216=4.5s 无中生有）
- 副产品: "错误音符" = 节拍错位后 track1(CALL结构,R192洞) 与 track4/5(literal) 相位分裂互相打架
- 渲染器: SND_TICK=1/192, TICK_SCALE=0.5 全局应用(rest/gate/mono onset)
- 验证: 渲染 vs 实录旋律带 onset 匹配 18/29 @0.1s 容差

## 10-25 音色微差定位（rec_BGM00 独立验证；当时文件名 rec_puzzle）
- rec_BGM00≈BGM00重头(用户澄清)，与96Hz渲染 onset 匹配 28/43@0.1s（独立第二实录验证 ✓）
- 注（10-26）：该录音已改名 `rec_BGM00.mp3` 并裁掉开头 1.315s 菜单音效，音乐本体自 1.320s 起
- 混音响度比(旋律/低音) 实录0.257 vs 渲染0.271 → 音量链无需改
- 八段频谱: 40Hz-4kHz 全部 ±1.1dB ✓✓；唯一差异 4k-8k/-5.5dB、8k-11k/-12.5dB（Hermite 太钝）
- 插值三连测: NN44k +3.2/+7.4 过冲 | linear44k -5.6/-7.6 | NN32k +3.5/+7.7 过冲 → 真值居中
- 渲染器新增 INTERP=linear；NN32k 与 linear 两版交付耳朵裁决（硬件真值=sample-hold@32768+
  DeSmuME重采样链，精确模拟其输出滤波器是后续课题）

## 10-25 鼓循环头破案（耳朵: 鼓点轻重缺失）
- track2/3 力度字节全 0x7F 均匀 → 轻重不在事件层；鼓 = wave2/3 循环采样连打(gate383+R3)，
  **轻重轮廓烤在采样里**，而 ADPCM 解码器不处理循环点状态头（loopOff=1 处 4B 预测器重置头被当样本解）
- 修复: adpcm_decode(data, loop_off) 到循环字节位读 4B 头重置 sample/table；受影响 wave1/2/3
- 频段: 鼓110-250 -1.2→+1.1dB；低音 +0.9→+2.8dB（wave1 循环修复连动，待耳朵裁决）

## 10-26 鼓循环头修复未遂（回滚）
- 用户裁决: 上一版循环头修复后鼓变成"调子变低的波形" → 回滚到 216b8bc(鼓正常/无轻重)
- 字节级验证: 鼓循环波 [80 81 58]=R216 真实; loopOff/totalLength 语义未解: wave1 数据 840B=1680样本
  vs totalLength=211、wave2 8000B=16000样本 vs totalLength=2001 —— **数据量恰为 totalLength×8**，
  循环字段单位(样本/字节/×8)与循环头位置均未定，需 SWAR ADPCM 规范精读后再动
- 现状: 鼓声正常但无轻重(轻重烤在采样循环体内，循环窗错位=轻重毁)
