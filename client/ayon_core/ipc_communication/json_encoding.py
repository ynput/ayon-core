import json

from ayon_core.host.interfaces import WorkfileInfo
from ayon_core.host import PublishedWorkfileInfo
from ayon_core.lib import get_icon_def_from_data, IconBase
from ayon_core.lib.attribute_definitions import (
    AbstractAttrDef,
    deserialize_attr_def,
)
from ayon_core.pipeline.actions import LoaderActionResult
from ayon_core.pipeline.create import InstanceContextInfo, ConvertorItem
from ayon_core.pipeline.publish import PublishReport
from ayon_core.tools.common_models import (
    TagItem,
    ProductTypeIconMapping,
    ProjectItem,
    StatusItem,
    FolderItem,
    TaskItem,
    FolderTypeItem,
    TaskTypeItem,
    UserItem,
)
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
            obj,
            (
                ProjectItem,
                StatusItem,
                FolderTypeItem,
                TaskTypeItem,
                ProductTypeItem,
                FolderItem,
                TaskItem,
                UserItem,
                TagItem,
                # Loader
                ProductItem,
                RepreItem,
                ActionItem,
                ProductTypesFilter,
                ProductTypeIconMapping,
                # Publisher
                ConvertorItem,
                CommentDef,
                CreatorItem,
                PublishReport,
                PublishErrorsReport,
                PublishAttrDefsInfo,
                InstanceContextInfo,
                PublishErrorInfo,
                InstanceItem,
                # Workfile
                WorkfileInfo,
                WorkareaFilepathResult,
                PublishedWorkfileInfo,
                PublishedWorkfileWrap,
            ),
        ):
            data = obj.to_data()
            data[OBJ_TYPE_ID_KEY] = type_name
            return data

        if isinstance(obj, LoaderActionResult):
            data = obj.to_json_data()
            data[OBJ_TYPE_ID_KEY] = type_name
            return data

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
        return UserItem.from_data(obj)

    def decode_TagItem(self, obj):
        return TagItem.from_data(obj)

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
        return ProductTypesFilter.from_data(obj)

    def decode_ProductTypeIconMapping(self, obj):
        return ProductTypeIconMapping.from_data(obj)

    def decode_LoaderActionResult(self, obj):
        return LoaderActionResult.from_json_data(obj)

    # Workfiles
    def decode_WorkfileInfo(self, obj):
        return WorkfileInfo.from_data(obj)

    def decode_PublishedWorkfileInfo(self, obj):
        return PublishedWorkfileInfo.from_data(obj)

    def decode_WorkareaFilepathResult(self, obj):
        return WorkareaFilepathResult.from_data(obj)

    def decode_PublishedWorkfileWrap(self, obj):
        return PublishedWorkfileWrap.from_data(obj)

    # Publisher
    def decode_InstanceContextInfo(self, obj):
        return InstanceContextInfo.from_data(obj)

    def decode_PublishErrorInfo(self, obj):
        return PublishErrorInfo.from_data(obj)

    def decode_InstanceItem(self, obj):
        return InstanceItem.from_data(obj)

    def decode_CreatorItem(self, obj):
        return CreatorItem.from_data(obj)

    def decode_PublishAttrDefsInfo(self, obj):
        return PublishAttrDefsInfo.from_data(obj)

    def decode_ConvertorItem(self, obj):
        return ConvertorItem.from_data(obj)

    def decode_CommentDef(self, obj):
        return CommentDef.from_data(obj)

    def decode_PublishReport(self, obj):
        return PublishReport.from_data(obj)

    def decode_PublishErrorsReport(self, obj):
        return PublishErrorsReport.from_data(obj)
