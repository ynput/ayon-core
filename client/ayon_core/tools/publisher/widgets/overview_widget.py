from qtpy import QtWidgets, QtCore

from .border_label_widget import BorderedLabelWidget

from .card_view_widgets import InstanceCardView
from .list_view_widgets import InstanceListView
from .widgets import (
    ProductAttributesWidget,
    CreateInstanceBtn,
    RemoveInstanceBtn,
    ChangeViewBtn,
)
from .create_widget import CreateWidget


class OverviewWidget(QtWidgets.QFrame):
    active_changed = QtCore.Signal()
    instance_context_changed = QtCore.Signal()
    create_requested = QtCore.Signal()
    convert_requested = QtCore.Signal()
    publish_tab_requested = QtCore.Signal()

    anim_end_value = 200
    anim_duration = 200

    def __init__(self, controller, parent):
        super(OverviewWidget, self).__init__(parent)

        self._refreshing_instances = False
        self._controller = controller

        product_content_widget = QtWidgets.QWidget(self)

        create_widget = CreateWidget(controller, product_content_widget)

        # --- Created Products/Instances ---
        # Common widget for creation and overview
        product_views_widget = BorderedLabelWidget(
            "Products to publish",
            product_content_widget
        )

        product_view_cards = InstanceCardView(controller, product_views_widget)
        product_list_view = InstanceListView(controller, product_views_widget)

        product_views_layout = QtWidgets.QStackedLayout()
        product_views_layout.addWidget(product_view_cards)
        product_views_layout.addWidget(product_list_view)
        product_views_layout.setCurrentWidget(product_view_cards)

        # Buttons at the bottom of product view
        create_btn = CreateInstanceBtn(product_views_widget)
        delete_btn = RemoveInstanceBtn(product_views_widget)
        change_view_btn = ChangeViewBtn(product_views_widget)

        # --- Overview ---
        # pProduct details widget
        product_attributes_wrap = BorderedLabelWidget(
            "Publish options", product_content_widget
        )
        product_attributes_widget = ProductAttributesWidget(
            controller, product_attributes_wrap
        )
        product_attributes_wrap.set_center_widget(product_attributes_widget)

        # Layout of buttons at the bottom of product view
        product_view_btns_layout = QtWidgets.QHBoxLayout()
        product_view_btns_layout.setContentsMargins(0, 5, 0, 0)
        product_view_btns_layout.addWidget(create_btn)
        product_view_btns_layout.addSpacing(5)
        product_view_btns_layout.addWidget(delete_btn)
        product_view_btns_layout.addStretch(1)
        product_view_btns_layout.addWidget(change_view_btn)

        # Layout of view and buttons
        # - widget 'product_view_widget' is necessary
        # - only layout won't be resized automatically to minimum size hint
        #   on child resize request!
        product_view_widget = QtWidgets.QWidget(product_views_widget)
        product_view_layout = QtWidgets.QVBoxLayout(product_view_widget)
        product_view_layout.setContentsMargins(0, 0, 0, 0)
        product_view_layout.addLayout(product_views_layout, 1)
        product_view_layout.addLayout(product_view_btns_layout, 0)

        product_views_widget.set_center_widget(product_view_widget)

        # Whole product layout with attributes and details
        product_content_layout = QtWidgets.QHBoxLayout(product_content_widget)
        product_content_layout.setContentsMargins(0, 0, 0, 0)
        product_content_layout.addWidget(create_widget, 7)
        product_content_layout.addWidget(product_views_widget, 3)
        product_content_layout.addWidget(product_attributes_wrap, 7)

        # Product frame layout
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(product_content_widget, 1)

        change_anim = QtCore.QVariantAnimation()
        change_anim.setStartValue(float(0))
        change_anim.setEndValue(float(self.anim_end_value))
        change_anim.setDuration(self.anim_duration)
        change_anim.setEasingCurve(QtCore.QEasingCurve.InOutQuad)

        # --- Calbacks for instances/products view ---
        create_btn.clicked.connect(self._on_create_clicked)
        delete_btn.clicked.connect(self._on_delete_clicked)
        change_view_btn.clicked.connect(self._on_change_view_clicked)

        change_anim.valueChanged.connect(self._on_change_anim)
        change_anim.finished.connect(self._on_change_anim_finished)

        # Selection changed
        product_list_view.selection_changed.connect(
            self._on_product_change
        )
        product_list_view.double_clicked.connect(
            self.publish_tab_requested
        )
        product_view_cards.selection_changed.connect(
            self._on_product_change
        )
        product_view_cards.double_clicked.connect(
            self.publish_tab_requested
        )
        # Active instances changed
        product_list_view.active_changed.connect(
            self._on_active_changed
        )
        product_view_cards.active_changed.connect(
            self._on_active_changed
        )
        # Instance context has changed
        product_attributes_widget.instance_context_changed.connect(
            self._on_instance_context_change
        )
        product_attributes_widget.convert_requested.connect(
            self._on_convert_requested
        )

        # --- Controller callbacks ---
        controller.event_system.add_callback(
            "publish.process.started", self._on_publish_start
        )
        controller.event_system.add_callback(
            "controller.reset.started", self._on_controller_reset_start
        )
        controller.event_system.add_callback(
            "publish.reset.finished", self._on_publish_reset
        )
        controller.event_system.add_callback(
            "instances.refresh.finished", self._on_instances_refresh
        )

        self._product_content_widget = product_content_widget
        self._product_content_layout = product_content_layout

        self._product_view_cards = product_view_cards
        self._product_list_view = product_list_view
        self._product_views_layout = product_views_layout

        self._create_btn = create_btn
        self._delete_btn = delete_btn

        self._product_attributes_widget = product_attributes_widget
        self._create_widget = create_widget
        self._product_views_widget = product_views_widget
        self._product_attributes_wrap = product_attributes_wrap

        self._change_anim = change_anim

        # Start in create mode
        self._current_state = "create"
        product_attributes_wrap.setVisible(False)

    def make_sure_animation_is_finished(self):
        if self._change_anim.state() == QtCore.QAbstractAnimation.Running:
            self._change_anim.stop()
        self._on_change_anim_finished()

    def set_state(self, new_state, animate):
        if new_state == self._current_state:
            return

        self._current_state = new_state

        if not animate:
            self.make_sure_animation_is_finished()
            return

        if new_state == "create":
            direction = QtCore.QAbstractAnimation.Backward
        else:
            direction = QtCore.QAbstractAnimation.Forward
        self._change_anim.setDirection(direction)

        if (
            self._change_anim.state() != QtCore.QAbstractAnimation.Running
        ):
            self._start_animation()

    def _start_animation(self):
        views_geo = self._product_views_widget.geometry()
        layout_spacing = self._product_content_layout.spacing()
        if self._create_widget.isVisible():
            create_geo = self._create_widget.geometry()
            product_geo = QtCore.QRect(create_geo)
            product_geo.moveTop(views_geo.top())
            product_geo.moveLeft(views_geo.right() + layout_spacing)
            self._product_attributes_wrap.setVisible(True)

        elif self._product_attributes_wrap.isVisible():
            product_geo = self._product_attributes_wrap.geometry()
            create_geo = QtCore.QRect(product_geo)
            create_geo.moveTop(views_geo.top())
            create_geo.moveRight(views_geo.left() - (layout_spacing + 1))
            self._create_widget.setVisible(True)
        else:
            self._change_anim.start()
            return

        while self._product_content_layout.count():
            self._product_content_layout.takeAt(0)
        self._product_views_widget.setGeometry(views_geo)
        self._create_widget.setGeometry(create_geo)
        self._product_attributes_wrap.setGeometry(product_geo)

        self._change_anim.start()

    def get_product_views_geo(self):
        parent = self._product_views_widget.parent()
        global_pos = parent.mapToGlobal(self._product_views_widget.pos())
        return QtCore.QRect(
            global_pos.x(),
            global_pos.y(),
            self._product_views_widget.width(),
            self._product_views_widget.height()
        )

    def has_items(self):
        view = self._product_views_layout.currentWidget()
        return view.has_items()

    def _on_create_clicked(self):
        """Pass signal to parent widget which should care about changing state.

        We don't change anything here until the parent will care about it.
        """

        self.create_requested.emit()

    def _on_delete_clicked(self):
        instance_ids, _, _ = self.get_selected_items()

        # Ask user if he really wants to remove instances
        dialog = QtWidgets.QMessageBox(self)
        dialog.setIcon(QtWidgets.QMessageBox.Question)
        dialog.setWindowTitle("Are you sure?")
        if len(instance_ids) > 1:
            msg = (
                "Do you really want to remove {} instances?"
            ).format(len(instance_ids))
        else:
            msg = (
                "Do you really want to remove the instance?"
            )
        dialog.setText(msg)
        dialog.setStandardButtons(
            QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel
        )
        dialog.setDefaultButton(QtWidgets.QMessageBox.Ok)
        dialog.setEscapeButton(QtWidgets.QMessageBox.Cancel)
        dialog.exec_()
        # Skip if OK was not clicked
        if dialog.result() == QtWidgets.QMessageBox.Ok:
            instance_ids = set(instance_ids)
            self._controller.remove_instances(instance_ids)

    def _on_change_view_clicked(self):
        self._change_view_type()

    def _on_product_change(self, *_args):
        # Ignore changes if in middle of refreshing
        if self._refreshing_instances:
            return

        instance_ids, context_selected, convertor_identifiers = (
            self.get_selected_items()
        )

        # Disable delete button if nothing is selected
        self._delete_btn.setEnabled(len(instance_ids) > 0)

        instances_by_id = self._controller.instances
        instances = [
            instances_by_id[instance_id]
            for instance_id in instance_ids
        ]
        self._product_attributes_widget.set_current_instances(
            instances, context_selected, convertor_identifiers
        )

    def _on_active_changed(self):
        if self._refreshing_instances:
            return
        self.active_changed.emit()

    def _on_change_anim(self, value):
        self._create_widget.setVisible(True)
        self._product_attributes_wrap.setVisible(True)
        layout_spacing = self._product_content_layout.spacing()

        content_width = (
            self._product_content_widget.width() - (layout_spacing * 2)
        )
        content_height = self._product_content_widget.height()
        views_width = max(
            int(content_width * 0.3),
            self._product_views_widget.minimumWidth()
        )
        width = content_width - views_width
        # Visible widths of other widgets
        product_attrs_width = int((float(width) / self.anim_end_value) * value)
        create_width = width - product_attrs_width

        views_geo = QtCore.QRect(
            create_width + layout_spacing, 0,
            views_width, content_height
        )
        create_geo = QtCore.QRect(0, 0, width, content_height)
        product_attrs_geo = QtCore.QRect(create_geo)
        create_geo.moveRight(views_geo.left() - (layout_spacing + 1))
        product_attrs_geo.moveLeft(views_geo.right() + layout_spacing)

        self._product_views_widget.setGeometry(views_geo)
        self._create_widget.setGeometry(create_geo)
        self._product_attributes_wrap.setGeometry(product_attrs_geo)

    def _on_change_anim_finished(self):
        self._change_visibility_for_state()
        self._product_content_layout.addWidget(self._create_widget, 7)
        self._product_content_layout.addWidget(self._product_views_widget, 3)
        self._product_content_layout.addWidget(self._product_attributes_wrap, 7)

    def _change_visibility_for_state(self):
        self._create_widget.setVisible(
            self._current_state == "create"
        )
        self._product_attributes_wrap.setVisible(
            self._current_state == "publish"
        )

    def _on_instance_context_change(self):
        current_idx = self._product_views_layout.currentIndex()
        for idx in range(self._product_views_layout.count()):
            if idx == current_idx:
                continue
            widget = self._product_views_layout.widget(idx)
            if widget.refreshed:
                widget.set_refreshed(False)

        current_widget = self._product_views_layout.widget(current_idx)
        current_widget.refresh_instance_states()

        self.instance_context_changed.emit()

    def _on_convert_requested(self):
        self.convert_requested.emit()

    def get_selected_items(self):
        """Selected items in current view widget.

        Returns:
            tuple[list[str], bool, list[str]]: Selected items. List of
                instance ids, context is selected, list of selected legacy
                convertor plugins.
        """

        view = self._product_views_layout.currentWidget()
        return view.get_selected_items()

    def get_selected_legacy_convertors(self):
        """Selected legacy convertor identifiers.

        Returns:
            list[str]: Selected legacy convertor identifiers.
                Example: ['io.openpype.creators.houdini.legacy']
        """

        _, _, convertor_identifiers = self.get_selected_items()
        return convertor_identifiers

    def _change_view_type(self):
        idx = self._product_views_layout.currentIndex()
        new_idx = (idx + 1) % self._product_views_layout.count()

        old_view = self._product_views_layout.currentWidget()
        new_view = self._product_views_layout.widget(new_idx)

        if not new_view.refreshed:
            new_view.refresh()
            new_view.set_refreshed(True)
        else:
            new_view.refresh_instance_states()

        instance_ids, context_selected, convertor_identifiers = (
            old_view.get_selected_items()
        )
        new_view.set_selected_items(
            instance_ids, context_selected, convertor_identifiers
        )

        self._product_views_layout.setCurrentIndex(new_idx)

        self._on_product_change()

    def _refresh_instances(self):
        if self._refreshing_instances:
            return

        self._refreshing_instances = True

        for idx in range(self._product_views_layout.count()):
            widget = self._product_views_layout.widget(idx)
            widget.set_refreshed(False)

        view = self._product_views_layout.currentWidget()
        view.refresh()
        view.set_refreshed(True)

        self._refreshing_instances = False

        # Force to change instance and refresh details
        self._on_product_change()

    def _on_publish_start(self):
        """Publish started."""

        self._create_btn.setEnabled(False)
        self._product_attributes_wrap.setEnabled(False)
        for idx in range(self._product_views_layout.count()):
            widget = self._product_views_layout.widget(idx)
            widget.set_active_toggle_enabled(False)

    def _on_controller_reset_start(self):
        """Controller reset started."""

        for idx in range(self._product_views_layout.count()):
            widget = self._product_views_layout.widget(idx)
            widget.set_active_toggle_enabled(True)

    def _on_publish_reset(self):
        """Context in controller has been reseted."""

        self._create_btn.setEnabled(True)
        self._product_attributes_wrap.setEnabled(True)
        self._product_content_widget.setEnabled(self._controller.host_is_valid)

    def _on_instances_refresh(self):
        """Controller refreshed instances."""

        self._refresh_instances()

        # Give a change to process Resize Request
        QtWidgets.QApplication.processEvents()
        # Trigger update geometry of
        widget = self._product_views_layout.currentWidget()
        widget.updateGeometry()
