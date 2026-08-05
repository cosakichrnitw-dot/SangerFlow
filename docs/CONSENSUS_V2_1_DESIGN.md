# Consensus v2.1 設計

## この文書の目的

この文書は、SangerFlowにおける次世代Forward/Reverse pair consensusの責務、適用範囲、判断根拠、および段階的な実装方針を定義する。現在のコードを唯一の実装事実とする。`core/consensus.py` のConsensus v1と、分離された実験的実装である `core/consensus_v2.py` を基準に、v2.1で安定化すべき契約を明文化する。

この文書の「実装済み」は現在のコードで確認した事項である。「提案」は将来のv2.1採用・統合前に検証が必要な仕様であり、科学的に確定した閾値や自動採用基準ではない。

関連する全体設計は[Architecture.md](Architecture.md)、pair assemblyの判断境界は[PAIR_ASSEMBLY_ALGORITHM_DESIGN.md](PAIR_ASSEMBLY_ALGORITHM_DESIGN.md)、alignmentの責務は[PAIR_ALIGNMENT_ALGORITHM_DESIGN.md](PAIR_ALIGNMENT_ALGORITHM_DESIGN.md)、開発上の制約は[DEVELOPMENT_RULES.md](DEVELOPMENT_RULES.md)を参照する。

## 実装状況とv2.1の位置付け

### 実装済み

- `core/consensus.py` の `build_pair_consensus()` は、`ConsensusResult`、`ConsensusDecision`、`AssemblyMetrics` を返すConsensus v1である。
- v1は `minimum_usable_quality=20.0` と `minimum_quality_difference=10.0` を既定のengineering thresholdとして持つ。
- `core/consensus_v2.py` の `build_pair_consensus_v2()` は、v1を変更せず `ConsensusV2Result` と `ConsensusV2Decision` を返す実験的実装である。
- 現在のv2はtwo-sided A/C/G/T columnを再判断し、one-sided、gap-only、IUPAC inputはv1結果を継承する。
- 現在のv2は、`TWO_SIDED_AGREEMENT`、`HIGHER_QUALITY_FORWARD`、`HIGHER_QUALITY_REVERSE`、完全同値conflictの `UNRESOLVED_CONFLICT_TIE` を区別する。
- 現在のv2のPhred由来scoreは `RelativePhredEvidence` のrelative log-likelihoodであり、校正済みposterior probabilityではない。
- `core/review.py` は現在 `ConsensusResult` を入力にする。v2結果をReview Engine、GUI、FASTA export、BLASTへ渡す統合は未実装である。

### v2.1で提案すること

v2.1は、上記の分離実装を直ちに本番置換するものではない。人手によるAB1波形確認に必要な根拠を残しつつ、two-sided evidenceを一貫した契約として安定化する**提案**である。

```mermaid
flowchart LR
    A["`PairAlignment`\n座標・gap・overlap"] --> C["v2.1 Consensus\ncolumnごとのbaseと根拠"]
    C --> R["`ConsensusV2Result`\nsequence / decision / metrics"]
    R --> V["人間による波形確認\n未実装のGUI統合"]
    R -. "将来の別責務" .-> Q["Review Engine\nPASS / REVIEW / FAIL"]

    A -. "base決定はしない" .-> C
    C -. "sample statusは決めない" .-> Q
```

## 1. 背景

Consensus v1には、次の実装上の特性がある。

- 単一readのPhred thresholdである `minimum_usable_quality` に依存する。
- ForwardとReverseが同じA/C/G/Tを支持していても、両方が既定値Q20未満なら `N` になる。
- conflictでは、quality differenceが `minimum_quality_difference` 未満なら `N` になる。

この挙動は保守的で説明可能である一方、二つの独立したreadが同じ塩基を支持する情報をbase決定に十分利用しない。人間がAB1波形を確認するときは、Forward/Reverseの一致、周辺配列、peak形状、品質値を合わせて判断する。現時点のv2.1 baselineは波形形状を自動評価しないが、少なくともForward/Reverse双方のbaseとPhred evidenceを保持して判断できるようにする。

