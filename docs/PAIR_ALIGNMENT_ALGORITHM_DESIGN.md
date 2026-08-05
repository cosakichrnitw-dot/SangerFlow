# Pair Alignment Algorithm Design

## この文書の目的

この文書は、Forward / Reverse pair assemblyにおける**quality-aware semi-global overlap alignment**の仕様を定義する**設計提案**である。目的は、trim済みのForward readとassembly方向へ変換したReverse readの重なりを求め、[PAIR_ALIGNMENT_MODEL_DESIGN.md](PAIR_ALIGNMENT_MODEL_DESIGN.md)で提案した`AlignmentColumn`へ、安全で追跡可能なindex対応を渡すことである。

現在のコードを唯一の実装事実の基準とする。semi-global alignment、candidate search、dynamic programming、`AssemblyReadView`、`AlignmentColumn`、`PairAlignment`、consensus、`AssemblyMetrics`、`PASS` / `REVIEW` / `FAIL`は、特記しない限り**未実装の提案**である。既存のpair assembly上位設計は[PAIR_ASSEMBLY_ALGORITHM_DESIGN.md](PAIR_ASSEMBLY_ALGORITHM_DESIGN.md)、データモデルは[PAIR_ALIGNMENT_MODEL_DESIGN.md](PAIR_ALIGNMENT_MODEL_DESIGN.md)を参照する。

## 1. 実装済み事項と提案事項

### 実装済み

- `SangerRead`はraw配列、Phred quality、raw trace位置、trim済み配列・品質・座標を保持する。
- `core/reverse_complement.py`の`build_reverse_complement_view(read)`は、Reverse readを変更せず、assembly方向の配列・品質・trimmed / raw index・raw / trimmed trace位置を0-basedで対応付ける。
- 現行のMAFFT処理はread-level multiple alignmentであり、本書のpair alignment algorithmとは別である。

### 未実装の提案

- ForwardとReverseを共通化する`AssemblyReadView`
- overlap候補探索、quality-aware semi-global DP、候補選択
- `AlignmentColumn`と`PairAlignment`の生成・検証
- `SequenceProvenance`、consensus、`AssemblyMetrics`、status、GUI・export接続

## 2. 採用方式: quality-aware semi-global overlap alignment

### 提案する方式

Forwardのassembly方向trim済み配列と、Reverseのreverse-complement assembly viewを入力とし、両readの外側non-overlap領域をfree-endとする**affine-gap semi-global alignment**を行う。match / mismatch / internal gapのscoreは、対応塩基のPhred qualityで補正する。

### 採用理由

| 要件 | この方式が満たす点 |
|---|---|
| 基本2 readのPCR産物 | multiple-read assemblerを導入せず、2配列の重なりを直接評価できる。 |
| read端のcoverage差 | 片側だけが伸びる末端gapを罰しない。 |
| indel / base-call error候補 | overlap内部のgapをscoreとcolumnとして保持できる。 |
| AB1由来の品質値 | 高品質一致を優先し、高品質不一致・gapを強く不利にできる。 |
| trace / provenance | DPはassembly indexのみを扱い、確定後にviewからraw・trace座標を復元できる。 |
| 説明可能性 | score、overlap、gap、候補差を後段で記録できる。 |

品質値はalignment選択を補助する**内部判断指標**であり、校正済みの確率、臨床的confidence、または`PASS`判定として表示してはならない。Phredから計算する誤り確率近似も、将来の検証・ベンチマーク前は相対比較に限る。

## 3. 入力・出力と責務境界

```mermaid
flowchart LR
    F["Forward `AssemblyReadView`\nnormal assembly direction"] --> Search["Candidate overlap search"]
    R["Reverse `AssemblyReadView`\nreverse-complement direction"] --> Search
    Search --> DP["Quality-aware semi-global DP"]
    DP --> Select["Candidate ranking and structural acceptance"]
    Select --> IndexColumns["Aligned assembly-index columns"]
    F --> Builder["`PairAlignment` builder"]
    R --> Builder
    IndexColumns --> Builder
    Builder --> Alignment["Proposed `PairAlignment`\n`AlignmentColumn` mapping"]
    Alignment --> Provenance["Future `SequenceProvenance` builder"]
    Alignment --> Consensus["Future `ConsensusDecision` builder"]
    Alignment --> Metrics["Future `AssemblyMetrics`"]
```

### 入力（提案）

```text
forward_view: AssemblyReadView(role=FORWARD)
reverse_view: AssemblyReadView(role=REVERSE)
scoring: AlignmentScoring
acceptance: OverlapAcceptanceCriteria
```

両viewの`sequence`、`quality`、index mapping配列の長さと座標整合性は、algorithmの前に検証する。algorithmは`SangerRead`、trace配列、GUI状態を変更しない。

