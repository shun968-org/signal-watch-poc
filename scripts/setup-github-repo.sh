#!/usr/bin/env bash
#
# GitHub リポジトリのブランチ運用(GitHub Flow・履歴を一直線に保つ)と、
# プロジェクト管理用のラベル・マイルストーン、Discussions を設定する。
# 何度実行しても同じ状態になる。リポジトリの管理者権限で `gh auth login` 済みであること。
#
#   - デフォルトブランチを main にする
#   - マージ方法を squash merge だけにする(マージコミット・rebase merge は不可)
#     squash のコミットメッセージは PR タイトルだけにする(CONTRIBUTING.md のコミット規約に合わせる)
#   - マージ後に head ブランチを自動で消す
#   - Discussions を有効にする(感想・質問の受け口)
#   - main にルールセットを張る: PR 必須、履歴の一直線化、CI(repo-checks)の成功必須、
#     強制 push・削除の禁止
#   - ラベル(種類・領域・優先度・重大度・出どころ・状態)を作る/更新する。
#     GitHub の既定ラベルのうち、種類ラベルと重複するもの(bug など)は使われていなければ消す
#   - マイルストーン(開発の段階)を作る(既にあれば触らない)
#
# 使い方: scripts/setup-github-repo.sh [--dry-run] [owner/repo]
#   owner/repo を省略すると git の origin から求める。
#   --dry-run は GitHub を変更せず、送る内容を表示するだけ。

set -euo pipefail

DEFAULT_BRANCH="main"
RULESET_NAME="main"
REQUIRED_CHECKS=("repo-checks")   # .github/workflows/ci.yml のジョブ名

# 名前|色|説明。種類はブランチ名の type と揃える(.github/labeler.yml が PR に自動で付ける)
LABELS=(
  "type:feature|1d76db|機能の追加"
  "type:fix|d93f0b|不具合の修正"
  "type:bug|b60205|報告された不具合(未修正)"
  "type:docs|0075ca|ドキュメント"
  "type:chore|cfd3d7|設定・CI・依存の更新など"
  "type:refactor|5319e7|振る舞いを変えない改善"
  "type:test|0e8a16|テストの追加・修正"
  "area:ci|fbca04|CI・devcontainer・リポジトリ設定"
  "area:docs|fbca04|ADR・README などのドキュメント"
  "priority:high|b60205|必須の要件・すぐやる"
  "priority:medium|e99695|推奨の要件・この段階でやる"
  "priority:low|f9d0c4|任意の要件・余裕があればやる"
  "severity:critical|5a0000|不具合: 使えない・更新を見落とす・誤った差分を出す"
  "severity:major|a52a2a|不具合: 主要な機能の一部が使えない"
  "severity:minor|d4a5a5|不具合: 見た目・文言など"
  "from:feedback|c2e0c6|開発メンバー以外からの報告・要望(自動で付く)"
  "status:blocked|000000|他の作業や判断待ちで進められない"
)
# 種類ラベルと重複する既定ラベル。使われていなければ消す
OBSOLETE_LABELS=("bug" "documentation" "enhancement" "question")
# 開発の段階(暫定)。基本設計「移行・リリース計画」が決まったらそれに合わせる。
# 既にあるマイルストーンは触らないので、名前を変えたら GitHub 側の古いものは手で直す
MILESTONES=("1. 土台" "2. 巡回・取得" "3. 変更検出" "4. 提示" "5. 検証")

dry_run=false
repo=""
for arg in "$@"; do
  case "$arg" in
    --dry-run) dry_run=true ;;
    -*) echo "エラー: 不明なオプション '$arg'" >&2; exit 1 ;;
    *) repo="$arg" ;;
  esac
done

if [[ -z "$repo" ]]; then
  url="$(git remote get-url origin)"
  repo="$(echo "$url" | sed -E 's#^(https://github\.com/|git@github\.com:)##; s#\.git$##')"
fi
if [[ ! "$repo" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]; then
  echo "エラー: リポジトリ '$repo' を owner/repo の形で解釈できません。" >&2
  exit 1
fi

repo_settings="$(jq -n --arg branch "$DEFAULT_BRANCH" '{
  default_branch: $branch,
  allow_squash_merge: true,
  allow_merge_commit: false,
  allow_rebase_merge: false,
  squash_merge_commit_title: "PR_TITLE",
  squash_merge_commit_message: "BLANK",
  delete_branch_on_merge: true,
  allow_update_branch: true,
  has_discussions: true
}')"

