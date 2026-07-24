import json
from pathlib import Path



# ==================================================
# Save selection
# ==================================================

def save_selection(
    reads,
    filepath
):
    """
    Save sample selection state.

    Parameters
    ----------
    reads : list
        List of SangerRead objects

    filepath : str or Path
        Output json path
    """


    selection = {}


    for read in reads:

        selection[read.filename] = (
            getattr(
                read,
                "selected",
                True
            )
        )


    with open(
        filepath,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            selection,
            f,
            indent=4,
            ensure_ascii=False
        )



# ==================================================
# Load selection
# ==================================================

def load_selection(
    reads,
    filepath
):
    """
    Load sample selection state.

    Parameters
    ----------
    reads : list
        List of SangerRead objects

    filepath : str or Path
        json file
    """


    filepath = Path(filepath)


    if not filepath.exists():

        return



    with open(
        filepath,
        "r",
        encoding="utf-8"
    ) as f:

        selection = json.load(f)



    for read in reads:

        if read.filename in selection:

            read.selected = (
                selection[
                    read.filename
                ]
            )