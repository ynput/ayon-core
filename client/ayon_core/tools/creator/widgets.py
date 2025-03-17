import re
import inspect

from qtpy import QtWidgets, QtCore, QtGui

import qtawesome

from ayon_core.pipeline.create import PRODUCT_NAME_ALLOWED_SYMBOLS
from ayon_core.tools.utils import ErrorMessageBox

if hasattr(QtGui, "QRegularExpressionValidator"):
    RegularExpressionValidatorClass = QtGui.QRegularExpressionValidator
    RegularExpressionClass = QtCore.QRegularExpression
else:
    RegularExpressionValidatorClass = QtGui.QRegExpValidator
    RegularExpressionClass = QtCore.QRegExp


class CreateErrorMessageBox(ErrorMessageBox):
    def __init__(
        self,
        product_type,
        product_name,
        folder_path,
        exc_msg,
        formatted_traceback,
        parent
    ):
        self._product_type = product_type
        self._product_name = product_name
        self._folder_path = folder_path
        self._exc_msg = exc_msg
        self._formatted_traceback = formatted_traceback
        super(CreateErrorMessageBox, self).__init__("Creation failed", parent)

    def _create_top_widget(self, parent_widget):
        label_widget = QtWidgets.QLabel(parent_widget)
        label_widget.setText(
            "<span style='font-size:18pt;'>Failed to create</span>"
        )
        return label_widget

    def _get_report_data(self):
        report_message = (
            "Failed to create Product: \"{product_name}\""
            " Type: \"{product_type}\""
            " in Folder: \"{folder_path}\""
            "\n\nError: {message}"
        ).format(
            product_name=self._product_name,
            product_type=self._product_type,
            folder_path=self._folder_path,
            message=self._exc_msg
        )
        if self._formatted_traceback:
            report_message += "\n\n{}".format(self._formatted_traceback)
        return [report_message]

    def _create_content(self, content_layout):
        item_name_template = (
            "<span style='font-weight:bold;'>{}:</span> {{}}<br>"
            "<span style='font-weight:bold;'>{}:</span> {{}}<br>"
            "<span style='font-weight:bold;'>{}:</span> {{}}<br>"
        ).format(
            "Product type",
            "Product name",
            "Folder"
        )
        exc_msg_template = "<span style='font-weight:bold'>{}</span>"

        line = self._create_line()
        content_layout.addWidget(line)

        item_name_widget = QtWidgets.QLabel(self)
        item_name_widget.setText(
            item_name_template.format(
                self._product_type, self._product_name, self._folder_path
            )
        )
        content_layout.addWidget(item_name_widget)

        message_label_widget = QtWidgets.QLabel(self)
        message_label_widget.setText(
            exc_msg_template.format(self.convert_text_for_html(self._exc_msg))
        )
        content_layout.addWidget(message_label_widget)

        if self._formatted_traceback:
            line_widget = self._create_line()
            tb_widget = self._create_traceback_widget(
                self._formatted_traceback
            )
            content_layout.addWidget(line_widget)
            content_layout.addWidget(tb_widget)


class ProductNameValidator(RegularExpressionValidatorClass):
    invalid = QtCore.Signal(set)
    pattern = "^[{}]*$".format(PRODUCT_NAME_ALLOWED_SYMBOLS)

    def __init__(self):
        reg = RegularExpressionClass(self.pattern)
        super(ProductNameValidator, self).__init__(reg)

    def validate(self, text, pos):
        results = super(ProductNameValidator, self).validate(text, pos)
        if results[0] == RegularExpressionValidatorClass.Invalid:
            self.invalid.emit(self.invalid_chars(text))
        return results

    def invalid_chars(self, text):
        invalid = set()
        re_valid = re.compile(self.pattern)
        for char in text:
            if char == " ":
                invalid.add("' '")
                continue
            if not re_valid.match(char):
                invalid.add(char)
        return invalid


