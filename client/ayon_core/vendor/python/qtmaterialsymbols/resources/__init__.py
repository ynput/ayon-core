import os
from typing import Optional

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))


def get_font_filepath(
    font_name: Optional[str] = "MaterialSymbolsOutlined-Regular"
) -> str:
    return os.path.join(CURRENT_DIR, f"{font_name}.ttf")


def get_mapping_filepath(
    font_name: Optional[str] = "MaterialSymbolsOutlined-Regular"
) -> str:
    return os.path.join(CURRENT_DIR, f"{font_name}.json")


def regenerate_mapping():
    """Regenerate the MaterialSymbolsOutlined.json file, assuming
    MaterialSymbolsOutlined.codepoints and the TrueType font file have been
    updated to support the new symbols.
    """
    import json
    jfile = get_mapping_filepath()
    cpfile = jfile.replace(".json", ".codepoints")
    with open(cpfile, "r") as cpf:
        codepoints = cpf.read()

    mapping = {}
    for cp in codepoints.splitlines():
        name, code = cp.split()
        mapping[name] = int(f"0x{code}", 16)

    with open(jfile, "w") as jf:
        json.dump(mapping, jf, indent=4)
