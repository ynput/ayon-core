"""
macos_tray_clickcount_fix.py

Workaround for Qt bug: https://codereview.qt-project.org/c/qt/qtbase/+/756941
Crash report: https://github.com/ynput/ayon-launcher/issues/329

Qt's QCocoaSystemTrayIcon::emitActivated() calls -[NSEvent clickCount] on
whatever NSEvent is current when the NSMenuTrackingSession "begin-tracking"
notification fires.  During right-click menu popup, the current event is
NSEventTypeSystemDefined (14), which does not support -clickCount.  AppKit
raises NSInternalInconsistencyException; Qt has no ObjC exception handler,
so the process terminates.

This module swizzles -[NSEvent clickCount] via the ObjC runtime (ctypes only,
no extra deps) to return 0 for non-mouse events.  For genuine mouse events the
original implementation is called unchanged, so click-detection is unaffected.

Usage:
    # Call ONCE at startup, before QApplication / QSystemTrayIcon
    from ayon_core.tools.tray.ui._macos_fix import install_clickcount_fix
    install_clickcount_fix()
"""

from __future__ import annotations

import ctypes
import ctypes.util
import platform

from ayon_core.lib import Logger

__all__ = ["install_clickcount_fix"]

_log = Logger.get_logger(__name__)

# ---------------------------------------------------------------------------
# NSEventType constants that legitimately support -clickCount.
# Apple docs: "The number of mouse clicks associated with a mouse-down or
# mouse-up event."  All other types raise NSInternalInconsistencyException.
# ---------------------------------------------------------------------------
_MOUSE_EVENT_TYPES: frozenset[int] = frozenset(
    {
        1,   # NSEventTypeLeftMouseDown
        2,   # NSEventTypeLeftMouseUp
        3,   # NSEventTypeRightMouseDown
        4,   # NSEventTypeRightMouseUp
        5,   # NSEventTypeMouseMoved
        6,   # NSEventTypeLeftMouseDragged
        7,   # NSEventTypeRightMouseDragged
        25,  # NSEventTypeOtherMouseDown
        26,  # NSEventTypeOtherMouseUp
        27,  # NSEventTypeOtherMouseDragged
    }
)


class _State:
    # ctypes callback objects must outlive the process – C holds the raw
    #   pointer.
    # If Python's GC collects them the pointer becomes dangling → segfault.
    keepalive: list[object] = []
    tried = False


def install_clickcount_fix() -> None:
    """
    Patch -[NSEvent clickCount] to be safe for non-mouse events.

    - No-op on non-Darwin platforms.
    - Idempotent; safe to call more than once.
    - Must be called before the first QSystemTrayIcon is shown.
    - Remove this call once PySide6 ships Qt fix 756941.
    """
    if _State.tried:
        return

    _State.tried = True
    if platform.system().lower() != "darwin":
        return

    # https://codereview.qt-project.org/c/qt/qtbase/+/756941
    try:
        _apply_patch()
        _log.debug("NSEvent.clickCount safety patch installed.")
    except Exception:
        _log.warning(
            "Could not install NSEvent.clickCount safety patch.",
            exc_info=True,
        )


def _apply_patch() -> None:
    """Perform the ObjC method swizzle via ctypes."""

    libobjc = ctypes.CDLL(ctypes.util.find_library("objc"), use_errno=True)

    # -- ObjC runtime helpers ------------------------------------------------
    libobjc.objc_getClass.restype = ctypes.c_void_p
    libobjc.objc_getClass.argtypes = [ctypes.c_char_p]

    libobjc.sel_registerName.restype = ctypes.c_void_p
    libobjc.sel_registerName.argtypes = [ctypes.c_char_p]

    libobjc.class_getInstanceMethod.restype = ctypes.c_void_p
    libobjc.class_getInstanceMethod.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p
    ]

    libobjc.method_getImplementation.restype = ctypes.c_void_p
    libobjc.method_getImplementation.argtypes = [ctypes.c_void_p]

    libobjc.method_setImplementation.restype = ctypes.c_void_p
    libobjc.method_setImplementation.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p
    ]

    # -- Locate NSEvent and the selectors we need ----------------------------
    ns_event_cls = libobjc.objc_getClass(b"NSEvent")
    if not ns_event_cls:
        raise RuntimeError("objc_getClass('NSEvent') returned NULL")

    sel_click_count = libobjc.sel_registerName(b"clickCount")
    sel_type = libobjc.sel_registerName(b"type")

    method = libobjc.class_getInstanceMethod(ns_event_cls, sel_click_count)
    if not method:
        raise RuntimeError(
            "class_getInstanceMethod(NSEvent, clickCount) returned NULL"
        )

    # -- IMP type for -clickCount  →  NSInteger (*)(id, SEL) -----------------
    _ClickCountIMP = ctypes.CFUNCTYPE(
        ctypes.c_long,    # NSInteger  – return value
        ctypes.c_void_p,  # id         – self
        ctypes.c_void_p,  # SEL        – _cmd
    )

    # -- Typed wrapper for calling -[NSEvent type] via objc_msgSend ----------
    #
    # We extract the raw address instead of reusing libobjc.objc_msgSend so we
    # don't change its global restype/argtypes and surprise other callers.
    _msgSend_addr: int = ctypes.cast(  # type: ignore[assignment]
        libobjc.objc_msgSend, ctypes.c_void_p
    ).value
    _TypeMsgSend = ctypes.CFUNCTYPE(
        ctypes.c_ulong,   # NSUInteger (NSEventType) – return value
        ctypes.c_void_p,  # id                       – self
        ctypes.c_void_p,  # SEL                      – _cmd
    )
    _call_type = _TypeMsgSend(_msgSend_addr)

    # -- Wrap the original IMP -----------------------------------------------
    orig_addr = libobjc.method_getImplementation(method)
    if not orig_addr:
        raise RuntimeError(
            "method_getImplementation returned NULL for -[NSEvent clickCount]"
        )
    _original = _ClickCountIMP(orig_addr)

    # -- Replacement IMP -----------------------------------------------------
    def _safe_click_count(self_ptr: int, sel_ptr: int) -> int:
        """
        Return 0 for non-mouse events; delegate to original for mouse events.

        ctypes acquires the GIL before entering this Python function, so
        accessing Python objects (_MOUSE_EVENT_TYPES etc.) is safe even
        though the immediate caller is C code.
        """
        event_type = _call_type(self_ptr, sel_type)
        if event_type not in _MOUSE_EVENT_TYPES:
            return 0
        return _original(self_ptr, sel_ptr)

    _new_imp = _ClickCountIMP(_safe_click_count)

    # -- Install -------------------------------------------------------------
    libobjc.method_setImplementation(
        method,
        ctypes.cast(_new_imp, ctypes.c_void_p),
    )

    # The closures keep _original and _call_type alive; _new_imp and
    # _safe_click_count must be kept explicitly so C's raw pointer stays valid.
    _State.keepalive = [_new_imp, _safe_click_count, _original, _call_type]
