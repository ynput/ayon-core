import os
from typing import Optional

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))


def get_font_filepath(
    font_name: Optional[str] = "MaterialSymbolsOutlined"
) -> str:
    return os.path.join(CURRENT_DIR, f"{font_name}.ttf")


def get_mapping_filepath(
    font_name: Optional[str] = "MaterialSymbolsOutlined"
) -> str:
    return os.path.join(CURRENT_DIR, f"{font_name}.json")