### 出力（提案）

algorithmは、各columnを次の最小形式で返す。

```text
(forward_assembly_index | None, reverse_assembly_index | None)
```

`None`はgapを表す。algorithm自身はraw index・trace座標を算出しない。`PairAlignment` builderが入力viewのmappingから`ReadCoordinate`と`AlignmentColumn`を生成・検証する。これにより、DPと座標復元の責務を分離する。

candidate score、候補順位、tie情報、採用しなかった候補の要約は、提案する`AlignmentSearchEvidence`として`PairAlignment`本体とは別に保持する。これは後の`AssemblyMetrics`の入力であり、statusではない。

## 4. overlap候補探索

### Baseline候補探索（提案）

1. `A` / `C` / `G` / `T`のみからなる短いexact seedを両viewで探索する。`N`およびIUPAC ambiguity codeはseedに使わない。
2. seed一致から相対offset（Forward assembly index - Reverse assembly index）を集計する。
3. offsetごとに、ungappedな共有領域で次を計算する。
   - unambiguous一致数
   - unambiguous不一致数
   - quality補正済みの暫定score
4. 上位`K`個の異なるoffsetと、必要な境界候補をsemi-global DPへ渡す。
5. seedが得られない場合、またはseedが短すぎて候補を絞れない場合は、全対角を対象とするunbanded semi-global DPへfallbackする。seed不在だけで科学的な`FAIL`にしない。

Sanger readは基本2本であり、trim済み長も通常は限定的であるため、Baselineでは全offset探索またはunbanded DPを許容する。k-mer index、repeat-aware search、adaptive bandingは[PAIR_ASSEMBLY_ALGORITHM_DESIGN.md](PAIR_ASSEMBLY_ALGORITHM_DESIGN.md)のAdvanced futureに属する。

### candidate searchの役割

candidate searchはDPの計算範囲を絞り、偶然の短い一致を候補として可視化するためのものである。最終的なalignmentの正当性、コンタミネーション、biological plausibilityを判断しない。これらは将来のmetrics、REVIEW workflow、人間確認の責務である。

## 5. quality-aware semi-global dynamic programming

### DP形式（提案）

affine gapを扱うため、各cellに少なくとも次の状態を持つ。

| 状態 | 意味 |
|---|---|
| `M[i, j]` | Forward `i`とReverse `j`を同じcolumnに置くpath |
| `F[i, j]` | Reverse側gapを含み、Forward塩基を進めるpath |
| `R[i, j]` | Forward側gapを含み、Reverse塩基を進めるpath |

内部では0-based assembly indexを使う。DP tableの境界は実装上1-basedのprefix長を使ってよいが、外部へ返すindexは必ずviewの0-based indexへ戻す。

semi-global条件として、read外側のleading / trailing gapはfree-endとする。内部でscoreをゼロへリセットするlocal alignmentにはしない。候補pathは少なくとも1つの「両側に塩基があるcolumn」を含まなければならない。

### qualityの正規化（提案）

各Phred値は入力検証後、次で内部用に制限する。

```text
q(Q) = clamp(Q, 0, Q_cap) / Q_cap
```

`Q_cap`は設定値であり、初期提案は`40`である。上限は極端な品質値がalignmentを支配するのを防ぐためである。欠落、負値、非数値のqualityは座標view作成時またはalgorithm入力検証でエラーにする。

2塩基columnの信頼性補正には、次を用いる。

```text
r(i, j) = min(q(Q_forward[i]), q(Q_reverse[j]))
```

片側が低品質なら、両readが高品質で一致・不一致である場合ほど強く評価しない。gap penaltyにはgapではない側の`q(Q)`を用いる。

### score式（未検証のBaseline提案）

`m, x, o, e, a, b, c`を正の設定パラメータとする。

| 事象 | score |
|---|---|
| A/C/G/Tの一致 | `+m + a * r(i, j)` |
| A/C/G/Tの不一致 | `-x - b * r(i, j)` |
| ambiguity codeを含む塩基対 | `0`（seedには不使用、quality bonusなし） |
| internal gap open（Forward塩基側） | `-o - c * q(Q_forward[i])` |
| internal gap open（Reverse塩基側） | `-o - c * q(Q_reverse[j])` |
| internal gap extend | `-e` |
| terminal gap | `0` |

初期の比較用設定例は`m=2, x=2, o=3, e=1, a=2, b=2, c=1`とする**未検証の提案**である。これは実装時に固定値として埋め込まず、`AlignmentScoring`設定として明示・保存する。対象遺伝子、primer、read品質、真のindel頻度を用いたベンチマークなしに、科学的な確定値として扱わない。

