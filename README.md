# snapshots ブランチ

[signal-watch-poc](https://github.com/shun968-org/signal-watch-poc) が巡回して取得した、監視対象ページの本文テキストと実行状態を置くブランチです。
GitHub Actions の Watch ワークフローが自動でコミットします。手で編集しないでください。

- `targets/<id>.txt`: 監視対象ごとに、比較範囲から抽出・整形した本文のテキスト。変更を検出したときだけコミットされ、
  コミットの差分がそのまま「何が変わったか」になります
- `state.json`: 監視対象ごとの前回取得日時・ETag・連続失敗回数など

## 出典と利用条件

`targets/` のテキストは、各ファイルの先頭に書いた取得元ページのコンテンツを、取得元の利用規約に基づいて
signal-watch-poc が抽出・加工して作成したものです。政府・取得元が作成した加工前の情報ではありません。

| 取得元 | 利用規約 |
|---|---|
| デジタル庁(https://www.digital.go.jp/) | [公共データ利用規約(第1.0版)](https://www.digital.go.jp/resources/open_data/public_data_license_v1.0) |

画像・ロゴ・添付ファイル(PDF・Excel など)の中身は保存していません(リンクの文字と URL のみ)。