v2.1の目的は `N` を最小化することではない。根拠があるcolumnでは情報量のあるbaseを返し、根拠が弱いcolumnは `N` として残し、両方を後から人間が監査できるようにすることである。

## 2. 責務分離

| 層 | 責務 | 行わないこと |
|---|---|---|
| Alignment | Forward/Reverseの座標対応、gap、overlap、terminal regionを `PairAlignment` と `AlignmentColumn` に保持する。 | consensus base、PASS/FAIL、波形の最終解釈を決めない。 |
| Consensus | alignment columnごとのbase、evidence、decision reason、confidence labelを生成する。 | sample-levelのPASS/REVIEW/FAIL、GUI表示、最終的な人間判断を行わない。 |
| Review Engine | consensusとalignmentの記述的metricsを評価し、PASS/REVIEW/FAILを決定する。 | base-call algorithmを変更しない。 |
| GUI | chromatogram/waveform確認、human review、manual confirmationを提供する。 | 科学的なbase決定ロジックをGUI event handlerへ直接実装しない。 |

この分離により、alignmentの座標マップから `alignment_index` を起点に、元readのtrimmed index、raw index、raw trace positionへ戻れる。詳細は[PAIR_ALIGNMENT_MODEL_DESIGN.md](PAIR_ALIGNMENT_MODEL_DESIGN.md)を参照する。

## 3. v2.1の適用範囲

### 初期対象

v2.1の自動column decision対象は、以下をすべて満たす `OVERLAP` 内部のcolumnに限定する。

- Forwardがnon-gap
- Reverseがnon-gap
- ForwardとReverseがともにunambiguousな `A` / `C` / `G` / `T`

この範囲では、two-sided agreementとtwo-sided conflictを別のreasonとして記録する。

### 対象外

| 領域 | v2.1初期方針 | 理由 |
|---|---|---|
| terminal one-sided region | 既存policyを維持し、two-sided ruleを適用しない。 | trim、read quality decay、contig extensionの問題であり、two-sided consensusと別に評価すべきため。 |
| internal gap region | 既存policyを維持し、two-sided ruleを適用しない。 | indel、alignment uncertainty、base-call errorの可能性を含むため。 |
| IUPAC ambiguity | 自動解決しない。 | mixed template等を `N` 以外へ自動的に縮約する根拠がまだないため。 |
| waveform shape | 自動判定に用いない。 | trace featureの検証・校正が未実装であるため。 |

`TERMINAL_ONE_SIDED_*` と `INTERNAL_GAP_*` は、将来のbenchmarkで別層として評価する。Consensus v2.1のtwo-sided ruleの結果と混ぜてprecisionを解釈しない。

## 4. Two-sided agreement

ForwardとReverseが同じA/C/G/Tを支持するとき、二つの独立した観測が同じbaseを支持することをevidenceとして扱う。

```text
Forward: A, Q16
Reverse: A, Q17
→ consensus: A
→ reason: TWO_SIDED_AGREEMENT
```

個々のqualityがQ20未満であっても、それだけを理由に `N` へ戻さない。これは、v1の単一read thresholdによる保守性を緩和する範囲である。

ただし、両readが極端に低品質なら一致のみでは十分な情報とみなさない。

```text
Forward: A, Q2
Reverse: A, Q3
→ consensus: N
→ reason: TWO_SIDED_AGREEMENT_LOW_CONFIDENCE
```

現在の実験的v2にある初期engineering defaultは、**両方のqualityが `<= 3` のとき `N`** である。この値は提示例を満たすための未校正defaultであり、科学的な閾値ではない。v2.1採用前に、波形確認済みbenchmarkで明示的に検証・記録して変更可能とする。

## 5. Two-sided conflict

ForwardとReverseが異なるunambiguous baseを支持するとき、v2.1はquality-aware relative evidenceで高品質側を選ぶ。

```text
Forward: A, Q40
Reverse: G, Q35
→ consensus: A
→ reason: HIGHER_QUALITY_FORWARD
→ selected_source: FORWARD
```

```text
Forward: A, Q20
Reverse: G, Q20
→ consensus: N
→ reason: UNRESOLVED_CONFLICT_TIE
→ selected_source: NONE
```