この方式では高品質同士の一致は強く、高品質同士の不一致や高品質塩基を飛ばすinternal gapは強く不利になる。低品質塩基を含む不一致は相対的に弱く扱うが、consensus baseを決めることはない。

### ambiguityの扱い（提案）

現行`reverse_complement.py`は標準DNA IUPAC ambiguity codeをreverse-complementできる。alignment Baselineでは、`A/C/G/T`以外を以下のように保守的に扱う。

- exact seed探索には使用しない。
- 同一codeでも高品質matchとして加点しない。
- non-gap同士のcolumnとしては保持し、scoreは中立の`0`とする。
- ambiguity compatibilityによる部分一致score、IUPAC consensus、heterozygosity解釈はAdvanced futureとする。

この扱いにより、曖昧塩基が偶然のoverlapを強く支持することを避ける。

## 6. terminal gapとinternal gap

| 種別 | 定義 | DP score | `AlignmentColumn` | 後段の扱い |
|---|---|---|---|---|
| terminal gap | overlapの外側で、片側readだけが残る連続区間 | free-end（0） | 一方の`ReadCoordinate`が`None` | one-sided coverageとしてmetricsへ渡す。 |
| internal gap | 最初と最後の両側塩基columnの間にあるgap | affine penalty | 一方の`ReadCoordinate`が`None` | gap数・位置をmetrics / REVIEW候補へ渡す。 |

`AlignmentColumn`にはgap種別を保存しない。`PairAlignment.columns`全体を見て、最初と最後の両側non-gap columnの外側をterminal、それ以外をinternalとして導出する。これはデータモデル設計の「gap状態を二重に持たない」原則と一致する。

## 7. tieと候補選択

### deterministic ranking（提案）

DPの同点pathまたは複数candidateに対し、以下を順に比較する。

1. quality-aware DP total scoreが高い。
2. A/C/G/Tのみの両側non-gap overlap長が長い。
3. unambiguous一致数が多い。
4. internal gap open数が少ない。
5. 両readのterminal overhang合計が短い。
6. それでも同じ場合、tracebackの優先順を`M`、`F`、`R`と固定し、実行ごとに同じpathを返す。

### tieの記録

第1位と別candidateの差が`candidate_score_delta`以内であり、かつindex列が異なる場合、algorithmは決定的に1件を返しても`alignment_ambiguous=True`と候補要約を記録する。これは`REVIEW`を直接設定しない。後段の`AssemblyMetrics`またはREVIEW policyが、score差・overlap差・gap差を含めて判断する。

## 8. overlap採用基準

algorithmは「`PASS`に十分か」を判断しない。ただし、意味のない空alignmentをresultとして返さないため、次の**構造的採用基準（提案）**を満たすcandidateだけを採用候補とする。

1. 少なくとも1つの両側non-gap columnを持つ。
2. 設定された`min_overlap_bases`以上の両側non-gap columnを持つ。
3. 設定された`min_unambiguous_overlap_bases`以上のA/C/G/T両側columnを持つ。
4. total scoreが設定された`min_alignment_score`を満たす。
5. index列が[PAIR_ALIGNMENT_MODEL_DESIGN.md](PAIR_ALIGNMENT_MODEL_DESIGN.md)の不変条件を満たす。

これらの閾値は、初期実装で設定化・結果へ記録すべきであり、本書では数値を固定しない。生物学的品質や最終採否を表す`PASS` / `REVIEW` / `FAIL`閾値とは別である。

基準を満たすcandidateがない場合、algorithmは`NO_CANDIDATE`という処理結果と探索evidenceを返す提案とする。これは「assemblyが成立しなかった」という事実であり、最終的な`FAIL` statusは`AssemblyMetrics`層が決める。

## 9. `AlignmentColumn`への接続

future tracebackはindex列だけを生成する。

```text
traceback output:
  (0, 0)
  (1, 1)
  (2, None)
  (3, 2)
```

`PairAlignment` builderは、各non-`None` indexを対応するviewのmappingへ照会する。

```text
(2, None)
  -> AlignmentColumn(
       alignment_index=2,
       forward=ReadCoordinate(
           assembly_index=2,
           trimmed_index=forward_view.assembly_to_trimmed_index[2],
           raw_index=forward_view.assembly_to_raw_index[2],
           raw_trace_position=forward_view.assembly_to_raw_trace_position[2],
           trimmed_trace_position=forward_view.assembly_to_trimmed_trace_position[2]),
       reverse=None)
```

このbuilderは範囲外index、gap-gap column、sideの順序不連続、viewとの座標不一致を拒否する。algorithmがraw indexを計算しないため、Reverseのreverse-complement方向と元read座標の取り違えを防ぐ。

