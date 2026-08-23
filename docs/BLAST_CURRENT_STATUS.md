# SangerFlow BLAST機能の現在の実装状況

> **v1.0 support note (2026-08-23):** This historical audit predates the
> current Studio workflow. SangerFlow Studio's NCBI BLAST online and official
> NCBI website/XML-import routes are supported in v1.0. BOLD online
> identification is not supported in v1.0. References below to Tkinter GUI
> routes are legacy/reference material, not user-facing v1.0 instructions.

## 0. 調査条件と結論

- 調査日: 2026-08-04
- 調査対象: 現在の作業ツリーにある `core/`、`gui/`、`tools/`、`tests/`、`docs/`、およびルートの実行入口
- 事実基準: Pythonコードを優先し、文書中の設計案・将来計画は現在の実装と区別した。
- 実通信: 実施していない。NCBIへの問い合わせは外部サービスへ処理と配列を送るため、本調査では静的なコード確認に限定した。
- 変更範囲: 本書の新規作成のみ。既存コード、テスト、文書、入力・生成物は変更していない。

結論として、Biopython経由でNCBI Web BLASTへ1配列ずつ問い合わせ、XMLをメモリ上で解析し、最大3件を既定値として辞書化する基盤は存在する。GUIにはAB1フォルダまたは複数レコードFASTAを選んでExcelへ出力する動線がある。ただしGUIのAB1フォルダ経路はトリム済み配列ではなくraw配列を送る。結果表示用 `BlastWindow` はMain Viewerへ未接続である。コンセンサス配列からのBLAST動線も未実装である。

ルートの単一AB1 CLI `pipeline.py` は、存在しない `core.report.save_blast_results` をimportするため、現在は起動時に `ImportError` となり実行できない。`main.py` と `batch_pipeline.py` は、依存関係、入力、ネットワークおよびNCBIサービスが利用可能なら、複数AB1を順次処理して各queryの先頭hitだけをExcelへ出力するコード経路を持つ。

## 1. 関連ファイル一覧

### 1.1 実装と直接の呼出し元

「公開API」は、先頭が `_` でないモジュールレベル関数またはGUIクラスを指す。パッケージとしての安定性や互換性が保証されているという意味ではない。

