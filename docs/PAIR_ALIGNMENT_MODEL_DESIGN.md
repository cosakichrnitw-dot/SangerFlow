# Pair Alignment Data Model Design

## この文書の目的

この文書は、Forward / Reverse pair assemblyのsemi-global overlap alignmentを実装する**前**に、alignment columnと元read座標を安全に保持するためのデータモデルを定義する**設計提案**である。

現在のコードを唯一の実装事実の基準とする。提案する`AssemblyReadView`、`AlignmentColumn`、`PairAlignment`、Forward view、alignment algorithm、consensus、`AssemblyMetrics`、GUI・export接続は、特記しない限り**未実装**である。pair assembly全体の設計は[PAIR_ASSEMBLY_ALGORITHM_DESIGN.md](PAIR_ASSEMBLY_ALGORITHM_DESIGN.md)、single/pair workflowは[PAIR_AND_SINGLE_WORKFLOW_DESIGN.md](PAIR_AND_SINGLE_WORKFLOW_DESIGN.md)、既存データモデルは[DataModel.md](DataModel.md)を参照する。

## 1. 現在の実装確認

### 実装済み

`core/reverse_complement.py` の`build_reverse_complement_view(read)`は、trim済みReverse readから不変の`ReverseComplementView`を生成する。元の`SangerRead`は変更しない。

- assembly方向のreverse-complement配列
- 逆順のtrim済み品質値
- assembly index → 元trim済みindex
- assembly index → 元raw sequence index
- assembly index → 元raw trace position
- assembly index → 現行trimmed chromatogram内の位置

をすべて0-basedで保持する。`trim_start` / `trim_end`、raw配列、trim済み配列、品質値、座標配列の整合性が検証できない入力は拒否する。`N`を含む標準DNA IUPAC ambiguity codeも扱う。

### 未実装

- Forward readを同じinterfaceで表すview
- Forward / Reverseのpair alignment結果
- `AlignmentColumn`
- semi-global overlap alignment algorithm
- consensus、`AssemblyMetrics`、`SequenceProvenance`の実体、GUI・export接続

したがって、本書のモデルは現行`ReverseComplementView`を置き換えるものではなく、次の実装でForwardとReverseを同じ契約で扱うための**提案**である。

## 2. 設計目標と非目標

### 目標

1. 両readをassembly方向の同一interfaceで参照する。
2. 各alignment columnから、Forward / Reverseそれぞれのassembly、trim済み、raw、trace座標を一意に追跡できる。
3. gapを曖昧な数値や仮の塩基で表さない。
4. 将来の`SequenceProvenance`が、final塩基からalignment columnとread evidenceへ遡れる。
5. `SangerRead`を変更せず、現行MAFFT read-level alignmentとも結合しない。

### 今回の非目標

- alignment score、overlap長、terminal / internal gapの科学的評価
- alignment候補の選択、tie-break、semi-global dynamic programming
- consensus塩基、quality decision、`final_index`
- `PASS` / `REVIEW` / `FAIL`、GUI表示、FASTA・BLAST・report出力

## 3. 座標と不変条件

### index規約

| 用語 | 規約 | 意味 |
|---|---|---|
| assembly index | 0-based | assembly方向のview内の位置 |
| trimmed index | 0-based | 元`SangerRead.trimmed_sequence`内の位置 |
| raw index | 0-based | 元`SangerRead.sequence`内の位置 |
| alignment index | 0-based | pair alignmentのcolumn位置 |
| end | exclusive | 将来rangeを表す場合のみ使用する。column自身は単一位置。 |
| UI表示 | 1-based | GUIが必要時に変換する。coreモデルは変換しない。 |

`raw_trace_position`は元AB1 trace座標系の`base_positions[raw_index]`であり、`trimmed_trace_position`とは別物である。現行`trim_sequence()`は後者をtrim開始位置からの相対座標として作るため、両者を混同してはならない。

### 必須不変条件（提案）