## 10. `SequenceProvenance`への接続

alignmentは各columnの「観測evidence」を保持するが、final塩基を決めない。将来のprovenance builderは、`ConsensusDecision`が選んだ`alignment_index`を起点にする。

```text
ConsensusDecision(final_index, alignment_index, decision_reason)
  -> PairAlignment.columns[alignment_index]
  -> forward / reverse ReadCoordinate
  -> corresponding AssemblyReadView
  -> source base, Phred, raw index, raw trace position,
     trimmed index, trimmed trace position
```

Forwardのみ、Reverseのみ、両read支持、manual edit、unresolvedのどの場合も、alignment事実は同じ`AlignmentColumn`から取得する。consensusの採用理由やmanual editはcolumnへ書き戻さず、future `SequenceProvenance` / `ManualEdit`側に保持する。

## 11. `ConsensusDecision`との境界

次はalignment algorithmの責務ではない。

- Forward / Reverseの不一致時にどちらのbaseを採用するか
- `N`、IUPAC、gapをfinal sequenceにどう反映するか
- per-base consensus qualityの算出
- final contig index、manual override、unresolved reason

future `ConsensusDecision`は少なくとも`final_index`、`alignment_index`、採用base、採用理由、evidence参照を持つ提案とする。algorithmはbase比較可能なcolumnを正しく渡すだけであり、consensusの科学的判断を内包しない。

## 12. `AssemblyMetrics`・statusとの境界

algorithmが出力するのは、alignment pathと探索evidenceである。`overlap_length`、identity、internal gap数、terminal gap数、candidate score差などは`AssemblyMetrics`が集計する。algorithmは下記を設定してはならない。

- `PASS` / `REVIEW` / `FAIL`
- final sequenceへのdataset inclusion
- human reviewの完了状態

ただし`NO_CANDIDATE`、入力検証エラー、candidate ambiguityは、metrics層が説明可能なstatus reasonを作るための処理事実として渡す。

## 13. 実装順序（提案）

1. [PAIR_ALIGNMENT_MODEL_DESIGN.md](PAIR_ALIGNMENT_MODEL_DESIGN.md)の`AssemblyReadView`、Forward view、`AlignmentColumn`、`PairAlignment`を実装・単体テストする。
2. 非qualityの小さなsemi-global affine-gap DPを実装し、index列・terminal gap・internal gap・tieをテストする。
3. `AlignmentScoring`とquality補正を追加し、低品質 / 高品質の一致・不一致・gapでscore順序をテストする。
4. candidate search、fallback、候補要約、構造的採用基準を追加する。
5. その後にのみconsensus、metrics、status、provenance、GUIを独立して追加する。

## 14. 整合性確認

| 対象 | 整合性 |
|---|---|
| `SangerRead` | raw・trim済みデータを読むだけで、フィールドを追加・変更しない。 |
| `core/reverse_complement.py` | Reverse viewの既存mappingを正規の座標情報として用いる。reverse raw配列・品質・traceは変更しない。 |
| [PAIR_ALIGNMENT_MODEL_DESIGN.md](PAIR_ALIGNMENT_MODEL_DESIGN.md) | algorithmはassembly index列のみを生成し、builderが`ReadCoordinate` / `AlignmentColumn`を生成する。gapは`None`で表す。 |
| [PAIR_ASSEMBLY_ALGORITHM_DESIGN.md](PAIR_ASSEMBLY_ALGORITHM_DESIGN.md) | semi-global overlap、quality利用、column mapping、metrics / consensus / status分離という方向性と整合する。 |
| [DEVELOPMENT_RULES.md](DEVELOPMENT_RULES.md) | raw配列、品質、ピーク位置、trim後座標の関係を推測で再構成しない。 |

既存`PAIR_ASSEMBLY_ALGORITHM_DESIGN.md`にはreverse-complement viewを未実装とする箇所があるが、現在の`core/reverse_complement.py`には実装が存在する。本書はコードを正とし、alignment algorithm以降を未実装の提案として扱う。

## 関連文書

- [Architecture.md](Architecture.md)
- [DataModel.md](DataModel.md)
- [DEVELOPMENT_RULES.md](DEVELOPMENT_RULES.md)
- [PAIR_AND_SINGLE_WORKFLOW_DESIGN.md](PAIR_AND_SINGLE_WORKFLOW_DESIGN.md)
- [PAIR_ASSEMBLY_ALGORITHM_DESIGN.md](PAIR_ASSEMBLY_ALGORITHM_DESIGN.md)
- [PAIR_ALIGNMENT_MODEL_DESIGN.md](PAIR_ALIGNMENT_MODEL_DESIGN.md)
