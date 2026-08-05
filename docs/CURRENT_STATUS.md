# SangerFlow 現在の実装状況

## この文書の目的

この文書は、2026-08-01時点でリポジトリのコードとGit作業ツリーから確認できる状態を記録する。コードを唯一の事実基準とし、READMEおよび既存文書と矛盾する場合はコードを正とする。将来計画は[Roadmap.md](Roadmap.md)を参照する。

## 基本情報

| 項目 | 確認内容 |
|---|---|
| 最終確認日 | 2026-08-01 |
| 現在のブランチ | `feature/tkinter-gui` |
| 現在のバージョン表示 | `SangerFlow v0.8`（`gui/main_window.py` のwindow title） |
| 本番GUI | Tkinter（`gui/app.py`、`gui/`） |
| PySide6 | `test_gui.py` の実験用スクリプトのみ。本番GUIではない。 |

## 実装済み機能

- AB1読込: `core/ab1_reader.py` が配列、品質値、波形、ピーク位置を読み込む。
- 共有データ: `core/models.py` に `SangerRead` がある。
- 品質評価: 平均品質、Q20、Q30、HQ%、波形QC。
- トリミング: `core/trimming.py` のModified Mottベース処理。
- GUI表示: 複数readのクロマトグラム、サンプル選択、品質パネル、アラインメント関連ウィンドウ。
- アラインメント: MAFFTを呼び出してBiopythonのアラインメントへ変換する。
- コンセンサス: 多数決と品質加重の実装がある。
- BLAST: NCBI BLASTへの問い合わせ、結果抽出、集計、Excel出力。
- 出力: FASTA、コンセンサスFASTA、Excelレポート、FASTA結合。

## 部分実装または確認が必要な機能

- `core/mafft.py` と `core/chromatogram_alignment.py` にMAFFT実行が分かれている。
- CLI・バッチの処理入口が `main.py`、`pipeline.py`、`batch_pipeline.py`、`core/pipeline.py` に分散している。
- `gui/main_window.py` は `alignment_clicked` を2回定義しており、後の定義だけが有効である。
- `test_ab1.py` は `read_ab1()` の現在の `SangerRead` 返却形式と一致しない辞書アクセスをしている。
- 実GUI、BLAST、MAFFTを含む統合動作の自動検証は確認できていない。

## 未実装またはコード上で確認できない機能

- `tests/` 配下の自動テスト。
- プロジェクトファイルの保存・読込。
- readの編集履歴、undo/redo、forward/reverse readの明示的なペアリング。
- BOLD、ASAP、ABGD連携。
- 本番PySide6 GUI。
- 配布パッケージまたはインストーラ。

これらは「存在しないこと」の完全証明ではなく、現行リポジトリのPythonコードとファイル構成で確認できない項目である。

## 既知の問題・技術的負債

- `requirements.txt` は本番コードでimportされる `openpyxl` と `certifi` を宣言していない。
- `requirements.txt` のPySide6、`pyqtgraph`、`colorama` は本番Tkinter GUIでは使用されていない。
- BLASTはネットワークと外部サービスに依存し、`process_file()` は結果が空の場合に `blast[0]` を参照する。
- 多くのエラー通知と診断に `print()` が使われ、統一されたログ方針はコード上で確認できない。
- `core/config.py` のQC設定パスはカレントディレクトリ相対である。
- 生成物の一部が追跡されている一方、`.gitignore` には `output/` とFASTA拡張子が含まれる。

## 現在の起動方法

| 用途 | コマンド |
|---|---|
| Tkinter GUI | `python -m gui.app` |
| 1ファイルCLI | `python pipeline.py path/to/sample.ab1` |
| `input/` フォルダ処理 | `python main.py` |
| 別バッチ実装 | `python batch_pipeline.py` |

詳細は[Workflow.md](Workflow.md)を参照する。

## 現在必要な依存

コード上で本番利用が確認できるPyPIパッケージは `biopython`、`numpy`、`openpyxl`、`certifi` である。TkinterはPython/OSの機能でありpipパッケージではない。アラインメントには`mafft`実行ファイルが必要である。BLASTにはネットワーク接続が必要である。

## テストの現状

`tests/` ディレクトリは空である。ルートの `test_ab1.py` は現行APIと不一致であり、`test_gui.py` はPySide6実験用である。自動テスト基盤の導入は[Roadmap.md](Roadmap.md)上の計画である。

## README・既存文書とコードの不整合

以下は、コードを基準に確認できた不整合または文書化が実装状態より先行している箇所である。

| 文書上の記述または前提 | コードで確認できる状態 | 扱い |
|---|---|---|
| `docs/DeveloperGuide.md` の想定リポジトリ構造には `tests/` が含まれる。 | `tests/` は存在するが空である。ルートの `test_ab1.py` と `test_gui.py` は自動テストとして整備されていない。 | コード・ファイル構成を正とする。 |
| `docs/Core.md` は将来のPySide利用可能性に言及する。 | 本番GUIの `gui/` はTkinterをimportする。PySide6をimportするのは `test_gui.py` のみである。 | Tkinterを現在の本番GUI、PySide6を実験用として扱う。 |
| `docs/GUI.md` はGUIがCore結果を表示する構成を示す。 | `gui/quality_panel.py` は選択FASTAを作成し、`core.mafft.run_mafft()` を直接呼ぶ。`gui/main_window.py` は複数の処理を仲介する。 | コード上の責務分散を正とする。設計原則は将来の改善方針であって現状説明ではない。 |
| `docs/DataModel.md` はrawデータの不変性を設計方針として記す。 | `SangerRead` のrawフィールドは読込後に置換されないが、トリミング等の派生状態は同一の可変オブジェクトに設定される。 | 現在の実装を正とする。 |
| `requirements.txt` は実行依存の完全な一覧としては扱えない。 | 本番コードは未宣言の `openpyxl` と `certifi` をimportし、宣言済みのPySide6系・`pyqtgraph`・`colorama` は本番Tkinter GUIで使用されない。 | コードで確認した依存を正とする。 |

`README.md` は現在、通常の利用案内ではなくソフトウェア設計を主題とする文書である。起動方法と現在の実装状態は、コードと本書および[Workflow.md](Workflow.md)を優先する。

## 未コミット変更

この確認時点の作業ツリーには、以下の変更が存在する。これらは本書作成の対象外として扱い、修正・削除・ステージ・復元を行わない。

- 変更済み: `gui/quality_panel.py`
- 変更済み: `output/fasta/C2_FishF1_trimmed.fas`
- 変更済み: `output/fasta/C6_FishF1_trimmed.fas`
- 変更済み: `output/fasta/R3_FishF1_trimmed.fas`
- 未追跡: `docs/`（この文書群を含む）

## 関連文書

- [Architecture.md](Architecture.md)
- [Roadmap.md](Roadmap.md)
- [Workflow.md](Workflow.md)
- [DEVELOPMENT_RULES.md](DEVELOPMENT_RULES.md)
- [PAIR_AND_SINGLE_WORKFLOW_DESIGN.md](PAIR_AND_SINGLE_WORKFLOW_DESIGN.md) — 未実装のpair assembly・single finalization設計提案
- [PAIR_ASSEMBLY_ALGORITHM_DESIGN.md](PAIR_ASSEMBLY_ALGORITHM_DESIGN.md) — 未実装のCAP3非依存pair assembly設計提案
