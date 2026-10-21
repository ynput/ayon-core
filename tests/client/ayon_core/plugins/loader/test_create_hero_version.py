from __future__ import annotations

from ayon_core.plugins.loader import create_hero_version


def test_execute_action_keeps_output_for_same_extensions(mocker):
    plugin = create_hero_version.CreateHeroVersion(None)
    selection = mocker.Mock()
    selection.project_name = "test_project"
    selection.get_project_settings.return_value = {}
    selection.get_project_anatomy.return_value = mocker.Mock()
    mocker.patch.object(
        create_hero_version,
        "get_template_data",
        return_value={"ext": "source", "product": {}},
    )

    version = {
        "id": "version-id",
        "productId": "product-id",
        "taskId": "task-id",
        "version": 1,
    }
    selection.get_selected_version_entities.return_value = [version]

    mocker.patch.object(
        create_hero_version.ayon_api,
        "get_project",
        return_value={"name": "test_project"},
    )
    mocker.patch.object(
        create_hero_version.ayon_api,
        "get_products",
        return_value=[
            {
                "id": "product-id",
                "folderId": "folder-id",
                "name": "image",
                "productType": "image",
            }
        ],
    )
    mocker.patch.object(
        create_hero_version.ayon_api,
        "get_folders",
        return_value=[{"id": "folder-id"}],
    )
    mocker.patch.object(
        create_hero_version.ayon_api,
        "get_tasks",
        return_value=[
            {"id": "task-id", "name": "paint", "taskType": "paint"}
        ],
    )
    mocker.patch.object(
        create_hero_version.ayon_api,
        "get_hero_versions",
        return_value=[],
    )
    mocker.patch.object(
        create_hero_version.ayon_api,
        "get_representations",
        return_value=[
            {
                "id": "png-id",
                "versionId": "version-id",
                "name": "png",
                "context": {"ext": "png", "output": "png"},
                "files": [],
            },
            {
                "id": "png-png-id",
                "versionId": "version-id",
                "name": "png_png",
                "context": {"ext": "png", "output": "png_png"},
                "files": [],
            },
        ],
    )
    create_hero_version_method = mocker.patch.object(
        plugin, "create_hero_version"
    )

    result = plugin.execute_action(selection, None, {})

    assert result.success is True
    src_representations = create_hero_version_method.call_args.args[4]
    assert src_representations["png-id"]["template_data"]["output"] == "png"
    assert (
        src_representations["png-png-id"]["template_data"]["output"]
        == "png_png"
    )
    assert (
        src_representations["png-id"]["template_data"]["ext"]
        == src_representations["png-png-id"]["template_data"]["ext"]
        == "png"
    )
