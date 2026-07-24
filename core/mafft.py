import subprocess
from pathlib import Path



def run_mafft(
    input_fasta,
    output_fasta
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

            "mafft",

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