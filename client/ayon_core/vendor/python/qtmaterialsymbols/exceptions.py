class ApplicationNotRunning(Exception):
    """Raised when the QApplication is not running."""
    pass


class FontError(Exception):
    """Raised when there is an issue with font."""
    pass
