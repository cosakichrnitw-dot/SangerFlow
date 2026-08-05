# SangerFlow: 現在のWorkflowと機能

## この文書の目的

この文書は、現在のSangerFlowで研究者が実行できる処理、各GUIの役割、coreの責務、および未接続・prototypeの範囲を一か所に整理する。**現在のPythonコードを唯一の事実基準**とする。既存の設計文書は将来方針を含むため、コードと矛盾する場合は本書の実装状態を優先する。

バージョン、依存関係、ブランチ、テスト全体のように変化しやすい情報は[CURRENT_STATUS.md](CURRENT_STATUS.md)を参照する。将来計画は[Roadmap.md](Roadmap.md)を補助資料とし、本書では「現在実装済み」と混同しない。

## 1. Overview

### 現在のreview workflow

`Open Folder` はAB1読込、既存トリミング、品質統計の計算を行い、読み込んだ`SangerRead`群をMain Viewerへ渡す。`Consensus Review`は、明確なファイル名由来のForward/Reverse pairだけを候補化する。single read、orphan reverse、曖昧なファイル名groupは、現在のManager候補には入らない。

```mermaid
flowchart TD
    Folder["Open Folder (.ab1)"] --> Loader["`load_ab1_folder()`\nAB1 read + trim + quality statistics"]
    Loader --> Main["Main Viewer\nread / chromatogram / QC selection"]
    Main --> Entry["Consensus Review entry\nfilename-based clear F/R pair detection"]
    Entry --> Pair["AssemblyReadView\n+ `align_pair()`"]
    Pair --> V21["`build_pair_consensus_v2_1()`\nConsensus Candidate (shadow)"]
    V21 --> Manager["Consensus Review Manager\ncandidate selection"]
    Manager -->|"one selected candidate"| Single["Single Consensus Review"]
    Manager -->|"two or more selected candidates"| Mafft["`run_consensus_alignment()`\nMAFFT"]
    Mafft --> Multiple["Multiple Consensus Alignment Viewer"]
    Single --> Trace["ReviewEvidence → TraceJumpTarget\n→ Main Viewer chromatogram"]
    Multiple --> Trace
    Multiple --> LocalDecision["HumanReviewDecision\nViewer-local in-memory list"]
    LocalDecision -. "GUI未接続" .-> Session["ConsensusReviewSession"]
    Session -. "core APIのみ" .-> Reviewed["ReviewedConsensus"]
    Reviewed -. "core APIのみ" .-> Export["reviewed FASTA / review TSV"]
```

重要な実装上の区別は次のとおりである。

- `build_pair_consensus_v2_1()` は`Consensus v1`を置換しない、独立した**shadow candidate**実装である。ただし、現在のConsensus Review entryはこのv2.1 candidateをViewerへ渡す。
- Multiple modeのMAFFT実行は、Managerが既存`run_consensus_alignment()`へ委譲する。Viewer自身はMAFFTを実行しない。
- Multiple ViewerのHuman Review操作は`HumanReviewDecision`を生成するが、現在はそのwindowの`review_decisions` listにだけ保持する。
- `ConsensusReviewSession`、`ReviewedConsensus`、review済みFASTA／TSV exportはcore APIとして存在するが、Manager・Single Viewer・Multiple Viewerからはまだ呼ばれない。

### 既存の別workflow

上図とは別に、Main Viewerには従来のread-level workflowもある。`Align Chromatograms`は選択readをMAFFTで整列し、既存のAlignment Viewerを開く。`Open Alignment`はユーザーが指定したFASTAをMAFFTで整列してSequence Alignment Viewerを開く。これらはForward/Reverse pair assemblyやConsensus Review Managerとは別の経路である。

## 2. GUI一覧