| ファイル | 役割 | 公開API | 主な呼出し元 | 使用状況 |
|---|---|---|---|---|
| `core/blast.py` | NCBI Web BLAST要求、XML解析、species/accession文字列抽出、read/FASTAの逐次処理 | `extract_species()`、`extract_accession()`、`blast_sequence()`、`blast_folder()`、`blast_fasta()`、`DEFAULT_HITS` | `pipeline.py`、`core/pipeline.py`、`batch_pipeline.py`、`core/blast_controller.py`、`gui/main_window.py` | 使用中。BLAST通信とparserの中心 |
| `core/blast_controller.py` | AB1フォルダ読込、品質集計、`blast_folder()`、Excel出力のオーケストレーション | `run_blast_folder()` | `gui/main_window.py` | GUIのAB1 Folder経路で使用中 |
| `core/blast_exporter.py` | BLAST全hit、品質、species集計、best hitを1 workbookへ出力 | `get_accession()`、`export_blast_excel()` | `core/blast_controller.py`、`gui/main_window.py` | GUIのExcel出力で使用中 |
| `core/blast_summary.py` | sample別best hitとspecies件数の集計 | `get_best_hits()`、`species_summary()`、`make_summary()` | `core/blast_exporter.py` | 前2関数は使用中。`make_summary()` の呼出しは未確認 |
| `core/pipeline.py` | AB1をQC、trim、FASTA、BLASTへ通す共通バッチ処理 | `process_file()`、`process_folder()` | `main.py` | 使用中。BLASTはtrim済み配列、先頭hitのみ |
| `core/report.py` | `core/pipeline.py` の結果からBLAST/QC summary Excelを作成 | `create_summary_excel()` | `main.py` | 使用中。`pipeline.py` がimportする `save_blast_results()` は存在しない |
| `gui/blast_dialog.py` | BLAST対象、入力、hit数、database、Excel保存先を収集 | `BlastDialog` | `gui/main_window.py` | 使用中 |
| `gui/blast_window.py` | 1 queryのBLAST hit一覧とtitle詳細を表示するTkinter window | `BlastWindow` | 呼出し元なし | GUI部品は存在するが未接続 |
| `gui/button_bar.py` | Main Viewerの `BLAST` buttonを生成 | `ButtonBar` | `gui/main_window.py` | 使用中 |
| `gui/main_window.py` | BLAST dialogを開き、FASTAまたはAB1フォルダ処理を同期実行し、完了/例外をmessage box表示 | `MainWindow.open_blast_dialog()`（クラスのmethod） | `gui/app.py` → `MainWindow`、`ButtonBar` callback | 使用中 |
| `pipeline.py` | 単一AB1 CLIを意図した入口 | `run_pipeline()` | `python pipeline.py sample.ab1` | **現在は使用不能**。欠落APIのimportで起動時停止 |
| `main.py` | `input/` の複数AB1を `core.pipeline` で処理しExcel/merged FASTAへ出力 | `run_analysis()`、`main()` | `python main.py` | コード経路は使用可能。BLASTは各read 1要求、先頭hitのみ |
| `batch_pipeline.py` | `input/` の複数AB1を独自実装でQC、trim、BLAST、Excel出力 | `create_summary_excel()`、`run_batch()` | `python batch_pipeline.py` | コード経路は使用可能。`main.py` 系と重複 |
| `core/sequence_loader.py` | GUIで表示するAB1を読み込み、trim済み派生状態と品質値を設定 | `load_ab1_file()`、`load_ab1_folder()` | `gui/main_window.py` | GUI読込では使用中。ただしBLAST dialogのAB1 Folder処理はこの読込済みreadを再利用しない |
| `core/trimming.py` | `trimmed_sequence` 等を `SangerRead` に設定 | `find_trim_region()`、`trim_sequence()` | CLI/バッチ、GUI loader | 間接関連。CLI/標準バッチのBLAST queryを作る |
| `core/exporter.py` | read/consensus FASTA出力 | `save_fasta()`、`export_consensus_fasta()` | CLI/バッチ、alignment GUI | BLAST result出力ではない。BLAST前後のFASTA経路として使用中 |

### 1.2 `tools/` と `tests/`

| 範囲 | 検索結果 | 状況 |
|---|---|---|
| `tools/` | BLAST、NCBI、Entrez、accession、e-value、taxonomyを扱う実装・入口は見つからない | BLAST toolは未実装 |
| `tests/` | BLAST module、通信、parser、exporter、GUIを対象とするtestは見つからない | BLAST関連testは未実装 |

`tools/` と `tests/` には `identity` や `value` に一致するファイルがあるが、pair/consensus alignmentの一致率や一般的な値検証であり、NCBI BLAST機能とは無関係である。

### 1.3 関連文書

