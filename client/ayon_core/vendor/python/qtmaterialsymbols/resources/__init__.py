import os
from typing import Optional

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))


def get_font_filepath(filled: bool = False) -> str:
    if filled:
        font_name = "MaterialSymbolsOutlinedFilled.ttf"
    else:
        font_name = "MaterialSymbolsOutlined.ttf"
    return os.path.join(CURRENT_DIR, font_name)


def get_mapping_filepath() -> str:
    return os.path.join(CURRENT_DIR, "MaterialSymbolsOutlined.json")
