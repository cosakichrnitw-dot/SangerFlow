# SangerFlow ロードマップ

> **Status note:** this roadmap contains historical Tkinter and BOLD planning
> material. For v1.0, SangerFlow Studio/PySide6 is the official GUI, and BOLD
> online identification is not a supported user-facing workflow.

## この文書の目的

この文書は、実装済みの機能と今後の計画を混同せず、長期的な開発判断のために整理する。現在のコードを唯一の事実基準とし、実装状況、バージョン、依存関係、テスト状態は[CURRENT_STATUS.md](CURRENT_STATUS.md)を正とする。この文書の将来項目はすべて「計画」または「検討候補」である。

## 読み方

- **実装確認済み**: 現在のPythonコードで確認できる。
- **計画**: 優先候補だが未実装または未完了である。
- **検討候補**: 採用・設計・時期が確定していない。

## 現行実装の基盤（実装確認済み）

### 目的

AB1読込、品質評価、トリミング、Tkinterでのクロマトグラム表示、MAFFT連携、コンセンサス、NCBI BLAST、FASTA/Excel出力の基盤を提供する。

### 確認済みの範囲

`SangerRead`、AB1読込、品質統計、波形QC、Modified Mottトリミング、Tkinter GUI、MAFFT実行、アラインメント表示、コンセンサス計算、BLAST、FASTA/Excel出力がコードに存在する。詳細は[CURRENT_STATUS.md](CURRENT_STATUS.md)および[Architecture.md](Architecture.md)を参照する。

### 制約・リスク

自動テストは実質的に未整備であり、NCBI BLASTとMAFFTに外部依存がある。複数の処理入口と重複実装が存在する。

## 安定化・テスト・依存関係整理（計画）

| 項目 | 内容 |
|---|---|
| 目的 | 既存機能の再現性、保守性、検証可能性を高める。 |
| 優先度 | 高 |
| 前提条件 | 現在のAB1、QC、トリミング、GUI操作の期待動作をサンプルデータで記録する。 |
| 影響範囲 | `core/`、テスト、依存関係定義、CLI/GUIのエラー表示。 |
| 完了条件 | コア処理の自動テスト、依存関係の整合、失敗時の一貫した報告方針を確認できる。 |
| リスク | 科学的なトリミング・QC判定を変更すると既存出力が変化する。 |

計画候補には、`requirements.txt` と実際のimportの整合、未使用依存の分離、MAFFT検出の改善が含まれる。現在の依存関係の詳細は[CURRENT_STATUS.md](CURRENT_STATUS.md)を参照する。

## 初回安定版（計画）

| 項目 | 内容 |
|---|---|
| 目的 | 研究者が単一または複数のSanger readを一貫した手順で処理できる安定版を目指す。 |
| 優先度 | 高 |
| 前提条件 | 安定化フェーズの検証、エラー処理、利用手順、生成物の扱いが整うこと。 |
| 影響範囲 | GUI、CLI、出力、文書、テスト。 |
| 完了条件 | 文書化された代表ワークフローを、対応環境で再現できる。 |
| リスク | NCBI BLASTの応答、MAFFT導入、AB1機器差異が利用体験を左右する。 |

## 編集・比較・品質管理の拡張（計画）

| 項目 | 内容 |
|---|---|
| 目的 | read編集、forward/reverse readの扱い、比較・品質確認を拡張する。 |
| 優先度 | 中 |
| 前提条件 | raw配列、品質値、ピーク位置、トリム後座標の対応を保つデータ設計。 |
| 影響範囲 | `SangerRead`、アラインメント、Canvas、出力、テスト。 |
| 完了条件 | 編集履歴、座標対応、保存仕様をテストで確認できる。 |
| リスク | 座標ずれや品質値との対応喪失が解析結果へ直接影響する。 |

## 将来候補（未実装・検討候補）

| 候補 | 目的 | 前提条件・主なリスク |
|---|---|---|
| BOLD連携 | BLAST以外の同定手段を検討する。 | API仕様、利用条件、結果モデルが未確認。 |
| ASAP / ABGD | 種区分解析との連携を検討する。 | 科学的妥当性と入力・出力仕様の専門家レビューが必要。 |
| バッチ処理の統合 | 分散した入口を整理する。 | 既存CLI出力の互換性を確認する必要がある。 |
| 別GUIフレームワーク | 現在のGUI以外への移行または併存を検討する。 | 現在のGUI構成は[CURRENT_STATUS.md](CURRENT_STATUS.md)を参照。本番移行は未決定。 |
| 配布パッケージ | 導入容易性を高める。 | Python/Tk、MAFFT、ネットワーク依存の配布方針が必要。 |
| プロジェクト保存 | read群・設定・出力の再現性を改善する。 | プロジェクトデータ形式と互換性方針が必要。 |

大規模なデータモデル再設計、GUIフレームワーク変更、独自の生物学的アルゴリズム導入は、いずれも確定事項ではなく**検討候補**とする。

## 開発判断の原則

1. 科学的ロジックの変更は、出力への影響と根拠を明示する。
2. まず既存のコア処理をテスト可能にする。
3. ネットワーク依存機能はローカル処理と分けて失敗を扱う。
4. 実装済み機能の説明は[CURRENT_STATUS.md](CURRENT_STATUS.md)へ、作業規則は[DEVELOPMENT_RULES.md](DEVELOPMENT_RULES.md)へ集約する。

## 関連文書

- [Architecture.md](Architecture.md)
- [CURRENT_STATUS.md](CURRENT_STATUS.md)
- [Workflow.md](Workflow.md)
- [DEVELOPMENT_RULES.md](DEVELOPMENT_RULES.md)
- [PAIR_AND_SINGLE_WORKFLOW_DESIGN.md](PAIR_AND_SINGLE_WORKFLOW_DESIGN.md) — pair / single workflowの段階的実装提案
- [PAIR_ASSEMBLY_ALGORITHM_DESIGN.md](PAIR_ASSEMBLY_ALGORITHM_DESIGN.md) — baselineとadvanced futureを分けたpair assembly設計提案