| GUI | 役割 | 入力 | 出力・次の操作 | 開く方法 | 関連core |
|---|---|---|---|---|---|
| Main Viewer (`gui/main_window.py`) | AB1 folder/readの読込、chromatogram表示、read選択、品質・BLAST・既存alignment・Consensus Reviewへの入口 | `.ab1` 1件またはfolder | `SangerRead`群の表示・選択、各ダイアログ／Viewerの起動 | `python -m gui.app`後に`Open AB1`または`Open Folder` | `sequence_loader`、`trimming`、`quality`、`chromatogram_alignment`、`blast_controller`、`samples`、Consensus Review entry |
| Alignment Viewer (`gui/alignment_window.py`) | 選択済みAB1 readのMAFFT alignmentと対応chromatogramの表示 | Main Viewerで選択した`SangerRead`群と`MultipleSeqAlignment` | alignment表示、従来型consensus FASTA export、クリック位置をMain Viewerへ返す | Main Viewerの`Align Chromatograms` | `chromatogram_alignment.align_reads()`、`exporter.export_consensus_fasta()` |
| Sequence Alignment Viewer (`gui/alignment_sequence_window.py`) | ユーザー指定FASTAをMAFFT整列して塩基alignmentを表示する、従来のAlignment Viewer系画面 | FASTAと`MultipleSeqAlignment` | alignment表示、従来型consensus FASTA export | Main Viewerの`Open Alignment` | `chromatogram_alignment.align_fasta()`、`exporter.export_consensus_fasta()` |
| Consensus Review Manager (`gui/consensus_review_manager.py`) | candidate一覧、Single / Multiple mode、対象sample selectionの管理 | clear F/R pairから作られた`ConsensusReviewCandidate`群 | 1 candidateをSingle Viewerへ渡す、または選択集合をMAFFTして`AlignedConsensusSet`をMultiple Viewer callbackへ渡す | Main Viewerの`Consensus Review` | `consensus_alignment.run_consensus_alignment()`。candidate/evidenceの準備は`consensus_review_entry` |
| Single Consensus Review (`gui/consensus_viewer.py`) | 1 F/R candidateの塩基、decision reason、quality、座標、ReviewEvidenceを確認する | `PairAlignment`、`ConsensusV21Result`から作られた`SingleConsensusViewModel` | Evidence表示、Forward / Reverse `TraceJumpTarget` callback | ManagerのSingle mode、または開発用`tools/launch_consensus_viewer.py` | `consensus_v2_1`、`consensus_review_bridge`、`assembly_models` |
| Multiple Consensus Alignment Viewer (`gui/multiple_consensus_viewer.py`) | 複数candidateのMAFFT alignment、gap、IUPAC、variable site、sample別evidenceを比較する | `AlignedConsensusSet`、任意の`ConsensusEvidenceMap` | 選択site表示、Single Viewer callback、TraceJump callback、window内`HumanReviewDecision` list | ManagerのMultiple mode、または開発用launcher | `consensus_alignment`、`consensus_evidence_map`、`human_review` |

### GUI責務の境界

- Main Viewerはchromatogramを表示し、既存`TraceJumpTarget` callbackを受けてraw trace positionへ移動する。Consensusのbase決定は実装しない。
- Single / Multiple Viewerは表示と既存データの選択・参照を行う。raw trace positionを再計算しない。
- Multiple ViewerのHuman Reviewはprototypeであり、`ConsensusReviewSession`の作成、`ReviewedConsensus`の生成、保存、exportはしない。

## 3. Core一覧

