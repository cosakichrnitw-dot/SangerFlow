# SangerFlow 開発ルール

## この文書の目的

この文書は、人間、Codex、CursorなどがSangerFlowを共同で開発・保守する際の最小ルールを定める。現在のコードを唯一の事実基準とし、READMEや既存文書と矛盾する場合はコードを優先する。現在の実装構成は[Architecture.md](Architecture.md)、可変のバージョン・依存関係・テスト状態は[CURRENT_STATUS.md](CURRENT_STATUS.md)を参照する。

## レイヤーと責務

1. 生物学的・解析的処理は `core/` に置く。GUIイベント処理内へ直接実装しない。
2. `core/` は `gui/` をimportしない。GUIは `core/` の結果を表示し、入力を渡す。
3. 外部ツール・外部サービスとの通信は、解析ロジックやCanvas描画と分離する。
4. GUIの表示状態と解析データの責務を混ぜない。`SangerRead` の状態を変更する場合は、利用箇所を確認する。

## 科学的データの保全

1. raw配列、品質値、ピーク位置、トリム後配列、トリム後座標、波形の対応を壊さない。
2. `trim_start`、`trim_end`、`trimmed_base_positions`、`trimmed_traces` を変更する場合は、クロマトグラム表示・アラインメント対応・出力への影響を確認する。
3. QCしきい値、トリミング、コンセンサス、BLAST結果の解釈などの科学的判断をAIだけで確定しない。根拠、サンプル、必要に応じて専門家レビューを明示する。
4. 科学的ロジックを変更するPRまたはコミットでは、変更理由、想定される出力差、確認方法を記録する。

## 変更の進め方

1. 変更前に関連ファイル、呼出し元、データの流れ、Git差分を調査する。
2. 1機能または1修正ごとに小さく変更する。無関係な整形、リネーム、再設計を同時に行わない。
3. 既存動作を変える大規模な変更は、設計・影響範囲・移行方針を先に文書化する。大規模再設計は確定事項として扱わず、[Roadmap.md](Roadmap.md)では「検討候補」と明記する。
4. public API、`SangerRead`、ファイル出力形式を変更する場合は、理由と互換性への影響を記録する。
5. 変更後は対象に応じたテストまたは手動確認を行い、実行できなかった確認は未確認として報告する。

## ネットワーク・外部依存

1. MAFFTはローカル実行ファイル、NCBI BLASTはネットワークサービスであることを区別する。
2. 外部依存の失敗は、原因、実行コマンドまたは要求、利用者が取れる次の行動を示す。
3. ネットワーク処理の変更では、タイムアウト、失敗時、空結果、サービス制約を考慮する。
4. 外部サービスの利用規約、アクセス制限、科学的な結果解釈は実装とは別に確認する。

## テスト・確認

テストの現状は[CURRENT_STATUS.md](CURRENT_STATUS.md)を参照する。変更規模に応じ、少なくとも以下を行う。

```bash
python -m compileall -q core gui main.py pipeline.py batch_pipeline.py
git status --short
```

- コア処理を変更した場合: 代表入力で配列、品質、座標、出力を確認する。
- GUIを変更した場合: 該当ボタン、選択、表示更新、例外時の挙動を手動確認する。
- MAFFTまたはBLASTを変更した場合: 依存が利用可能な環境で成功・失敗の両方を確認する。

将来の自動テスト導入は[Roadmap.md](Roadmap.md)の計画である。

## Gitとデータの扱い

1. 変更前後に `git status --short` と差分を確認する。
2. AB1データ、生成FASTA、Excel、ログ、一時ファイルを不用意にGitへ追加しない。既に追跡されている生成物の扱いを変える場合は、対象を明示する。
3. 他者の未コミット変更は所有者のものとして扱う。依頼または明確な承認なしに、削除、復元、ステージ、上書きをしない。
4. コミットは目的を1つに絞り、変更内容と確認結果を説明できる状態にする。

## 言語方針

- Pythonのファイル名、関数名、クラス名、コマンド、設定キーは原文のままバッククォートで表記する。
- UI表示、コメント、利用者向け文書の言語は、対象利用者と既存表示を確認して決める。一つの画面・機能で無秩序に混在させない。
- 新規の長い開発文書は日本語を基本とし、技術用語とコード識別子は必要に応じて英語を併記する。既存英語文書を翻訳する際は、意味とコード上の事実を確認する。

## 関連文書

- [Architecture.md](Architecture.md)
- [CURRENT_STATUS.md](CURRENT_STATUS.md)
- [Workflow.md](Workflow.md)
- [Roadmap.md](Roadmap.md)
- [PAIR_AND_SINGLE_WORKFLOW_DESIGN.md](PAIR_AND_SINGLE_WORKFLOW_DESIGN.md) — scientific data integrityを要するpair / single workflow設計提案
- [PAIR_ASSEMBLY_ALGORITHM_DESIGN.md](PAIR_ASSEMBLY_ALGORITHM_DESIGN.md) — scientific judgementを伴うpair assembly設計提案
- [AGENTS.md](../AGENTS.md)
