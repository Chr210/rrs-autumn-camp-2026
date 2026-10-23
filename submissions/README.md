# 提出フォルダ

`at/<team>/` または `fb/<team>/` に通常のエージェントフォルダ一式を置いてPRで提出します。

```sh
uv run python tools/create_team.py at myteam
cd submissions/at/myteam
uv sync --locked
uv run python main.py -a 20 -f 20 -ac 0 -fs 0
```

[開発・提出手順](../docs/development.md)を参照してください。