1. viewの全mapping配列は`sequence`と同じ長さである。
2. `ReadCoordinate.assembly_index`は、そのsideの`AssemblyReadView`の範囲内である。
3. `ReadCoordinate`のtrimmed / raw / trace値は、対応するviewの同じassembly indexの値と一致する。
4. `AlignmentColumn`はForwardとReverseの少なくとも一方を持つ。両方`None`のgap-gap columnは禁止する。
5. 同一sideのnon-gap assembly indexは、columnを左から右へ読むと厳密に1ずつ増加する。readの順序を勝手に入れ替えない。
6. alignment result内の`alignment_index`は`0..length-1`で重複・欠番がない。
7. 元readの座標が不整合または復元不能なら、モデルを作らず入力検証エラーとして扱う。推測値を格納しない。

## 4. 推奨モデル

### 4.1 `AssemblyReadView`（提案）

ForwardとReverseを同じ形式で扱う、assembly方向の不変値オブジェクトである。trace配列自体を複製せず、各塩基の座標対応だけを持つ。

```text
AssemblyReadView
  source_filename: str
  role: FORWARD | REVERSE
  sequence: str
  quality: tuple
  assembly_to_trimmed_index: tuple[int]
  assembly_to_raw_index: tuple[int]
  assembly_to_raw_trace_position: tuple[int]
  assembly_to_trimmed_trace_position: tuple[int]
```

| フィールド | 責務 | 可変性 |
|---|---|---|
| `source_filename` | 現行`SangerRead.filename`への参照キー。filename重複の扱いは将来の`Sample` / stable read ID設計で補う。 | immutable |
| `role` | pair内の`FORWARD`または`REVERSE`。readの生物学的向きを明示する。 | immutable |
| `sequence` | assembly方向のtrim済み塩基列。Forwardは通常順、Reverseはreverse-complement順。 | immutable |
| `quality` | `sequence`と同じassembly方向のPhred値。 | immutable |
| `assembly_to_trimmed_index` | assembly indexから元trim済みindexへの完全対応。 | immutable |
| `assembly_to_raw_index` | assembly indexから元raw sequence indexへの完全対応。 | immutable |
| `assembly_to_raw_trace_position` | assembly indexから元AB1 trace位置への完全対応。 | immutable |
| `assembly_to_trimmed_trace_position` | assembly indexから現行trimmed chromatogram内位置への完全対応。 | immutable |

Forward viewは将来、trim済み配列と各対応配列を自然順で保持する`build_forward_assembly_view(read)`として作る**提案**である。Reverse viewは既存`ReverseComplementView`をこの契約へ適合させる。初期段階では`AssemblyReadView`を新設せず、両viewが同名の属性を持つ`Protocol`として定義する方法も可能である。ただし`role`と共通入力検証を一箇所に固定できる不変dataclassの方が、alignment実装時の分岐を減らすため推奨する。

### 4.2 `ReadCoordinate`（提案）

alignment columnが片側readに持つ座標evidenceである。columnに多数の平行配列を置くより、同じsideの座標を1つにまとめて不整合を防ぐ。

```text
ReadCoordinate
  assembly_index: int
  trimmed_index: int
  raw_index: int
  raw_trace_position: int
  trimmed_trace_position: int
```

これはbaseやqualityの複製を持たない。baseとqualityは`PairAlignment`が保持する該当`AssemblyReadView`の`assembly_index`から得る。これにより、alignment columnとviewで同じ生物学的データを二重に保持しない。

### 4.3 `AlignmentColumn`（提案）

```text
AlignmentColumn
  alignment_index: int
  forward: ReadCoordinate | None
  reverse: ReadCoordinate | None
```

各columnが要求する最低限の情報は次のように対応する。

| 要求情報 | 保持場所 | gap時 |
|---|---|---|
| alignment index | `alignment_index` | 常に整数 |
| forward assembly index | `forward.assembly_index` | `forward is None` |
| reverse assembly index | `reverse.assembly_index` | `reverse is None` |
| forward original read index | `forward.raw_index` | `forward is None` |
| reverse original read index | `reverse.raw_index` | `reverse is None` |
| gap情報 | `forward is None` / `reverse is None` | `None`がgapを表す |

