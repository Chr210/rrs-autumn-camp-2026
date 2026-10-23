# エージェントの開発と提出

## 環境

Java 21、Python 3.13、uv、Git、Bashを使います。

## チームフォルダを作る

フォーク・クローンしたリポジトリのルートで実行します。

```sh
uv sync --locked
uv run python tools/create_team.py at myteam
```

FB担当者は `at` を `fb` に置き換えます。`submissions/at/myteam/` に通常のADF-Python形式のエージェントフォルダが作成されます。チーム名は英小文字で始まる英小文字・数字・アンダースコアを使い、他チームと重複しない名前にしてください。

```text
myteam/
  main.py
  pyproject.toml
  uv.lock
  .python-version
  LICENSE.adf-python
  config/
    launcher.yaml
    module.yaml
    development.json
  src/
    __init__.py
    myteam/
      __init__.py
      module/
        __init__.py
        complex/
          __init__.py
          sample_human_detector.py
          sample_search.py
    camp_default_2026/           運営固定の初期エージェント
```

作成後は、このチームフォルダを直接扱います。

## 編集と起動

```sh
cd submissions/at/myteam
uv sync --locked
uv run python main.py -a 20 -f 20 -ac 0 -fs 0
```

`src/myteam/` 内を編集します。`src/camp_default_2026/` は運営が提供する初期エージェントです。FB担当の場合、消防隊は自分の `myteam`、救急隊は初期エージェントのコードで動作します。AT担当の場合はその逆です。

サーバは別ターミナルで起動します。[RRSチュートリアルの環境構築](https://rcsimjp.github.io/rrs-tutorials/docs/tutorial-2/)も参照してください。

```sh
# リポジトリのルートで実行
mkdir -p .local
git clone https://github.com/roborescue/rcrs-server.git .local/rcrs-server
cd .local/rcrs-server
./gradlew completeBuild
```

ビルド後、同じターミナルで配布マップを指定してサーバを起動します。エージェントは、先ほどのチームフォルダ側のターミナルから起動してください。

```sh
# .local/rcrs-server/ から実行
cd scripts
./start-comprun.sh -m ../../../map/aichi_university/map -c ../../../map/aichi_university/config
```

配布シナリオはAT 20台・FB 20台で、センターはありません。起動例の `-a 20 -f 20 -ac 0 -fs 0` は、その人数に合わせた指定です。PFは配布設定で無効になっています。

シミュレーションをGUIなしで実行する場合は、サーバの起動コマンドに `-g` を追加します。実行後のログは、次のコマンドでLogViewerに表示できます。

```sh
# .local/rcrs-server/ から実行
java -Xmx1024m -cp ".:jars/*:lib/*" sample.SampleLogViewer \
  -c ../../map/aichi_university/config/logviewer.cfg logs/log/rescue.log.7z
```

## 設定の追加

通常のモジュール改良では `module.yaml` を編集する必要はありません。新しいモジュールや依存先の登録が必要になったら、IssuesまたはPRで運営へ連絡してください。

担当部隊の接続先として利用できるものは次のとおりです。

| 部隊 | 接続先 |
| --- | --- |
| AT | HumanDetector、Search、ExtendActionTransport、CommandExecutorAmbulance |
| FB | HumanDetector、Search、ExtendActionRescue、CommandExecutorFire |

表にある接続先を変更できます。それ以外の接続先と、DefaultSearchなどの共通設定は運営が固定します。

### 独自PathPlanning・Clusteringの追加例

AT担当の `myteam` が、探索に使うPathPlanningとClusteringを自作する例です。FB担当でも手順は同じです。`myteam` は自分のチーム名に読み替えてください。

**1. 自分のパッケージにコードを追加する**

```text
src/myteam/
  module/
    algorithm/
      __init__.py
      my_path_planning.py
      my_clustering.py
    complex/
      sample_human_detector.py
      sample_search.py
```

`algorithm/` と空の `__init__.py` を作り、次のクラスを置きます。以下は接続を確認するための最小例で、継承元と同じ動作をします。ここから必要なメソッドを実装・変更してください。

`src/myteam/module/algorithm/my_path_planning.py`:

```python
from src.camp_default_2026.cached_path_planning import CachedPathPlanning


class MyPathPlanning(CachedPathPlanning):
    pass
```

`src/myteam/module/algorithm/my_clustering.py`:

```python
from adf_core_python.implement.module.algorithm.k_means_clustering import (
    KMeansClustering,
)


class MyClustering(KMeansClustering):
    pass
```

既存クラスを継承して改良するほか、ADFのPathPlanning・Clusteringのインターフェースに沿って新しく実装することも可能です。

**2. 自分の部隊が使う設定キーを確認する**

チームフォルダ内の `sample_search.py` は、次のキーを参照しています。

```python
# Searchが使うPathPlanning
module_manager.get_module(
    "myteam.Search.PathPlanning",
    "src.camp_default_2026.cached_path_planning.CachedPathPlanning",
)

# Searchが使うClustering
module_manager.get_module(
    "myteam.Search.Clustering",
    "adf_core_python.implement.module.algorithm.k_means_clustering.KMeansClustering",
)
```

この2つは初期コードに設定済みなので、参照キーを書き換える必要はありません。新しいモジュールから依存先を読み込む場合も、このようにチーム名から始まるキーを使います。

**3. 運営に設定の反映を依頼する**

コードを追加しただけでは、使用するクラスは切り替わりません。IssuesまたはPRで、追加したクラスと設定キーを運営に伝えてください。運営がチームフォルダ内の `config/module.yaml` の該当箇所を更新します。

```yaml
myteam:
  Search:
    PathPlanning: src.myteam.module.algorithm.my_path_planning.MyPathPlanning
    Clustering: src.myteam.module.algorithm.my_clustering.MyClustering
```

これは変更箇所の抜粋です。既存の `myteam` セクション内を更新し、ほかの設定は残します。module.yaml全体をこの内容で置き換えたり、同名のセクションを追加したりしないでください。

この設定を反映すると、自分のSearchが自作のPathPlanning・Clusteringを使います。相手方の初期エージェントや共通の `DefaultSearch` の設定は変わりません。HumanDetectorでも自作Clusteringを使いたい場合は、別途 `myteam.HumanDetector.Clustering` の変更を依頼してください。

初期SearchのPathPlanningには、同じ出発地点から各地点までの経路距離をまとめて計算し、再利用する `CachedPathPlanning` を使っています。

## 提出

`submissions/<at|fb>/<team>/` を **フォルダごと** PRに含めます。main.py・config・src・依存ファイルを含め、`.venv`・ログ・キャッシュは含めません。PRにはチーム名、参加者名、担当部隊、改良点を記載してください。

ルートに戻って提出形式を確認できます。

```sh
uv run python tools/assemble.py --check submissions/at/myteam
```

この検査はフォルダ・設定・静的なクラス参照を確認します。コードの動作や規則遵守は、手元のシミュレーションと運営のPRレビューで確認します。