class VariantLineEdit(QtWidgets.QLineEdit):
    report = QtCore.Signal(str)
    colors = {
        "empty": (QtGui.QColor("#78879b"), ""),
        "exists": (QtGui.QColor("#4E76BB"), "border-color: #4E76BB;"),
        "new": (QtGui.QColor("#7AAB8F"), "border-color: #7AAB8F;"),
    }

    def __init__(self, *args, **kwargs):
        super(VariantLineEdit, self).__init__(*args, **kwargs)

        validator = ProductNameValidator()
        self.setValidator(validator)
        self.setToolTip("Only alphanumeric characters (A-Z a-z 0-9), "
                        "'_' and '.' are allowed.")

        self._status_color = self.colors["empty"][0]

        anim = QtCore.QPropertyAnimation()
        anim.setTargetObject(self)
        anim.setPropertyName(b"status_color")
        anim.setEasingCurve(QtCore.QEasingCurve.InCubic)
        anim.setDuration(300)
        anim.setStartValue(QtGui.QColor("#C84747"))  # `Invalid` status color
        self.animation = anim

        validator.invalid.connect(self.on_invalid)

    def on_invalid(self, invalid):
        message = "Invalid character: %s" % ", ".join(invalid)
        self.report.emit(message)
        self.animation.stop()
        self.animation.start()

    def as_empty(self):
        self._set_border("empty")
        self.report.emit("Empty product name ..")

    def as_exists(self):
        self._set_border("exists")
        self.report.emit("Existing product, appending next version.")

    def as_new(self):
        self._set_border("new")
        self.report.emit("New product, creating first version.")

    def _set_border(self, status):
        qcolor, style = self.colors[status]
        self.animation.setEndValue(qcolor)
        self.setStyleSheet(style)

    def _get_status_color(self):
        return self._status_color

    def _set_status_color(self, color):
        self._status_color = color
        self.setStyleSheet("border-color: %s;" % color.name())

    status_color = QtCore.Property(
        QtGui.QColor, _get_status_color, _set_status_color
    )


class ProductTypeDescriptionWidget(QtWidgets.QWidget):
    """A product type description widget.

    Shows a product type icon, name and a help description.
    Used in creator header.

     _______________________
    |  ____                 |
    | |icon| PRODUCT TYPE   |
    | |____| help           |
    |_______________________|

    """

    SIZE = 35

    def __init__(self, parent=None):
        super(ProductTypeDescriptionWidget, self).__init__(parent=parent)

        icon_label = QtWidgets.QLabel(self)
        icon_label.setSizePolicy(
            QtWidgets.QSizePolicy.Maximum,
            QtWidgets.QSizePolicy.Maximum
        )

        # Add 4 pixel padding to avoid icon being cut off
        icon_label.setFixedWidth(self.SIZE + 4)
        icon_label.setFixedHeight(self.SIZE + 4)

        label_layout = QtWidgets.QVBoxLayout()
        label_layout.setSpacing(0)

        product_type_label = QtWidgets.QLabel(self)
        product_type_label.setObjectName("CreatorProductTypeLabel")
        product_type_label.setAlignment(
            QtCore.Qt.AlignBottom | QtCore.Qt.AlignLeft
        )

        help_label = QtWidgets.QLabel(self)
        help_label.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft)

        label_layout.addWidget(product_type_label)
        label_layout.addWidget(help_label)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        layout.addWidget(icon_label)
        layout.addLayout(label_layout)

        self._help_label = help_label
        self._product_type_label = product_type_label
        self._icon_label = icon_label

    def set_item(self, creator_plugin):
        """Update elements to display information of a product type item.

        Args:
            creator_plugin (dict): A product type item as registered with
                name, help and icon.

        Returns:
            None

        """
        if not creator_plugin:
            self._icon_label.setPixmap(None)
            self._product_type_label.setText("")
            self._help_label.setText("")
            return

        # Support a font-awesome icon
        icon_name = getattr(creator_plugin, "icon", None) or "info-circle"
        try:
            icon = qtawesome.icon("fa.{}".format(icon_name), color="white")
            pixmap = icon.pixmap(self.SIZE, self.SIZE)
        except Exception:
            print("BUG: Couldn't load icon \"fa.{}\"".format(str(icon_name)))
            # Create transparent pixmap
            pixmap = QtGui.QPixmap()
            pixmap.fill(QtCore.Qt.transparent)
        pixmap = pixmap.scaled(self.SIZE, self.SIZE)

        # Parse a clean line from the Creator's docstring
        docstring = inspect.getdoc(creator_plugin)
        creator_help = docstring.splitlines()[0] if docstring else ""

        self._icon_label.setPixmap(pixmap)
        self._product_type_label.setText(creator_plugin.product_type)
        self._help_label.setText(creator_help)