| 領域 | 主な実装 | 現在の責務 | GUIとの接続状態 |
|---|---|---|---|
| AB1 Reader | `core/ab1_reader.py`、`core/sequence_loader.py`、`core/models.py` | BiopythonでAB1を読み、`SangerRead`へsequence、Phred quality、4 trace、base positionを格納する。folder loaderはtrimと品質統計も行う。 | Main Viewerの`Open AB1` / `Open Folder`から利用される。 |
| QC・trim | `core/quality.py`、`core/waveform_qc.py`、`core/trimming.py` | 品質統計、waveform QC、Modified Mottベースのtrim。trim結果は既存の可変`SangerRead`へ保持する。 | Main Viewer読込、Quality Panel、pair review entryから利用される。 |
| pairing / sample分類 | `core/samples.py` | filename suffixの`_F` / `_R`、`_Forward` / `_Reverse`を保守的に分類し、clear pair、single、orphan、ambiguousを返す。 | Manager entryはclear pairのみ使う。分類結果全体のGUI一覧は未実装。 |
| F/R Assembly | `core/reverse_complement.py`、`core/assembly_models.py`、`core/assembly_view_builders.py`、`core/pair_alignment.py` | trim済みReverse readをassembly方向へview化し、raw / trimmed / trace coordinateを保った2-read semi-global affine-gap alignmentを作る。 | Consensus Review entryと開発用診断CLIから利用される。 |
| legacy pair consensus | `core/consensus.py` | `PairAlignment`から説明可能な`ConsensusResult`とmetricsを作る。多数決／quality-awareの既存関数も含む。 | Review diagnostic CLIが利用する。Main Managerのcandidate経路は使わない。 |
| experimental consensus | `core/consensus_experimental.py`、`core/consensus_v2.py`、`core/consensus_v2_1.py` | v1を変更せず候補を比較する実験的実装。v2.1はtwo-sided evidence等を持つ`ConsensusV21Result`を返す。 | Manager entryとSingle / Multiple review candidateにv2.1が使われる。正式なv1置換ではない。 |
| automated Review Engine | `core/review.py` | legacy`ConsensusResult`と`PairAlignment`を条件評価し、`PASS` / `REVIEW` / `FAIL`と理由を返す。 | `tools/inspect_pair_review.py`とtestsで利用。現在のManager / Viewerには未接続。 |
| ReviewEvidence | `core/consensus_review_bridge.py` | v2.1 decisionと`PairAlignment`の既存`ReadCoordinate`からbase・quality・raw / trimmed index・trace position・`TraceJumpTarget`を作る。 | Single Viewer、Multiple Viewerのevidence経路で利用される。 |
| ConsensusEvidenceMap | `core/consensus_evidence_map.py` | `(sample_id, consensus_position)`から既存`ReviewEvidence`を返す。不明位置・MAFFT gapは`None`のまま扱う。 | Manager entryが構築し、Multiple Viewerが参照する。 |
| consensus-level MSA | `core/consensus_alignment.py` | candidate sequenceをMAFFTへ渡し、gap-awareな`AlignedConsensusSet`とmultiple alignment column → sample consensus position mappingを作る。 | Manager Multiple mode、開発用launcherで利用される。 |
| HumanReviewDecision | `core/human_review.py` | 人間判断のimmutable record。`ACCEPT`、`CHANGE`、`AMBIGUOUS`、`REJECT`を定義する。 | Multiple Viewerがwindow内listへ追加できる。永続化・Session接続は未実装。 |
| ConsensusReviewSession | `core/consensus_review_session.py` | sampleごとのcandidate参照、decision list、作成・更新時刻を保持し、変更有無を返す。 | core prototypeのみ。GUI未接続。 |
| ReviewedConsensus | `core/human_review.py`、`core/reviewed_consensus.py` | decisionを元candidate sequenceへ適用した派生sequenceを作る。`REJECT`は現時点ではsequenceを変更しない。 | core prototypeのみ。GUI未接続。 |
| Export | `core/exporter.py`、`core/blast_exporter.py`、`core/reviewed_export.py`、`core/report.py`、`core/merge.py` | 従来FASTA、consensus FASTA、BLAST Excel、レポート、FASTA結合、およびreviewed FASTA / review TSVを出力する。 | 従来出力とBLAST ExcelはGUI接続済み。reviewed exportはcore APIのみ。 |

## 4. 現在できること

### Main GUIから実行できること

- ✓ `.ab1` 1件の読込
- ✓ `.ab1` folderの読込（現在は小文字拡張子`*.ab1`を対象）
- ✓ raw sequence、Phred quality、trace、base positionを持つ`SangerRead`の生成
- ✓ trim済みsequence・quality・base position・traceの生成
- ✓ 複数readのchromatogram表示、read選択、trim region表示
- ✓ Quality PanelでHQ%を基にread選択、選択readのFASTA export、selection保存／読込、選択readのalignment起動
- ✓ 選択readのchromatogram MAFFT alignmentと既存Alignment Viewer表示
- ✓ FASTAのMAFFT alignmentとSequence Alignment Viewer表示
- ✓ 従来Alignment Viewerからconsensus FASTA export
- ✓ AB1 folderまたはFASTAを対象にNCBI BLASTを起動し、Excel出力を指定
- ✓ 読込済みreadのclear F/R pairを検出してConsensus Review Managerを開く
- ✓ Managerで1 pairを選び、v2.1 candidateのSingle Consensus Reviewを開く
- ✓ Managerで2以上のcandidateを選び、MAFFT後のMultiple Consensus Alignment Viewerを開く
- ✓ Single Viewerでcandidate base、decision reason、confidence、Forward / Reverse evidence、座標を確認し、既存Main Viewerのchromatogramへjumpする
- ✓ Multiple Viewerでsample row、gap、IUPAC、variable site、sample consensus position、対応evidenceを確認する
- ✓ Multiple ViewerのHuman Review sectionから`HumanReviewDecision`をwindow内に追加する

### GUI外の開発用・core APIとしてできること

