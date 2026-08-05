# SangerFlow AI開発エージェント向け指示

## この文書の目的

この文書は、CodexなどのAI開発エージェントがSangerFlowを変更する前後に守る短い実務指示である。現在のコードを唯一の事実基準とし、READMEや既存文書と矛盾する場合はコードを優先する。人間開発者を含む詳細な規則は[docs/DEVELOPMENT_RULES.md](docs/DEVELOPMENT_RULES.md)を参照する。

## プロジェクト概要

SangerFlowはSanger sequencingのAB1読込、QC、トリミング、アラインメント、コンセンサス、BLAST、出力を扱うPythonプロジェクトである。現在の技術構成、依存関係、バージョン、テスト状態は[docs/CURRENT_STATUS.md](docs/CURRENT_STATUS.md)を参照する。

## 最重要ファイル

- `core/models.py`: `SangerRead`
- `core/ab1_reader.py`: AB1読込
- `core/trimming.py`: トリミングと座標・波形の派生状態
- `core/quality.py`、`core/waveform_qc.py`: 品質処理
- `core/chromatogram_alignment.py`、`core/alignment_mapper.py`: MAFFTと座標対応
- `core/consensus.py`: コンセンサス
- `core/blast.py`: NCBI BLAST
- `gui/main_window.py`: Tkinter GUIの中心コントローラ

全体像は[docs/Architecture.md](docs/Architecture.md)、実装状態は[docs/CURRENT_STATUS.md](docs/CURRENT_STATUS.md)、実行手順は[docs/Workflow.md](docs/Workflow.md)を先に読む。

## 変更前の必須手順

1. 依頼対象、関連呼出し元、データフロー、既存Git差分を読む。
2. 調査結果、影響範囲、最小の変更案を利用者へ説明する。
3. 科学的ロジックに触れる場合は、配列、品質、ピーク位置、トリム後座標への影響を明示する。
4. 未確認事項を推測で事実として記述しない。「未確認」「提案」「計画」を使い分ける。

## 実行・確認コマンド

```bash
python -m gui.app
python pipeline.py path/to/sample.ab1
mafft --version
python -m compileall -q core gui main.py pipeline.py batch_pipeline.py
git status --short
```

MAFFTとNCBI BLASTは外部依存である。利用可能性を前提にせず、失敗を明確に報告する。

## 勝手に変更してはいけないもの

- 依頼範囲外のPythonソース、設定、依存関係、テスト、生成物
- 他者の未コミット変更
- AB1入力データ、生成FASTA、Excel、ログ、一時ファイル
- 科学的しきい値・アルゴリズムの意味

削除、復元、ステージ、コミット、pushは、利用者の明示的な依頼がある場合だけ行う。

## 変更時の原則

- `core/` と `gui/` を分離し、科学的処理をGUIに直接書かない。
- 最小限の差分を優先し、無関係な整形・リファクタリングを混ぜない。
- public API、`SangerRead`、出力形式の変更は理由と影響を記録する。
- 変更後に、実行したテストまたは手動確認と未実行理由を報告する。
- 報告には変更ファイル、変更理由、確認結果、残るリスクを含める。

詳細は[docs/DEVELOPMENT_RULES.md](docs/DEVELOPMENT_RULES.md)を優先する。