`original read index`はraw `SangerRead.sequence`に対する0-based `raw_index`を意味する。future provenanceで必要となるtrim済みindexとtrace位置も`ReadCoordinate`に同時に保持する。gapを`-1`、空文字、架空の`N`で表してはならない。

`forward_is_gap`と`reverse_is_gap`は保存せず、上記の`None`から導出する。これはgap状態とindexの二重管理を避けるためである。terminal gap / internal gapの区別もこの最初のモデルには格納しない。alignment全体を見て導出でき、科学的評価やmetricsを早期に混入させないためである。

### 4.4 `PairAlignment`（提案）

個々のcolumnだけでは、indexがどのviewに属するか確定できない。alignment algorithmが返す最小の結果コンテナを設ける。

```text
PairAlignment
  forward_view: AssemblyReadView
  reverse_view: AssemblyReadView
  columns: tuple[AlignmentColumn]
```

この段階ではscore、overlap範囲、algorithm parameter、metrics、status、consensus文字列を持たない。`columns`は生成後に変更不可とし、再alignmentは別の`PairAlignment`として生成する。これにより、将来の候補比較・manual reviewでも旧結果を参照できる。

## 5. 関係図

```mermaid
classDiagram
    class SangerRead {
        +sequence
        +quality
        +base_positions
        +trimmed_sequence
        +trimmed_quality
        +trimmed_base_positions
    }

    class AssemblyReadView {
        +source_filename: str
        +role: ReadRole
        +sequence: str
        +quality: tuple
        +assembly_to_trimmed_index: tuple
        +assembly_to_raw_index: tuple
        +assembly_to_raw_trace_position: tuple
        +assembly_to_trimmed_trace_position: tuple
    }

    class ReadCoordinate {
        +assembly_index: int
        +trimmed_index: int
        +raw_index: int
        +raw_trace_position: int
        +trimmed_trace_position: int
    }

    class AlignmentColumn {
        +alignment_index: int
        +forward: ReadCoordinate?
        +reverse: ReadCoordinate?
    }

    class PairAlignment {
        +forward_view: AssemblyReadView
        +reverse_view: AssemblyReadView
        +columns: tuple
    }

    class SequenceProvenance {
        +final_index: int
        +alignment_index: int
        +evidence[]
    }

    SangerRead --> AssemblyReadView : "derived; source unchanged"
    AssemblyReadView --> PairAlignment
    PairAlignment --> AlignmentColumn
    AlignmentColumn --> ReadCoordinate
    AlignmentColumn --> SequenceProvenance : "future evidence source"
```

## 6. `SequenceProvenance`への接続（提案）

consensus未実装の段階では、`AlignmentColumn`に`final_index`やdecision reasonを追加しない。これらは「alignment事実」ではなく「後段の塩基決定」であるためである。

将来、contigのfinal塩基を採用したときに、provenance builderは次の順でevidenceを作る。

```text
FinalSequence[final_index]
  -> chosen AlignmentColumn[alignment_index]
  -> forward / reverse ReadCoordinate (one or both)
  -> PairAlignment.forward_view / reverse_view
  -> source base, Phred, raw / trimmed trace position
```

この分離により、同じalignment columnから「Forward採用」「Reverse採用」「両者支持」「manual edit」「unresolved」を記録できる。`AlignmentColumn`自体は採用判断を持たないため、manual reviewによってconsensusが変わってもalignment座標マップを破壊しない。

## 7. gapと境界の表現

| columnの状態 | `forward` | `reverse` | 意味 |
|---|---|---|---|
| 両側塩基 | `ReadCoordinate` | `ReadCoordinate` | overlapまたはmismatch候補。base比較は後段。 |
| Forwardのみ | `ReadCoordinate` | `None` | Reverse側gap。one-sided coverage候補。 |
| Reverseのみ | `None` | `ReadCoordinate` | Forward側gap。one-sided coverage候補。 |
| 両側gap | `None` | `None` | 不正。生成・保存しない。 |

terminalかinternalかは、この表の`None`を`PairAlignment.columns`全体で評価して決める。これをcolumn構築時のenumへ固定しないことで、semi-global alignmentのfree-end規則と後のmetrics設計を分離できる。