- ✓ `tools/inspect_pair_alignment.py`、`tools/inspect_pair_consensus.py`、`tools/inspect_pair_review.py`によるpair処理の診断
- ✓ v1 / experimental candidate / v2 / v2.1の比較用CLI
- ✓ `ConsensusReviewSession`へdecisionを追加し、`build_reviewed_consensus()`で`ReviewedConsensus`を作る
- ✓ `export_reviewed_consensus_fasta()`でreview済みFASTA、`export_review_report()`でreview decision TSVを出力する

後半の項目はcore APIまたは開発ツールとして存在するだけであり、通常のGUI workflowが自動的に実行する機能ではない。

## 5. GUI Workflow

### A. AB1品質確認と既存read alignment

1. `python -m gui.app`でMain Viewerを起動する。
2. `Open Folder`でAB1 folderを開く。各readについて読込、trim、品質統計が実行される。
3. Main Viewerでchromatogramとread selectionを確認する。必要なら`Quality Report`を開く。
4. 既存read-level alignmentが必要な場合は、対象readを選択して`Align Chromatograms`を開く。
5. FASTA同士のalignmentが必要な場合は`Open Alignment`を使用する。

### B. F/R candidateのSingle Review

1. Main ViewerでAB1 folderを読み込む。
2. `Consensus Review`を押す。
3. entryがファイル名を分類し、明確なF/R pairだけを対象にtrim済みread → AssemblyReadView → `PairAlignment` → v2.1 candidateを作る。
4. Managerで1 candidateを選択し、`Single Consensus Review`を選んで`Open Review`を押す。
5. sequence stripまたはReview sitesを選択し、decision reasonとForward / Reverse evidenceを確認する。
6. 必要時はForward / Reverse chromatogram buttonでMain Viewerの該当raw trace positionへ移動する。

### C. sample間のMultiple Review

1. Main ViewerからManagerを開き、2件以上のcandidateを選択する。
2. `Multiple Consensus Alignment Review`を選んで`Open Review`を押す。
3. Managerが選択candidateをMAFFTで整列し、Multiple Viewerが`AlignedConsensusSet`を表示する。
4. Matrix上のbaseまたはVariable Sites panelを選択し、multiple alignment column、sample consensus position、gap、evidenceを確認する。
5. non-gap baseでは、Evidence Panelからchromatogramへjumpできる。Human Review sectionでは判断をwindow内listへ追加できる。

### D. review済みsequenceの現状

`HumanReviewDecision`を`ConsensusReviewSession`へ追加し、`ReviewedConsensus`を作り、reviewed FASTA / TSVを出力する処理は**GUIの操作手順にはまだ含まれない**。現在はPython callerまたはテストからcore APIを明示的に呼ぶ必要がある。

## 6. Export

### 現在GUIから出力できるもの

| 出力 | 実行経路 | 実装 |
|---|---|---|
| 選択済みreadのFASTA | Quality Panelの`Export Selected FASTA` | `core.exporter.save_fasta()` |
| 既存alignmentのconsensus FASTA | Alignment Viewer / Sequence Alignment Viewerの`Export Consensus FASTA` | `core.exporter.export_consensus_fasta()` |
| BLAST結果Excel | Main ViewerのBLAST dialog | `core.blast_exporter.export_blast_excel()`など |
| CLI / batchのFASTA・Excel・結合FASTA | `pipeline.py`、`main.py`、`batch_pipeline.py` | `core.pipeline`、`report`、`merge`など |

### 実装済みだがGUI未接続の出力

| 出力 | core API | 現状 |
|---|---|---|
| reviewed consensus FASTA | `export_reviewed_consensus_fasta()` | `ReviewedConsensus`を明示的に渡す必要がある。Manager・Viewerにbuttonはない。 |
| review decision TSV | `export_review_report()` | `ConsensusReviewSession`を明示的に渡す必要がある。Multiple Viewerの一時listはSessionではない。 |

したがって、現在の`Consensus Review`画面で確認したcandidateが自動的に最終datasetやFASTA exportへ送られることはない。

## 7. 現在の未実装・未接続範囲

以下は単なるTODOの一覧ではなく、コードで確認できる実装境界である。

