from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from core.sequence_dataset import SequenceDataset, SequenceRecord, SourceType
from workflow.ncbi_blast_xml_import import BlastXmlImportError, import_ncbi_blast_xml, preview_ncbi_blast_xml


_XML = """<?xml version=\"1.0\"?>
<!DOCTYPE BlastOutput PUBLIC \"-//NCBI//NCBI BlastOutput/EN\" \"NCBI_BlastOutput.dtd\">
<BlastOutput>
<BlastOutput_program>blastn</BlastOutput_program><BlastOutput_version>BLASTN 2.14.0+</BlastOutput_version>
<BlastOutput_reference>ref</BlastOutput_reference><BlastOutput_db>nt</BlastOutput_db>
<BlastOutput_query-ID>Query_1</BlastOutput_query-ID><BlastOutput_query-def>sample1</BlastOutput_query-def><BlastOutput_query-len>4</BlastOutput_query-len>
<BlastOutput_param><Parameters><Parameters_expect>10</Parameters_expect><Parameters_sc-match>1</Parameters_sc-match><Parameters_sc-mismatch>-2</Parameters_sc-mismatch><Parameters_gap-open>0</Parameters_gap-open><Parameters_gap-extend>0</Parameters_gap-extend><Parameters_filter>L;</Parameters_filter></Parameters></BlastOutput_param>
<BlastOutput_iterations><Iteration><Iteration_iter-num>1</Iteration_iter-num><Iteration_query-ID>Query_1</Iteration_query-ID><Iteration_query-def>sample1</Iteration_query-def><Iteration_query-len>4</Iteration_query-len>
<Iteration_hits><Hit><Hit_num>1</Hit_num><Hit_id>gi|1|ref|ACC1|</Hit_id><Hit_def>Example sequence [Example species]</Hit_def><Hit_accession>ACC1</Hit_accession><Hit_len>4</Hit_len><Hit_hsps><Hsp><Hsp_num>1</Hsp_num><Hsp_bit-score>8.0</Hsp_bit-score><Hsp_score>4</Hsp_score><Hsp_evalue>1e-10</Hsp_evalue><Hsp_query-from>1</Hsp_query-from><Hsp_query-to>4</Hsp_query-to><Hsp_hit-from>1</Hsp_hit-from><Hsp_hit-to>4</Hsp_hit-to><Hsp_query-frame>0</Hsp_query-frame><Hsp_hit-frame>0</Hsp_hit-frame><Hsp_identity>4</Hsp_identity><Hsp_positive>4</Hsp_positive><Hsp_gaps>0</Hsp_gaps><Hsp_align-len>4</Hsp_align-len><Hsp_qseq>ATGC</Hsp_qseq><Hsp_hseq>ATGC</Hsp_hseq><Hsp_midline>||||</Hsp_midline></Hsp></Hit_hsps></Hit></Iteration_hits><Iteration_stat><Statistics><Statistics_db-num>1</Statistics_db-num><Statistics_db-len>4</Statistics_db-len><Statistics_hsp-len>0</Statistics_hsp-len><Statistics_eff-space>1</Statistics_eff-space><Statistics_kappa>0.7</Statistics_kappa><Statistics_lambda>1.37</Statistics_lambda><Statistics_entropy>1.3</Statistics_entropy></Statistics></Iteration_stat></Iteration></BlastOutput_iterations>
</BlastOutput>"""


