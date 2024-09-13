# Publish
AYON is using `pyblish` for publishing process which is a little bit extented and modified mainly for UI purposes. AYON's (new) publish UI does not allow to enable/disable instances or plugins that can be done during creation part. Also does support actions only for validators after validation exception.

## Exceptions
AYON define few specific exceptions that should be used in publish plugins.

### Publish error
Exception `PublishError` can be raised on known error. The message is shown to artist.
- **message** Error message.
- **title** Short description of error (2-5 words). Title can be used for grouping of exceptions per plugin.
- **description** Override of 'message' for UI, you can add markdown and html. By default, is filled with 'message'.
- **detail**  Additional detail message that is hidden under collapsed component.

Arguments `title`, `description` and `detail` are optional. Title is filled with generic message "This is not your fault" if is not passed.

### Validation exception
Validation plugins should raise `PublishValidationError` to show to an artist what's wrong and give him actions to fix it. The exception says that error happened in plugin can be fixed by artist himself (with or without action on plugin). Any other errors will stop publishing immediately. Exception `PublishValidationError` raised after validation order has same effect as any other exception.

Exception expect same arguments as `PublishError`. Value of `title` is filled with plugin label if is not passed.

## Plugin extension
Publish plugins can be extended by additional logic when inherits from `AYONPyblishPluginMixin` which can be used as mixin (additional inheritance of class).

```python
import pyblish.api
from ayon_core.pipeline import AYONPyblishPluginMixin


# Example context plugin
class MyExtendedPlugin(
    pyblish.api.ContextPlugin, AYONPyblishPluginMixin
):
    pass

```

### Extensions
Currently only extension is ability to define attributes for instances during creation. Method `get_attribute_defs` returns attribute definitions for families defined in plugin's `families` attribute if it's instance plugin or for whole context if it's context plugin. To convert existing values (or to remove legacy values) can be implemented `convert_attribute_values`. Values of publish attributes from created instance are never removed automatically so implementing of this method is best way to remove legacy data or convert them to new data structure.

Possible attribute definitions can be found in `ayon_core/lib/attribute_definitions.py`.
