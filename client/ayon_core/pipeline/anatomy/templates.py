import os
import re
import copy
import collections
import numbers

from ayon_core.lib.path_templates import (
    TemplateResult,
    StringTemplate,
)

from .exceptions import (
    ProjectNotSet,
    TemplateMissingKey,
    AnatomyTemplateUnsolved,
)

_PLACEHOLDER = object()


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
    """String template which has access to anatomy.

    Args:
        anatomy_templates (AnatomyTemplates): Anatomy templates object.
        template (str): Template string.
    """

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
        rootless_path = anatomy_templates.get_rootless_path_from_result(
            result
        )
        return AnatomyTemplateResult(result, rootless_path)


def _merge_dict(main_dict, enhance_dict):
    """Merges dictionaries by keys.

    Function call itself if value on key is again dictionary.

    Args:
        main_dict (dict): First dict to merge second one into.
        enhance_dict (dict): Second dict to be merged.

    Returns:
        dict: Merged result.

    .. note:: does not override whole value on first found key
              but only values differences from enhance_dict

    """

    merge_queue = collections.deque()
    merge_queue.append((main_dict, enhance_dict))
    while merge_queue:
        queue_item = merge_queue.popleft()
        l_dict, r_dict = queue_item

        for key, value in r_dict.items():
            if key not in l_dict:
                l_dict[key] = value
            elif isinstance(value, dict) and isinstance(l_dict[key], dict):
                merge_queue.append((l_dict[key], value))
            else:
                l_dict[key] = value
    return main_dict


class TemplatesResultDict(dict):
    """Holds and wrap 'AnatomyTemplateResult' for easy bug report.

    Dictionary like object which holds 'AnatomyTemplateResult' in the same
    data structure as base dictionary of anatomy templates. It can raise

    """

    def __init__(self, in_data, key=None, parent=None, strict=None):
        super(TemplatesResultDict, self).__init__()
        for _key, _value in in_data.items():
            if isinstance(_value, TemplatesResultDict):
                _value.parent = self
            elif isinstance(_value, dict):
                _value = self.__class__(_value, _key, self)
            self[_key] = _value

        if strict is None and parent is None:
            strict = True

        self.key = key
        self.parent = parent
        self._is_strict = strict

    def __getitem__(self, key):
        if key not in self.keys():
            hier = self.get_hierarchy()
            hier.append(key)
            raise TemplateMissingKey(hier)

        value = super(TemplatesResultDict, self).__getitem__(key)
        if isinstance(value, self.__class__):
            return value

        # Raise exception when expected solved templates and it is not.
        if self.is_strict and hasattr(value, "validate"):
            value.validate()
        return value

    def get_is_strict(self):
        return self._is_strict

    def set_is_strict(self, is_strict):
        if is_strict is None and self.parent is None:
            is_strict = True
        self._is_strict = is_strict
        for child in self.values():
            if isinstance(child, self.__class__):
                child.set_is_strict(is_strict)
            elif isinstance(child, AnatomyTemplateResult):
                child.strict = is_strict

    strict = property(get_is_strict, set_is_strict)
    is_strict = property(get_is_strict, set_is_strict)

    def get_hierarchy(self):
        """Return dictionary keys one by one to root parent."""
        if self.key is None:
            return []

        if self.parent is None:
            return [self.key]

        par_hier = list(self.parent.get_hierarchy())
        par_hier.append(self.key)
        return par_hier

    @property
    def missing_keys(self):
        """Return missing keys of all children templates."""
        missing_keys = set()
        for value in self.values():
            missing_keys |= value.missing_keys
        return missing_keys

    @property
    def invalid_types(self):
        """Return invalid types of all children templates."""
        invalid_types = {}
        for value in self.values():
            invalid_types = _merge_dict(invalid_types, value.invalid_types)
        return invalid_types

    @property
    def used_values(self):
        """Return used values for all children templates."""
        used_values = {}
        for value in self.values():
            used_values = _merge_dict(used_values, value.used_values)
        return used_values

    def get_solved(self):
        """Get only solved key from templates."""
        result = {}
        for key, value in self.items():
            if isinstance(value, self.__class__):
                value = value.get_solved()
                if not value:
                    continue
                result[key] = value

            elif (
                not hasattr(value, "solved") or
                value.solved
            ):
                result[key] = value
        return self.__class__(result, key=self.key, parent=self.parent)


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
        return TemplatesResultDict(output, strict=strict)


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

            if isinstance(value, TemplatesResultDict):
                value.key = key
            output[key] = value
        return TemplatesResultDict(output, key=self.name, strict=strict)

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

        # Use default when the key is the category name
        if key == self._name:
            return "default"

        # Remove prefix if is key prefixed
        if key.startswith(self._name_prefix):
            new_key = key[len(self._name_prefix):]
            if new_key in self._category_data:
                return new_key
        return key


