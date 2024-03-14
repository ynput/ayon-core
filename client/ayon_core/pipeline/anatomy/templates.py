import os
import copy
import re
import collections
import numbers

import six

from ayon_core.lib import Logger
from ayon_core.lib.path_templates import (
    TemplateResult,
    StringTemplate,
    TemplatesDict,
)

from .exceptions import AnatomyTemplateUnsolved
from .roots import RootItem


class AnatomyTemplateResult(TemplateResult):
    rootless = None

    def __new__(cls, result, rootless_path):
        new_obj = super(AnatomyTemplateResult, cls).__new__(
            cls,
            str(result),
            result.template,
            result.solved,
            result.used_values,
            result.missing_keys,
            result.invalid_types
        )
        new_obj.rootless = rootless_path
        return new_obj

    def validate(self):
        if not self.solved:
            raise AnatomyTemplateUnsolved(
                self.template,
                self.missing_keys,
                self.invalid_types
            )

    def copy(self):
        tmp = TemplateResult(
            str(self),
            self.template,
            self.solved,
            self.used_values,
            self.missing_keys,
            self.invalid_types
        )
        return self.__class__(tmp, self.rootless)

    def normalized(self):
        """Convert to normalized path."""

        tmp = TemplateResult(
            os.path.normpath(self),
            self.template,
            self.solved,
            self.used_values,
            self.missing_keys,
            self.invalid_types
        )
        return self.__class__(tmp, self.rootless)


class AnatomyStringTemplate(StringTemplate):
    """String template which has access to anatomy."""

    def __init__(self, anatomy_templates, template):
        self.anatomy_templates = anatomy_templates
        super(AnatomyStringTemplate, self).__init__(template)

    def format(self, data):
        """Format template and add 'root' key to data if not available.

        Args:
            data (dict[str, Any]): Formatting data for template.

        Returns:
            AnatomyTemplateResult: Formatting result.
        """

        anatomy_templates = self.anatomy_templates
        if not data.get("root"):
            data = copy.deepcopy(data)
            data["root"] = anatomy_templates.anatomy.roots
        result = StringTemplate.format(self, data)
        rootless_path = anatomy_templates.rootless_path_from_result(result)
        return AnatomyTemplateResult(result, rootless_path)


class TemplateItem:
    """Template item under template category.

    This item data usually contains 'file' and 'directory' by anatomy
        definition, enhanced by common data ('frame_padding',
        'version_padding'). It adds 'path' key which is combination of
        'file' and 'directory' values.

    Args:
        anatomy_templates (AnatomyTemplates): Anatomy templates object.
        template_data (dict[str, Any]): Templates data.

    """
    def __init__(self, anatomy_templates, template_data):
        template_data = copy.deepcopy(template_data)

        # Backwards compatibility for 'folder'
        # TODO remove when deprecation not needed anymore
        if (
            "folder" not in template_data
            and "directory" in template_data
        ):
            template_data["folder"] = template_data["directory"]

        # Add 'path' key
        if (
            "path" not in template_data
            and "file" in template_data
            and "directory" in template_data
        ):
            template_data["path"] = "/".join(
                (template_data["directory"], template_data["file"])
            )

        for key, value in template_data.items():
            if isinstance(value, str):
                value = AnatomyStringTemplate(anatomy_templates, value)
            template_data[key] = value

        self._template_data = template_data
        self._anatomy_templates = anatomy_templates

    def __getitem__(self, key):
        return self._template_data[key]

    def get(self, key, default=None):
        return self._template_data.get(key, default)

    def format(self, data, strict=True):
        output = {}
        for key, value in self._template_data.items():
            if isinstance(value, AnatomyStringTemplate):
                value = value.format(data)
            output[key] = value
        return output