完全同値でないconflictをbaseとして返すことは、「絶対に正しい」と主張することではない。選ばれなかったbase、両quality、quality difference、evidence margin、selected sourceを残し、将来のReview EngineまたはGUIで人間確認可能にする。

`HIGHER_QUALITY_FORWARD` と `HIGHER_QUALITY_REVERSE` は、base-levelのdecision reasonであり、PASS/REVIEW/FAILではない。conflictを解決したcolumnのsample-level扱いはReview Engineの別責務である。

## 6. Decision情報

v2.1のdecision値オブジェクトは、現在の `ConsensusV2Decision` と互換な次の情報を保持することを提案する。

| 情報 | 用途 |
|---|---|
| `alignment_index` | `PairAlignment` と将来のprovenanceへ接続する0-based位置。 |
| `forward_base` / `reverse_base` | 各readのbase evidence。gapは `None`。 |
| `forward_quality` / `reverse_quality` | 対応するPhred値。gapは `None`。 |
| `consensus_base` | 当該columnのv2.1出力base。 |
| `reason` | baseを選んだ、または未解決とした説明可能な理由。 |
| `legacy_reason` | v1との比較・移行監査に用いるv1のreason。 |
| `evidence_context` | `TWO_SIDED_AGREEMENT`、`TWO_SIDED_CONFLICT`、one-sided等のevidence形状。 |
| `quality_difference` | `forward_quality - reverse_quality`。two-sided以外では `None`。 |
| `confidence_level` | `HIGH`、`MODERATE`、`LOW`、`UNRESOLVED`、`INHERITED` の定性的label。 |
| `evidence` / `evidence_margin` | A/C/G/Tのrelative score、winner、runner-up、差分。 |
| `selected_source` | `FORWARD`、`REVERSE`、`BOTH`、`NONE`。 |

`consensus_base` がbaseであることは、そのbaseが絶対的に正しいことを意味しない。v2.1は採用根拠を保存し、波形確認時に追跡できることを優先する。

## 7. Evidenceモデル

### Phred由来の相対evidence

two-sided A/C/G/T columnでは、候補真塩基 `b ∈ {A,C,G,T}` ごとに、ForwardとReverseの観測を組み合わせたrelative log-likelihoodを保存する提案とする。

```text
e(Q) = 10^(-Q / 10)

P(observed base | candidate base) =
    1 - e(Q)    # observed base == candidate base
    e(Q) / 3    # observed base != candidate base

score(candidate base) =
    log P(Forward observation | candidate base)
    + log P(Reverse observation | candidate base)
```

最大scoreのbaseをwinner、次点をrunner-upとし、`evidence_margin = winner score - runner-up score` を保持する。

```text
Forward: A, Q16
Reverse: A, Q17

reason: TWO_SIDED_AGREEMENT
selected_source: BOTH
confidence: MODERATE
winner: A
runner-up: C / G / T のいずれか
evidence_margin: relative internal score
```

このscoreは、Phredが完全に校正済みの独立誤差確率であるという強い仮定を置かない。したがって、表示上の「99.9%正確」などの確率表現、臨床的confidence、PASS判定へ直接変換してはならない。benchmark前は**内部比較指標**として扱う。

### Confidence label

現在の実験的v2には、display用の `confidence_reference_quality=20.0` がある。これはtwo-sided baseを返すかどうかを決めず、`HIGH` / `MODERATE` / `LOW` / `UNRESOLVED` 等の定性的labelにのみ使う。

v2.1では、confidence labelを次のように解釈することを提案する。

| Label | 意味 |
|---|---|
| `HIGH` | 現行engineering referenceを満たすtwo-sided evidence、または選択readのqualityが高いconflict。 |
| `MODERATE` | two-sided agreementだが少なくとも一方がreference未満。ただし極端低品質ではない。 |
| `LOW` | baseを返したconflictだが、選択readのqualityがreference未満。 |
| `UNRESOLVED` | `N`、完全同値conflict、または極端低品質agreement。 |
| `INHERITED` | v2.1対象外でv1 policyを継承したcolumn。 |

これらは人間reviewの優先順位付けを補助するlabelであり、sample statusを決めるものではない。

## 8. MetricsとReviewの境界

