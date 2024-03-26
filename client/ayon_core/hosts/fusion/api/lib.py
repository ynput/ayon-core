import os
import sys
import re
import contextlib

from ayon_core.lib import Logger

from ayon_core.pipeline.context_tools import get_current_project_folder

self = sys.modules[__name__]
self._project = None


def update_frame_range(start, end, comp=None, set_render_range=True,
                       handle_start=0, handle_end=0):
    """Set Fusion comp's start and end frame range

    Args:
        start (float, int): start frame
        end (float, int): end frame
        comp (object, Optional): comp object from fusion
        set_render_range (bool, Optional): When True this will also set the
            composition's render start and end frame.
        handle_start (float, int, Optional): frame handles before start frame
        handle_end (float, int, Optional): frame handles after end frame

    Returns:
        None

    """

    if not comp:
        comp = get_current_comp()

    # Convert any potential none type to zero
    handle_start = handle_start or 0
    handle_end = handle_end or 0

    attrs = {
        "COMPN_GlobalStart": start - handle_start,
        "COMPN_GlobalEnd": end + handle_end
    }

    # set frame range
    if set_render_range:
        attrs.update({
            "COMPN_RenderStart": start,
            "COMPN_RenderEnd": end
        })

    with comp_lock_and_undo_chunk(comp):
        comp.SetAttrs(attrs)


def set_current_context_framerange():
    """Set Comp's frame range based on current folder."""
    folder_entity = get_current_project_folder()
    folder_attributes = folder_entity["attrib"]
    start = folder_attributes["frameStart"]
    end = folder_attributes["frameEnd"]
    handle_start = folder_attributes["handleStart"]
    handle_end = folder_attributes["handleEnd"]
    update_frame_range(start, end, set_render_range=True,
                       handle_start=handle_start,
                       handle_end=handle_end)


def set_current_context_resolution():
    """Set Comp's resolution width x height default based on current folder"""
    folder_entity = get_current_project_folder()
    folder_attributes = folder_entity["attrib"]
    width = folder_attributes["resolutionWidth"]
    height = folder_attributes["resolutionHeight"]
    comp = get_current_comp()

    print("Setting comp frame format resolution to {}x{}".format(width,
                                                                 height))
    comp.SetPrefs({
        "Comp.FrameFormat.Width": width,
        "Comp.FrameFormat.Height": height,
    })


def validate_comp_prefs(comp=None, force_repair=False):
    """Validate current comp defaults with folder settings.

    Validates fps, resolutionWidth, resolutionHeight, aspectRatio.

    This does *not* validate frameStart, frameEnd, handleStart and handleEnd.
    """

    if comp is None:
        comp = get_current_comp()

    log = Logger.get_logger("validate_comp_prefs")

    fields = {
        "path",
        "attrib.fps",
        "attrib.resolutionWidth",
        "attrib.resolutionHeight",
        "attrib.pixelAspect",
    }
    folder_entity = get_current_project_folder(fields=fields)
    folder_path = folder_entity["path"]
    folder_attributes = folder_entity["attrib"]

    comp_frame_format_prefs = comp.GetPrefs("Comp.FrameFormat")

    # Pixel aspect ratio in Fusion is set as AspectX and AspectY so we convert
    # the data to something that is more sensible to Fusion
    folder_attributes["pixelAspectX"] = folder_attributes.pop("pixelAspect")
    folder_attributes["pixelAspectY"] = 1.0

    validations = [
        ("fps", "Rate", "FPS"),
        ("resolutionWidth", "Width", "Resolution Width"),
        ("resolutionHeight", "Height", "Resolution Height"),
        ("pixelAspectX", "AspectX", "Pixel Aspect Ratio X"),
        ("pixelAspectY", "AspectY", "Pixel Aspect Ratio Y")
    ]

    invalid = []
    for key, comp_key, label in validations:
        folder_value = folder_attributes[key]
        comp_value = comp_frame_format_prefs.get(comp_key)
        if folder_value != comp_value:
            invalid_msg = "{} {} should be {}".format(label,
                                                      comp_value,
                                                      folder_value)
            invalid.append(invalid_msg)

            if not force_repair:
                # Do not log warning if we force repair anyway
                log.warning(
                    "Comp {pref} {value} does not match folder "
                    "'{folder_path}' {pref} {folder_value}".format(
                        pref=label,
                        value=comp_value,
                        folder_path=folder_path,
                        folder_value=folder_value)
                )

    if invalid:

        def _on_repair():
            attributes = dict()
            for key, comp_key, _label in validations:
                value = folder_value[key]
                comp_key_full = "Comp.FrameFormat.{}".format(comp_key)
                attributes[comp_key_full] = value
            comp.SetPrefs(attributes)

        if force_repair:
            log.info("Applying default Comp preferences..")
            _on_repair()
            return

        from . import menu
        from ayon_core.tools.utils import SimplePopup
        from ayon_core.style import load_stylesheet
        dialog = SimplePopup(parent=menu.menu)
        dialog.setWindowTitle("Fusion comp has invalid configuration")

        msg = "Comp preferences mismatches '{}'".format(folder_path)
        msg += "\n" + "\n".join(invalid)
        dialog.set_message(msg)
        dialog.set_button_text("Repair")
        dialog.on_clicked.connect(_on_repair)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        dialog.setStyleSheet(load_stylesheet())


