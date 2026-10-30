#!/bin/bash
# 把当前 DeSmuME 电池存档快照提交并推送到远端（task#16：定期推送存档）。
#
# 用法： bash push_save.sh "<提交说明>"
#
# 机制（2026-10-13 实测）：DeSmuME 在游戏每次「セーブ中です…」时就把 SRAM
# 落盘到 ~/.config/desmume/game.dsv，故无需杀进程，随时可复制推送。
# 为稳妥，复制前仍做一次 SIGTERM 探针可选（默认不杀，见 KEEP_RUNNING）。
#
# 安全：push token 仅通过 -c url.<..>.insteadOf 注入到**单条 push 命令**，
#       不写入 .git/config；推送后 grep 校验无残留。
set +e
MSG="${1:-存档快照}"
cd /workspace/Kanji || exit 99
TOKEN="gPmq2ykSPsoMLExZ_GB-afLU"

SAVE_SRC="$HOME/.config/desmume/game.dsv"
mkdir -p saves
if [ ! -f "$SAVE_SRC" ]; then
  echo "⚠️ 找不到存档 $SAVE_SRC"; exit 1
fi
cp -f "$SAVE_SRC" saves/game.dsv
echo "存档 md5: $(md5sum saves/game.dsv | cut -d' ' -f1)  size=$(stat -c%s saves/game.dsv)"

git add saves/game.dsv validation/
if git diff --cached --quiet; then
  echo "（存档无变化，跳过提交）"
else
  git -c user.name='Barry_Wu_' -c user.email='barry@local' commit -m "$MSG"
fi

echo "=== push ==="
git -c url."https://Barry_Wu_:${TOKEN}@gitcode.com/".insteadOf="https://gitcode.com/" \
    push origin main 2>&1 | tail -5

echo "=== token 残留校验（应输出 0） ==="
grep -c "${TOKEN}" .git/config 2>/dev/null || echo 0