| 範囲 | コード上の状態 | 現在できないこと |
|---|---|---|
| Single-read finalization | `Sample`分類はsingleを表せるが、Managerはclear F/R pairだけを候補化する。 | Forward-only readをSingle workflowでfinal candidate化し、review・datasetへ渡すこと。 |
| pairing review queue | `PairingStatus`はある。 | ambiguous pair、duplicate、orphan readをGUIで一覧・手動解決すること。 |
| automated Review Engineの統合 | `core/review.py`はlegacy`ConsensusResult`用に実装済み。 | Manager / Single / Multiple ViewerでPASS・REVIEW・FAILを表示・操作すること。 |
| Human Reviewの永続管理 | `HumanReviewDecision`、`ConsensusReviewSession`、`ReviewedConsensus`はある。Multiple Viewerはwindow内listだけを使う。 | session作成、reviewer指定、decision保存／再読込、複数window間共有。 |
| Single Viewerからの人間判断 | Single Viewerはevidence確認とtrace navigationを行う。 | Single Viewerでdecisionを保存すること。 |
| ReviewedConsensusのGUI接続 | build / FASTA / TSV export APIはある。 | ManagerやViewerからreview済み配列を生成・確認・exportすること。 |
| final dataset | `FinalSequence`またはdataset collectionの実装は確認できない。 | pair candidateとsingle final sequenceを統一してBLAST、FASTA、multiple alignment、reportへ渡すこと。 |
| existing alignmentの再利用 | Managerは選択candidateをMAFFTする実装である。 | 既存`AlignedConsensusSet`をManager UIから開き、MAFFTを再実行しないこと。 |
| manual edit policy | `CHANGE` / `AMBIGUOUS` decisionはcoreで適用できる。 | candidateとreview済みalignmentを明示的に切替・再整列・履歴管理すること。 |
| project persistence | project save / reloadの実装は確認できない。 | read、candidate、alignment、review session、export設定を再現すること。 |
| BOLD / ASAP / ABGD | 実装を確認できない。 | これらの外部・解析連携。 |

## 8. 今後のRoadmap

この節は**提案**であり、実装済みの機能ではない。既存設計の方向性は[Roadmap.md](Roadmap.md)、[PAIR_AND_SINGLE_WORKFLOW_DESIGN.md](PAIR_AND_SINGLE_WORKFLOW_DESIGN.md)、[CONSENSUS_VIEWER_UNIFIED_DESIGN.md](CONSENSUS_VIEWER_UNIFIED_DESIGN.md)を参照する。

| 優先度 | 提案 | 目的・完了の目安 |
|---|---|---|
| Priority S | candidate → `ConsensusReviewSession` → `ReviewedConsensus` → reviewed FASTA / TSV のGUI接続 | Multiple Viewerの判断をwindow閉鎖後も失わず、review済みsequenceを明示的に出力できる。候補配列を直接変更しない。 |
| Priority S | Current workflowの統合テストと実データbenchmark | Main Viewer folder読込からSingle / Multiple mode、trace jump、MAFFT失敗、reviewed exportまでを代表AB1で確認する。v2.1・Review Engineの科学的閾値は別途benchmarkする。 |
| Priority S | single / ambiguous / orphan sampleの明示的な扱い | `Sample`分類をManager UIへ表示し、F/R pair以外を黙ってcandidate対象外にしない。single-read finalizationはpair workflowと区別する。 |
| Priority A | Automated Review Engineの表示・責務統合 | legacy v1用の`ReviewResult`とv2.1 candidateの関係を明示してから、PASS / REVIEW / FAILをreview queueへ接続する。閾値変更はbenchmark後に行う。 |
| Priority A | Candidate / Reviewed alignmentの区別と再利用 | `AlignedConsensusSet`を既存alignmentとして開く選択、review後のalignment状態・再実行方針を明示する。 |
| Priority A | Main Viewerの責務分離とCLI入口の整理 | GUI内のworkflow仲介、複数のMAFFT・batch入口、エラー報告を段階的に整理する。既存の作業手順を壊さない。 |
| Priority B | project save / reload、reviewer・annotation履歴 | 解析の再現性と複数回reviewを支える。データ形式と互換性を先に定義する。 |
| Priority B | BOLD、ASAP、ABGD、配布パッケージ、別GUI framework | 需要、外部仕様、科学的妥当性、配布方針を確認してから検討する。 |

## 9. Architecture Diagram

### 現在の依存関係