@contextlib.contextmanager
def maintained_selection(comp=None):
    """Reset comp selection from before the context after the context"""
    if comp is None:
        comp = get_current_comp()

    previous_selection = comp.GetToolList(True).values()
    try:
        yield
    finally:
        flow = comp.CurrentFrame.FlowView
        flow.Select()  # No args equals clearing selection
        if previous_selection:
            for tool in previous_selection:
                flow.Select(tool, True)


@contextlib.contextmanager
def maintained_comp_range(comp=None,
                          global_start=True,
                          global_end=True,
                          render_start=True,
                          render_end=True):
    """Reset comp frame ranges from before the context after the context"""
    if comp is None:
        comp = get_current_comp()

    comp_attrs = comp.GetAttrs()
    preserve_attrs = {}
    if global_start:
        preserve_attrs["COMPN_GlobalStart"] = comp_attrs["COMPN_GlobalStart"]
    if global_end:
        preserve_attrs["COMPN_GlobalEnd"] = comp_attrs["COMPN_GlobalEnd"]
    if render_start:
        preserve_attrs["COMPN_RenderStart"] = comp_attrs["COMPN_RenderStart"]
    if render_end:
        preserve_attrs["COMPN_RenderEnd"] = comp_attrs["COMPN_RenderEnd"]

    try:
        yield
    finally:
        comp.SetAttrs(preserve_attrs)


def get_frame_path(path):
    """Get filename for the Fusion Saver with padded number as '#'

    >>> get_frame_path("C:/test.exr")
    ('C:/test', 4, '.exr')

    >>> get_frame_path("filename.00.tif")
    ('filename.', 2, '.tif')

    >>> get_frame_path("foobar35.tif")
    ('foobar', 2, '.tif')

    Args:
        path (str): The path to render to.

    Returns:
        tuple: head, padding, tail (extension)

    """
    filename, ext = os.path.splitext(path)

    # Find a final number group
    match = re.match('.*?([0-9]+)$', filename)
    if match:
        padding = len(match.group(1))
        # remove number from end since fusion
        # will swap it with the frame number
        filename = filename[:-padding]
    else:
        padding = 4  # default Fusion padding

    return filename, padding, ext


def get_fusion_module():
    """Get current Fusion instance"""
    fusion = getattr(sys.modules["__main__"], "fusion", None)
    return fusion


def get_bmd_library():
    """Get bmd library"""
    bmd = getattr(sys.modules["__main__"], "bmd", None)
    return bmd


def get_current_comp():
    """Get current comp in this session"""
    fusion = get_fusion_module()
    if fusion is not None:
        comp = fusion.CurrentComp
        return comp


@contextlib.contextmanager
def comp_lock_and_undo_chunk(
    comp,
    undo_queue_name="Script CMD",
    keep_undo=True,
):
    """Lock comp and open an undo chunk during the context"""

    # If comp is already locked do nothing and consider us to
    # be inside another undo chunk currently. This allows nesting the chunks.
    if comp.IsLocked():
        yield
        return

    try:
        comp.Lock()
        comp.StartUndo(undo_queue_name)
        yield
    finally:
        comp.Unlock()
        comp.EndUndo(keep_undo)
