import subprocess
import shutil
from pathlib import Path

from tools.mafft_tool import resolve_mafft_executable



def run_mafft(
    input_fasta,
    output_fasta,
    *,
    mafft_executable=None,
):
    """
    Run MAFFT alignment.

    Parameters
    ----------
    input_fasta : str
        Input FASTA file

    output_fasta : str
        Output aligned FASTA file

    Returns
    -------
    bool
        Success or failure
    """



    try:

        command = [

            resolve_mafft_executable(mafft_executable, which=shutil.which),

            "--auto",

            str(input_fasta)

        ]



        with open(
            output_fasta,
            "w"
        ) as outfile:


            subprocess.run(

                command,

                stdout=outfile,

                stderr=subprocess.PIPE,

                text=True,

                check=True

            )



        return True



    except subprocess.CalledProcessError as e:


        print(
            "MAFFT error:"
        )


        print(
            e.stderr
        )


        return False



    except Exception as e:


        print(
            "MAFFT failed:"
        )


        print(e)


        return False