| 文書 | BLASTに関する役割 | 現在実装との関係 |
|---|---|---|
| `docs/Architecture.md` | NCBIWWW、XML解析、主要フローと入口を説明 | 現状説明。ただしGUI raw queryや単一CLIの破損までは記載しない |
| `docs/CURRENT_STATUS.md` | BLASTの外部依存、空結果時の `blast[0]`、test不足、依存不足を記録 | 現状説明。一部は現在の作業ツリーより古い |
| `docs/CURRENT_WORKFLOW_AND_FEATURES.md` | GUIのAB1 folder/FASTA BLASTとExcel接続を記録 | 現状説明と未実装のfinal dataset統合を区別 |
| `docs/Workflow.md` | GUI/CLI/batchの利用手順とネットワーク・証明書エラーを説明 | 利用案内。ただし `pipeline.py` を実行可能としており現コードと不一致 |
| `docs/Core.md` | `blast.py`、controller、summary、exporterの責務を説明 | 概念的説明。個別APIや制約は不足 |
| `docs/GUI.md` | BLAST Windowの表示責務を説明 | `BlastWindow` 自体は存在するが現在未接続 |
| `docs/DataModel.md` | 独立したBLAST resultと元readへの参照を設計方針として記述 | 現実装は辞書で、単一query resultに元read参照を持たない。folder/FASTA時の `sample` 文字列のみ |
| `docs/DeveloperGuide.md` | 外部通信分離、非同期処理、エラー、network test分離等の原則 | 開発指針。現実装は同期通信でtestなし |
| `docs/DEVELOPMENT_RULES.md` | NCBI BLASTをネットワークサービスとして扱う規則 | 開発規則 |
| `docs/Roadmap.md` | BLAST基盤、外部依存、バッチ入口重複を記録 | 現状と将来計画 |
| `docs/PAIR_AND_SINGLE_WORKFLOW_DESIGN.md` | `FinalSequence` をBLASTへ渡すadapterを提案 | 設計案。未実装 |
| `docs/CONSENSUS_V2_1_DESIGN.md` | v2結果からReview/GUI/FASTA/BLASTへの統合未実装を明記 | 設計案・未実装事項 |
| `docs/CONSENSUS_VIEWER_DESIGN.md` | reviewed/final sequenceのBLAST反映を将来範囲として記述 | 設計案。未実装 |
| `docs/SINGLE_CONSENSUS_REVIEW_GUI_DESIGN.md` | review結果のBLAST/dataset反映を対象外または将来事項として記述 | 設計案。未実装 |
| `docs/MULTIPLE_CONSENSUS_ALIGNMENT_VIEWER_DESIGN.md` | BLAST統合を対象外として記述 | 設計案。未実装 |
| `docs/MULTIPLE_CONSENSUS_ALIGNMENT_WORKFLOW_DESIGN.md` | BLAST統合を対象外として記述 | 設計案。未実装 |
| `docs/PAIR_ALIGNMENT_MODEL_DESIGN.md` | pair結果からBLAST/reportへの下流接続を議論 | 設計案。未実装 |

`docs/PAIR_ASSEMBLY_ALGORITHM_DESIGN.md` など、検索語の `identity` や文献中の `NCBI` にだけ一致する文書は、現在のBLAST機能を実装・接続する文書ではない。

## 2. 現在のBLAST workflow

### 2.1 BLAST core共通部分

```text
文字列sequence
→ blast_sequence(sequence, database="nt", program="blastn", max_hits=3)
→ Bio.Blast.NCBIWWW.qblast(program, database, sequence)
→ NCBI Web BLASTのXML response handle
→ Bio.Blast.NCBIXML.read(handle)
→ alignmentをresponse順で最大max_hits件取得
→ 各alignmentの先頭HSPだけを辞書化
→ list[dict]
```

`blast_sequence()` 自身は、空配列、塩基文字、長さ、向き、query ID、database/program、`max_hits` の妥当性を検証しない。

### 2.2 Main Viewer: FASTA経路

```text
Main ViewerのBLAST button
→ BlastDialogで「FASTA File」を選択
→ 外部FASTAファイルを選択
→ blast_fasta()
→ SeqIO.parse()で全recordを逐次処理
→ 各record.seqをblast_sequence()へ送信
→ 各hitへrecord.idをsampleとして付与
→ export_blast_excel(results, [], save_path)
→ 完了message box
```

- Main Viewerに現在読み込まれているreadや選択状態は使わない。
- FASTAがコンセンサスFASTAなら、その配列を送ること自体は可能である。ただし「現在のconsensusをBLASTへ送る」専用接続、provenance、review状態の引継ぎはない。
- 1 recordの通信例外で処理全体が中断し、それまでの結果もExcelへ保存されない。

### 2.3 Main Viewer: AB1 Folder経路

```text
Main ViewerのBLAST button
→ BlastDialogで「AB1 Folder」を選択
→ run_blast_folder()
→ folder直下の*.ab1をread_ab1()で再読込
→ quality_report()とhq_percentを計算
→ blast_folder(reads)
→ 各read.sequenceをblast_sequence()へ送信
→ 各hitへread.filenameをsampleとして付与
→ export_blast_excel()
→ 完了message box
```

この経路では `trim_sequence()` を呼ばず、`read.sequence`、すなわちraw base-call sequenceを送る。Main Viewerの `load_ab1_file()` / `load_ab1_folder()` が作った `trimmed_sequence` も再利用しない。このためGUI表示で確認したtrim領域とBLAST queryは一致しない。

