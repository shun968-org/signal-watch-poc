# CLAUDE.md

## このリポジトリ

公開情報の更新を自動的に検出し、変更された箇所を分かりやすく提示する仕組みの試作(PoC)。
概要は [README.md](README.md)。技術選定は ADR に残す(`docs/adr/`)。

## 構成とコマンド

- 実装は Python 3.13(ADR-0002)。道具は uv・ruff・mypy(strict)・pytest(ADR-0003)
- 構成: `src/signal_watch/`(巡回処理のパッケージ)、`tests/`(pytest)、`targets.yaml`(監視対象の設定)、
  `pyproject.toml`・`uv.lock`(依存の固定)。
  モジュールの分け方は Notion の基本設計「システム構成」に従う
- コマンド(dev container 内):
  - `uv sync`(依存の導入。CI と同じにするなら `--locked`)
  - `uv run ruff check` / `uv run ruff format`(lint / 書式整形)
  - `uv run mypy`(型検査)
  - `uv run pytest`(テスト)
  - `uv run python -m signal_watch validate-config`(`targets.yaml` の検証。CI でも走る)
  - `uv run python -m signal_watch fetch [--id <id>] [--save-dir <dir>]`(監視対象を実際に取得する。
    対象サイトにアクセスするので、試すときは `--id` で絞り、続けて何度も実行しない。
    GitHub Actions では `Watch` ワークフローの手動実行で同じことをする)
  - 対話シェルでは `.venv` が自動で有効になる(`~/.bashrc`)ので、`uv run` を省いて `pytest` などと打ってもよい
- 依存を足したら `uv lock` して `uv.lock` もコミットする。`pyproject.toml` の `exclude-newer` より新しい版は入らない
- Node.js は lefthook / commitlint のために使っている(`package.json`)。実装に別の言語を使う場合も残す
- CI の `repo-checks` は ADR 書式・lint・書式・型検査・テスト・`targets.yaml`・PR タイトル・ブランチ名を検査する
- Slack 通知(Incoming Webhook)のアプリは `docs/slack-app-manifest.yml` から作る(手順はファイル冒頭)。
  Webhook URL は GitHub Actions の Secret `SLACK_WEBHOOK_URL` にだけ置く。エージェントは URL を受け取らない
- 監視対象を増やすときは、そのサイトの利用規約・robots.txt を確認してから `targets.yaml` に足す。
  新しいドメインは `src/signal_watch/config.py` の `ALLOWED_DOMAINS` と `init-firewall.sh` の両方に足す

## 開発規約

- ブランチ・コミット・PR の規約は [CONTRIBUTING.md](CONTRIBUTING.md)。lefthook と commitlint で機械的に強制される
- ADR は `docs/adr/`(`managing-adrs` スキル)。要件・設計ドキュメントは `managing-notion-docs` スキル
- Notion(`ntn`)の認証と権限制御は `managing-notion-docs` スキルの「前提条件」。`NOTION_API_TOKEN`(最小権限の内部インテグレーション)を使い、`ntn login` / `ntn auth` は使わない
- CI は `.github/workflows/ci.yml`(`repo-checks`。ルールセットの必須チェック)
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
- `gh` の認証情報(`~/.config/gh`)は名前付きボリュームに置き、rebuild 後も残す。トークンは平文のファイルで残るため、
  permissions で Read/Edit を拒否している。初回は `gh auth login` → `gh auth refresh -h github.com -s workflow`
  (CI の設定を変える push に要る)→ `gh auth setup-git` を人が実行する。2回目以降の rebuild では
  `postCreateCommand` が `gh auth setup-git` を実行する。消したいときは `gh auth logout` かボリュームを削除する
- Slack CLI(`slack`)はイメージに入れてある(Dockerfile。公式のインストールスクリプト)。
  `slack login` は人が実行する。認証情報(`~/.slack/credentials.json`)は permissions で Read/Edit を拒否しており、
  rebuild すると消える。通信先の `slack.com`・`api.slack.com` は許可ドメインに入れてある
- 機密(`.ssh`, `.aws`, `~/.config/gh`, `~/.slack/credentials.json`, `.credentials*`, `secrets/`)は permissions で読み取りを拒否している。
  `.env` はエージェントが読める(編集は拒否、git 管理外)。
  **運用ルール: `.env` にはエージェント向けの認証情報(`NOTION_API_TOKEN`)だけを書く。人間用・本番用の資格情報は置かない**。
  これがセキュリティの前提。`.env` が無いと起動に失敗するため、`initializeCommand` で空ファイルを作る
