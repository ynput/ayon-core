from __future__ import annotations

from typing import Optional

from qtpy.QtCore import Qt
from qtpy.QtWidgets import QWidget

from ..style_types import get_ayon_style
from ..utils import clear_layout
from .label import AYLabel
from .layouts import AYHBoxLayout


class AYEntityPathSegment(AYLabel):
    def __init__(
        self,
        text,
        parent=None,
        variant: AYLabel.Variants = AYLabel.Variants.Default,
    ):
        super().__init__(text, dim=True, rel_text_size=-2, parent=parent)
        get_ayon_style().style_widget(self)
        self.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self._variant_str: str = variant.value
        self.setFixedSize(
            self.fontMetrics().size(self.alignment(), self.text()),
        )


class AYEntityPath(QWidget):
    def __init__(
        self,
        path: str = "",
        simple: bool = False,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setStyle(get_ayon_style())
        self._path = path
        self._path_segments = []
        self._entity_id = None
        self._simple = simple

        lyt = AYHBoxLayout(self, spacing=1)
        self.setLayout(lyt)

        if self._simple:
            self._label = AYLabel(
                self._path,
                dim=True,
                rel_text_size=-2,
                elide_mode=Qt.TextElideMode.ElideMiddle,
            )
            lyt.addWidget(self._label)
            lyt.addStretch(100)

        self.entity_path = path

    @property
    def entity_path(self):
        return self._path

    @entity_path.setter
    def entity_path(self, value):
        self._path = value
        if not self._simple:
            self._path_segments = value.split("/")
            self._build()
        else:
            self._label.setText(self._path.replace("/", " / "))

    def _build(self):
        lyt = self.layout()
        if not lyt:
            return

        clear_layout(lyt)
        for p in self._path_segments:
            w = AYEntityPathSegment(p, parent=self)
            lyt.addWidget(w)
            if p != self._path_segments[-1]:
                lyt.addWidget(AYEntityPathSegment("/", parent=self))
        lyt.addStretch(100)