`blast_folder()` はread単位で例外を捕捉し、`species="ERROR"` の疑似resultを追加して次のreadへ進む。

### 2.4 単一AB1 CLI (`pipeline.py`)

意図された経路は次のとおりである。

```text
AB1
→ read_ab1()
→ quality_report()
→ trim_sequence()
→ trimmed FASTA保存
→ blast_sequence(sample.trimmed_sequence)
→ results[0]を標準出力
→ save_blast_results()
```

ただし `core.report` に `save_blast_results()` が存在しないため、現在はmodule import時に停止する。したがって、この経路は**実動しない**。

### 2.5 `main.py` / `core.pipeline` 経路

```text
input/*.ab1
→ process_folder()
→ read_ab1()
→ waveform_qc() / quality_report()
→ FAILならBLAST skip
→ trim_sequence()
→ 100 bp未満ならFAILとしてBLAST skip
→ trimmed FASTA保存
→ blast_sequence(sample.trimmed_sequence)
→ results[0]だけをsample summaryへ格納
→ BLAST Summary / QC Summary Excel
→ trimmed FASTAをmerged FASTAへ結合
```

read単位の例外は `process_folder()` が捕捉するが、返すerror辞書は `core.report.create_summary_excel()` が要求するQC列を持たない。このため1 readの例外が後段のExcel生成を失敗させる可能性がコード上で確認できる。

### 2.6 `batch_pipeline.py` 経路

```text
input/*.ab1
→ read_ab1()
→ waveform_qc() / quality_report()
→ FAILならBLAST skip
→ trim_sequence()
→ 100 bp未満なら当該sampleをfailedへ追加
→ trimmed FASTA保存
→ blast_sequence(sample.trimmed_sequence)
→ results[0]だけをsummaryへ格納
→ 全sample終了後にBLAST Summary / QC Summary Excel
```

sample単位の例外は捕捉し、次のsampleへ進む。ただし失敗sampleは `failed` listにだけ入り、Excelには失敗内容もsample行も出力されない。

## 3. GUI接続状況

| 項目 | 状況 | 確認内容 |
|---|---|---|
| BLAST button | 実装済み・接続済み | `ButtonBar` の `BLAST` → `MainWindow.open_blast_dialog()` |
| menu | 未実装 | BLAST menuは見つからない |
| 設定dialog | 実装済み・接続済み | AB1 Folder / FASTA、Top 3/5/10、nt/refseq、Excel checkbox、保存先 |
| result window | 部品のみ | `BlastWindow` はあるがimport/生成する呼出し元がない |
| GUI table | 部品のみ | Rank、Species、Identity、Coverage、E-value、Accession。選択hitのtitle詳細欄あり |
| progress表示 | BLAST用は未実装 | status bar更新、progress bar、処理件数、cancelはBLAST経路にない |
| 完了表示 | 実装済み | `messagebox.showinfo()`。実際のhit数やerror result有無は表示しない |
| error表示 | 一部実装 | controllerまで伝播した例外は `messagebox.showerror()`。AB1 folderのread単位例外は疑似result化され、完了扱いになる |
| 非同期実行 | 未実装 | `open_blast_dialog()` のGUI event handler内で通信とExcel出力を同期実行 |

送信配列は次のとおりである。

- AB1 Folder: 選択folderの各AB1のraw `read.sequence`。
- FASTA File: 選択ファイルの各FASTA record sequence。Main Viewer上の現在選択readとは無関係。
- trim済みread: GUIのAB1 Folder経路では送れない。事前にtrim済みFASTAを作り、FASTA経路で選べば配列文字列としては送れる。
- consensus: GUI状態から直接送る機能はない。別途保存済みconsensus FASTAをFASTA経路で選ぶ間接手段だけがある。
- batch: folderまたは複数record FASTAの逐次処理には対応するが、件数上限、queue、cancel、rate制御はない。

Excel checkboxをOFFにすると `save_path=None` のままだが、Main Windowは両経路で無条件にExcel exporterを呼ぶ。このため「Excelを出力せず検索だけ行う」動線は実質的に完成していない。またGUI結果windowが未接続なので、ExcelをOFFにした場合の代替表示もない。

