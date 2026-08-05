# SangerFlow ワークフロー

## この文書の目的

この文書は、現在のリポジトリで確認できる利用・開発手順を示す。コードを唯一の事実基準とし、READMEや既存文書と矛盾する場合はコードを優先する。コマンドは現行コードの入口に基づく。可変のバージョン、依存関係、テスト状態は重複して記載せず、[CURRENT_STATUS.md](CURRENT_STATUS.md)を参照する。未確認の環境依存事項は「未確認」または「提案」と明記する。

## 前提条件

- PythonとTkinterが利用できること。Tkinterはpip依存ではなくPython/OS側の提供である。
- MAFFTがインストールされ、`mafft` が `PATH` から実行できること。
- BLASTにはネットワーク接続が必要である。
- AB1ファイルは`.ab1`拡張子で扱われる。

## 仮想環境と依存関係

以下は標準的な仮想環境作成例である。OSごとのPython/Tkinter導入方法はこのリポジトリでは未確認である。

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

現在のコードで確認した依存関係と`requirements.txt`との差異は[CURRENT_STATUS.md](CURRENT_STATUS.md)を参照する。この文書は依存定義を変更しない。

## MAFFTの確認

```bash
mafft --version
```

`core/mafft.py` と `core/chromatogram_alignment.py` は `mafft --auto` を実行する。コマンドが見つからない場合、アラインメントは実行できない。外部依存の現状は[CURRENT_STATUS.md](CURRENT_STATUS.md)を参照する。

## GUIの起動

リポジトリルートで実行する。

```bash
python -m gui.app
```

`gui/app.py` はGUIのroot windowを作成し、`gui/main_window.py` の `MainWindow` を起動する。現在の本番GUIと実験用GUIの区分は[CURRENT_STATUS.md](CURRENT_STATUS.md)を参照する。

## CLI・バッチ処理

### 単一AB1ファイル

```bash
python pipeline.py path/to/sample.ab1
```

`pipeline.py` は読込、品質表示、トリミング、FASTA保存、BLAST、BLASTレポート保存を行う。

### 既定の `input/` フォルダ処理

```bash
python main.py
```

`main.py` は `input/` 内の`*.ab1`を対象に処理し、`output/` 以下へFASTA、Excel、結合FASTAを出力する。

```bash
python batch_pipeline.py
```

`batch_pipeline.py` も `input/` を対象に別実装のバッチ処理を行う。両者は処理が重複しており、用途の統合は未実施である。

## 利用者の処理フロー

1. GUIから単一AB1またはAB1フォルダを開く。
2. `SangerRead` に配列、品質値、波形、ピーク位置を読み込む。
3. QCおよび品質統計を確認する。
4. トリム済み配列とトレースを用いて表示・選択を行う。
5. 選択したreadをMAFFTでアラインメントする。
6. アラインメントからコンセンサスを表示またはFASTA出力する。
7. 必要に応じてNCBI BLASTを実行し、結果を確認・Excel出力する。
8. FASTAまたはExcelを保存する。

各処理の実装関係は[Architecture.md](Architecture.md)、機能の現状は[CURRENT_STATUS.md](CURRENT_STATUS.md)を参照する。

## よくあるエラーと確認箇所

| 状況 | 確認箇所 |
|---|---|
| アラインメントに失敗する | `mafft --version` が成功するか、選択readにトリム済み配列があるかを確認する。 |
| BLASTに失敗する | ネットワーク接続、NCBIサービス応答、配列が空でないことを確認する。 |
| Excel出力でimportエラーになる | 現在のPython依存と依存定義との差異を[CURRENT_STATUS.md](CURRENT_STATUS.md)で確認する。 |
| BLAST通信で証明書エラーになる | 現在のPython依存とネットワーク要件を[CURRENT_STATUS.md](CURRENT_STATUS.md)で確認する。 |
| GUIが起動しない | Tkinter対応Pythonか確認し、`python -m gui.app` をリポジトリルートで実行する。 |
| 実験用GUIのエラーが出る | 現在のGUI区分を[CURRENT_STATUS.md](CURRENT_STATUS.md)で確認し、本番GUI確認には`python -m gui.app`を使う。 |

## 開発時の基本確認

Pythonソースを変更した場合は、少なくとも対象モジュールの構文確認と、変更した操作の手動確認を行う。テストの現状は[CURRENT_STATUS.md](CURRENT_STATUS.md)を参照する。

```bash
python -m compileall -q core gui main.py pipeline.py batch_pipeline.py
git status --short
```

科学的処理を変更する場合は、品質値、ピーク位置、トリム後座標、出力配列への影響を確認する。詳細は[DEVELOPMENT_RULES.md](DEVELOPMENT_RULES.md)を参照する。

## 関連文書

- [Architecture.md](Architecture.md)
- [CURRENT_STATUS.md](CURRENT_STATUS.md)
- [Roadmap.md](Roadmap.md)
- [DEVELOPMENT_RULES.md](DEVELOPMENT_RULES.md)