class AnatomyTemplates:
    inner_key_pattern = re.compile(r"(\{@.*?[^{}0]*\})")
    inner_key_name_pattern = re.compile(r"\{@(.*?[^{}0]*)\}")

    def __init__(self, anatomy):
        self._anatomy = anatomy

        self._loaded_project = None
        self._raw_templates = None
        self._templates = None
        self._objected_templates = None

    def __getitem__(self, key):
        self._validate_discovery()
        return self._objected_templates[key]

    def get(self, key, default=None):
        self._validate_discovery()
        return self._objected_templates.get(key, default)

    def keys(self):
        return self._objected_templates.keys()

    def reset(self):
        self._raw_templates = None
        self._templates = None
        self._objected_templates = None

    @property
    def anatomy(self):
        """Anatomy instance.

        Returns:
            Anatomy: Anatomy instance.

        """
        return self._anatomy

    @property
    def project_name(self):
        """Project name.

        Returns:
            Union[str, None]: Project name if set, otherwise None.

        """
        return self._anatomy.project_name

    @property
    def roots(self):
        """Anatomy roots object.

        Returns:
            RootItem: Anatomy roots data.

        """
        return self._anatomy.roots

    @property
    def templates(self):
        """Templates data.

        Templates data with replaced common data.

        Returns:
            dict[str, Any]: Templates data.

        """
        self._validate_discovery()
        return self._templates

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

    def format(self, data, strict=True):
        """Fill all templates based on entered data.

        Args:
            data (dict[str, Any]): Fill data used for template formatting.
            strict (Optional[bool]): Raise exception is accessed value is
                not fully filled.

        Returns:
            TemplatesResultDict: Output `TemplateResult` have `strict`
                attribute set to False so accessing unfilled keys in templates
                won't raise any exceptions.

        """
        self._validate_discovery()
        copy_data = copy.deepcopy(data)
        roots = self._anatomy.roots
        if roots:
            copy_data["root"] = roots

        return self._solve_dict(copy_data, strict)

    def format_all(self, in_data):
        """Fill all templates based on entered data.

        Deprecated:
            Use `format` method with `strict=False` instead.

        Args:
            in_data (dict): Containing keys to be filled into template.

        Returns:
            TemplatesResultDict: Output `TemplateResult` have `strict`
                attribute set to False so accessing unfilled keys in templates
                won't raise any exceptions.

        """
        return self.format(in_data, strict=False)

    def get_template_item(
        self, category_name, template_name, subkey=None, default=_PLACEHOLDER
    ):
        """Get template item from category.

        Args:
            category_name (str): Category name.
            template_name (str): Template name.
            subkey (Optional[str]): Subkey name.
            default (Any): Default value if template is not found.

        Returns:
            Any: Template item or subkey value.

        Raises:
            KeyError: When any passed key is not available. Raise of error
                does not happen if 'default' is filled.

        """
        self._validate_discovery()
        category = self.get(category_name)
        if category is None:
            if default is not _PLACEHOLDER:
                return default
            raise KeyError("Category '{}' not found.".format(category_name))

        template_item = category.get(template_name)
        if template_item is None:
            if default is not _PLACEHOLDER:
                return default
            raise KeyError(
                "Template '{}' not found in category '{}'.".format(
                    template_name, category_name
                )
            )

        if subkey is None:
            return template_item

        item = template_item.get(subkey)
        if item is not None:
            return item

        if default is not _PLACEHOLDER:
            return default
        raise KeyError(
            "Subkey '{}' not found in '{}/{}'.".format(
                subkey, category_name, template_name
            )
        )

    def _solve_dict(self, data, strict):
        """ Solves templates with entered data.

        Args:
            data (dict): Containing keys to be filled into template.

        Returns:
            dict: With `TemplateResult` in values containing filled or
                partially filled templates.

        """
        output = {}
        for key, value in self._objected_templates.items():
            if isinstance(value, TemplateCategory):
                value = value.format(data, strict)
            elif isinstance(value, AnatomyStringTemplate):
                value = value.format(data)
            output[key] = value
        return TemplatesResultDict(output, strict=strict)

    def _validate_discovery(self):
        """Validate if templates are discovered and loaded for anatomy project.

        When project changes the cached data are reset and discovered again.
        """
        if self.project_name != self._loaded_project:
            self.reset()

        if self._templates is None:
            self._discover()
            self._loaded_project = self.project_name

    def _create_objected_templates(self, templates):
        """Create objected templates from templates data.

        Args:
            templates (dict[str, Any]): Templates data from project entity.

        Returns:
            dict[str, Any]: Values are cnmverted to template objects.

        """
        objected_templates = {}
        for category_name, category_value in copy.deepcopy(templates).items():
            if isinstance(category_value, dict):
                category_value = TemplateCategory(
                    self, category_name, category_value
                )
            elif isinstance(category_value, str):
                category_value = AnatomyStringTemplate(self, category_value)
            objected_templates[category_name] = category_value
        return objected_templates

    def _discover(self):
        """Load and cache templates from project entity."""
        if self.project_name is None:
            raise ProjectNotSet("Anatomy project is not set.")

        templates = self.anatomy["templates"]
        self._raw_templates = copy.deepcopy(templates)

        templates = copy.deepcopy(templates)
        # Make sure all the keys are available
        for key in (
            "publish",
            "hero",
            "work",
            "delivery",
            "staging",
            "others",
        ):
            templates.setdefault(key, {})

        solved_templates = self._solve_template_inner_links(templates)
        self._templates = solved_templates
        self._objected_templates = self._create_objected_templates(
            solved_templates
        )

    @classmethod
    def _replace_inner_keys(cls, matches, value, key_values, key):
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
                    or isinstance(replace_value, str)
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
    def _prepare_inner_keys(cls, key_values):
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

                if isinstance(value, str):
                    matches = cls.inner_key_pattern.findall(value)
                    if not matches:
                        keys_to_solve.remove(key)
                        continue

                    found = True
                    key_values[key] = cls._replace_inner_keys(
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
                    key_values[key][_key] = cls._replace_inner_keys(
                        matches, _value, key_values,
                        "{}.{}".format(key, _key)
                    )

                if not subdict_found:
                    keys_to_solve.remove(key)

            if not found:
                break

        return key_values

    @classmethod
    def _solve_template_inner_links(cls, templates):
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

        Returns:
            dict[str, Any]: Solved templates data.

        """
        default_key_values = templates.pop("common", {})
        output = {}
        for category_name, category_value in templates.items():
            new_category_value = {}
            for key, value in category_value.items():
                key_values = copy.deepcopy(default_key_values)
                key_values.update(value)
                new_category_value[key] = cls._prepare_inner_keys(key_values)
            output[category_name] = new_category_value

        default_keys_by_subkeys = cls._prepare_inner_keys(default_key_values)
        for key, value in default_keys_by_subkeys.items():
            output[key] = value

        return output

    @classmethod
    def _dict_to_subkeys_list(cls, subdict):
        """Convert dictionary to list of subkeys.

        Example::

            _dict_to_subkeys_list({
                "root": {
                    "work": "path/to/work",
                    "publish": "path/to/publish"
                }
            })
            [
                ["root", "work"],
                ["root", "publish"]
            ]


        Args:
            dict[str, Any]: Dictionary to be converted.

        Returns:
            list[list[str]]: List of subkeys.

        """
        output = []
        subkey_queue = collections.deque()
        subkey_queue.append((subdict, []))
        while subkey_queue:
            queue_item = subkey_queue.popleft()
            data, pre_keys = queue_item
            for key, value in data.items():
                result = list(pre_keys)
                result.append(key)
                if isinstance(value, dict):
                    subkey_queue.append((value, result))
                else:
                    output.append(result)
        return output