## 4. CLI / batch BLAST対応表

| 要件 | 判定 | 根拠 |
|---|---|---|
| 単一sequence | 一部実装 | Python API `blast_sequence(sequence)` は実装済み。sequence文字列を受ける専用CLIはない |
| 単一AB1 CLI | 破損 | `pipeline.py` は欠落した `save_blast_results` のimportで起動不能 |
| 複数FASTA | 実装済み（GUI/Python API） | `blast_fasta()` が全recordを逐次処理。専用CLIはない |
| 複数AB1 | 実装済み | GUI folder、`main.py`、`batch_pipeline.py` が存在。ただしquery選択や出力仕様が異なる |
| 100配列以内のbatch | 一部実装 | 100件を処理できる逐次loopはあるが、100件以内を保証・検証する上限はない |
| 上位3 hit | 一部実装 | coreとGUI Excelは既定3 hit。`main.py` / `batch_pipeline.py` は取得しても先頭1 hitだけを保持・出力 |
| Excel出力 | 実装済み | GUI exporterは全取得hit、`main.py` / batchは先頭hit summaryを出力 |

ルートスクリプトに一般的な引数parserはなく、database、program、hit数、email、API key、出力先をCLI optionとして指定できない。GUIはTop 3/5/10とdatabaseを選べる。

## 5. NCBIとの通信

| 項目 | 現状 |
|---|---|
| Biopython `NCBIWWW` | 使用中。`NCBIWWW.qblast(program, database, sequence)` |
| BLAST+ local executable | 未使用。`blastn` subprocessやlocal database処理はない |
| HTTP API直接使用 | 未実装。`requests` / `urllib` による独自BLAST API呼出しはない |
| XML parser | `Bio.Blast.NCBIXML.read()` を使用 |
| `certifi` | 使用中。`core/blast.py` import時にdefault HTTPS contextを `certifi.where()` へ差し替える |
| timeout | 明示設定なし |
| retry / backoff | なし |
| rate limit / request間隔 | なし。各queryを連続して逐次要求 |
| email | `blast_sequence(email=...)` は `Entrez.email` を設定するが、`qblast()` へemailを直接渡していない。既存の呼出し元はいずれもemail未指定 |
| API key | 未対応 |
| SSL処理 | process全体の `ssl._create_default_https_context` をmodule import時に上書きするglobal side effectあり |
| network error handling | `blast_sequence()` は捕捉しない。`blast_folder()` はread単位で捕捉。FASTA GUIは全体例外、`main.py` / batchはsample単位で上位が捕捉 |
| response handle close | 明示的な `close()` またはcontext managerなし |
| request ID / polling状態 | application側では保持・表示しない |

`BlastDialog` のdatabase候補は `nt` と文字列 `refseq` であり、その値を無変換で `qblast()` に渡す。`refseq` がNCBI側で有効なdatabase名かは本調査では実通信未確認である。

## 6. BLAST結果

### 6.1 取得するフィールド

`blast_sequence()` が各hitに格納する辞書は次のとおりである。

| key | 算出元・意味 |
|---|---|
| `species` | `alignment.title` から正規表現/単語規則で推測 |
| `identity` | 先頭HSPの `identities / align_length * 100`、小数3桁丸め |
| `coverage` | 先頭HSPの `align_length / len(sequence) * 100`、小数3桁丸め |
| `alignment_length` | 先頭HSPの `align_length` |
| `e_value` | 先頭HSPの `expect` |
| `accession` | `alignment.title` の正規表現抽出 |
| `title` | `alignment.title` 全文 |
| `sample` | `blast_folder()` / `blast_fasta()` が後付け。単一 `blast_sequence()` にはない |

### 6.2 取得しない情報

- scientific nameの構造化フィールド
- taxonomy ID、lineage、rankなどのtaxonomy情報
- descriptionとorganismを分けた構造化情報
- query ID（`sample` 文字列による代用のみ）
- query start/end、subject start/end、strand
- mismatches
- gaps / gap openings
- bit score / raw score
- HSP配列、midline
- 複数HSPを統合したcoverage