class TemplateCategory:
    """Template category.

    Template category groups template items for specific usage. Categories
        available at the moment are 'work', 'publish', 'hero', 'delivery',
        'staging' and 'others'.

    Args:
        anatomy_templates (AnatomyTemplates): Anatomy templates object.
        category_name (str): Category name.
        category_data (dict[str, Any]): Category data.

    """
    def __init__(self, anatomy_templates, category_name, category_data):
        for key, value in category_data.items():
            if isinstance(value, dict):
                value = TemplateItem(anatomy_templates, value)
            elif isinstance(value, str):
                value = AnatomyStringTemplate(anatomy_templates, value)
            category_data[key] = value
        self._name = category_name
        self._name_prefix = "{}_".format(category_name)
        self._category_data = category_data

    def __getitem__(self, key):
        new_key = self._convert_getter_key(key)
        return self._category_data[new_key]

    def get(self, key, default=None):
        new_key = self._convert_getter_key(key)
        return self._category_data.get(new_key, default)

    @property
    def name(self):
        """Category name.

        Returns:
            str: Category name.

        """
        return self._name

    def format(self, data, strict=True):
        output = {}
        for key, value in self._category_data.items():
            if isinstance(value, TemplateItem):
                value = value.format(data, strict)
            elif isinstance(value, AnatomyStringTemplate):
                value = value.format(data)

            output[key] = value
        return output

    def _convert_getter_key(self, key):
        """Convert key for backwards compatibility.

        OpenPype compatible settings did contain template keys prefixed by
        category name e.g. 'publish_render' which should be just 'render'.

        This method keeps the backwards compatibility but only if the key
        starts with the category name prefix and the key is available in
        roots.

        Args:
            key (str): Key to be converted.

        Returns:
            str: Converted string.

        """
        if key in self._category_data:
            return key
        if key.startswith(self._name_prefix):
            new_key = key[len(self._name_prefix):]
            if new_key in self._category_data:
                return new_key
        return key


