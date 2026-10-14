# コントリビューションガイド

## ブランチ

`<type>/<issue番号>-<slug>`(type は feature/fix/docs/chore/refactor/test)。`main` への直接コミットは対象外。
例: `feature/3-fetch-target-pages`

lefthook の `pre-commit` で強制される。チェックアウトごとに一度 `npm install` を実行すること
(`prepare` スクリプトが `lefthook install` を呼ぶ。devcontainer 内では `postCreateCommand` で自動実行)。

## コミットメッセージ

[Conventional Commits](https://www.conventionalcommits.org/) に従い、**タイトルのみ**とする
(本文・フッターは付けない)。末尾に Issue 参照が必須。

例: `feat(watch): 変更箇所の抽出を追加 (#3)`

commitlint が lefthook の `commit-msg` フックで強制する。
エディタが開く `git commit` では、`prepare-commit-msg` フックが Claude(`claude` CLI があれば)による案を下書きに入れる。

## プルリクエスト

GitHub Flow に従う。長く残るブランチは `main` だけで、作業ブランチから PR で `main` へ直接マージする。
マージは squash merge だけにし、マージコミットを作らずに履歴を一直線に保つ(コミットメッセージは PR タイトル)。

この設定(squash merge のみ・`main` への PR 必須・CI 必須・強制 push 禁止・マージ後のブランチ削除)は
`scripts/setup-github-repo.sh` で GitHub に適用する。リポジトリの管理者が `gh auth login` してから実行する
(`--dry-run` で送る内容だけを確認できる)。

## Issue・ラベル・マイルストーン

作業は Issue(タスク / 不具合のテンプレート)から始め、その Issue 番号でブランチを切る。
ラベルとマイルストーンは `scripts/setup-github-repo.sh` が作る。

| ラベル | 付け方 | 使い道 |
|---|---|---|
| `type:*` | Issue はテンプレートの「種類」、PR はブランチ名から自動 | 作業の内訳 |
| `area:*` | PR は変更したファイルから自動。Issue は手で付ける | どこに作業・不具合が集中しているか |
| `priority:*` | 手で付ける(要件の必須 / 推奨 / 任意に対応) | 着手順 |
| `severity:*` | 不具合に手で付ける | 品質の状況 |
| `from:feedback` | 開発メンバー以外が作った Issue に自動 | 外部からの反応 |
| `eval:*` | 誤検知(`eval:false-positive`)・検出漏れ(`eval:missed`)の報告に手で付ける | PoC の評価(基本設計 F-09) |
| `status:blocked` | 手で付ける | 止まっている作業の把握 |

`area:*` は `ci`・`docs`・`watch`(巡回処理)・`config`(`targets.yaml`)。領域を足すときは `.github/labeler.yml` と `scripts/setup-github-repo.sh` の両方に足す。

Issue には開発の段階に合わせたマイルストーン(`1. 土台` 〜 `5. 検証`。暫定)を付ける。
段階ごとの進み具合は、マイルストーンの完了率で見る。

## ADR

アーキテクチャ(実装上の技術選定)の判断根拠は `docs/adr/` に記録する。書式は `managing-adrs` スキルと
`scripts/check-adr-format.sh`(pre-commit)が定める。