各alignmentでは `alignment.hsps[0]` だけを使う。複数HSPの統合や最良HSPのapplication側再選択はない。hitの順位は `blast_record.alignments` のresponse順であり、application側でe-valueやbit scoreによる再sortはしない。

### 6.3 speciesとaccessionの抽出

speciesはtaxonomy serviceやEntrez recordから取得せず、title文字列から次の順で推測する。

1. `| Genus species` に似た正規表現
2. titleを空白分割し、「先頭が大文字の単語 + 先頭が小文字の単語」の最初の組合せ
3. 見つからなければ `Unknown`

したがって、strain、uncultured/environmental sample、属名略記、hybrid、subspecies、title形式変更等に対する正確性は保証されない。

accession抽出は3箇所で別々の正規表現を使う。

- `core.blast.extract_accession()`
- `core.blast_exporter.get_accession()`
- `gui.blast_window.BlastWindow.extract_accession()`

core resultに `accession` が既にあるにもかかわらず、Excel exporterと未接続GUI windowは `title` から再抽出する。対応形式が異なるため、同一hitでもcore辞書、Excel、GUIでaccessionが空または `Unknown` になる可能性がある。

## 7. 出力

### 7.1 対応形式

| 形式 | 状況 |
|---|---|
| GUI table | 部品のみ。`BlastWindow` は未接続 |
| text / console | `print()` による進捗、単一CLI意図経路の先頭hit辞書のみ。独立したtext report保存なし |
| CSV | 未実装 |
| TSV | BLAST resultについて未実装 |
| Excel | 実装済み。GUI用詳細workbookとCLI/batch用summary workbookの2系統 |
| FASTA | query/trimmed/consensus FASTA出力はあるが、BLAST resultのFASTA出力はない |
| XML保存 | 未実装。responseはparserへ直接渡す |
| JSON保存 | 未実装 |

### 7.2 GUI用 `export_blast_excel()`

既存file pathへ `Workbook.save()` するため、保存dialogで選択・確認されたpathを上書きする。

| sheet | columns / 内容 |
|---|---|
| `BLAST_Result` | Sample, Species, Identity (%), Coverage (%), Alignment Length, E-value, Accession, Title |
| `Quality_Report` | Sample, Original Length, Average Quality, Q20 (%), Q30 (%), HQ (%), Trim Start, Trim End, Trimmed Length |
| `Species_Summary` | Species, Sample Count |
| `Best_Identification` | Sample, Species, Identity (%), Coverage (%), Accession, Title |

- 1 queryあたりのhit数: dialog指定の3/5/10件を上限として `BLAST_Result` に出力。返却hitが少なければその件数。
- query ID: FASTAでは `record.id`、AB1 folderでは `read.filename` を `Sample` に使用。
- 重複query IDの検証はない。
- `Best_Identification` はidentity降順、同率ならcoverageで選ぶ。e-valueやbit scoreは判定に使わない。
- `Species_Summary` はhit行を数えるため、sample数ではなくhit数を数える。headerの `Sample Count` と意味が一致しない。
- AB1 folderのerror疑似resultもspecies `ERROR` として集計・出力される。
- FASTA経路では品質listが空なので `Quality_Report` はheaderのみ。

### 7.3 `main.py` / `batch_pipeline.py` のsummary Excel

| sheet | columns |
|---|---|
| `BLAST Summary` | Sample, Species, Identity (%), Coverage (%), Alignment length, E-value |
| `QC Summary` | Sample, QC Status, QC Problems, Raw length, Trim length, Average Quality, Q20 (%), Q30 (%), Longest Q30 block, 5' Quality, 3' Quality |

- 1 queryあたり1 hitだけを出力する。
- query IDはAB1 file stem。
- accession、titleは出力しない。
- `batch_pipeline.py` の出力先は固定の `output/summary.xlsx` で、既存fileを上書きする。
- `main.py` も固定の `output/summary.xlsx` を使う。

## 8. テスト状況

BLAST関連testは0件である。

| test種別 | 状況 |
|---|---|
| NCBIを実際に呼ぶnetwork test | なし |
| `NCBIWWW.qblast` のmock test | なし |
| XML fixtureを使うparser test | なし |
| species/accession抽出unit test | なし |
| summary/exporter test | なし |
| GUI dialog/window/controller test | なし |
| timeout/retry/error test | なし |

