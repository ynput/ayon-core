from dataclasses import asdict
import json

from ayon_core.host.interfaces import WorkfileInfo
from ayon_core.host import PublishedWorkfileInfo
from ayon_core.lib import get_icon_def_from_data, IconBase
from ayon_core.lib.attribute_definitions import (
    AbstractAttrDef,
    deserialize_attr_def,
)
from ayon_core.tools.common_models import (
    TagItem,
    ProductTypeIconMapping,
    ProjectItem,
    StatusItem,
    FolderItem,
    TaskItem,
    FolderTypeItem,
    TaskTypeItem,
)
from ayon_core.pipeline.create import InstanceContextInfo, ConvertorItem
from ayon_core.pipeline.publish import PublishReport
from ayon_core.tools.common_models.users import UserItem
from ayon_core.tools.loader.abstract import (
    ProductItem,
    ProductTypeItem,
    RepreItem,
    ActionItem,
    ProductTypesFilter,
)
from ayon_core.tools.publisher.models.create import (
    InstanceItem,
    CreatorItem,
)
from ayon_core.tools.publisher.models.publish import (
    PublishErrorsReport,
    PublishErrorInfo,
)
from ayon_core.tools.publisher.abstract import (
    CommentDef,
    PublishAttrDefsInfo,
)
from ayon_core.tools.workfiles.abstract import (
    WorkareaFilepathResult,
    PublishedWorkfileWrap,
)

OBJ_TYPE_ID_KEY = "__obj_type__"


class DataEncoder(json.JSONEncoder):
    def default(self, obj):
        if obj is None:
            return None

        if isinstance(obj, (list, dict, str, int, float, bool)):
            return obj

        if isinstance(obj, set):
            return {
                OBJ_TYPE_ID_KEY: "py_set",
                "data": list(obj),
            }

        if isinstance(obj, IconBase):
            data = obj.to_data()
            data[OBJ_TYPE_ID_KEY] = "IconBase"
            return data

        if isinstance(obj, AbstractAttrDef):
            data = obj.serialize()
            data[OBJ_TYPE_ID_KEY] = "AbstractAttrDef"
            return data

        type_name = type(obj).__name__
        if isinstance(
            obj, (
                ProjectItem,
                StatusItem,
                FolderTypeItem,
                TaskTypeItem,
                ProductTypeItem,
                FolderItem,
                TaskItem,
                # Loader
                ProductItem,
                RepreItem,
                ActionItem,
                # Publisher
                ConvertorItem,
                CommentDef,
                CreatorItem,
                PublishReport,
                PublishErrorsReport,
                # Workfile
                WorkfileInfo,
                PublishedWorkfileInfo,
            )
        ):
            data = obj.to_data()
            data[OBJ_TYPE_ID_KEY] = type_name
            return data

        if isinstance(obj, UserItem):
            return {
                OBJ_TYPE_ID_KEY: type_name,
                "username": obj.username,
                "full_name": obj.full_name,
                "email": obj.email,
                "avatar_url": obj.avatar_url,
                "active": obj.active,
            }

        if isinstance(obj, TagItem):
            return {
                OBJ_TYPE_ID_KEY: type_name,
                "name": obj.name,
                "color": obj.color,
            }

        # Loader
        if isinstance(obj, ProductTypesFilter):
            return {
                OBJ_TYPE_ID_KEY: type_name,
                "product_types": obj.product_types,
                "is_allow_list": obj.is_allow_list,
            }

        if isinstance(obj, ProductTypeIconMapping):
            return {
                OBJ_TYPE_ID_KEY: type_name,
                "default": obj._default,
                "definitions": obj._definitions,
            }

        # Publisher
        if isinstance(obj, InstanceItem):
            return {
                OBJ_TYPE_ID_KEY: type_name,
                "instance_id": obj.id,
                "creator_identifier": obj.creator_identifier,
                "label": obj.label,
                "group_label": obj.group_label,
                "product_base_type": obj.product_base_type,
                "product_type": obj.product_type,
                "product_name": obj.product_name,
                "variant": obj.variant,
                "folder_path": obj.folder_path,
                "task_name": obj.task_name,
                "is_active": obj.is_active,
                "is_mandatory": obj.is_mandatory,
                "has_promised_context": obj.has_promised_context,
                "parent_instance_id": obj.parent_instance_id,
                "parent_flags": obj.parent_flags,
            }

        if isinstance(obj, PublishAttrDefsInfo):
            data = asdict(obj)
            data[OBJ_TYPE_ID_KEY] = type_name
            return data

        if isinstance(obj, InstanceContextInfo):
            return {
                OBJ_TYPE_ID_KEY: type_name,
                "folder_path": obj.folder_path,
                "task_name": obj.task_name,
                "folder_is_valid": obj.folder_is_valid,
                "task_is_valid": obj.task_is_valid,
            }

        if isinstance(obj, PublishErrorInfo):
            return {
                OBJ_TYPE_ID_KEY: type_name,
                "message": obj.message,
                "is_unknown_error": obj.is_unknown_error,
                "description": obj.description,
                "title": obj.title,
                "detail": obj.detail,
            }

        # Workfiles
        if isinstance(obj, WorkareaFilepathResult):
            return {
                OBJ_TYPE_ID_KEY: type_name,
                "root": obj.root,
                "filename": obj.filename,
                "exists": obj.exists,
                "filepath": obj.filepath,
            }

        if isinstance(obj, PublishedWorkfileWrap):
            return {
                OBJ_TYPE_ID_KEY: type_name,
                "info": obj.info,
                "comment": obj.comment,
            }

        return super().default(obj)


