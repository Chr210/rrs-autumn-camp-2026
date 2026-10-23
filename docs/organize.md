# 運営向け資料

採用したチームフォルダを `submissions/at/<team>/` と `submissions/fb/<team>/` に配置してから実行します。

## 統合フォルダの生成

```sh
# リポジトリのルート
uv sync --locked

# 1組
uv run python tools/assemble.py \
  --at alpha --fb beta --output .local/exports/alpha_beta

# 全組合せ
uv run python tools/assemble.py --all --output .local/exports/release
```

`--all` はAT×FBの全組合せを生成します。AT 2件・FB 2件なら4フォルダです。出力先や対応する組合せ一覧（manifest）が存在する場合は上書きしません。

```text
.local/exports/
  release/
    at_alpha__fb_beta/
      main.py
      pyproject.toml
      uv.lock
      .python-version
      LICENSE.adf-python
      config/
      src/
        __init__.py
        alpha/
        beta/
        camp_default_2026/
    ...
  release.manifest.json
```

## 設定の統合

通常の `module.yaml` を入力として使います。

1. 固定ファイル、相手方の設定、共通のDefault設定が配布版と同じことを確認します。
2. AT提出からATのTactics配下の接続先と、そのチーム名の設定を取り込みます。
3. FB提出からFBのTactics配下の接続先と、そのチーム名の設定を取り込みます。
4. 運営の共通設定を基に、上記の範囲だけを反映して `module.yaml` を生成します。
5. クラス定義・import先、リテラルで指定された専用設定キー、Python構文を検査します。

YAMLの重複キー、チーム名の重複、他チーム参照、共通設定の変更、解決できないローカル参照はエラーです。設定はチーム名を最上位キーにしたネスト形式に統一し、ドットを含むYAMLキーは使いません。動的に組み立てる設定参照や任意のPythonコードの意味までは検査しないため、運営レビューと実行確認が必要です。

## 外部バッチ環境への受け渡し

生成したエージェントフォルダを丸ごと渡し、その中で次を実行します。

```sh
uv sync --locked
uv run python main.py
```

組合せ一覧はエージェントフォルダ群の外側の `release.manifest.json` に出力されます。地図とサーバはエージェントフォルダに含めません。試合実行・結果収集・スコア集計は外部バッチ環境で行います。