したがって、現在のtest suiteに実通信依存で不安定になりうるBLAST testは存在しない。一方で、BLASTのAPI互換性、NCBI response形式、network failure、空hit、Excel schema、GUI接続を自動検知するtestも存在しない。

もし将来network testを通常testへ直接追加すると、NCBIの可用性、応答時間、利用制限、database更新により不安定になる。これは将来上のリスクであり、現在そのようなtestがあるという事実ではない。

## 9. 問題点・リスク

### 9.1 コードから確認済みの事実

1. **GUI同期通信**: Tkinter event handler内で全queryの `qblast()` とExcel保存を同期実行する。BLAST中にprogress更新、cancel、worker thread/processはない。
2. **GUI AB1はraw query**: `blast_folder()` は `read.sequence` を送信し、trimやQC skipを行わない。
3. **読込済みGUI状態を使わない**: Main Viewerで表示・選択したreadではなく、dialogで別途選んだfolderを再読込する。
4. **consensus未接続**: current/reviewed/final consensusを直接BLASTへ送るcallbackやadapterはない。
5. **単一CLI破損**: `pipeline.py` が存在しない `save_blast_results()` をimportする。
6. **空hit未処理**: `pipeline.py`、`core.pipeline.process_file()`、`batch_pipeline.py` は `blast[0]` を無条件参照する。
7. **timeout/retry/rate制御なし**: 明示的timeout、retry、backoff、query間隔、件数上限がない。
8. **API key未対応**: emailも既存呼出し元から設定されない。
9. **FASTA batchの部分失敗非保存**: `blast_fasta()` はrecord単位の例外処理がなく、途中の1失敗で全体がexport前に中断する。
10. **AB1 folderの失敗が成功表示される**: `blast_folder()` はerror行を返すため、controllerは通常完了し、GUIは `Excel exported successfully.` と表示する。
11. **Excel OFF動線が不完全**: checkboxがfalseでもexporterを無条件に呼び、`save_path` は `None` になる。
12. **結果window未接続**: `BlastWindow` は呼ばれず、GUIでhitを閲覧できない。
13. **speciesはtitle推測**: 構造化taxonomyを取得しない。
14. **accession抽出が重複・不一致**: 3実装があり、core resultの `accession` をexporter/windowが再利用しない。
15. **coverage定義が単純**: `hsp.align_length / len(query)` であり、query座標や複数HSPを使わない。
16. **先頭HSPのみ**: mismatches、gaps、bit score、strand等を保持しない。
17. **best hit基準が限定的**: identity、次にcoverageだけでapplication側bestを決める。
18. **sample/query ID重複を検証しない**: `get_best_hits()` は同名sampleを同一queryとしてまとめる。
19. **summaryの件数意味が不一致**: `Species_Summary` は全hit行を数えるが列名は `Sample Count`。
20. **global SSL side effect**: `core.blast` importだけでPython process全体のdefault HTTPS context factoryを置換する。
21. **response handleを明示closeしない**。
22. **出力上書き**: GUIの選択path、`main.py`、`batch_pipeline.py` の固定pathへworkbookを保存する。
23. **入口ごとの仕様不一致**: raw/trimmed、全hit/先頭hit、例外処理、Excel schemaがGUI・CLI・batchで異なる。
24. **`main.py` error rowの後段互換性不足**: `process_folder()` のerror辞書とreporter必須列が一致しない。
25. **依存宣言不足**: `certifi` と `openpyxl` はコードでimportされるが、現在の `requirements.txt` にない。
26. **query orientationの方針なし**: reverse complementを選択・記録するBLAST-specific処理はない。渡された文字列をそのまま送る。

### 9.2 推測・運用上のリスク

以下はコード構造から予想されるが、実通信・代表AB1・NCBI仕様との照合を本調査では行っていない。

