# CLAUDE.md

## このリポジトリ

公開情報の更新を自動的に検出し、変更された箇所を分かりやすく提示する仕組みの試作(PoC)。
概要は [README.md](README.md)。技術選定は ADR に残す(`docs/adr/`。まだ1件も無い)。

## 構成とコマンド

- 実装の言語・構成は未定。決めたら ADR を書き、ここにパッケージ構成とコマンドを足す
- Node.js は lefthook / commitlint のために使っている(`package.json`)。実装に別の言語を使う場合も残す
- CI の `repo-checks` は現在、ADR 書式・PR タイトル・ブランチ名だけを検査する。
  実装を始めたら型検査・lint・テストなどを `.github/workflows/ci.yml` に足す

## 開発規約

- ブランチ・コミット・PR の規約は [CONTRIBUTING.md](CONTRIBUTING.md)。lefthook と commitlint で機械的に強制される
- ADR は `docs/adr/`(`managing-adrs` スキル)。要件・設計ドキュメントは `managing-notion-docs` スキル
- Notion(`ntn`)の認証と権限制御は `managing-notion-docs` スキルの「前提条件」。`NOTION_API_TOKEN`(最小権限の内部インテグレーション)を使い、`ntn login` / `ntn auth` は使わない
- CI は `.github/workflows/ci.yml`(ADR 書式・PR タイトル・ブランチ名)
- 巡回の対象サイトには、利用規約・robots.txt に従い、アクセス間隔を空けて取得する。
  試作中の取得は少数の対象に限り、短い間隔で繰り返し叩かない

## Dev container

- `.devcontainer/` に定義。ベースは言語非依存の Debian イメージで、Node.js(lefthook/commitlint 用)と `gh`・`ntn` を含む。
  他の言語は `devcontainer.json` の `features` に追加する
- Claude Code の sandbox(bubblewrap)は使わない。ホストのカーネル設定
  (Ubuntu 系の `kernel.apparmor_restrict_unprivileged_userns=1`)次第で動かず、各自のホスト設定に頼れないため。
  代わりにコンテナ全体の外向き通信を `.devcontainer/init-firewall.sh`(iptables + ipset)で許可ドメインだけに絞る
- ネットワークの許可ドメインは `init-firewall.sh` の `ALLOWED_DOMAINS`(言語の依存取得先が増えたらここに足し、rebuild する)。
  スクリプトはイメージに焼き込むため、コンテナ内でリポジトリのファイルを書き換えても反映されない
- **巡回対象のサイトもファイアウォールで遮断される。** コンテナ内から取得を試すときは、対象のドメインを
  `ALLOWED_DOMAINS` の「巡回対象の Web サイト」に1つずつ足して rebuild する。全許可にはしない
  (エージェントの外向き通信を絞るというセキュリティの前提が崩れるため)。
  名前解決は起動時の1回だけなので、CDN 配下で IP が変わるサイトは繋がらなくなることがある(再起動で直る)
- Claude Code の devcontainer feature(`ghcr.io/anthropics/devcontainer-features/claude-code`)は使わない。
  独自の `init-firewall.sh` を `/usr/local/bin` に上書きコピーし、自前のファイアウォールを置き換えてしまうため。
  Claude Code は `postCreateCommand` で `npm install -g` する
- コンテナ内の `vscode` ユーザーの sudo は `init-firewall.sh`だけに限定している(ファイアウォールを外せないようにするため)。
  コンテナ内で `apt install` などはできないので、必要なものは `Dockerfile` か `features` に足す
- 機密(`.ssh`, `.aws`, `.credentials*`, `secrets/`)は permissions で読み取りを拒否している。
  `.env` はエージェントが読める(編集は拒否、git 管理外)。
  **運用ルール: `.env` にはエージェント向けの認証情報(`NOTION_API_TOKEN`)だけを書く。人間用・本番用の資格情報は置かない**。
  これがセキュリティの前提。`.env` が無いと起動に失敗するため、`initializeCommand` で空ファイルを作る
