#!/bin/sh
# 本仓库的 git 身份设置——不硬编码任何个人账号。
#
# 规则：
#   · user.name  固定为 WorkBuddy（本仓库所有自动化提交的署名）
#   · user.email 自动取「本机用户名@主机名」，换台机器跑就是那台机器的身份
#   · 需要覆盖时用环境变量：GIT_AUTHOR_NAME=xxx GIT_AUTHOR_EMAIL=yyy ./setup-git-identity.sh
set -e
name="${GIT_AUTHOR_NAME:-WorkBuddy}"
mailhost="$(hostname -s 2>/dev/null || hostname)"
email="${GIT_AUTHOR_EMAIL:-$(whoami)@"$mailhost"}"

git config user.name "$name"
git config user.email "$email"

echo "user.name  = $name"
echo "user.email = $email"
