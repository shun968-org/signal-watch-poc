#!/usr/bin/env bash
#
# git の user.name・user.email が未設定なら、gh でログインしている GitHub アカウントから設定する。
# devcontainer.json の postCreateCommand から呼ばれる(単体でも実行できる)。
#
# rebuild すると ~/.gitconfig が作り直され、VS Code がホストの設定をコピーしないことがあるため。
# 特定の人の名前・アドレスをリポジトリに書かないよう、ログイン中のアカウントから組み立てる。
#   user.name  = GitHub のログイン名
#   user.email = <ID>+<ログイン名>@users.noreply.github.com(GitHub の noreply アドレス)

set -euo pipefail

if git config --global user.email >/dev/null; then
  exit 0
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "gh にログインしていないため、git の user.name・user.email を設定しません。" >&2
  echo "gh auth login の後に .devcontainer/setup-git-identity.sh を実行してください。" >&2
  exit 0
fi

read -r login id < <(gh api user --jq '"\(.login) \(.id)"')
git config --global user.name "$login"
git config --global user.email "${id}+${login}@users.noreply.github.com"
echo "git の user.name・user.email を設定しました: $login <${id}+${login}@users.noreply.github.com>"
