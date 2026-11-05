#!/usr/bin/env bash
# 安装仓库的 git 钩子。运行一次即可让 pre-commit 防护生效。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOKS="$ROOT/.git/hooks"

mkdir -p "$HOOKS"
cp "$ROOT/tools/pre-commit-block-media" "$HOOKS/pre-commit"
chmod +x "$HOOKS/pre-commit"

echo "✅ 已安装 pre-commit 钩子 -> $HOOKS/pre-commit"
echo "   现在任何提交里的视频/超大文件都会被自动拦截。"