class AnatomyTemplates(TemplatesDict):
    inner_key_pattern = re.compile(r"(\{@.*?[^{}0]*\})")
    inner_key_name_pattern = re.compile(r"\{@(.*?[^{}0]*)\}")

    def __init__(self, anatomy):
        self._log = Logger.get_logger(self.__class__.__name__)
        super(AnatomyTemplates, self).__init__()
        self.anatomy = anatomy
        self.loaded_project = None

    def reset(self):
        self._raw_templates = None
        self._templates = None
        self._objected_templates = None

    @property
    def project_name(self):
        return self.anatomy.project_name

    @property
    def roots(self):
        return self.anatomy.roots

    @property
    def templates(self):
        self._validate_discovery()
        return self._templates

    @property
    def objected_templates(self):
        self._validate_discovery()
        return self._objected_templates

    def _validate_discovery(self):
        if self.project_name != self.loaded_project:
            self.reset()

        if self._templates is None:
            self._discover()
            self.loaded_project = self.project_name

    def _format_value(self, value, data):
        if isinstance(value, RootItem):
            return self._solve_dict(value, data)
        return super(AnatomyTemplates, self)._format_value(value, data)

    @staticmethod
    def _ayon_template_conversion(templates):
        def _convert_template_item(template_item):
            # Change 'directory' to 'folder'
            if "directory" in template_item:
                template_item["folder"] = template_item["directory"]

            if (
                "path" not in template_item
                and "file" in template_item
                and "folder" in template_item
            ):
                template_item["path"] = "/".join(
                    (template_item["folder"], template_item["file"])
                )

        def _get_default_template_name(templates):
            default_template = None
            for name, template in templates.items():
                if name == "default":
                    return "default"

                if default_template is None:
                    default_template = name

            return default_template

        def _fill_template_category(templates, cat_templates, cat_key):
            default_template_name = _get_default_template_name(cat_templates)
            for template_name, cat_template in cat_templates.items():
                _convert_template_item(cat_template)
                if template_name == default_template_name:
                    templates[cat_key] = cat_template
                else:
                    new_name = "{}_{}".format(cat_key, template_name)
                    templates["others"][new_name] = cat_template

        others_templates = templates.pop("others", None) or {}
        new_others_templates = {}
        templates["others"] = new_others_templates
        for name, template in others_templates.items():
            _convert_template_item(template)
            new_others_templates[name] = template

        for key in (
            "work",
            "publish",
            "hero",
        ):
            cat_templates = templates.pop(key)
            _fill_template_category(templates, cat_templates, key)

        delivery_templates = templates.pop("delivery", None) or {}
        new_delivery_templates = {}
        for name, delivery_template in delivery_templates.items():
            new_delivery_templates[name] = "/".join(
                (delivery_template["directory"], delivery_template["file"])
            )
        templates["delivery"] = new_delivery_templates

    def set_templates(self, templates):
        if not templates:
            self.reset()
            return

        templates = copy.deepcopy(templates)
        # TODO remove AYON convertion
        self._ayon_template_conversion(templates)

        self._raw_templates = copy.deepcopy(templates)
        v_queue = collections.deque()
        v_queue.append(templates)
        while v_queue:
            item = v_queue.popleft()
            if not isinstance(item, dict):
                continue

            for key in tuple(item.keys()):
                value = item[key]
                if isinstance(value, dict):
                    v_queue.append(value)

                elif (
                    isinstance(value, six.string_types)
                    and "{task}" in value
                ):
                    item[key] = value.replace("{task}", "{task[name]}")

        solved_templates = self.solve_template_inner_links(templates)
        self._templates = solved_templates
        self._objected_templates = self.create_objected_templates(
            solved_templates
        )

    def _create_template_object(self, template):
        return AnatomyStringTemplate(self, template)

    def default_templates(self):
        """Return default templates data with solved inner keys."""
        return self.solve_template_inner_links(
            self.anatomy["templates"]
        )

    def _discover(self):
        """ Loads anatomy templates from yaml.
        Default templates are loaded if project is not set or project does
        not have set it's own.
        TODO: create templates if not exist.

        Returns:
            TemplatesResultDict: Contain templates data for current project of
                default templates.
        """

    @property
    def frame_padding(self):
        """Default frame padding.

        Returns:
            int: Frame padding used by default in templates.

        """
        self._validate_discovery()
        return self["frame_padding"]

    @property
    def version_padding(self):
        """Default version padding.

        Returns:
            int: Version padding used by default in templates.

        """
        self._validate_discovery()
        return self["version_padding"]

    @classmethod
    def get_rootless_path_from_result(cls, result):
        """Calculate rootless path from formatting result.

        Args:
            result (TemplateResult): Result of StringTemplate formatting.

        Returns:
            str: Rootless path if result contains one of anatomy roots.
        """

        used_values = result.used_values
        missing_keys = result.missing_keys
        template = result.template
        invalid_types = result.invalid_types
        if (
            "root" not in used_values
            or "root" in missing_keys
            or "{root" not in template
        ):
            return

        for invalid_type in invalid_types:
            if "root" in invalid_type:
                return

        root_keys = cls._dict_to_subkeys_list({"root": used_values["root"]})
        if not root_keys:
            return

        output = str(result)
        for used_root_keys in root_keys:
            if not used_root_keys:
                continue

            used_value = used_values
            root_key = None
            for key in used_root_keys:
                used_value = used_value[key]
                if root_key is None:
                    root_key = key
                else:
                    root_key += "[{}]".format(key)

            root_key = "{" + root_key + "}"
            output = output.replace(str(used_value), root_key)

        return output

        if self.project_name is None:
            # QUESTION create project specific if not found?
            raise AssertionError((
                "Project \"{0}\" does not have his own templates."
                " Trying to use default."
            ).format(self.project_name))

        self.set_templates(self.anatomy["templates"])

    @classmethod
    def replace_inner_keys(cls, matches, value, key_values, key):
        """Replacement of inner keys in template values."""
        for match in matches:
            anatomy_sub_keys = (
                cls.inner_key_name_pattern.findall(match)
            )
            if key in anatomy_sub_keys:
                raise ValueError((
                    "Unsolvable recursion in inner keys, "
                    "key: \"{}\" is in his own value."
                    " Can't determine source, please check Anatomy templates."
                ).format(key))

            for anatomy_sub_key in anatomy_sub_keys:
                replace_value = key_values.get(anatomy_sub_key)
                if replace_value is None:
                    raise KeyError((
                        "Anatomy templates can't be filled."
                        " Anatomy key `{0}` has"
                        " invalid inner key `{1}`."
                    ).format(key, anatomy_sub_key))

                if not (
                    isinstance(replace_value, numbers.Number)
                    or isinstance(replace_value, six.string_types)
                ):
                    raise ValueError((
                        "Anatomy templates can't be filled."
                        " Anatomy key `{0}` has"
                        " invalid inner key `{1}`"
                        " with value `{2}`."
                    ).format(key, anatomy_sub_key, str(replace_value)))

                value = value.replace(match, str(replace_value))

        return value

    @classmethod
    def prepare_inner_keys(cls, key_values):
        """Check values of inner keys.

        Check if inner key exist in template group and has valid value.
        It is also required to avoid infinite loop with unsolvable recursion
        when first inner key's value refers to second inner key's value where
        first is used.
        """
        keys_to_solve = set(key_values.keys())
        while True:
            found = False
            for key in tuple(keys_to_solve):
                value = key_values[key]

                if isinstance(value, six.string_types):
                    matches = cls.inner_key_pattern.findall(value)
                    if not matches:
                        keys_to_solve.remove(key)
                        continue

                    found = True
                    key_values[key] = cls.replace_inner_keys(
                        matches, value, key_values, key
                    )
                    continue

                elif not isinstance(value, dict):
                    keys_to_solve.remove(key)
                    continue

                subdict_found = False
                for _key, _value in tuple(value.items()):
                    matches = cls.inner_key_pattern.findall(_value)
                    if not matches:
                        continue

                    subdict_found = True
                    found = True
                    key_values[key][_key] = cls.replace_inner_keys(
                        matches, _value, key_values,
                        "{}.{}".format(key, _key)
                    )

                if not subdict_found:
                    keys_to_solve.remove(key)

            if not found:
                break

        return key_values

    @classmethod
    def solve_template_inner_links(cls, templates):
        """Solve templates inner keys identified by "{@*}".

        Process is split into 2 parts.
        First is collecting all global keys (keys in top hierarchy where value
        is not dictionary). All global keys are set for all group keys (keys
        in top hierarchy where value is dictionary). Value of a key is not
        overridden in group if already contain value for the key.

        In second part all keys with "at" symbol in value are replaced with
        value of the key afterward "at" symbol from the group.

        Args:
            templates (dict): Raw templates data.

        Example:
            templates::
                key_1: "value_1",
                key_2: "{@key_1}/{filling_key}"

                group_1:
                    key_3: "value_3/{@key_2}"

                group_2:
                    key_2": "value_2"
                    key_4": "value_4/{@key_2}"

            output::
                key_1: "value_1"
                key_2: "value_1/{filling_key}"

                group_1: {
                    key_1: "value_1"
                    key_2: "value_1/{filling_key}"
                    key_3: "value_3/value_1/{filling_key}"

                group_2: {
                    key_1: "value_1"
                    key_2: "value_2"
                    key_4: "value_3/value_2"
        """
        default_key_values = templates.pop("common", {})
        for key, value in tuple(templates.items()):
            if isinstance(value, dict):
                continue
            default_key_values[key] = templates.pop(key)

        # Pop "others" key before before expected keys are processed
        other_templates = templates.pop("others") or {}

        keys_by_subkey = {}
        for sub_key, sub_value in templates.items():
            key_values = {}
            key_values.update(default_key_values)
            key_values.update(sub_value)
            keys_by_subkey[sub_key] = cls.prepare_inner_keys(key_values)

        for sub_key, sub_value in other_templates.items():
            if sub_key in keys_by_subkey:
                self.log.warning((
                    "Key \"{}\" is duplicated in others. Skipping."
                ).format(sub_key))
                continue

            key_values = {}
            key_values.update(default_key_values)
            key_values.update(sub_value)
            keys_by_subkey[sub_key] = cls.prepare_inner_keys(key_values)

        default_keys_by_subkeys = cls.prepare_inner_keys(default_key_values)

        for key, value in default_keys_by_subkeys.items():
            keys_by_subkey[key] = value

        return keys_by_subkey

    @classmethod
    def _dict_to_subkeys_list(cls, subdict, pre_keys=None):
        if pre_keys is None:
            pre_keys = []
        output = []
        for key in subdict:
            value = subdict[key]
            result = list(pre_keys)
            result.append(key)
            if isinstance(value, dict):
                for item in cls._dict_to_subkeys_list(value, result):
                    output.append(item)
            else:
                output.append(result)
        return output

    def _keys_to_dicts(self, key_list, value):
        if not key_list:
            return None
        if len(key_list) == 1:
            return {key_list[0]: value}
        return {key_list[0]: self._keys_to_dicts(key_list[1:], value)}

    @classmethod
    def rootless_path_from_result(cls, result):
        """Calculate rootless path from formatting result.

        Args:
            result (TemplateResult): Result of StringTemplate formatting.

        Returns:
            str: Rootless path if result contains one of anatomy roots.
        """

        used_values = result.used_values
        missing_keys = result.missing_keys
        template = result.template
        invalid_types = result.invalid_types
        if (
            "root" not in used_values
            or "root" in missing_keys
            or "{root" not in template
        ):
            return

        for invalid_type in invalid_types:
            if "root" in invalid_type:
                return

        root_keys = cls._dict_to_subkeys_list({"root": used_values["root"]})
        if not root_keys:
            return

        output = str(result)
        for used_root_keys in root_keys:
            if not used_root_keys:
                continue

            used_value = used_values
            root_key = None
            for key in used_root_keys:
                used_value = used_value[key]
                if root_key is None:
                    root_key = key
                else:
                    root_key += "[{}]".format(key)

            root_key = "{" + root_key + "}"
            output = output.replace(str(used_value), root_key)

        return output

    def format(self, data, strict=True):
        copy_data = copy.deepcopy(data)
        roots = self.roots
        if roots:
            copy_data["root"] = roots
        result = super(AnatomyTemplates, self).format(copy_data)
        result.strict = strict
        return result

    def format_all(self, in_data, only_keys=True):
        """ Solves templates based on entered data.

        Args:
            data (dict): Containing keys to be filled into template.

        Returns:
            TemplatesResultDict: Output `TemplateResult` have `strict`
                attribute set to False so accessing unfilled keys in templates
                won't raise any exceptions.
        """
        return self.format(in_data, strict=False)