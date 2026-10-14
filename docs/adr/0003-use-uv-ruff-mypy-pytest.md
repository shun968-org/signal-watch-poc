# ADR-0003: Python の開発ツールに uv・ruff・mypy・pytest を使う

- ステータス: 採用
- 日付: 2026-10-13
- 関連: ADR-0002、Notion 基本設計(移行・リリース計画 マイルストーン 1、未決事項 #3)

## コンテキスト

ADR-0002 で巡回処理を Python で実装すると決めたが、パッケージ管理・lint/書式・型検査・テストの道具が決まっていない。
dev container は外向き通信を許可ドメインに絞っており(PyPI は許可済み)、`vscode` ユーザーは `sudo` で `apt install` できない。
CI(GitHub Actions)と dev container で同じ依存のバージョンを再現でき、1人で保守できる少ない道具の組み合わせが要る。
dev container のベースイメージ(Debian)には Python 3.13 が入っているが、pip は無い。

### 検討した選択肢

| 案 | 却下理由 |
|---|---|
| pip + venv + requirements.txt | ロックファイルでのバージョン固定に pip-tools などの追加が要る。dev container に pip が無く、入れるには Dockerfile の変更が要るのは uv と同じ |
| Poetry | 依存解決が遅く、Python の管理は別の道具が要る。uv で足りる機能に対して道具が増える |
| flake8 + black + isort | 3つの道具の設定と更新を保つ必要がある。ruff 1つで同等の検査と書式整形ができる |
| pyright(型検査) | 速いが Node.js 版の配布が中心で、Python の依存として固定しにくい。mypy は uv の dev 依存として固定できる |

## 決定

**パッケージ管理に uv、lint と書式整形に ruff、型検査に mypy(strict)、テストに pytest を使う。
Python は dev container では OS の Python 3.13 を使い(uv による Python のダウンロードは無効にする)、CI でも 3.13 を使う。**

判断の根拠:

1. **再現できる。** `uv.lock` で依存のバージョンを固定し、dev container と CI で `uv sync --locked` によって同じ環境を作れる。
2. **道具が少ない。** ruff が lint・import 整列・書式整形をまとめて担う。
3. **ファイアウォールと両立する。** uv 本体はイメージのビルド時に入れ、実行時の取得先は PyPI(許可済み)だけで済む。

## 結果

- dev container の Dockerfile に uv のバイナリを固定バージョンで入れる。uv を上げるときはイメージの再ビルドが要る。
- Python のバージョンは dev container のベースイメージ(Debian)の Python に縛られる。3.13 以外に上げたくなったら、Python の入れ方を見直す。
- mypy の strict により、型ヒントの無いライブラリ(PyYAML など)は型スタブ(`types-PyYAML` など)を dev 依存に足す必要がある。
- CI の `repo-checks` に `ruff check`・`ruff format --check`・`mypy`・`pytest` が加わり、PR の確認時間が延びる。
