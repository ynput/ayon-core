# AYON addons
AYON addons should contain separated logic of specific kind of implementation, such as ftrack connection and its usage code, Deadline farm rendering or may contain only special plugins. Addons work the same way currently, there is no difference between module and addon functionality.

## Addons concept
- addons are dynamically imported based on current AYON bundle

## Base class `AYONAddon`
- abstract class as base for each addon
- implementation should contain addon's api without GUI parts
- may implement `get_global_environments` method which should return dictionary of environments that are globally applicable and value is the same for whole studio if launched at any workstation (except os specific paths)
- abstract parts:
 - `name` attribute - name of a addon
 - `initialize` method - method for own initialization of a addon (should not override `__init__`)
 - `connect_with_addons` method - where addon may look for it's interfaces implementations or check for other addons
- `__init__` should not be overridden and `initialize` should not do time consuming part but only prepare base data about addon
 - also keep in mind that they may be initialized in headless mode
- connection with other addons is made with help of interfaces
- `cli` method - add cli commands specific for the addon
    - command line arguments are handled using `click_wrap` python module located in `ayon_core.addon`
    - `cli` method should expect single argument which is click group on which can be called any group specific methods (e.g. `add_command` to add another click group as children see `ExampleAddon`)
    - it is possible to add trigger cli commands using `./ayon addon <addon name> <command> *args`

# Interfaces
- interface is class that has defined abstract methods to implement and may contain pre implemented helper methods
- addon that inherit from an interface must implement those abstract methods otherwise won't be initialized
- it is easy to find which addon object inherited from which interfaces with 100% chance they have implemented required methods
- default interfaces are defined in `interfaces.py`

## IPluginPaths
- addon wants to add directory path/s to publish, load, create or inventory plugins
- addon must implement `get_plugin_paths` which must return dictionary with possible keys `"publish"`, `"load"`, `"create"` or `"actions"`
 - each key may contain list or string with a path to directory with plugins

## ITrayAddon
- addon has more logic when used in a tray
 - it is possible that addon can be used only in the tray
- abstract methods
 - `tray_init` - initialization triggered after `initialize` when used in `TrayModulesManager` and before `connect_with_addons`
 - `tray_menu` - add actions to tray widget's menu that represent the addon
 - `tray_start` - start of addon's login in tray
 - addon is initialized and connected with other addons
 - `tray_exit` - addon's cleanup like stop and join threads etc.
 - order of calling is based on implementation this order is how it works with `TrayModulesManager`
 - it is recommended to import and use GUI implementation only in these methods
- has attribute `tray_initialized` (bool) which is set to False by default and is set by `TrayModulesManager` to True after `tray_init`
 - if addon has logic only in tray or for both then should be checking for `tray_initialized` attribute to decide how should handle situations

### ITrayService
- inherits from `ITrayAddon` and implements `tray_menu` method for you
 - adds action to submenu "Services" in tray widget menu with icon and label
- abstract attribute `label`
 - label shown in menu
- interface has pre implemented methods to change icon color
 - `set_service_running` - green icon
 - `set_service_failed` - red icon
 - `set_service_idle` - orange icon
 - these states must be set by addon itself `set_service_running` is default state on initialization

### ITrayAction
- inherits from `ITrayAddon` and implements `tray_menu` method for you
 - adds action to tray widget menu with label
- abstract attribute `label`
 - label shown in menu
- abstract method `on_action_trigger`
 - what should happen when an action is triggered
- NOTE: It is a good idea to implement logic in `on_action_trigger` to the api method and trigger that method on callbacks. This gives ability to trigger that method outside tray


### AddonsManager
- collects addon classes and tries to initialize them
- important attributes
 - `addons` - list of available attributes
 - `addons_by_id` - dictionary of addons mapped by their ids
 - `addons_by_name` - dictionary of addons mapped by their names
 - all these attributes contain all found addons even if are not enabled
- helper methods
 - `collect_global_environments` to collect all global environments from enabled addons with calling `get_global_environments` on each of them
 - `collect_plugin_paths` collects plugin paths from all enabled addons
 - output is always dictionary with all keys and values as an list
 ```
 {
 "publish": [],
 "create": [],
 "load": [],
 "actions": [],
 "inventory": []
 }
 ```

### TrayAddonsManager
- inherits from `AddonsManager`
- has specific implementation for AYON Tray and handle `ITrayAddon` methods