## 8. 生成・検証の責務分離（提案）

| 処理 | 入力 | 出力 | 責務 |
|---|---|---|---|
| view builder | `SangerRead` | `AssemblyReadView` | trim済みデータと座標の整合性を検証し、assembly方向へ変換する。 |
| alignment algorithm | 2つの`AssemblyReadView` | aligned assembly index列 | ここでは将来実装。座標を推測しない。 |
| alignment result builder | viewsとaligned index列 | `PairAlignment` | 各indexをviewから`ReadCoordinate`へ展開し、不変条件を検証する。 |
| consensus / provenance builder | `PairAlignment` | future `FinalSequence` / `SequenceProvenance` | 塩基採用理由とfinal indexを追加する。 |

alignment algorithmは`(forward_assembly_index | None, reverse_assembly_index | None)`の列だけを返し、raw / trace座標の再計算をしてはならない。座標の正規形は常に`AssemblyReadView`であり、result builderが対応値を参照する。

## 9. 擬似コード（実装ではない）

```python
# Proposed only; not implemented.
forward_view = build_forward_assembly_view(forward_read)
reverse_view = build_reverse_complement_view(reverse_read)

index_columns = semi_global_align(forward_view.sequence, reverse_view.sequence)
alignment = build_pair_alignment(forward_view, reverse_view, index_columns)

# Example index column returned by a future algorithm
# (forward_assembly_index=42, reverse_assembly_index=None)
# becomes an AlignmentColumn with forward coordinates and reverse=None.
```

## 10. 実装順序（提案）

1. `AssemblyReadView`の共通契約とForward view builderを追加し、既存`ReverseComplementView`を適合させる。
2. `ReadCoordinate`、`AlignmentColumn`、`PairAlignment`を不変dataclassとして追加する。
3. viewの範囲外index、gap-gap column、index不連続、座標不一致を検証するunit testを追加する。
4. このモデルだけを入力・出力として、semi-global alignment algorithmを別モジュールで実装する。
5. consensus、metrics、status、provenance、GUIを後続の独立段階として追加する。

## 11. 現行文書との整合性・不整合

本設計は[PAIR_ASSEMBLY_ALGORITHM_DESIGN.md](PAIR_ASSEMBLY_ALGORITHM_DESIGN.md)のcolumn-to-read-index mapping、[PAIR_AND_SINGLE_WORKFLOW_DESIGN.md](PAIR_AND_SINGLE_WORKFLOW_DESIGN.md)のraw read不変性と`SequenceProvenance`構想、[DEVELOPMENT_RULES.md](DEVELOPMENT_RULES.md)のraw配列・品質・ピーク位置・trim座標の関係を維持する規則と整合する。

一方、現行コードに照らして次の記述は更新が必要である。

- `PAIR_ASSEMBLY_ALGORITHM_DESIGN.md`はreverse-complement viewを未実装としているが、`core/reverse_complement.py`には実装が存在する。
- `PAIR_AND_SINGLE_WORKFLOW_DESIGN.md`はreverse-complement pair assembly全体を未実装としており、semi-global alignment以降については現在も正しい。ただしreverse-complement view単体は実装済みである。
- `CURRENT_STATUS.md`は`tests/`が空と記載するが、現在は`tests/test_reverse_complement.py`および`tests/test_samples.py`が存在する。

これらは本書作成時に確認したコードとの不整合である。本書ではコードの実装状態を正とし、既存文書自体の更新は今回の最小変更範囲には含めない。

## 関連文書

- [Architecture.md](Architecture.md)
- [DataModel.md](DataModel.md)
- [CURRENT_STATUS.md](CURRENT_STATUS.md)
- [DEVELOPMENT_RULES.md](DEVELOPMENT_RULES.md)
- [PAIR_AND_SINGLE_WORKFLOW_DESIGN.md](PAIR_AND_SINGLE_WORKFLOW_DESIGN.md)
- [PAIR_ASSEMBLY_ALGORITHM_DESIGN.md](PAIR_ASSEMBLY_ALGORITHM_DESIGN.md)
