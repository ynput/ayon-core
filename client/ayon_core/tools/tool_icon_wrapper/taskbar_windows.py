"""Windows-only native taskbar identity (AppUserModelID).

Linux-native taskbar hints are not maintained in this package; see roadmap
``PipelineEngineering/patch-stack/roadmap-cross-platform-dock-shim-upstream-hardening.md``.
"""

from __future__ import annotations


def win_set_app_user_model_id(hwnd: int, app_id: str) -> None:
    """Set Win32 AppUserModelID via ``IPropertyStore`` on a visible ``HWND``."""
    import ctypes
    import struct
    from ctypes import wintypes

    def _guid(d1: int, d2: int, d3: int, tail: str) -> bytes:
        return struct.pack("<IHH", d1, d2, d3) + bytes.fromhex(tail)

    # IID_IPropertyStore = {886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99}
    iid = (ctypes.c_byte * 16)(
        *_guid(0x886D8EEB, 0x8CF2, 0x4446, "8D02CDBA1DBDCF99")
    )
    ps = ctypes.c_void_p()
    hwnd_arg = wintypes.HWND(int(hwnd))
    result = ctypes.windll.shell32.SHGetPropertyStoreForWindow(
        hwnd_arg, ctypes.byref(iid), ctypes.byref(ps)
    )
    if result != 0 or not ps:
        return

    class _GUID(ctypes.Structure):
        _fields_ = [("b", ctypes.c_byte * 16)]

    class _PROPKEY(ctypes.Structure):
        _fields_ = [
            ("fmtid", _GUID),
            ("pid", ctypes.c_uint32),
        ]

    class _PROPVARIANT(ctypes.Structure):
        _fields_ = [
            ("vt", ctypes.c_uint16),
            ("_reserved", ctypes.c_uint16 * 3),
            ("_value", ctypes.c_uint64),
        ]

    # PKEY_AppUserModel_ID = {9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}, pid 5
    pkey = _PROPKEY()
    pkey.fmtid.b[:] = _guid(0x9F4C2855, 0x9F79, 0x4B39, "A8D0E1D42DE1D5F3")
    pkey.pid = 5

    buf = ctypes.create_unicode_buffer(app_id)
    pv = _PROPVARIANT()
    pv.vt = 31  # VT_LPWSTR
    pv._value = ctypes.cast(buf, ctypes.c_void_p).value or 0

    vt = ctypes.cast(
        ctypes.cast(ps, ctypes.POINTER(ctypes.c_void_p)).contents,
        ctypes.POINTER(ctypes.c_void_p),
    )
    try:
        set_value = ctypes.WINFUNCTYPE(
            ctypes.HRESULT,
            ctypes.c_void_p,
            ctypes.POINTER(_PROPKEY),
            ctypes.POINTER(_PROPVARIANT),
        )(vt[6])
        if set_value(ps, ctypes.byref(pkey), ctypes.byref(pv)) == 0:
            ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p)(vt[7])(ps)
    finally:
        ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vt[2])(ps)
