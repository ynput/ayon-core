import collections

import ayon_api


def get_last_versions_for_instances(
    project_name, instances, use_value_for_missing=False
):
    """Get last versions for instances by their folder path and product name.

    Args:
        project_name (str): Project name.
        instances (list[CreatedInstance]): Instances to get next versions for.
        use_value_for_missing (Optional[bool]): Missing values are replaced
            with negative value if True. Otherwise None is used. -2 is used
            for instances without filled folder or product name. -1 is used
            for missing entities.

    Returns:
        dict[str, Union[int, None]]: Last versions by instance id.
    """

    output = {
        instance.id: -1 if use_value_for_missing else None
        for instance in instances
    }
    product_names_by_folder_path = collections.defaultdict(set)
    instances_by_hierarchy = {}
    for instance in instances:
        folder_path = instance.data.get("folderPath")
        product_name = instance.product_name
        if not folder_path or not product_name:
            if use_value_for_missing:
                output[instance.id] = -2
            continue

        (
            instances_by_hierarchy
            .setdefault(folder_path, {})
            .setdefault(product_name, [])
            .append(instance)
        )
        product_names_by_folder_path[folder_path].add(product_name)

    product_names = set()
    for names in product_names_by_folder_path.values():
        product_names |= names

    if not product_names:
        return output

    folder_entities = ayon_api.get_folders(
        project_name,
        folder_paths=product_names_by_folder_path.keys(),
        fields={"id", "path"}
    )
    folder_paths_by_id = {
        folder_entity["id"]: folder_entity["path"]
        for folder_entity in folder_entities
    }
    if not folder_paths_by_id:
        return output

    product_entities = ayon_api.get_products(
        project_name,
        folder_ids=folder_paths_by_id.keys(),
        product_names=product_names,
        fields={"id", "name", "folderId"}
    )
    product_entities_by_id = {}
    for product_entity in product_entities:
        # Filter product entities by names under parent
        folder_id = product_entity["folderId"]
        product_name = product_entity["name"]
        folder_path = folder_paths_by_id[folder_id]
        if product_name not in product_names_by_folder_path[folder_path]:
            continue
        product_entities_by_id[product_entity["id"]] = product_entity

    if not product_entities_by_id:
        return output

    last_versions_by_product_id = ayon_api.get_last_versions(
        project_name,
        product_entities_by_id.keys(),
        fields={"version", "productId"}
    )
    for product_id, version_entity in last_versions_by_product_id.items():
        product_entity = product_entities_by_id[product_id]
        product_name = product_entity["name"]
        folder_id = product_entity["folderId"]
        folder_path = folder_paths_by_id[folder_id]
        _instances = instances_by_hierarchy[folder_path][product_name]
        for instance in _instances:
            output[instance.id] = version_entity["version"]

    return output


def get_next_versions_for_instances(project_name, instances):
    """Get next versions for instances by their folder path and product name.

    Args:
        project_name (str): Project name.
        instances (list[CreatedInstance]): Instances to get next versions for.

    Returns:
        dict[str, Union[int, None]]: Next versions by instance id. Version is
            'None' if instance has no folder path or product name.
    """

    last_versions = get_last_versions_for_instances(
        project_name, instances, True)

    output = {}
    for instance_id, version in last_versions.items():
        if version == -2:
            output[instance_id] = None
        elif version == -1:
            output[instance_id] = 1
        else:
            output[instance_id] = version + 1
    return output