class BlastXmlImportTests(unittest.TestCase):
    def _dataset(self) -> SequenceDataset:
        return SequenceDataset("input", "Input", SourceType.IMPORTED_FASTA, (
            SequenceRecord("sample1", "ATGC"), SequenceRecord("sample2", "ATGT"),
        ))

    def test_preview_and_import_keep_description_and_provenance(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "blast.xml"
            path.write_text(_XML, encoding="utf-8")
            preview = preview_ncbi_blast_xml(path, self._dataset())
            result, _ = import_ncbi_blast_xml(path, self._dataset(), result_id="web-xml")
        self.assertEqual(preview.matched_query_ids, ("sample1",))
        self.assertEqual(preview.dataset_only_record_ids, ("sample2",))
        self.assertEqual(result.hits[0].description, "Example sequence [Example species]")
        self.assertEqual(result.hits[0].scientific_name, "Example species")
        self.assertEqual(result.metadata["source"], "NCBI_WEB_XML_IMPORT")

    def test_reference_description_and_scientific_name_are_separate(self) -> None:
        xml = _XML.replace(
            "Example sequence [Example species]",
            "Rhynchobatus australiae mitochondrion, complete genome",
        )
        with TemporaryDirectory() as directory:
            path = Path(directory) / "blast.xml"
            path.write_text(xml, encoding="utf-8")
            result, _ = import_ncbi_blast_xml(path, self._dataset(), result_id="web-xml")

        self.assertEqual(
            result.hits[0].description,
            "Rhynchobatus australiae mitochondrion, complete genome",
        )
        self.assertEqual(result.hits[0].scientific_name, "Rhynchobatus australiae")

    def test_ambiguous_taxon_title_does_not_invent_a_scientific_name(self) -> None:
        xml = _XML.replace(
            "Example sequence [Example species]",
            "Rhynchobatus sp. voucher ABC mitochondrial COI gene",
        )
        with TemporaryDirectory() as directory:
            path = Path(directory) / "blast.xml"
            path.write_text(xml, encoding="utf-8")
            result, _ = import_ncbi_blast_xml(path, self._dataset(), result_id="web-xml")

        self.assertEqual(result.hits[0].description, "Rhynchobatus sp. voucher ABC mitochondrial COI gene")
        self.assertEqual(result.hits[0].scientific_name, "Unknown")

    def test_unmatched_and_malformed_xml_are_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            bad = Path(directory) / "bad.xml"
            bad.write_text("<not-blast/>", encoding="utf-8")
            with self.assertRaises(BlastXmlImportError):
                preview_ncbi_blast_xml(bad, self._dataset())

    def test_changed_or_suffixed_fasta_headers_are_rejected_by_exact_matching(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "changed-header.xml"
            path.write_text(_XML.replace("sample1", "sample1 exported-description"), encoding="utf-8")
            preview = preview_ncbi_blast_xml(path, self._dataset())
            self.assertEqual(preview.unmatched_xml_query_ids, ("sample1 exported-description",))
            with self.assertRaisesRegex(BlastXmlImportError, "unmatched XML query IDs"):
                import_ncbi_blast_xml(path, self._dataset(), result_id="web-xml")

    def test_no_hit_query_is_preserved_as_a_matched_query_without_hits(self) -> None:
        no_hit = _XML.replace(
            "<Iteration_hits><Hit><Hit_num>1</Hit_num><Hit_id>gi|1|ref|ACC1|</Hit_id><Hit_def>Example sequence [Example species]</Hit_def><Hit_accession>ACC1</Hit_accession><Hit_len>4</Hit_len><Hit_hsps><Hsp><Hsp_num>1</Hsp_num><Hsp_bit-score>8.0</Hsp_bit-score><Hsp_score>4</Hsp_score><Hsp_evalue>1e-10</Hsp_evalue><Hsp_query-from>1</Hsp_query-from><Hsp_query-to>4</Hsp_query-to><Hsp_hit-from>1</Hsp_hit-from><Hsp_hit-to>4</Hsp_hit-to><Hsp_query-frame>0</Hsp_query-frame><Hsp_hit-frame>0</Hsp_hit-frame><Hsp_identity>4</Hsp_identity><Hsp_positive>4</Hsp_positive><Hsp_gaps>0</Hsp_gaps><Hsp_align-len>4</Hsp_align-len><Hsp_qseq>ATGC</Hsp_qseq><Hsp_hseq>ATGC</Hsp_hseq><Hsp_midline>||||</Hsp_midline></Hsp></Hit_hsps></Hit></Iteration_hits>",
            "<Iteration_hits></Iteration_hits>",
        )
        with TemporaryDirectory() as directory:
            path = Path(directory) / "no-hit.xml"
            path.write_text(no_hit, encoding="utf-8")
            result, preview = import_ncbi_blast_xml(path, self._dataset(), result_id="web-xml")
        self.assertEqual(preview.matched_query_ids, ("sample1",))
        self.assertEqual(result.hit_count(), 0)
        self.assertEqual(result.metadata["no_hit_query_ids"], ("sample1",))
