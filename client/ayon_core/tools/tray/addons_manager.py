import time
from ayon_core.addon import AddonsManager, ITrayAddon, ITrayService


class TrayAddonsManager(AddonsManager):
    # Define order of addons in menu
    # TODO find better way how to define order
    addons_menu_order = (
        "user",
        "ftrack",
        "kitsu",
        "launcher_tool",
        "avalon",
        "clockify",
        "traypublish_tool",
        "log_viewer",
    )

    def __init__(self, settings=None):
        super(TrayAddonsManager, self).__init__(settings, initialize=False)

        self.tray_manager = None

        self.doubleclick_callbacks = {}
        self.doubleclick_callback = None

    def add_doubleclick_callback(self, addon, callback):
        """Register double-click callbacks on tray icon.

        Currently, there is no way how to determine which is launched. Name of
        callback can be defined with `doubleclick_callback` attribute.

        Missing feature how to define default callback.

        Args:
            addon (AYONAddon): Addon object.
            callback (FunctionType): Function callback.
        """

        callback_name = "_".join([addon.name, callback.__name__])
        if callback_name not in self.doubleclick_callbacks:
            self.doubleclick_callbacks[callback_name] = callback
            if self.doubleclick_callback is None:
                self.doubleclick_callback = callback_name
            return

        self.log.warning((
            "Callback with name \"{}\" is already registered."
        ).format(callback_name))

    def initialize(self, tray_manager, tray_menu):
        self.tray_manager = tray_manager
        self.initialize_addons()
        self.tray_init()
        self.connect_addons()
        self.tray_menu(tray_menu)

    def get_enabled_tray_addons(self):
        """Enabled tray addons.

        Returns:
            list[AYONAddon]: Enabled addons that inherit from tray interface.
        """

        return [
            addon
            for addon in self.get_enabled_addons()
            if isinstance(addon, ITrayAddon)
        ]

    def restart_tray(self):
        if self.tray_manager:
            self.tray_manager.restart()

    def tray_init(self):
        report = {}
        time_start = time.time()
        prev_start_time = time_start
        for addon in self.get_enabled_tray_addons():
            try:
                addon._tray_manager = self.tray_manager
                addon.tray_init()
                addon.tray_initialized = True
            except Exception:
                self.log.warning(
                    "Addon \"{}\" crashed on `tray_init`.".format(
                        addon.name
                    ),
                    exc_info=True
                )

            now = time.time()
            report[addon.__class__.__name__] = now - prev_start_time
            prev_start_time = now

        if self._report is not None:
            report[self._report_total_key] = time.time() - time_start
            self._report["Tray init"] = report

    def tray_menu(self, tray_menu):
        ordered_addons = []
        enabled_by_name = {
            addon.name: addon
            for addon in self.get_enabled_tray_addons()
        }

        for name in self.addons_menu_order:
            addon_by_name = enabled_by_name.pop(name, None)
            if addon_by_name:
                ordered_addons.append(addon_by_name)
        ordered_addons.extend(enabled_by_name.values())

        report = {}
        time_start = time.time()
        prev_start_time = time_start
        for addon in ordered_addons:
            if not addon.tray_initialized:
                continue

            try:
                addon.tray_menu(tray_menu)
            except Exception:
                # Unset initialized mark
                addon.tray_initialized = False
                self.log.warning(
                    "Addon \"{}\" crashed on `tray_menu`.".format(
                        addon.name
                    ),
                    exc_info=True
                )
            now = time.time()
            report[addon.__class__.__name__] = now - prev_start_time
            prev_start_time = now

        if self._report is not None:
            report[self._report_total_key] = time.time() - time_start
            self._report["Tray menu"] = report

    def start_addons(self):
        report = {}
        time_start = time.time()
        prev_start_time = time_start
        for addon in self.get_enabled_tray_addons():
            if not addon.tray_initialized:
                if isinstance(addon, ITrayService):
                    addon.set_service_failed_icon()
                continue

            try:
                addon.tray_start()
            except Exception:
                self.log.warning(
                    "Addon \"{}\" crashed on `tray_start`.".format(
                        addon.name
                    ),
                    exc_info=True
                )
            now = time.time()
            report[addon.__class__.__name__] = now - prev_start_time
            prev_start_time = now

        if self._report is not None:
            report[self._report_total_key] = time.time() - time_start
            self._report["Addons start"] = report

    def on_exit(self):
        for addon in self.get_enabled_tray_addons():
            if addon.tray_initialized:
                try:
                    addon.tray_exit()
                except Exception:
                    self.log.warning(
                        "Addon \"{}\" crashed on `tray_exit`.".format(
                            addon.name
                        ),
                        exc_info=True
                    )