checks_json="$(printf '%s\n' "${REQUIRED_CHECKS[@]}" | jq -R '{context: .}' | jq -s '.')"
ruleset="$(jq -n --arg name "$RULESET_NAME" --argjson checks "$checks_json" '{
  name: $name,
  target: "branch",
  enforcement: "active",
  conditions: { ref_name: { include: ["~DEFAULT_BRANCH"], exclude: [] } },
  rules: [
    { type: "deletion" },
    { type: "non_fast_forward" },
    { type: "required_linear_history" },
    { type: "pull_request", parameters: {
        required_approving_review_count: 0,
        dismiss_stale_reviews_on_push: false,
        require_code_owner_review: false,
        require_last_push_approval: false,
        required_review_thread_resolution: false,
        allowed_merge_methods: ["squash"]
    } },
    { type: "required_status_checks", parameters: {
        strict_required_status_checks_policy: false,
        required_status_checks: $checks
    } }
  ]
}')"

if $dry_run; then
  echo "== リポジトリ設定(PATCH repos/$repo) =="
  echo "$repo_settings"
  echo "== ルールセット '$RULESET_NAME'(repos/$repo/rulesets) =="
  echo "$ruleset"
  echo "== ラベル =="
  printf '%s\n' "${LABELS[@]}"
  echo "== 使われていなければ消す既定ラベル =="
  printf '%s\n' "${OBSOLETE_LABELS[@]}"
  echo "== マイルストーン =="
  printf '%s\n' "${MILESTONES[@]}"
  exit 0
fi

if ! gh api "repos/$repo/branches/$DEFAULT_BRANCH" --silent 2>/dev/null; then
  echo "エラー: $repo に $DEFAULT_BRANCH ブランチがありません。先に push してください。" >&2
  exit 1
fi

echo "リポジトリ設定を更新します: $repo"
echo "$repo_settings" | gh api -X PATCH "repos/$repo" --input - --silent

ruleset_id="$(gh api "repos/$repo/rulesets" --jq ".[] | select(.name == \"$RULESET_NAME\") | .id")"
if [[ -n "$ruleset_id" ]]; then
  echo "ルールセット '$RULESET_NAME' を更新します(id: $ruleset_id)"
  method=PUT
  endpoint="repos/$repo/rulesets/$ruleset_id"
else
  echo "ルールセット '$RULESET_NAME' を作成します"
  method=POST
  endpoint="repos/$repo/rulesets"
fi

if ! out="$(echo "$ruleset" | gh api -X "$method" "$endpoint" --input - 2>&1)"; then
  echo "エラー: ルールセットを設定できませんでした。" >&2
  echo "$out" >&2
  echo "非公開リポジトリでは、ルールセットに GitHub の有料プラン(Pro / Team 以上)が必要です。" >&2
  echo "リポジトリを公開するか、プランを確認してから再実行してください。" >&2
  exit 1
fi

echo "ラベルを作成・更新します"
for entry in "${LABELS[@]}"; do
  IFS='|' read -r name color description <<< "$entry"
  encoded="$(jq -rn --arg v "$name" '$v | @uri')"
  if gh api "repos/$repo/labels/$encoded" --silent 2>/dev/null; then
    gh api -X PATCH "repos/$repo/labels/$encoded" -f color="$color" -f description="$description" --silent
  else
    gh api -X POST "repos/$repo/labels" -f name="$name" -f color="$color" -f description="$description" --silent
  fi
done

for name in "${OBSOLETE_LABELS[@]}"; do
  encoded="$(jq -rn --arg v "$name" '$v | @uri')"
  gh api "repos/$repo/labels/$encoded" --silent 2>/dev/null || continue
  used="$(gh api "search/issues?q=$(jq -rn --arg q "repo:$repo label:\"$name\"" '$q | @uri')" --jq '.total_count')"
  if [[ "$used" == "0" ]]; then
    gh api -X DELETE "repos/$repo/labels/$encoded" --silent
    echo "  既定ラベル '$name' を消しました"
  else
    echo "  既定ラベル '$name' は ${used} 件で使われているので残します"
  fi
done

echo "マイルストーンを作成します(既にあるものは触らない)"
existing="$(gh api "repos/$repo/milestones?state=all&per_page=100" --jq '.[].title')"
for title in "${MILESTONES[@]}"; do
  if ! grep -qxF "$title" <<< "$existing"; then
    gh api -X POST "repos/$repo/milestones" -f title="$title" --silent
    echo "  '$title' を作りました"
  fi
done

echo "完了: ブランチ運用・Discussions・ラベル・マイルストーンを設定しました。"