v2.1は既存の `AssemblyMetrics` と互換な記述的値を返せる。

- `overlap_length`
- `overlap_identity`
- `conflict_count`
- `resolved_conflict_count`
- `unresolved_base_count`
- `one_sided_coverage_count`

これらは観測・decisionの要約であり、合否ではない。Review Engineは、unresolved base、resolved conflict、identity、gap等を組み合わせて別途PASS/REVIEW/FAILを決める。v2.1でconflict baseを返しただけでReviewを省略する仕様にはしない。

## 9. 人手確認と座標追跡

v2.1の各decisionは `alignment_index` を持つ。`PairAlignment.column_at(alignment_index)` から、Forward/Reverseのassembly index、trimmed index、raw index、raw trace positionを取得できる。GUI統合は未実装だが、診断CLIはこの経路を使って波形確認対象を表示できる。

```text
ConsensusV2Decision.alignment_index
    -> PairAlignment.AlignmentColumn
    -> ReadCoordinate.assembly_index
    -> ReadCoordinate.trimmed_index
    -> ReadCoordinate.raw_index
    -> ReadCoordinate.raw_trace_position
```

将来の `SequenceProvenance` は、採用baseだけでなく、両readのevidence、selected source、reason、alignment columnを保持できる形にする。詳細は[PAIR_AND_SINGLE_WORKFLOW_DESIGN.md](PAIR_AND_SINGLE_WORKFLOW_DESIGN.md)を参照する。

## 10. 段階的な実装・検証方針

### Phase 1: 分離された候補計算（実装済み）

- v1を変更せず `build_pair_consensus_v2()` を提供する。
- v2 decision、relative evidence、v1 reasonを保持する。
- v1/v2比較CLIと座標付きCSVを使い、人間が波形確認する。

### Phase 2: benchmark評価（進行中）

- v1/v2変更columnへ `ACCEPT` / `KEEP_N` を付与する。
- reason、region type、quality、evidence margin別に一致を評価する。
- 変更columnだけではrecallを評価できないことを明記し、必要ならv2非変更columnも注釈対象へ含める。

### Phase 3: 採用可否の判断（提案）

- two-sided agreement、conflict、terminal one-sided、internal gapを別々にbenchmarkする。
- 閾値変更または本番統合の前に、波形確認済みの代表pairと失敗例を記録する。
- Review Engineへv2を渡す場合は、`ConsensusV2Result` との互換アダプタまたは明示的なreview contractを別設計として追加する。

### Phase 4: 将来候補（未実装）

- trace peak形状、secondary peak、spacing等をevidenceへ加える。
- IUPAC ambiguity、indel、internal gapの別policyを設計・検証する。
- `FinalSequence` と `SequenceProvenance` に採用理由と座標を接続する。
- GUIでv1/v2差分とcorresponding chromatogram locationを表示する。

## 11. 非目標と安全上の注意

- v2.1は`N`を機械的に削減する機能ではない。
- v2.1は波形を見ずに生物学的・解析学的判断を完結させない。
- `confidence_level` とPhred由来relative scoreを校正済み確率として表示しない。
- v2.1は単独でPASS/REVIEW/FAIL、dataset inclusion、BLAST、FASTA exportを決めない。
- terminal one-sided、internal gap、IUPACをtwo-sided agreementの成功率に含めない。

## 関連文書

- [Architecture.md](Architecture.md)
- [CURRENT_STATUS.md](CURRENT_STATUS.md)
- [PAIR_ALIGNMENT_MODEL_DESIGN.md](PAIR_ALIGNMENT_MODEL_DESIGN.md)
- [PAIR_ALIGNMENT_ALGORITHM_DESIGN.md](PAIR_ALIGNMENT_ALGORITHM_DESIGN.md)
- [PAIR_ASSEMBLY_ALGORITHM_DESIGN.md](PAIR_ASSEMBLY_ALGORITHM_DESIGN.md)
- [PAIR_AND_SINGLE_WORKFLOW_DESIGN.md](PAIR_AND_SINGLE_WORKFLOW_DESIGN.md)
- [DEVELOPMENT_RULES.md](DEVELOPMENT_RULES.md)
- [AGENTS.md](../AGENTS.md)
