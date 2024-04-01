"""Workfile build based on settings.

Workfile builder will do stuff based on project settings. Advantage is that
it need only access to settings. Disadvantage is that it is hard to focus
build per context and being explicit about loaded content.

For more explicit workfile build is recommended 'AbstractTemplateBuilder'
from '~/ayon_core/pipeline/workfile/workfile_template_builder'. Which gives
more abilities to define how build happens but require more code to achive it.
"""

import re
import collections
import json

import ayon_api

from ayon_core.settings import get_project_settings
from ayon_core.lib import (
    filter_profiles,
    Logger,
)
from ayon_core.pipeline.load import (
    discover_loader_plugins,
    IncompatibleLoaderError,
    load_container,
)


class BuildWorkfile:
    """Wrapper for build workfile process.

    Load representations for current context by build presets. Build presets
    are host related, since each host has it's loaders.
    """

    _log = None

    @property
    def log(self):
        if self._log is None:
            self._log = Logger.get_logger(self.__class__.__name__)
        return self._log

    @staticmethod
    def map_products_by_type(product_entities):
        products_by_type = collections.defaultdict(list)
        for product_entity in product_entities:
            product_type = product_entity["productType"]
            products_by_type[product_type].append(product_entity)
        return products_by_type

    def process(self):
        """Main method of this wrapper.

        Building of workfile is triggered and is possible to implement
        post processing of loaded containers if necessary.

        Returns:
            List[Dict[str, Any]]: Loaded containers during build.
        """

        return self.build_workfile()

    def build_workfile(self):
        """Prepares and load containers into workfile.

        Loads latest versions of current and linked folders to workfile by
        logic stored in Workfile profiles from presets. Profiles are set
        by host, filtered by current task name and used by families.

        Each product type can specify representation names and loaders for
        representations and first available and successful loaded
        representation is returned as container.

        At the end you'll get list of loaded containers per each folder.

        loaded_containers [{
            "folder_entity": <FolderEntity1>,
            "containers": [<Container1>, <Container2>, ...]
        }, {
            "folder_entity": <FolderEntity2>,
            "containers": [<Container3>, ...]
        }, {
            ...
        }]

        Returns:
            List[Dict[str, Any]]: Loaded containers during build.
        """

        from ayon_core.pipeline.context_tools import get_current_context

        loaded_containers = []

        # Get current folder and task entities
        context = get_current_context()
        project_name = context["project_name"]
        current_folder_path = context["folder_path"]
        current_task_name = context["task_name"]

        current_folder_entity = ayon_api.get_folder_by_path(
            project_name, current_folder_path
        )
        # Skip if folder was not found
        if not current_folder_entity:
            print("Folder entity `{}` was not found".format(
                current_folder_path
            ))
            return loaded_containers

        # Prepare available loaders
        loaders_by_name = {}
        for loader in discover_loader_plugins():
            if not loader.enabled:
                continue
            loader_name = loader.__name__
            if loader_name in loaders_by_name:
                raise KeyError(
                    "Duplicated loader name {0}!".format(loader_name)
                )
            loaders_by_name[loader_name] = loader

        # Skip if there are any loaders
        if not loaders_by_name:
            self.log.warning("There are no registered loaders.")
            return loaded_containers

        # Load workfile presets for task
        self.build_presets = self.get_build_presets(
            current_task_name, current_folder_entity["id"]
        )

        # Skip if there are any presets for task
        if not self.build_presets:
            self.log.warning(
                "Current task `{}` does not have any loading preset.".format(
                    current_task_name
                )
            )
            return loaded_containers

        # Get presets for loading current folder
        current_context_profiles = self.build_presets.get("current_context")
        # Get presets for loading linked folders
        link_context_profiles = self.build_presets.get("linked_assets")
        # Skip if both are missing
        if not current_context_profiles and not link_context_profiles:
            self.log.warning(
                "Current task `{}` has empty loading preset.".format(
                    current_task_name
                )
            )
            return loaded_containers

        elif not current_context_profiles:
            self.log.warning((
                "Current task `{}` doesn't have any loading"
                " preset for it's context."
            ).format(current_task_name))

        elif not link_context_profiles:
            self.log.warning((
                "Current task `{}` doesn't have any"
                "loading preset for it's linked folders."
            ).format(current_task_name))

        # Prepare folders to process by workfile presets
        folder_entities = []
        current_folder_id = None
        if current_context_profiles:
            # Add current folder entity if preset has current context set
            folder_entities.append(current_folder_entity)
            current_folder_id = current_folder_entity["id"]

        if link_context_profiles:
            # Find and append linked folders if preset has set linked mapping
            linked_folder_entities = self._get_linked_folder_entities(
                project_name, current_folder_entity["id"]
            )
            if linked_folder_entities:
                folder_entities.extend(linked_folder_entities)

        # Skip if there are no folders. This can happen if only linked mapping
        # is set and there are no links for his folder.
        if not folder_entities:
            self.log.warning(
                "Folder does not have linked folders. Nothing to process."
            )
            return loaded_containers

        # Prepare entities from database for folders
        prepared_entities = self._collect_last_version_repres(
            folder_entities
        )

        # Load containers by prepared entities and presets
        # - Current folder containers
        if current_folder_id and current_folder_id in prepared_entities:
            current_context_data = prepared_entities.pop(current_folder_id)
            loaded_data = self.load_containers_by_folder_data(
                current_context_data,
                current_context_profiles,
                loaders_by_name
            )
            if loaded_data:
                loaded_containers.append(loaded_data)

        # - Linked assets container
        for linked_folder_data in prepared_entities.values():
            loaded_data = self.load_containers_by_folder_data(
                linked_folder_data,
                link_context_profiles,
                loaders_by_name
            )
            if loaded_data:
                loaded_containers.append(loaded_data)

        # Return list of loaded containers
        return loaded_containers

    def get_build_presets(self, task_name, folder_id):
        """ Returns presets to build workfile for task name.

        Presets are loaded for current project received by
        'get_current_project_name', filtered by registered host
        and entered task name.

        Args:
            task_name (str): Task name used for filtering build presets.
            folder_id (str): Folder id.

        Returns:
            Dict[str, Any]: preset per entered task name
        """

        from ayon_core.pipeline.context_tools import (
            get_current_host_name,
            get_current_project_name,
        )

        project_name = get_current_project_name()
        host_name = get_current_host_name()
        project_settings = get_project_settings(project_name)

        host_settings = project_settings.get(host_name) or {}
        # Get presets for host
        wb_settings = host_settings.get("workfile_builder")
        if not wb_settings:
            # backward compatibility
            wb_settings = host_settings.get("workfile_build") or {}

        builder_profiles = wb_settings.get("profiles")
        if not builder_profiles:
            return None

        task_entity = ayon_api.get_task_by_name(
            project_name,
            folder_id,
            task_name,
        )
        task_type = None
        if task_entity:
            task_type = task_entity["taskType"]

        filter_data = {
            "task_types": task_type,
            "tasks": task_name
        }
        return filter_profiles(builder_profiles, filter_data)

    def _filter_build_profiles(self, build_profiles, loaders_by_name):
        """ Filter build profiles by loaders and prepare process data.

        Valid profile must have "loaders", "families" and "repre_names" keys
        with valid values.
        - "loaders" expects list of strings representing possible loaders.
        - "families" expects list of strings for filtering
                     by product type.
        - "repre_names" expects list of strings for filtering by
                        representation name.

        Lowered "families" and "repre_names" are prepared for each profile with
        all required keys.

        Args:
            build_profiles (Dict[str, Any]): Profiles for building workfile.
            loaders_by_name (Dict[str, LoaderPlugin]): Available loaders
                per name.

        Returns:
            List[Dict[str, Any]]: Filtered and prepared profiles.
        """

        valid_profiles = []
        for profile in build_profiles:
            # Check loaders
            profile_loaders = profile.get("loaders")
            if not profile_loaders:
                self.log.warning((
                    "Build profile has missing loaders configuration: {0}"
                ).format(json.dumps(profile, indent=4)))
                continue

            # Check if any loader is available
            loaders_match = False
            for loader_name in profile_loaders:
                if loader_name in loaders_by_name:
                    loaders_match = True
                    break

            if not loaders_match:
                self.log.warning((
                    "All loaders from Build profile are not available: {0}"
                ).format(json.dumps(profile, indent=4)))
                continue

            # Check product types
            profile_product_types = profile.get("product_types")
            if not profile_product_types:
                self.log.warning((
                    "Build profile is missing families configuration: {0}"
                ).format(json.dumps(profile, indent=4)))
                continue

            # Check representation names
            profile_repre_names = profile.get("repre_names")
            if not profile_repre_names:
                self.log.warning((
                    "Build profile is missing"
                    " representation names filtering: {0}"
                ).format(json.dumps(profile, indent=4)))
                continue

            # Prepare lowered families and representation names
            profile["product_types_lowered"] = [
                product_type.lower()
                for product_type in profile_product_types
            ]
            profile["repre_names_lowered"] = [
                name.lower() for name in profile_repre_names
            ]

            valid_profiles.append(profile)

        return valid_profiles

    def _get_linked_folder_entities(self, project_name, folder_id):
        """Get linked folder entities for entered folder.

        Args:
            project_name (str): Project name.
            folder_id (str): Folder id.

        Returns:
            list[dict[str, Any]]: Linked folder entities.

        """
        links = ayon_api.get_folder_links(
            project_name, folder_id, link_direction="in"
        )
        linked_folder_ids = {
            link["entityId"]
            for link in links
            if link["entityType"] == "folder"
        }
        if not linked_folder_ids:
            return []
        return list(ayon_api.get_folders(
            project_name, folder_ids=linked_folder_ids
        ))

    def _prepare_profile_for_products(self, product_entities, profiles):
        """Select profile for each product by it's data.

        Profiles are filtered for each product individually.
        Profile is filtered by product type, optionally by name regex and
        representation names set in profile.
        It is possible to not find matching profile for product, in that case
        product is skipped and it is possible that none of products have
        matching profile.

        Args:
            product_entities (List[Dict[str, Any]]): product entities.
            profiles (List[Dict[str, Any]]): Build profiles.

        Returns:
            Dict[str, Any]: Profile by product id.
        """

        # Prepare products
        products_by_type = self.map_products_by_type(product_entities)

        profiles_by_product_id = {}
        for product_type, product_entities in products_by_type.items():
            product_type_low = product_type.lower()
            for profile in profiles:
                # Skip profile if does not contain product type
                if product_type_low not in profile["product_types_lowered"]:
                    continue

                # Precompile name filters as regexes
                profile_regexes = profile.get("product_name_filters")
                if profile_regexes:
                    _profile_regexes = []
                    for regex in profile_regexes:
                        _profile_regexes.append(re.compile(regex))
                    profile_regexes = _profile_regexes

                # TODO prepare regex compilation
                for product_entity in product_entities:
                    # Verify regex filtering (optional)
                    if profile_regexes:
                        valid = False
                        for pattern in profile_regexes:
                            if re.match(pattern, product_entity["name"]):
                                valid = True
                                break

                        if not valid:
                            continue

                    profiles_by_product_id[product_entity["id"]] = profile

                # break profiles loop on finding the first matching profile
                break
        return profiles_by_product_id

    def load_containers_by_folder_data(
        self, linked_folder_data, build_profiles, loaders_by_name
    ):
        """Load containers for entered folder entity by Build profiles.

        Args:
            linked_folder_data (Dict[str, Any]): Prepared data with products,
                last versions and representations for specific folder.
            build_profiles (Dict[str, Any]): Build profiles.
            loaders_by_name (Dict[str, LoaderPlugin]): Available loaders
                per name.

        Returns:
            Dict[str, Any]: Output contains folder entity
                and loaded containers.
        """

        # Make sure all data are not empty
        if not linked_folder_data or not build_profiles or not loaders_by_name:
            return

        folder_entity = linked_folder_data["folder_entity"]

        valid_profiles = self._filter_build_profiles(
            build_profiles, loaders_by_name
        )
        if not valid_profiles:
            self.log.warning(
                "There are not valid Workfile profiles. Skipping process."
            )
            return

        self.log.debug("Valid Workfile profiles: {}".format(valid_profiles))

        products_by_id = {}
        version_by_product_id = {}
        repres_by_version_id = {}
        for product_id, in_data in linked_folder_data["products"].items():
            product_entity = in_data["product_entity"]
            products_by_id[product_entity["id"]] = product_entity

            version_data = in_data["version"]
            version_entity = version_data["version_entity"]
            version_by_product_id[product_id] = version_entity
            repres_by_version_id[version_entity["id"]] = (
                version_data["repres"]
            )

        if not products_by_id:
            self.log.warning("There are not products for folder {}".format(
                folder_entity["path"]
            ))
            return

        profiles_by_product_id = self._prepare_profile_for_products(
            products_by_id.values(), valid_profiles
        )
        if not profiles_by_product_id:
            self.log.warning("There are not valid products.")
            return

        valid_repres_by_product_id = collections.defaultdict(list)
        for product_id, profile in profiles_by_product_id.items():
            profile_repre_names = profile["repre_names_lowered"]

            version_entity = version_by_product_id[product_id]
            version_id = version_entity["id"]
            repres = repres_by_version_id[version_id]
            for repre in repres:
                repre_name_low = repre["name"].lower()
                if repre_name_low in profile_repre_names:
                    valid_repres_by_product_id[product_id].append(repre)

        # DEBUG message
        msg = "Valid representations for Folder: `{}`".format(
            folder_entity["path"]
        )
        for product_id, repres in valid_repres_by_product_id.items():
            product_entity = products_by_id[product_id]
            msg += "\n# Product Name/ID: `{}`/{}".format(
                product_entity["name"], product_id
            )
            for repre in repres:
                msg += "\n## Repre name: `{}`".format(repre["name"])

        self.log.debug(msg)

        containers = self._load_containers(
            valid_repres_by_product_id, products_by_id,
            profiles_by_product_id, loaders_by_name
        )

        return {
            "folder_entity": folder_entity,
            "containers": containers
        }

    def _load_containers(
        self, repres_by_product_id, products_by_id,
        profiles_by_product_id, loaders_by_name
    ):
        """Real load by collected data happens here.

        Loading of representations per product happens here. Each product can
        loads one representation. Loading is tried in specific order.
        Representations are tried to load by names defined in configuration.
        If product has representation matching representation name each loader
        is tried to load it until any is successful. If none of them was
        successful then next representation name is tried.
        Product process loop ends when any representation is loaded or
        all matching representations were already tried.

        Args:
            repres_by_product_id (Dict[str, Dict[str, Any]]): Available
                representations mapped by their parent (product) id.
            products_by_id (Dict[str, Dict[str, Any]]): Product entities
                mapped by their id.
            profiles_by_product_id (Dict[str, Dict[str, Any]]): Build profiles
                mapped by product id.
            loaders_by_name (Dict[str, LoaderPlugin]): Available loaders
                per name.

        Returns:
            List[Dict[str, Any]]: Objects of loaded containers.
        """

        loaded_containers = []

        # Get product id order from build presets.
        build_presets = self.build_presets.get("current_context", [])
        build_presets += self.build_presets.get("linked_assets", [])
        product_ids_ordered = []
        for preset in build_presets:
            for product_type in preset["product_types"]:
                for product_id, product_entity in products_by_id.items():
                    # TODO 'families' is not available on product
                    families = product_entity["data"].get("families") or []
                    if product_type not in families:
                        continue

                    product_ids_ordered.append(product_id)

        # Order representations from products.
        print("repres_by_product_id", repres_by_product_id)
        representations_ordered = []
        representations = []
        for ordered_product_id in product_ids_ordered:
            for product_id, repres in repres_by_product_id.items():
                if repres in representations:
                    continue

                if ordered_product_id == product_id:
                    representations_ordered.append((product_id, repres))
                    representations.append(repres)

        print("representations", representations)

        # Load ordered representations.
        for product_id, repres in representations_ordered:
            product_name = products_by_id[product_id]["name"]

            profile = profiles_by_product_id[product_id]
            loaders_last_idx = len(profile["loaders"]) - 1
            repre_names_last_idx = len(profile["repre_names_lowered"]) - 1

            repre_by_low_name = {
                repre["name"].lower(): repre for repre in repres
            }

            is_loaded = False
            for repre_name_idx, profile_repre_name in enumerate(
                profile["repre_names_lowered"]
            ):
                # Break iteration if representation was already loaded
                if is_loaded:
                    break

                repre = repre_by_low_name.get(profile_repre_name)
                if not repre:
                    continue

                for loader_idx, loader_name in enumerate(profile["loaders"]):
                    if is_loaded:
                        break

                    loader = loaders_by_name.get(loader_name)
                    if not loader:
                        continue
                    try:
                        container = load_container(
                            loader,
                            repre["id"],
                            name=product_name
                        )
                        loaded_containers.append(container)
                        is_loaded = True

                    except Exception as exc:
                        if exc == IncompatibleLoaderError:
                            self.log.info((
                                "Loader `{}` is not compatible with"
                                " representation `{}`"
                            ).format(loader_name, repre["name"]))

                        else:
                            self.log.error(
                                "Unexpected error happened during loading",
                                exc_info=True
                            )

                        msg = "Loading failed."
                        if loader_idx < loaders_last_idx:
                            msg += " Trying next loader."
                        elif repre_name_idx < repre_names_last_idx:
                            msg += (
                                " Loading of product `{}` was not successful."
                            ).format(product_name)
                        else:
                            msg += " Trying next representation."
                        self.log.info(msg)

        return loaded_containers

    def _collect_last_version_repres(self, folder_entities):
        """Collect products, versions and representations for folder_entities.

        Args:
            folder_entities (List[Dict[str, Any]]): Folder entities for which
                want to find data.

        Returns:
            Dict[str, Any]: collected entities

        Example output:
        ```
        {
            <folder id>: {
                "folder_entity": <dict[str, Any]>,
                "products": {
                    <product id>: {
                        "product_entity": <dict[str, Any]>,
                        "version": {
                            "version_entity": <VersionEntity>,
                            "repres": [
                                <RepreEntity1>, <RepreEntity2>, ...
                            ]
                        }
                    },
                    ...
                }
            },
            ...
        }
        output[folder_id]["products"][product_id]["version"]["repres"]
        ```
        """

        from ayon_core.pipeline.context_tools import get_current_project_name

        output = {}
        if not folder_entities:
            return output

        folder_entities_by_id = {
            folder_entity["id"]: folder_entity
            for folder_entity in folder_entities
        }

        project_name = get_current_project_name()
        product_entities = list(ayon_api.get_products(
            project_name, folder_ids=folder_entities_by_id.keys()
        ))
        product_entities_by_id = {
            product_entity["id"]: product_entity
            for product_entity in product_entities
        }

        last_version_by_product_id = ayon_api.get_last_versions(
            project_name, product_entities_by_id.keys()
        )
        last_version_entities_by_id = {
            version_entity["id"]: version_entity
            for version_entity in last_version_by_product_id.values()
        }
        repre_entities = ayon_api.get_representations(
            project_name, version_ids=last_version_entities_by_id.keys()
        )

        for repre_entity in repre_entities:
            version_id = repre_entity["versionId"]
            version_entity = last_version_entities_by_id[version_id]

            product_id = version_entity["productId"]
            product_entity = product_entities_by_id[product_id]

            folder_id = product_entity["folderId"]
            folder_entity = folder_entities_by_id[folder_id]

            if folder_id not in output:
                output[folder_id] = {
                    "folder_entity": folder_entity,
                    "products": {}
                }

            if product_id not in output[folder_id]["products"]:
                output[folder_id]["products"][product_id] = {
                    "product_entity": product_entity,
                    "version": {
                        "version_entity": version_entity,
                        "repres": []
                    }
                }

            (
                output
                [folder_id]
                ["products"]
                [product_id]
                ["version"]
                ["repres"]
            ).append(repre_entity)

        return output