```mermaid
flowchart LR
    App["`gui/app.py`"] --> Main["Main Viewer\n`gui/main_window.py`"]
    Main --> Loader["`core/sequence_loader.py`"]
    Main --> LegacyAlign["read-level MAFFT / Alignment Viewer"]
    Main --> Blast["BLAST dialog / controller"]
    Main --> Entry["`gui/consensus_review_entry.py`"]

    Entry --> Samples["`core/samples.py`"]
    Entry --> Assembly["assembly view builders\n+ reverse complement\n+ `align_pair()`"]
    Assembly --> V21["`core/consensus_v2_1.py`"]
    V21 --> Evidence["`ReviewEvidence` bridge"]
    Entry --> Manager["Consensus Review Manager"]

    Manager --> Single["Single Consensus Review"]
    Manager --> MSA["`core/consensus_alignment.py`\nMAFFT"]
    MSA --> Multiple["Multiple Consensus Alignment Viewer"]
    Evidence --> EvidenceMap["`ConsensusEvidenceMap`"]
    EvidenceMap --> Multiple
    Single --> Main
    Multiple --> Main

    Multiple --> Local["window-local\n`HumanReviewDecision` list"]
    Local -. "未接続" .-> Session["`ConsensusReviewSession`"]
    Session --> Reviewed["`ReviewedConsensus`"]
    Reviewed --> ReviewedExport["reviewed FASTA / review TSV"]
```

### 座標とEvidenceの経路

```mermaid
flowchart LR
    Column["multiple alignment column"] --> Position["sample consensus position\n(gap = None)"]
    Position --> Map["`ConsensusEvidenceMap`"]
    Map --> Evidence["`ReviewEvidence`"]
    Evidence --> Jump["`TraceJumpTarget`\nread identifier + raw trace position"]
    Jump --> Main["Main Viewer chromatogram"]
```

MAFFT gapは`sample consensus position = None`であり、Evidence lookupやtrace jumpの対象にしない。GUIはalignment columnからraw trace positionを推定しない。

## 既存文書との相違

現在のコードと比較すると、次の既存文書は更新時点または実装範囲が古い。

| 文書 | 相違 | 本書での扱い |
|---|---|---|
| [CURRENT_STATUS.md](CURRENT_STATUS.md) | `tests/`が空、Human Review / ReviewedConsensusが未実装と記載されているが、現在は多数の`tests/test_*.py`、`core/human_review.py`、`core/consensus_review_session.py`、`core/reviewed_consensus.py`、`core/reviewed_export.py`がある。 | 現在のコードを正とし、これらをcore prototypeまたはGUI実装済みとして記載する。 |
| [Architecture.md](Architecture.md) | 新しいpair assembly、Consensus v2.1、EvidenceMap、Manager、Single / Multiple Viewer、reviewed export経路を主要構成としては記載していない。 | 現在の依存関係を本書の図に示す。 |
| [CONSENSUS_VIEWER_UNIFIED_DESIGN.md](CONSENSUS_VIEWER_UNIFIED_DESIGN.md) | Human Review、ReviewedConsensus、exportを未実装提案として扱う部分がある。現在はcore prototypeがあり、Multiple Viewerにはwindow内decision保存UIもある。 | GUI未接続・非永続という実装境界を明記する。 |
| [Roadmap.md](Roadmap.md) | 自動テストが実質的に未整備とある。現在は新規pair assembly・consensus・review・viewer・export周辺にunit testが存在する。 | テストの存在と、外部サービスを含む正式workflowの統合検証が別課題であることを区別する。 |

この相違表は既存文書を修正するものではない。今後の文書更新では、コードを再確認して整合させる必要がある。

## 関連文書

- [CURRENT_STATUS.md](CURRENT_STATUS.md)
- [Architecture.md](Architecture.md)
- [Workflow.md](Workflow.md)
- [Roadmap.md](Roadmap.md)
- [PAIR_AND_SINGLE_WORKFLOW_DESIGN.md](PAIR_AND_SINGLE_WORKFLOW_DESIGN.md)
- [PAIR_ASSEMBLY_ALGORITHM_DESIGN.md](PAIR_ASSEMBLY_ALGORITHM_DESIGN.md)
- [CONSENSUS_V2_1_DESIGN.md](CONSENSUS_V2_1_DESIGN.md)
- [CONSENSUS_VIEWER_UNIFIED_DESIGN.md](CONSENSUS_VIEWER_UNIFIED_DESIGN.md)
- [MULTIPLE_CONSENSUS_ALIGNMENT_WORKFLOW_DESIGN.md](MULTIPLE_CONSENSUS_ALIGNMENT_WORKFLOW_DESIGN.md)
- [DEVELOPMENT_RULES.md](DEVELOPMENT_RULES.md)
- [AGENTS.md](../AGENTS.md)
