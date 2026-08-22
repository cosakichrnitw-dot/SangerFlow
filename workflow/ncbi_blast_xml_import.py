"""Offline import of NCBI Web BLAST XML into the existing BLAST result model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re

from Bio.Blast import NCBIXML

from core.blast_result import BlastAnalysisMode, BlastHit, BlastResultDataset
from core.sequence_dataset import SequenceDataset


class BlastXmlImportError(ValueError):
    pass


@dataclass(frozen=True)
class BlastXmlImportPreview:
    matched_query_ids: tuple[str, ...]
    unmatched_xml_query_ids: tuple[str, ...]
    dataset_only_record_ids: tuple[str, ...]
    duplicate_query_ids: tuple[str, ...]
    program: str | None
    database: str | None


def preview_ncbi_blast_xml(filepath: str | Path, dataset: SequenceDataset) -> BlastXmlImportPreview:
    records = _parse(filepath)
    xml_ids = tuple(_query_id(record) for record in records)
    duplicate = tuple(sorted({query_id for query_id in xml_ids if xml_ids.count(query_id) > 1}))
    dataset_ids = set(dataset.sequence_ids)
    matched = tuple(query_id for query_id in xml_ids if query_id in dataset_ids)
    unmatched = tuple(query_id for query_id in xml_ids if query_id not in dataset_ids)
    return BlastXmlImportPreview(
        matched_query_ids=tuple(dict.fromkeys(matched)),
        unmatched_xml_query_ids=tuple(dict.fromkeys(unmatched)),
        dataset_only_record_ids=tuple(record_id for record_id in dataset.sequence_ids if record_id not in set(xml_ids)),
        duplicate_query_ids=duplicate,
        program=_text(getattr(records[0], "application", None)) if records else None,
        database=_text(getattr(records[0], "database", None)) if records else None,
    )


def import_ncbi_blast_xml(
    filepath: str | Path,
    dataset: SequenceDataset,
    *,
    result_id: str,
    name: str | None = None,
    allow_unmatched: bool = False,
) -> tuple[BlastResultDataset, BlastXmlImportPreview]:
    """Convert exact query-ID matched Web BLAST XML to ``BlastResultDataset``.

    The default refuses unmatched or duplicate XML query IDs so a user never
    unknowingly applies external hits to the wrong immutable Dataset.
    """

    if not isinstance(dataset, SequenceDataset):
        raise BlastXmlImportError("dataset must be a SequenceDataset")
    records = _parse(filepath)
    preview = preview_ncbi_blast_xml(filepath, dataset)
    if preview.duplicate_query_ids:
        raise BlastXmlImportError("duplicate XML query IDs: " + ", ".join(preview.duplicate_query_ids))
    if preview.unmatched_xml_query_ids and not allow_unmatched:
        raise BlastXmlImportError("unmatched XML query IDs: " + ", ".join(preview.unmatched_xml_query_ids))
    database = preview.database or "unknown"
    hits: list[BlastHit] = []
    for record in records:
        query_id = _query_id(record)
        if query_id not in dataset.sequence_ids:
            continue
        query_length = int(getattr(record, "query_length", 0) or 0)
        for alignment in getattr(record, "alignments", ()):
            hsps = getattr(alignment, "hsps", ())
            if not hsps:
                continue
            hsp = hsps[0]
            length = int(getattr(hsp, "align_length", 0) or 0)
            if length <= 0:
                continue
            title = _text(getattr(alignment, "hit_def", None)) or _text(getattr(alignment, "title", None)) or "Unknown"
            scientific_name = _scientific_name(title)
            query_coverage = min(100.0, (length / query_length * 100.0)) if query_length else 0.0
            hits.append(BlastHit(
                query_id=query_id,
                hit_accession=_text(getattr(alignment, "accession", None)) or "unknown",
                scientific_name=scientific_name,
                organism=scientific_name,
                description=title,
                identity=round(float(getattr(hsp, "identities", 0)) / length * 100.0, 3),
                query_coverage=round(query_coverage, 3),
                evalue=float(getattr(hsp, "expect", 0.0) or 0.0),
                alignment_length=length,
                bit_score=float(getattr(hsp, "bits", 0.0) or 0.0),
                database=database,
            ))
    source = Path(filepath)
    result = BlastResultDataset(
        result_id=result_id,
        name=name or f"Imported BLAST: {dataset.name}",
        parent_dataset_id=dataset.dataset_id,
        hits=tuple(hits),
        analysis_mode=BlastAnalysisMode.IDENTIFICATION,
        database=database,
        metadata={
            "source": "NCBI_WEB_XML_IMPORT",
            "source_filename": source.name,
            "import_timestamp": datetime.now(timezone.utc).isoformat(),
            "program": preview.program or "",
            "database": database,
            "matched_query_ids": preview.matched_query_ids,
            "no_hit_query_ids": tuple(
                query_id for query_id in preview.matched_query_ids
                if query_id not in {hit.query_id for hit in hits}
            ),
            "dataset_only_record_ids": preview.dataset_only_record_ids,
        },
    )
    return result, preview


def _parse(filepath: str | Path) -> tuple[object, ...]:
    path = Path(filepath)
    if not path.is_file():
        raise BlastXmlImportError("BLAST XML file does not exist")
    try:
        with path.open("r", encoding="utf-8") as handle:
            records = tuple(NCBIXML.parse(handle))
    except Exception as error:
        raise BlastXmlImportError(f"invalid or unsupported NCBI BLAST XML: {error}") from error
    if not records:
        raise BlastXmlImportError("BLAST XML contains no query records")
    return records


def _query_id(record: object) -> str:
    value = _text(getattr(record, "query", None))
    if not value:
        raise BlastXmlImportError("BLAST XML query ID is empty")
    return value


def _scientific_name(title: str) -> str:
    """Extract only defensible taxonomy from an NCBI XML title.

    Traditional BLAST XML does not expose a separate organism element for each
    hit.  We therefore prefer NCBI's terminal ``[organism]`` annotation, then
    recognise a deliberately small set of unambiguous title forms.  We never
    infer a binomial merely from the first two words of an arbitrary title.
    ``Unknown`` is the result-model safe value; metadata application converts
    it to an empty Scientific Name while retaining the complete Best Hit.
    """

    bracketed = re.search(r"\[([^\[\]]+)\]\s*$", title)
    if bracketed:
        value = _validated_taxon(bracketed.group(1))
        if value is not None:
            return value

    # NCBI reference titles commonly begin with a taxon followed by a clear
    # biological descriptor.  Accept only that known grammar, never a generic
    # free-text title.  Preserve a valid trinomial rather than truncating it.
    leading = re.match(
        r"^(?P<taxon>[A-Z][a-z-]+\s+[a-z][a-z-]+(?:\s+[a-z][a-z-]+)?)"
        r"\s+(?=(?:mitochondr(?:ion|ial)|complete genome|cytochrome|COI\b|"
        r"16S\b|18S\b|isolate\b|voucher\b|strain\b))",
        title,
        flags=re.IGNORECASE,
    )
    if leading:
        value = _validated_taxon(leading.group("taxon"))
        if value is not None:
            return value
    return "Unknown"


def _validated_taxon(value: str) -> str | None:
    normalized = " ".join(value.split())
    lowered = normalized.casefold()
    if any(marker in lowered for marker in ("uncultured", "environmental", "unidentified", "unknown")):
        return None
    # Rank qualifiers are meaningful but do not establish a species-level
    # scientific name.  Do not manufacture one by discarding the qualifier.
    if re.search(r"(?:^|\s)(?:sp\.|cf\.|aff\.)(?:\s|$)", normalized, flags=re.IGNORECASE):
        return None
    if re.fullmatch(r"[A-Z][a-z-]+\s+[a-z][a-z-]+(?:\s+[a-z][a-z-]+)?", normalized):
        return normalized
    return None


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None
