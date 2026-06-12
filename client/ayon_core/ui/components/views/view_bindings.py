"""Glue between :class:`View` settings and the widget/model stack.

The :class:`AYViewSelector` is intentionally generic: it knows about a
:class:`ViewManager` and a single opaque :class:`ViewBindings` object.
The bindings know how to *apply* a captured :class:`ViewSettings` to
the concrete widget instances the consumer app has wired up, and how
to *capture* the live widget state back into a :class:`ViewSettings`.

All adapter components (table view, card view, filter proxy, slicer)
are optional — when ``None`` the relevant slice of the settings is
treated as a no-op on apply and an empty value on capture.

Order of operations on :meth:`ViewBindings.apply`:

    columns → filter → grouping/sort → row height → extras

Capture is the inverse: it walks the live widgets and assembles a
fresh :class:`ViewSettings` instance.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from ..table_model import PaginatedTableModel

from .data_models import (
    ColumnState,
    FilterDef,
    GroupingDef,
    ViewSettings,
)

log = logging.getLogger(__name__)

# Callable invoked when a non-fatal error happens inside apply/capture.
# Signature is ``(stage: str, exc: BaseException) -> None`` where
# ``stage`` is a short identifier such as ``"column_state"`` or
# ``"filter_apply"`` allowing the caller to surface meaningful messages.
ErrorCallback = Callable[[str, BaseException], None]


@dataclass
class ViewBindings:
    """Adapter wiring a :class:`View` to a concrete widget stack.

    Only :attr:`model` is required.  Every other widget is optional and
    skipped when ``None``.

    Attributes:
        model: The shared :class:`PaginatedTableModel` instance.
        table_view: Optional :class:`AYTableView` for column state.
        card_view: Optional :class:`AYCardView` for row-height /
            card-size mapping.
        filter_bar: Optional :class:`AYTableFilter` exposing
            :meth:`get_criteria` / :meth:`set_criteria`.
        slicer: Optional :class:`AYSlicer` (opaque; round-tripped via
            :attr:`ViewSettings.extra`).
        on_extra_apply: Optional callback ``(extra: dict) -> None``
            invoked at the end of :meth:`apply` with the un-claimed
            :attr:`ViewSettings.extra` dict.  Lets the consumer wire
            up custom settings (``showProducts``, ``gridHeight``, …)
            without subclassing.
        on_extra_capture: Optional callback ``() -> dict`` invoked
            during :meth:`capture` to merge consumer-specific keys
            back into :attr:`ViewSettings.extra`.
        on_error: Optional callback
            ``(stage: str, exc: BaseException) -> None`` invoked for
            non-fatal failures during :meth:`apply` and :meth:`capture`
            so the host UI can surface a message.  When ``None`` the
            failure is only logged.
    """

    model: PaginatedTableModel
    table_view: Any | None = None
    card_view: Any | None = None
    filter_bar: Any | None = None
    on_extra_apply: Any | None = None
    on_extra_capture: Any | None = None
    on_error: ErrorCallback | None = None
    # Keys not consumed by built-in handlers; preserved verbatim for
    # roundtrip even when the consumer does not supply a callback.
    _untouched_extra: dict[str, Any] = field(default_factory=dict)
    # Last applied filter operator — preserved across capture so an
    # incoming ``operator="or"`` is not silently downgraded to ``"and"``
    # when AYTableFilter does not yet expose operator semantics.
    _last_filter_operator: str = "and"
    # Last applied grouping — round-tripped verbatim because no
    # grouping widget exists yet.
    _last_grouping: GroupingDef = field(default_factory=GroupingDef)

    # ------------------------------------------------------------------
    # Error reporting
    # ------------------------------------------------------------------

    def _report_error(self, stage: str, exc: BaseException) -> None:
        """Log the failure and forward it to :attr:`on_error` when set.

        The log line always uses ``logging.ERROR`` so problems are
        visible without enabling debug output.  The optional
        :attr:`on_error` callback receives the same ``(stage, exc)``
        pair so the host UI can surface a message to the user.

        Args:
            stage: Short identifier of the failing operation
                (e.g. ``"column_state"``).
            exc: The caught exception.
        """
        log.exception("ViewBindings %s failed: %s", stage, exc)
        if self.on_error is None:
            return
        try:
            self.on_error(stage, exc)
        except Exception:
            log.exception("on_error callback raised while handling %s", stage)

    # ------------------------------------------------------------------
    # Apply
    # ------------------------------------------------------------------

    def apply(self, settings: ViewSettings) -> None:
        """Apply *settings* to every wired widget.

        Args:
            settings: The :class:`ViewSettings` to apply.

        Raises:
            TypeError: If *settings* is not a :class:`ViewSettings`.
        """
        if not isinstance(settings, ViewSettings):
            raise TypeError(
                f"apply expected ViewSettings, got {type(settings).__name__}"
            )

        # 1. Columns + sort live on the model.  When the consumer also
        #    wired a table view, widths and visibility are the header's
        #    responsibility — strip them from the model payload so the
        #    model only owns ordering and sort, avoiding cross-view
        #    contamination of the shared TableColumn catalog.
        model_settings = self._settings_for_model(settings)
        self.model.apply_settings(model_settings)

        # 1b. Column hidden state / pinning / width live on the header.
        if self.table_view is not None and settings.columns:
            try:
                self.table_view.set_column_state(settings.columns)
            except Exception as exc:
                self._report_error("column_state_apply", exc)

        # 2. Filter — opaque condition dicts in the View are converted
        #    to FilterCriterion via FilterCriterion.from_def.  The
        #    operator is stashed for capture() because AYTableFilter
        #    does not yet expose AND/OR semantics.
        self._last_filter_operator = settings.filter.operator or "and"
        if self.filter_bar is not None:
            self._apply_filter(settings.filter)

        # 3. Grouping — placeholder for future grouping widget; we keep
        #    the data on the binding so capture() can re-emit it.
        self._last_grouping = copy.deepcopy(settings.grouping)

        # 4. Row height — applied to the table view (real per-row
        #    override) and best-effort on the card view.
        self._apply_row_height(settings.row_height)

        # 5. Extras — let the consumer handle the un-claimed slice.
        self._untouched_extra = dict(settings.extra)
        if self.on_extra_apply is not None and settings.extra:
            try:
                self.on_extra_apply(settings.extra)
            except Exception as exc:
                self._report_error("on_extra_apply", exc)

    # ------------------------------------------------------------------
    # Capture
    # ------------------------------------------------------------------

    def capture(self) -> ViewSettings:
        """Build a fresh :class:`ViewSettings` from the live widget state.

        Returns:
            A new :class:`ViewSettings` instance.
        """
        settings = self.model.capture_settings()

        # Column visibility/pinning come from the header, overriding the
        # plain key/width snapshot returned by the model.
        if self.table_view is not None:
            try:
                header_states = self.table_view.get_column_state()
            except Exception as exc:
                self._report_error("column_state_capture", exc)
                header_states = []
            if header_states:
                settings.columns = list(header_states)

        # Filter conditions.
        if self.filter_bar is not None:
            settings.filter = self._capture_filter()

        # Grouping (round-tripped verbatim; no widget yet).
        settings.grouping = copy.deepcopy(self._last_grouping)

        # Row height.
        settings.row_height = self._capture_row_height(settings.row_height)

        # Extras.
        extras: dict[str, Any] = dict(self._untouched_extra)
        if self.on_extra_capture is not None:
            try:
                emitted = self.on_extra_capture() or {}
            except Exception as exc:
                self._report_error("on_extra_capture", exc)
                emitted = {}
            if isinstance(emitted, dict):
                extras.update(emitted)
        settings.extra = extras

        return settings

    # ------------------------------------------------------------------
    # Settings helpers
    # ------------------------------------------------------------------

    def _settings_for_model(self, settings: ViewSettings) -> ViewSettings:
        """Return a copy of *settings* with widths stripped for the model.

        The model and the table-view header both consume
        ``settings.columns``.  Letting both write widths mutates the
        shared :class:`TableColumn` catalog and can leak widths across
        views that share the same model.  This helper hands the model a
        copy where every column ``width`` is ``None`` so only the
        header (via :meth:`AYTableView.set_column_state`) ever writes
        widths.

        Args:
            settings: The original :class:`ViewSettings`.

        Returns:
            A shallow-cloned :class:`ViewSettings` whose
            :class:`ColumnState` instances have ``width=None`` when a
            table view is wired; the original object otherwise.
        """
        if self.table_view is None:
            return settings
        stripped_cols = [
            ColumnState(
                name=c.name,
                visible=c.visible,
                pinned=c.pinned,
                width=None,
            )
            for c in settings.columns
        ]
        return ViewSettings(
            columns=stripped_cols,
            sort_by=settings.sort_by,
            sort_desc=settings.sort_desc,
            row_height=settings.row_height,
            grouping=settings.grouping,
            filter=settings.filter,
            extra=settings.extra,
        )

    # ------------------------------------------------------------------
    # Filter helpers
    # ------------------------------------------------------------------

    def _apply_filter(self, filter_def: FilterDef) -> None:
        """Convert *filter_def* to FilterCriteria and push to the bar.

        Args:
            filter_def: The :class:`FilterDef` to apply.
        """
        # Lazy import keeps the views package self-contained and avoids
        # a circular import between views and table_filter.
        from ..table_filter import FilterCriterion

        criteria = [
            FilterCriterion.from_def(c)
            for c in filter_def.conditions
            if isinstance(c, dict)
        ]
        try:
            self.filter_bar.set_active_criteria(criteria)
        except Exception as exc:
            self._report_error("filter_apply", exc)

    def _capture_filter(self) -> FilterDef:
        """Capture filter criteria from the live filter bar.

        The operator is preserved from the last :meth:`apply` call so a
        view that arrived with ``operator="or"`` roundtrips losslessly,
        even though :class:`AYTableFilter` only implements AND.

        Returns:
            A new :class:`FilterDef`.
        """
        try:
            criteria = self.filter_bar.get_criteria()
        except Exception as exc:
            self._report_error("filter_capture", exc)
            return FilterDef(operator=self._last_filter_operator)
        return FilterDef(
            conditions=[c.to_def() for c in criteria],
            operator=self._last_filter_operator,
        )

    # ------------------------------------------------------------------
    # Row-height helpers
    # ------------------------------------------------------------------

    def _apply_row_height(self, row_height: int) -> None:
        """Apply *row_height* to whichever views are wired.

        The table view receives the real pixel value via
        :meth:`AYTableView.set_row_height`; the card view is mapped
        only when it exposes a real ``set_card_height`` setter.
        Mapping table-row-height to card *width* is never done — the
        units do not match and a 32px-wide card is not useful.

        Args:
            row_height: Row height in pixels (``<= 0`` = ignore).
        """
        if row_height <= 0:
            return

        if self.table_view is not None:
            setter = getattr(self.table_view, "set_row_height", None)
            if callable(setter):
                try:
                    setter(row_height)
                except Exception as exc:
                    self._report_error("row_height_table", exc)

        if self.card_view is not None:
            setter = getattr(self.card_view, "set_card_height", None)
            if callable(setter):
                try:
                    setter(row_height)
                except Exception as exc:
                    self._report_error("row_height_card", exc)

    def _capture_row_height(self, fallback: int) -> int:
        """Best-effort read of the current row height.

        Args:
            fallback: Value to return when no widget can answer.

        Returns:
            Row height in pixels.
        """
        if self.table_view is not None:
            override = getattr(self.table_view, "_row_height_override", None)
            if isinstance(override, int) and override > 0:
                return int(override)
            # Use the visualRect of the first index when available.
            try:
                model = self.table_view.model()
                if model is not None and model.rowCount() > 0:
                    idx = model.index(0, 0)
                    rect = self.table_view.visualRect(idx)
                    if rect.height() > 0:
                        return int(rect.height())
            except Exception:
                log.debug("Could not measure table row height", exc_info=True)
        return fallback


# Convenience export name kept short for consumer code.
__all__ = ("ColumnState", "ViewBindings")