- 同期処理中にMain Viewerが長時間応答しない可能性が高い。
- 件数上限とrequest間隔がないため、大きなfolder/FASTAではNCBIへの過剰要求や制限に達する可能性がある。
- `align_length / query length` はgap等を含むresponseでは、期待する「query coverage」と異なる値、場合によっては100%超を生む可能性がある。
- title形式やaccession表記が正規表現の想定外だと、species/accessionが誤抽出される可能性がある。
- global SSL context変更は、同一processの他のHTTPS通信へ影響する可能性がある。
- `refseq` database選択はNCBI側で拒否される可能性があるため、実通信での確認が必要である。
- reverse readをrawの向きのまま送ってもBLAST自体が両strandを探索する通常動作は期待されるが、本コードは向きやquery provenanceを記録しないため、下流での解釈を誤る可能性がある。NCBI側の実挙動は本調査では未確認である。
- batch結果を終了時にだけ保存する経路では、process強制終了時にそれまでの結果を失う可能性がある。

## 10. 現在できること・できないこと

### 実装済み

- Python APIへ1本のsequence文字列を渡し、NCBI Web BLASTのXMLを解析する。
- 既定 `blastn` / `nt`、既定上位3 hitを取得する。
- 複数record FASTAまたは複数AB1を1 queryずつ逐次処理する。
- species推測、percent identity、単純coverage、alignment length、e-value、accession、titleを辞書化する。
- GUIからAB1 folderまたはFASTAを選び、BLAST Excelを出力する。
- `main.py` / `batch_pipeline.py` でtrim済みAB1配列の先頭hitをsummary Excelへ出力するコード経路がある。
- `certifi` CA bundleをdefault HTTPS contextへ設定するコードがある。

### 一部実装

- batch: loopはあるが100件上限、rate制御、retry、resume、checkpointはない。
- 上位3 hit: core/GUI詳細Excelは対応するが、`main.py` / `batch_pipeline.py` は先頭1件だけ。
- error handling: 経路ごとに捕捉単位と出力が異なり、部分結果を確実に保持しない。
- email: API parameterはあるがGUI/CLIから設定されず、qblast callへ直接渡していない。
- Excel optional設定: GUI部品はあるがOFF時の実行経路が完成していない。
- consensus FASTA: 外部FASTAとして手動選択はできるが、consensus workflowとの接続ではない。

### GUI未接続

- `BlastWindow` によるhit table/detail表示。
- Main Viewerの選択read、trimmed sequence、current consensus、reviewed/final consensusからの直接BLAST。
- BLAST progress、query件数、cancel、部分失敗一覧。

### 未実装

- local BLAST+。
- 直接HTTP API client。
- timeout、retry/backoff、rate limiter、API key。
- 構造化taxonomy取得。
- mismatches、gaps、bit score、strand、query/subject座標、複数HSP coverage。
- BLAST resultのCSV、TSV、text report、XML、JSON保存。
- sequence専用CLI、複数FASTA専用CLI、一般的なCLI option。
- BLAST関連のnetwork/mock/parser/export/GUI test。
- 100配列以内という明示的batch制約。
- query IDの一意性検証とprovenance model。

### 技術的負債

- BLAST orchestrationとExcel schemaが複数箇所に重複している。
- GUI AB1だけraw配列、他の主要batchはtrim済み配列という科学的に重要な不一致がある。
- result modelが非型付き辞書で、query情報、ranking根拠、taxonomy、error状態が統一されていない。
- species/accessionをtitle文字列から重複抽出する。
- 同期GUI通信、global SSL変更、欠落timeout、欠落testがある。
- 壊れた単一AB1 CLIと空hit処理不足がある。
- `certifi` / `openpyxl` の実行依存がrequirementsに宣言されていない。

### 推奨する次の最小改善

1. **query選択を統一する**: GUIのAB1 Folder経路も、QCとtrimの方針を明示した共通adapterから `trimmed_sequence` を渡す。raw/trimmed/consensus、sample ID、向きをresultに記録し、科学的なquery変更は代表データでレビューする。
2. **失敗境界を最小限整える**: `pipeline.py` の欠落API、空hit、Excel OFF、record単位errorを修正し、timeout・限定retry・request間隔・部分結果保存を共通controllerへ置く。
3. **外部通信なしのtestを先に追加する**: `qblast` mockと固定XML fixtureでparser、species/accession、空hit、複数HSP、Excel schema、GUI controllerを検証し、実通信testは通常testから分離する。
