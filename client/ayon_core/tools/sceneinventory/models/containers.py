import uuid
import collections

import ayon_api
from ayon_api.graphql import GraphQlQuery
from ayon_core.host import ILoadHost


# --- Implementation that should be in ayon-python-api ---
# The implementation is not available in all versions of ayon-python-api.
RepresentationHierarchy = collections.namedtuple(
    "RepresentationHierarchy",
    ("folder", "product", "version", "representation")
)


def representations_parent_ids_qraphql_query():
    query = GraphQlQuery("RepresentationsHierarchyQuery")

    project_name_var = query.add_variable("projectName", "String!")
    repre_ids_var = query.add_variable("representationIds", "[String!]")

    project_field = query.add_field("project")
    project_field.set_filter("name", project_name_var)

    repres_field = project_field.add_field_with_edges("representations")
    repres_field.add_field("id")
    repres_field.add_field("name")
    repres_field.set_filter("ids", repre_ids_var)
    version_field = repres_field.add_field("version")
    version_field.add_field("id")
    product_field = version_field.add_field("product")
    product_field.add_field("id")
    product_field.add_field("name")
    product_field.add_field("productType")
    product_attrib_field = product_field.add_field("attrib")
    product_attrib_field.add_field("productGroup")
    folder_field = product_field.add_field("folder")
    folder_field.add_field("id")
    folder_field.add_field("path")
    return query


def get_representations_hierarchy(project_name, representation_ids):
    """Find representations parents by representation id.

    Representation parent entities up to project.

    Args:
         project_name (str): Project where to look for entities.
         representation_ids (Iterable[str]): Representation ids.

    Returns:
        dict[str, RepresentationParents]: Parent entities by
            representation id.

    """
    if not representation_ids:
        return {}

    repre_ids = set(representation_ids)
    output = {
        repre_id: RepresentationHierarchy(None, None, None, None)
        for repre_id in representation_ids
    }

    query = representations_parent_ids_qraphql_query()
    query.set_variable_value("projectName", project_name)
    query.set_variable_value("representationIds", list(repre_ids))

    con = ayon_api.get_server_api_connection()
    parsed_data = query.query(con)
    for repre in parsed_data["project"]["representations"]:
        repre_id = repre["id"]
        version = repre.pop("version")
        product = version.pop("product")
        folder = product.pop("folder")

        output[repre_id] = RepresentationHierarchy(
            folder, product, version, repre
        )

    return output
# --- END of ayon-python-api implementation ---


class ContainerItem:
    def __init__(
        self,
        representation_id,
        loader_name,
        namespace,
        object_name,
        item_id
    ):
        self.representation_id = representation_id
        self.loader_name = loader_name
        self.object_name = object_name
        self.namespace = namespace
        self.item_id = item_id

    @classmethod
    def from_container_data(cls, container):
        return cls(
            representation_id=container["representation"],
            loader_name=container["loader"],
            namespace=container["namespace"],
            object_name=container["objectName"],
            item_id=uuid.uuid4().hex,
        )


class RepresentationInfo:
    def __init__(
        self,
        folder_id,
        folder_path,
        product_id,
        product_name,
        product_type,
        product_group,
        version_id,
        representation_name,
    ):
        self.folder_id = folder_id
        self.folder_path = folder_path
        self.product_id = product_id
        self.product_name = product_name
        self.product_type = product_type
        self.product_group = product_group
        self.version_id = version_id
        self.representation_name = representation_name
        self._is_valid = None

    @property
    def is_valid(self):
        if self._is_valid is None:
            self._is_valid = (
                self.folder_id is not None
                and self.product_id is not None
                and self.version_id is not None
                and self.representation_name is not None
            )
        return self._is_valid

    @classmethod
    def new_invalid(cls):
        return cls(None, None, None, None, None, None, None, None)


class VersionItem:
    def __init__(self, version_id, product_id, version, status, is_latest):
        self.version = version
        self.version_id = version_id
        self.product_id = product_id
        self.version = version
        self.status = status
        self.is_latest = is_latest

    @property
    def is_hero(self):
        return self.version < 0

    @classmethod
    def from_entity(cls, version_entity, is_latest):
        return cls(
            version_id=version_entity["id"],
            product_id=version_entity["productId"],
            version=version_entity["version"],
            status=version_entity["status"],
            is_latest=is_latest,
        )


