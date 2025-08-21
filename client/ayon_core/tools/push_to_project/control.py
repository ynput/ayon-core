import threading

import ayon_api

from ayon_core.settings import get_project_settings
from ayon_core.lib import prepare_template_data
from ayon_core.lib.events import QueuedEventSystem
from ayon_core.pipeline.create import get_product_name_template
from ayon_core.tools.common_models import ProjectsModel, HierarchyModel

from .models import (
    PushToProjectSelectionModel,
    UserPublishValuesModel,
    IntegrateModel,
)


class PushToContextController:
    def __init__(self, project_name=None, version_ids=None):
        self._event_system = self._create_event_system()

        self._projects_model = ProjectsModel(self)
        self._hierarchy_model = HierarchyModel(self)
        self._integrate_model = IntegrateModel(self)

        self._selection_model = PushToProjectSelectionModel(self)
        self._user_values = UserPublishValuesModel(self)

        self._src_project_name = None
        self._src_version_ids = []
        self._src_folder_entity = None
        self._src_folder_task_entities = {}
        self._src_version_entities = []
        self._src_label = None

        self._submission_enabled = False
        self._process_thread = None
        self._process_item_id = None

        self._use_original_name = False

        self.set_source(project_name, version_ids)

    # Events system
    def emit_event(self, topic, data=None, source=None):
        """Use implemented event system to trigger event."""

        if data is None:
            data = {}
        self._event_system.emit(topic, data, source)

    def register_event_callback(self, topic, callback):
        self._event_system.add_callback(topic, callback)

    def set_source(self, project_name, version_ids):
        """Set source project and version.

        Args:
            project_name (Union[str, None]): Source project name.
            version_ids (Optional[list[str]]): Version ids.
        """
        if not project_name or not version_ids:
            return
        if (
            project_name == self._src_project_name
            and version_ids == self._src_version_ids
        ):
            return

        self._src_project_name = project_name
        self._src_version_ids = version_ids
        self._src_label = None
        folder_entity = None
        task_entities = {}
        product_entities = []
        version_entities = []
        if project_name and self._src_version_ids:
            version_entities = list(ayon_api.get_versions(
                project_name, version_ids=self._src_version_ids))

        if version_entities:
            product_ids = [
                version_entity["productId"]
                for version_entity in version_entities
            ]
            product_entities = list(ayon_api.get_products(
                project_name, product_ids=product_ids)
            )

        if product_entities:
            # all products for same folder
            product_entity = product_entities[0]
            folder_entity = ayon_api.get_folder_by_id(
                project_name, product_entity["folderId"]
            )

        if folder_entity:
            task_entities = {
                task_entity["name"]: task_entity
                for task_entity in ayon_api.get_tasks(
                    project_name, folder_ids=[folder_entity["id"]]
                )
            }

        self._src_folder_entity = folder_entity
        self._src_folder_task_entities = task_entities
        self._src_version_entities = version_entities
        if folder_entity:
            self._user_values.set_new_folder_name(folder_entity["name"])
            variant = self._get_src_variant()
            if variant:
                self._user_values.set_variant(variant)

            comment = version_entities[0]["attrib"].get("comment")
            if comment:
                self._user_values.set_comment(comment)

        self._emit_event(
            "source.changed",
            {
                "project_name": project_name,
                "version_ids": self._src_version_ids
            }
        )

    def get_source_label(self):
        """Get source label.

        Returns:
            str: Label describing source project and version as path.
        """

        if self._src_label is None:
            self._src_label = self._prepare_source_label()
        return self._src_label

    def get_project_items(self, sender=None):
        return self._projects_model.get_project_items(sender)

    def get_folder_items(self, project_name, sender=None):
        return self._hierarchy_model.get_folder_items(project_name, sender)

    def get_task_items(self, project_name, folder_id, sender=None):
        return self._hierarchy_model.get_task_items(
            project_name, folder_id, sender
        )

    def get_user_values(self):
        return self._user_values.get_data()

    def set_user_value_folder_name(self, folder_name):
        self._user_values.set_new_folder_name(folder_name)
        self._invalidate()

    def set_user_value_variant(self, variant):
        self._user_values.set_variant(variant)
        self._invalidate()

    def set_user_value_comment(self, comment):
        self._user_values.set_comment(comment)
        self._invalidate()

    def set_selected_project(self, project_name):
        self._selection_model.set_selected_project(project_name)
        self._invalidate()

    def set_selected_folder(self, folder_id):
        self._selection_model.set_selected_folder(folder_id)
        self._invalidate()

    def set_selected_task(self, task_id, task_name):
        self._selection_model.set_selected_task(task_id, task_name)

    def get_process_item_status(self, item_id):
        return self._integrate_model.get_item_status(item_id)

    # Processing methods
    def submit(self, wait=True):
        if not self._submission_enabled:
            return

        if self._process_thread is not None:
            return

        item_ids = []
        for src_version_entity in self._src_version_entities:
            item_id = self._integrate_model.create_process_item(
                self._src_project_name,
                src_version_entity["id"],
                self._selection_model.get_selected_project_name(),
                self._selection_model.get_selected_folder_id(),
                self._selection_model.get_selected_task_name(),
                self._user_values.variant,
                comment=self._user_values.comment,
                new_folder_name=self._user_values.new_folder_name,
                dst_version=1,
                use_original_name=self._use_original_name,
            )
            item_ids.append(item_id)

        self._process_item_ids = item_ids
        self._emit_event("submit.started")
        if wait:
            self._submit_callback()
            self._process_item_ids = []
            return item_id

        thread = threading.Thread(target=self._submit_callback)
        self._process_thread = thread
        thread.start()
        return item_ids

    def wait_for_process_thread(self):
        if self._process_thread is None:
            return
        self._process_thread.join()
        self._process_thread = None

    def _prepare_source_label(self):
        if not self._src_project_name or not self._src_version_ids:
            return "Source is not defined"

        folder_entity = self._src_folder_entity
        if not folder_entity:
            return "Source is invalid"

        folder_path = folder_entity["path"]
        src_labels = []
        for version_entity in self._src_version_entities:
            product_entity = ayon_api.get_product_by_id(
                self._src_project_name,
                version_entity["productId"]
            )
            src_labels.append(
                "Source: {}{}/{}/v{:0>3}".format(
                    self._src_project_name,
                    folder_path,
                    product_entity["name"],
                    version_entity["version"],
                )
            )

        return "\n".join(src_labels)

    def _get_task_info_from_repre_entities(
        self, task_entities, repre_entities
    ):
        found_comb = []
        for repre_entity in repre_entities:
            context = repre_entity["context"]
            repre_task_name = context.get("task")
            if repre_task_name is None:
                continue

            if isinstance(repre_task_name, dict):
                repre_task_name = repre_task_name.get("name")

            task_name = None
            task_type = None
            if repre_task_name:
                task_info = task_entities.get(repre_task_name) or {}
                task_name = task_info.get("name")
                task_type = task_info.get("type")

            if task_name and task_type:
                return task_name, task_type

            if task_name:
                found_comb.append((task_name, task_type))

        for task_name, task_type in found_comb:
            return task_name, task_type
        return None, None

    def _get_src_variant(self):
        project_name = self._src_project_name
        # parse variant only from first version
        version_entity = self._src_version_entities[0]
        task_entities = self._src_folder_task_entities
        repre_entities = ayon_api.get_representations(
            project_name, version_ids={version_entity["id"]}
        )
        task_name, task_type = self._get_task_info_from_repre_entities(
            task_entities, repre_entities
        )
        product_entity = ayon_api.get_product_by_id(
            project_name,
            version_entity["productId"]
        )

        project_settings = get_project_settings(project_name)
        product_type = product_entity["productType"]
        template = get_product_name_template(
            self._src_project_name,
            product_type,
            task_name,
            task_type,
            None,
            project_settings=project_settings
        )
        template_low = template.lower()
        variant_placeholder = "{variant}"
        if (
            variant_placeholder not in template_low
            or (not task_name and "{task" in template_low)
        ):
            return ""

        idx = template_low.index(variant_placeholder)
        template_s = template[:idx]
        template_e = template[idx + len(variant_placeholder):]
        fill_data = prepare_template_data({
            "family": product_type,
            "product": {
                "type": product_type,
            },
            "task": task_name
        })
        try:
            product_s = template_s.format(**fill_data)
            product_e = template_e.format(**fill_data)
        except Exception as exc:
            print("Failed format", exc)
            return ""

        product_name = product_entity["name"]
        if (
            (product_s and not product_name.startswith(product_s))
            or (product_e and not product_name.endswith(product_e))
        ):
            return ""

        if product_s:
            product_name = product_name[len(product_s):]
        if product_e:
            product_name = product_name[:len(product_e)]
        return product_name

    def _check_submit_validations(self):
        if not self._selection_model.get_selected_project_name():
            return False

        if (
            self._user_values.new_folder_name is None
            and not self._selection_model.get_selected_folder_id()
        ):
            return False

        if self._use_original_name:
            return True

        if not self._user_values.is_valid:
            return False

        return True

    def _invalidate(self):
        submission_enabled = self._check_submit_validations()
        if submission_enabled == self._submission_enabled:
            return
        self._submission_enabled = submission_enabled
        self._emit_event(
            "submission.enabled.changed",
            {"enabled": submission_enabled}
        )

    def _submit_callback(self):
        process_item_ids = self._process_item_ids
        for process_item_id in process_item_ids:
            self._integrate_model.integrate_item(process_item_id)

        self._emit_event("submit.finished", {})

        if process_item_ids is self._process_item_ids:
            self._process_item_ids = []

    def _emit_event(self, topic, data=None):
        if data is None:
            data = {}
        self.emit_event(topic, data, "controller")

    def _create_event_system(self):
        return QueuedEventSystem()
