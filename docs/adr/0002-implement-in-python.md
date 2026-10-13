# ADR-0002: 巡回・差分検出の処理を Python で実装する

- ステータス: 採用
- 日付: 2026-10-13
- 関連: ADR-0001、Notion 要件定義(REQ-004, REQ-005, REQ-006, REQ-008)

## コンテキスト

ADR-0001 により、巡回処理は GitHub Actions 上で定期実行するバッチになる。
処理の中心は、HTML の取得、比較範囲の抽出と除外ルールの適用(REQ-004〜006)、行単位の差分生成(REQ-008)、Slack への通知である。
リポジトリには lefthook / commitlint のための Node.js が既にあるが、実装言語は未定だった。
dev container の許可ドメインには PyPI と npm のどちらも含まれている。

### 検討した選択肢

| 案 | 却下理由 |
|---|---|
| TypeScript(Node.js) | 既存の Node.js 環境を流用できるが、HTML 抽出・差分生成は外部ライブラリの組み合わせが必要で、Python ほど定番が固まっていない |
| シェルスクリプト + 既存コマンド(curl, diff など) | robots.txt の解釈・HTML の抽出・除外ルールを書くには表現力が足りず、保守しにくい |

## 決定

**巡回・抽出・差分検出・通知の処理を Python で実装する。**

判断の根拠:

1. **必要な部品が揃っている。** robots.txt の解釈(`urllib.robotparser`)と差分生成(`difflib`)は標準ライブラリにあり、HTML の抽出は BeautifulSoup などの定番がある。
2. **GitHub Actions で動かしやすい。** `actions/setup-python` で環境を用意でき、バッチ処理に向く。

## 結果

- リポジトリに Node.js(開発ツール用)と Python(実装用)の2つの実行環境が並ぶ。Node.js は lefthook / commitlint のために残す。
- dev container に Python を追加する必要がある(`devcontainer.json` の `features`)。
- パッケージ管理・型検査・lint・テストの道具(uv / pip、mypy、ruff、pytest など)は未定。実装を始めるときに決め、CI(`.github/workflows/ci.yml`)に足す。