class ContainersModel:
    def __init__(self, controller):
        self._controller = controller
        self._items_cache = None
        self._containers_by_id = {}
        self._container_items_by_id = {}
        self._version_items_by_product_id = {}
        self._repre_info_by_id = {}

    def reset(self):
        self._items_cache = None
        self._containers_by_id = {}
        self._container_items_by_id = {}
        self._version_items_by_product_id = {}
        self._repre_info_by_id = {}

    def get_containers(self):
        self._update_cache()
        return list(self._containers_by_id.values())

    def get_containers_by_item_ids(self, item_ids):
        return {
            item_id: self._containers_by_id.get(item_id)
            for item_id in item_ids
        }

    def get_container_items(self):
        self._update_cache()
        return list(self._items_cache)

    def get_container_items_by_id(self, item_ids):
        return {
            item_id: self._container_items_by_id.get(item_id)
            for item_id in item_ids
        }

    def get_representation_info_items(self, representation_ids):
        output = {}
        missing_repre_ids = set()
        for repre_id in representation_ids:
            try:
                uuid.UUID(repre_id)
            except ValueError:
                output[repre_id] = RepresentationInfo.new_invalid()
                continue

            repre_info = self._repre_info_by_id.get(repre_id)
            if repre_info is None:
                missing_repre_ids.add(repre_id)
            else:
                output[repre_id] = repre_info

        if not missing_repre_ids:
            return output

        project_name = self._controller.get_current_project_name()
        repre_hierarchy_by_id = get_representations_hierarchy(
            project_name, missing_repre_ids
        )
        for repre_id, repre_hierarchy in repre_hierarchy_by_id.items():
            kwargs = {
                "folder_id": None,
                "folder_path": None,
                "product_id": None,
                "product_name": None,
                "product_type": None,
                "product_group": None,
                "version_id": None,
                "representation_name": None,
            }
            folder = repre_hierarchy.folder
            product = repre_hierarchy.product
            version = repre_hierarchy.version
            repre = repre_hierarchy.representation
            if folder:
                kwargs["folder_id"] = folder["id"]
                kwargs["folder_path"] = folder["path"]
            if product:
                group = product["attrib"]["productGroup"]
                kwargs["product_id"] = product["id"]
                kwargs["product_name"] = product["name"]
                kwargs["product_type"] = product["productType"]
                kwargs["product_group"] = group
            if version:
                kwargs["version_id"] = version["id"]
            if repre:
                kwargs["representation_name"] = repre["name"]

            repre_info = RepresentationInfo(**kwargs)
            self._repre_info_by_id[repre_id] = repre_info
            output[repre_id] = repre_info
        return output

    def get_version_items(self, product_ids):
        if not product_ids:
            return {}

        missing_ids = {
            product_id
            for product_id in product_ids
            if product_id not in self._version_items_by_product_id
        }
        if missing_ids:
            def version_sorted(entity):
                return entity["version"]

            project_name = self._controller.get_current_project_name()
            version_entities_by_product_id = {
                product_id: []
                for product_id in missing_ids
            }

            version_entities = list(ayon_api.get_versions(
                project_name,
                product_ids=missing_ids,
                fields={"id", "version", "productId", "status"}
            ))
            version_entities.sort(key=version_sorted)
            for version_entity in version_entities:
                product_id = version_entity["productId"]
                version_entities_by_product_id[product_id].append(
                    version_entity
                )

            for product_id, version_entities in (
                version_entities_by_product_id.items()
            ):
                last_version = abs(version_entities[-1]["version"])
                version_items_by_id = {
                    entity["id"]: VersionItem.from_entity(
                        entity, abs(entity["version"]) == last_version
                    )
                    for entity in version_entities
                }
                self._version_items_by_product_id[product_id] = (
                    version_items_by_id
                )

        return {
            product_id: dict(self._version_items_by_product_id[product_id])
            for product_id in product_ids
        }

    def _update_cache(self):
        if self._items_cache is not None:
            return

        host = self._controller.get_host()
        if isinstance(host, ILoadHost):
            containers = list(host.get_containers())
        elif hasattr(host, "ls"):
            containers = list(host.ls())
        else:
            containers = []

        container_items = []
        containers_by_id = {}
        container_items_by_id = {}
        for container in containers:
            try:
                item = ContainerItem.from_container_data(container)
            except Exception as e:
                # skip item if required data are missing
                self._controller.log_error(
                    f"Failed to create item: {e}"
                )
                continue

            containers_by_id[item.item_id] = container
            container_items_by_id[item.item_id] = item
            container_items.append(item)


        self._containers_by_id = containers_by_id
        self._container_items_by_id = container_items_by_id
        self._items_cache = container_items
