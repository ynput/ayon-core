"""Widget displaying publish timing information with detailed breakdown."""

import qtawesome
from qtpy import QtCore, QtWidgets


class PublishTimeWidget(QtWidgets.QWidget):
    """Widget displaying total publish time.

    Shows the total publish time next to the "Finished" label in the publish
    report overlay.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        time_icon_label = QtWidgets.QLabel(self)
        clock_icon = qtawesome.icon("fa.clock-o")
        time_icon_label.setPixmap(clock_icon.pixmap(16, 16))
        time_icon_label.setObjectName("PublishTimeIcon")

        time_label = QtWidgets.QLabel(self)
        time_label.setObjectName("PublishTimeLabel")
        time_label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 0, 0)
        layout.setSpacing(5)
        layout.addWidget(time_icon_label, 0)
        layout.addWidget(time_label, 0)

        self._time_label = time_label
        self._time_icon_label = time_icon_label

        self.setVisible(False)

    def set_timing_data(self, timing_data):
        """Set timing data and update display.

        Args:
            timing_data (dict): Dictionary containing:
                - total_time (float): Total publish time in seconds
        """
        if timing_data is None:
            self.setVisible(False)
            return

        total_time = timing_data.get("total_time", 0)
        self._time_label.setText(self._format_time(total_time))
        self.setVisible(True)

    def _format_time(self, seconds):
        """Format time in seconds to human-readable string.

        Args:
            seconds (float): Time in seconds

        Returns:
            str: Formatted time string (e.g., "1m 23s", "45s", "1.2s")
        """
        if seconds < 1:
            return f"{seconds:.1f}s"

        minutes = int(seconds // 60)
        remaining_seconds = int(seconds % 60)

        if minutes > 0:
            return f"{minutes}m {remaining_seconds}s"
        return f"{remaining_seconds}s"

    def clear(self):
        """Clear timing data and hide widget."""
        self._time_label.setText("")
        self.setVisible(False)
