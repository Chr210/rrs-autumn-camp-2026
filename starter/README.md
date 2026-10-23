# 初期エージェント

`at/` と `fb/` は、main.py・config・src・依存ファイルを持つ通常のADF-Pythonエージェントです。

ルートで `uv run python tools/create_team.py at <team>` を実行すると、チーム名を設定したフォルダを `submissions/` にコピーします。FB担当の場合は、コマンド内の `at` を `fb` に置き換えてください。作成後はチームフォルダ内で通常の `uv run python main.py` により起動します。
