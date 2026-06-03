"""text edit"""

from __future__ import annotations

from ..variants import QTextEditVariants

from qtpy.QtCore import Qt
from qtpy.QtWidgets import QTextEdit

from ..style import get_ayon_style


class AYTextEdit(QTextEdit):
    """AYON styled text edit widget.

    Overrides Qt's stylesheet painting with AYONStyle custom rendering.

    Args:
        *args: Positional arguments passed to QTextEdit.
        **kwargs: Keyword arguments passed to QTextEdit.
    """

    Variants = QTextEditVariants

    def __init__(
        self,
        *args,
        variant: Variants = Variants.Default,
        **kwargs,
    ):
        """Initialize AYTextEdit widget.

        Args:
            *args: Positional arguments passed to QTextEdit.
            variant: Text edit variant.
            **kwargs: Keyword arguments passed to QTextEdit.
        """
        self._variant_str: str = variant.value
        super().__init__(*args, **kwargs)
        self.setStyle(get_ayon_style())
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