class DataDecoder(json.JSONDecoder):
    def __init__(self, **kwargs):
        kwargs["object_hook"] = self.object_hook
        super().__init__(**kwargs)

    def object_hook(self, obj):
        name = obj.pop(OBJ_TYPE_ID_KEY, None)
        if name is None:
            return obj

        decoder = getattr(self, f"decode_{name}")
        return decoder(obj)

    def decode_py_set(self, obj):
        return set(obj["data"])

    def decode_IconBase(self, obj):
        return get_icon_def_from_data(obj)

    def decode_AbstractAttrDef(self, obj):
        return deserialize_attr_def(obj)

    def decode_UserItem(self, obj):
        return UserItem(**obj)

    def decode_TagItem(self, obj):
        return TagItem(**obj)

    def decode_ProjectItem(self, obj):
        return ProjectItem.from_data(obj)

    def decode_StatusItem(self, obj):
        return StatusItem.from_data(obj)

    def decode_FolderTypeItem(self, obj):
        return FolderTypeItem.from_data(obj)

    def decode_TaskTypeItem(self, obj):
        return TaskTypeItem.from_data(obj)

    def decode_ProductTypeItem(self, obj):
        return ProductTypeItem.from_data(obj)

    def decode_FolderItem(self, obj):
        return FolderItem.from_data(obj)

    def decode_TaskItem(self, obj):
        return TaskItem.from_data(obj)

    # Loader
    def decode_ProductItem(self, obj):
        return ProductItem.from_data(obj)

    def decode_RepreItem(self, obj):
        return RepreItem.from_data(obj)

    def decode_ActionItem(self, obj):
        return ActionItem.from_data(obj)

    def decode_ProductTypesFilter(self, obj):
        return ProductTypesFilter(**obj)

    def decode_ProductTypeIconMapping(self, obj):
        return ProductTypeIconMapping(obj["default"], obj["definitions"])

    # Workfiles
    def decode_WorkfileInfo(self, obj):
        return WorkfileInfo.from_data(obj)

    def decode_PublishedWorkfileInfo(self, obj):
        return PublishedWorkfileInfo.from_data(obj)

    def decode_WorkareaFilepathResult(self, obj):
        return WorkareaFilepathResult(
            root=obj["root"],
            filename=obj["filename"],
            exists=obj["exists"],
            filepath=obj["filepath"]
        )

    def decode_PublishedWorkfileWrap(self, obj):
        return PublishedWorkfileWrap(
            info=obj["info"],
            comment=obj["comment"]
        )

    # Publisher
    def decode_InstanceContextInfo(self, obj):
        return InstanceContextInfo(
            folder_path=obj["folder_path"],
            task_name=obj["task_name"],
            folder_is_valid=obj["folder_is_valid"],
            task_is_valid=obj["task_is_valid"],
        )

    def decode_PublishErrorInfo(self, obj):
        return PublishErrorInfo(
            message=obj["message"],
            is_unknown_error=obj["is_unknown_error"],
            description=obj["description"],
            title=obj["title"],
        )

    def decode_InstanceItem(self, obj):
        return InstanceItem(**obj)

    def decode_CreatorItem(self, obj):
        return CreatorItem.from_data(obj)

    def decode_PublishAttrDefsInfo(self, obj):
        return PublishAttrDefsInfo(**obj)

    def decode_ConvertorItem(self, obj):
        return ConvertorItem.from_data(obj)

    def decode_CommentDef(self, obj):
        return CommentDef.from_data(obj)

    def decode_PublishReport(self, obj):
        return PublishReport.from_data(obj)

    def decode_PublishErrorsReport(self, obj):
        # TODO fix bug in ayon-core where 'from_data' is wrong
        from ayon_core.tools.publisher.models.publish import (
            PublishErrorItem,
            PublishPluginActionItem,
        )

        error_items = [
            PublishErrorItem.from_data(error_item)
            for error_item in obj["error_items"]
        ]
        plugin_action_items = {}
        for plugin_id, action_items in obj["plugin_action_items"].items():
            action_items = plugin_action_items.setdefault(plugin_id, [])
            for action_item in action_items:
                item = PublishPluginActionItem.from_data(action_item)
                action_items.append(item)

        return PublishErrorsReport(error_items, plugin_action_items)
