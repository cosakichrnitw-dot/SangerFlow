from Bio.Blast import NCBIWWW
from Bio.Blast import NCBIXML
from Bio import Entrez
from Bio import SeqIO

import re
import ssl
import certifi
import warnings

DEFAULT_HITS = 3

# ==================================================
# Legacy TLS compatibility
# ==================================================

def enable_legacy_certifi_ssl_context() -> None:
    """Opt in to the historical process-wide SSL workaround.

    Studio uses ``workflow.ncbi_blast_service`` instead, which supplies a
    certifi-backed context per request.  Importing this legacy module must not
    silently mutate HTTPS behavior for unrelated application code.
    """

    warnings.warn(
        "enable_legacy_certifi_ssl_context() changes Python's global HTTPS "
        "context and is retained only for legacy callers.",
        DeprecationWarning,
        stacklevel=2,
    )
    ssl._create_default_https_context = lambda: ssl.create_default_context(
        cafile=certifi.where()
    )

# ==================================================
# Extract species name
# ==================================================

def extract_species(title):

    match = re.search(
        r"\|\s*([A-Z][a-z]+ [a-z]+)",
        title
    )

    if match:
        return match.group(1)

    words = title.split()

    for i in range(len(words)-1):

        if (
            words[i][0].isupper()
            and words[i+1][0].islower()
        ):

            return words[i] + " " + words[i+1]

    return "Unknown"


# ==================================================
# Extract accession
# ==================================================

def extract_accession(title):

    m = re.search(
        r"\|([A-Z]{1,3}_?[A-Z0-9]+\.[0-9]+)\|",
        title
    )

    if m:
        return m.group(1)

    return ""


# ==================================================
# Single BLAST
# ==================================================

def blast_sequence(
    sequence,
    database="nt",
    program="blastn",
    email=None,
    max_hits=DEFAULT_HITS
):

    if email:
        Entrez.email = email

    result_handle = NCBIWWW.qblast(
        program,
        database,
        sequence
    )

    blast_record = NCBIXML.read(
        result_handle
    )

    results = []

    for alignment in blast_record.alignments[:max_hits]:

        hsp = alignment.hsps[0]

        identity = (
            hsp.identities /
            hsp.align_length *
            100
        )

        coverage = (
            hsp.align_length /
            len(sequence) *
            100
        )

        results.append({

            "species":
                extract_species(
                    alignment.title
                ),

            "identity":
                round(identity,3),

            "coverage":
                round(coverage,3),

            "alignment_length":
                hsp.align_length,

            "e_value":
                hsp.expect,

            "accession":
                extract_accession(
                    alignment.title
                ),

            "title":
                alignment.title

        })

    return results


# ==================================================
# Folder BLAST
# ==================================================

def blast_folder(
    reads,
    database="nt",
    program="blastn",
    email=None,
    max_hits=DEFAULT_HITS
):

    all_results = []

    for read in reads:

        print(
            f"Running BLAST: {read.filename}"
        )

        try:

            results = blast_sequence(

                read.sequence,

                database=database,

                program=program,

                email=email,

                max_hits=max_hits

            )

            for result in results:

                result["sample"] = read.filename

                all_results.append(
                    result
                )

        except Exception as e:

            print(
                f"BLAST failed: {read.filename}"
            )

            all_results.append({

                "sample":
                    read.filename,

                "species":
                    "ERROR",

                "identity":
                    0,

                "coverage":
                    0,

                "alignment_length":
                    0,

                "e_value":
                    None,

                "accession":
                    "",

                "title":
                    str(e)

            })

    return all_results


# ==================================================
# FASTA BLAST
# ==================================================

def blast_fasta(
    fasta_file,
    database="nt",
    program="blastn",
    email=None,
    max_hits=DEFAULT_HITS
):

    all_results = []

    for record in SeqIO.parse(
        fasta_file,
        "fasta"
    ):

        print(
            f"Running BLAST: {record.id}"
        )

        results = blast_sequence(

            str(record.seq),

            database=database,

            program=program,

            email=email,

            max_hits=max_hits

        )

        for result in results:

            result["sample"] = record.id

            all_results.append(
                result
            )

    return all_results
