import os
import logging
import sys
import copy

import clique
import six
import pyblish.api
from ayon_api import (
    get_attributes_for_type,
    get_product_by_name,
    get_version_by_name,
    get_representations,
)
from ayon_api.operations import (
    OperationsSession,
    new_product_entity,
    new_version_entity,
    new_representation_entity,
)
from ayon_api.utils import create_entity_id

from ayon_core.lib import source_hash
from ayon_core.lib.file_transaction import (
    FileTransaction,
    DuplicateDestinationError
)
from ayon_core.pipeline.publish import (
    KnownPublishError,
    get_publish_template_name,
)

log = logging.getLogger(__name__)


def prepare_changes(old_entity, new_entity):
    """Prepare changes for entity update.

    Args:
        old_entity: Existing entity.
        new_entity: New entity.

    Returns:
        dict[str, Any]: Changes that have new entity.
        
    """
    changes = {}
    for key in set(new_entity.keys()):
        if key == "attrib":
            continue

        if key in new_entity and new_entity[key] != old_entity.get(key):
            changes[key] = new_entity[key]
            continue

    attrib_changes = {}
    if "attrib" in new_entity:
        for key, value in new_entity["attrib"].items():
            if value != old_entity["attrib"].get(key):
                attrib_changes[key] = value
    if attrib_changes:
        changes["attrib"] = attrib_changes
    return changes


def get_instance_families(instance):
    """Get all families of the instance"""
    # todo: move this to lib?
    family = instance.data.get("family")
    families = []
    if family:
        families.append(family)

    for _family in (instance.data.get("families") or []):
        if _family not in families:
            families.append(_family)

    return families


def get_frame_padded(frame, padding):
    """Return frame number as string with `padding` amount of padded zeros"""
    return "{frame:0{padding}d}".format(padding=padding, frame=frame)


class IntegrateAsset(pyblish.api.InstancePlugin):
    """Register publish in the database and transfer files to destinations.

    Steps:
        1) Register the product and version
        2) Transfer the representation files to the destination
        3) Register the representation

    Requires:
        instance.data['representations'] - must be a list and each member
        must be a dictionary with following data:
            'files': list of filenames for sequence, string for single file.
                     Only the filename is allowed, without the folder path.
            'stagingDir': "path/to/folder/with/files"
            'name': representation name (usually the same as extension)
            'ext': file extension
        optional data
            "frameStart"
            "frameEnd"
            'fps'
            "data": additional metadata for each representation.
    """

    label = "Integrate Asset"
    order = pyblish.api.IntegratorOrder
    families = ["workfile",
                "pointcache",
                "pointcloud",
                "proxyAbc",
                "camera",
                "animation",
                "model",
                "maxScene",
                "mayaAscii",
                "mayaScene",
                "setdress",
                "layout",
                "ass",
                "vdbcache",
                "scene",
                "vrayproxy",
                "vrayscene_layer",
                "render",
                "prerender",
                "imagesequence",
                "review",
                "rendersetup",
                "rig",
                "plate",
                "look",
                "ociolook",
                "audio",
                "yetiRig",
                "yeticache",
                "nukenodes",
                "gizmo",
                "source",
                "matchmove",
                "image",
                "assembly",
                "fbx",
                "gltf",
                "textures",
                "action",
                "harmony.template",
                "harmony.palette",
                "editorial",
                "background",
                "camerarig",
                "redshiftproxy",
                "effect",
                "xgen",
                "hda",
                "usd",
                "staticMesh",
                "skeletalMesh",
                "mvLook",
                "mvUsd",
                "mvUsdComposition",
                "mvUsdOverride",
                "online",
                "uasset",
                "blendScene",
                "yeticacheUE",
                "tycache"
                ]

    default_template_name = "publish"

    # Representation context keys that should always be written to
    # the database even if not used by the destination template
    db_representation_context_keys = [
        "project",
        "asset",
        "hierarchy",
        "folder",
        "task",
        "product",
        "subset",
        "family",
        "version",
        "representation",
        "username",
        "user",
        "output"
    ]

    def process(self, instance):
        # Instance should be integrated on a farm
        if instance.data.get("farm"):
            self.log.debug(
                "Instance is marked to be processed on farm. Skipping")
            return

        # Instance is marked to not get integrated
        if not instance.data.get("integrate", True):
            self.log.debug("Instance is marked to skip integrating. Skipping")
            return

        filtered_repres = self.filter_representations(instance)
        # Skip instance if there are not representations to integrate
        #   all representations should not be integrated
        if not filtered_repres:
            self.log.warning((
                "Skipping, there are no representations"
                " to integrate for instance {}"
            ).format(instance.data["productType"]))
            return

        file_transactions = FileTransaction(log=self.log,
                                            # Enforce unique transfers
                                            allow_queue_replacements=False)
        try:
            self.register(instance, file_transactions, filtered_repres)
        except DuplicateDestinationError as exc:
            # Raise DuplicateDestinationError as KnownPublishError
            # and rollback the transactions
            file_transactions.rollback()
            six.reraise(KnownPublishError,
                        KnownPublishError(exc),
                        sys.exc_info()[2])
        except Exception:
            # clean destination
            # todo: preferably we'd also rollback *any* changes to the database
            file_transactions.rollback()
            self.log.critical("Error when registering", exc_info=True)
            six.reraise(*sys.exc_info())

        # Finalizing can't rollback safely so no use for moving it to
        # the try, except.
        file_transactions.finalize()

    def filter_representations(self, instance):
        # Prepare repsentations that should be integrated
        repres = instance.data.get("representations")
        # Raise error if instance don't have any representations
        if not repres:
            raise KnownPublishError(
                "Instance {} has no representations to integrate".format(
                    instance.data["productType"]
                )
            )

        # Validate type of stored representations
        if not isinstance(repres, (list, tuple)):
            raise TypeError(
                "Instance 'files' must be a list, got: {0} {1}".format(
                    str(type(repres)), str(repres)
                )
            )

        # Filter representations
        filtered_repres = []
        for repre in repres:
            if "delete" in repre.get("tags", []):
                continue
            filtered_repres.append(repre)

        return filtered_repres

    def register(self, instance, file_transactions, filtered_repres):
        project_name = instance.context.data["projectName"]

        instance_stagingdir = instance.data.get("stagingDir")
        if not instance_stagingdir:
            self.log.debug((
                "{0} is missing reference to staging directory."
                " Will try to get it from representation."
            ).format(instance))

        else:
            self.log.debug(
                "Establishing staging directory "
                "@ {0}".format(instance_stagingdir)
            )

        template_name = self.get_template_name(instance)

        op_session = OperationsSession()
        product_entity = self.prepare_product(
            instance, op_session, project_name
        )
        version_entity = self.prepare_version(
            instance, op_session, product_entity, project_name
        )
        instance.data["versionEntity"] = version_entity

        anatomy = instance.context.data["anatomy"]

        # Get existing representations (if any)
        existing_repres_by_name = {
            repre_entity["name"].lower(): repre_entity
            for repre_entity in get_representations(
                project_name,
                version_ids=[version_entity["id"]]
            )
        }

        # Prepare all representations
        prepared_representations = []
        for repre in filtered_repres:
            # todo: reduce/simplify what is returned from this function
            prepared = self.prepare_representation(
                repre,
                template_name,
                existing_repres_by_name,
                version_entity,
                instance_stagingdir,
                instance)

            for src, dst in prepared["transfers"]:
                # todo: add support for hardlink transfers
                file_transactions.add(src, dst)

            prepared_representations.append(prepared)

        # Each instance can also have pre-defined transfers not explicitly
        # part of a representation - like texture resources used by a
        # .ma representation. Those destination paths are pre-defined, etc.
        # todo: should we move or simplify this logic?
        resource_destinations = set()

        file_copy_modes = [
            ("transfers", FileTransaction.MODE_COPY),
            ("hardlinks", FileTransaction.MODE_HARDLINK)
        ]
        for files_type, copy_mode in file_copy_modes:
            for src, dst in instance.data.get(files_type, []):
                self._validate_path_in_project_roots(anatomy, dst)

                file_transactions.add(src, dst, mode=copy_mode)
                resource_destinations.add(os.path.abspath(dst))

        # Bulk write to the database
        # We write the product and version to the database before the File
        # Transaction to reduce the chances of another publish trying to
        # publish to the same version number since that chance can greatly
        # increase if the file transaction takes a long time.
        op_session.commit()

        self.log.info((
            "Product '{}' version {} written to database.."
        ).format(product_entity["name"], version_entity["version"]))

        # Process all file transfers of all integrations now
        self.log.debug("Integrating source files to destination ...")
        file_transactions.process()
        self.log.debug(
            "Backed up existing files: {}".format(file_transactions.backups))
        self.log.debug(
            "Transferred files: {}".format(file_transactions.transferred))
        self.log.debug("Retrieving Representation Site Sync information ...")

        # Compute the resource file infos once (files belonging to the
        # version instance instead of an individual representation) so
        # we can re-use those file infos per representation
        resource_file_infos = self.get_files_info(
            resource_destinations, anatomy
        )

        # Finalize the representations now the published files are integrated
        # Get 'files' info for representations and its attached resources
        new_repre_names_low = set()
        for prepared in prepared_representations:
            repre_entity = prepared["representation"]
            repre_update_data = prepared["repre_update_data"]
            transfers = prepared["transfers"]
            destinations = [dst for src, dst in transfers]
            repre_files = self.get_files_info(
                destinations, anatomy
            )
            # Add the version resource file infos to each representation
            repre_files += resource_file_infos
            repre_entity["files"] = repre_files

            # Set up representation for writing to the database. Since
            # we *might* be overwriting an existing entry if the version
            # already existed we'll use ReplaceOnce with `upsert=True`
            if repre_update_data is None:
                op_session.create_entity(
                    project_name, "representation", repre_entity
                )
            else:
                # Add files to update data
                repre_update_data["files"] = repre_files
                op_session.update_entity(
                    project_name,
                    "representation",
                    repre_entity["id"],
                    repre_update_data
                )

            new_repre_names_low.add(repre_entity["name"].lower())

        # Delete any existing representations that didn't get any new data
        # if the instance is not set to append mode
        if not instance.data.get("append", False):
            for name, existing_repres in existing_repres_by_name.items():
                if name not in new_repre_names_low:
                    # We add the exact representation name because `name` is
                    # lowercase for name matching only and not in the database
                    op_session.delete_entity(
                        project_name, "representation", existing_repres["id"]
                    )

        self.log.debug("{}".format(op_session.to_data()))
        op_session.commit()

        # Backwards compatibility used in hero integration.
        # todo: can we avoid the need to store this?
        instance.data["published_representations"] = {
            p["representation"]["id"]: p
            for p in prepared_representations
        }

        self.log.info(
            "Registered {} representations: {}".format(
                len(prepared_representations),
                ", ".join(p["representation"]["name"]
                          for p in prepared_representations)
            )
        )

    def prepare_product(self, instance, op_session, project_name):
        folder_entity = instance.data["folderEntity"]
        product_name = instance.data["productName"]
        product_type = instance.data["productType"]
        self.log.debug("Product: {}".format(product_name))

        # Get existing product if it exists
        existing_product_entity = get_product_by_name(
            project_name, product_name, folder_entity["id"]
        )

        # Define product data
        data = {
            "families": get_instance_families(instance)
        }
        attribibutes = {}

        product_group = instance.data.get("productGroup")
        if product_group:
            attribibutes["productGroup"] = product_group
        elif existing_product_entity:
            # Preserve previous product group if new version does not set it
            product_group = existing_product_entity.get("attrib", {}).get(
                "productGroup"
            )
            if product_group is not None:
                attribibutes["productGroup"] = product_group

        product_id = None
        if existing_product_entity:
            product_id = existing_product_entity["id"]

        product_entity = new_product_entity(
            product_name,
            product_type,
            folder_entity["id"],
            data=data,
            attribs=attribibutes,
            entity_id=product_id
        )

        if existing_product_entity is None:
            # Create a new product
            self.log.info(
                "Product '%s' not found, creating ..." % product_name
            )
            op_session.create_entity(
                project_name, "product", product_entity
            )

        else:
            # Update existing product data with new data and set in database.
            # We also change the found product in-place so we don't need to
            # re-query the product afterwards
            update_data = prepare_changes(
                existing_product_entity, product_entity
            )
            op_session.update_entity(
                project_name,
                "product",
                product_entity["id"],
                update_data
            )

        self.log.debug("Prepared product: {}".format(product_name))
        return product_entity

    def prepare_version(
        self, instance, op_session, product_entity, project_name
    ):
        version_number = instance.data["version"]
        task_id = None
        task_entity = instance.data.get("taskEntity")
        if task_entity:
            task_id = task_entity["id"]

        existing_version = get_version_by_name(
            project_name,
            version_number,
            product_entity["id"]
        )
        version_id = None
        if existing_version:
            version_id = existing_version["id"]

        all_version_data = self.create_version_data(instance)
        version_data = {}
        version_attributes = {}
        attr_defs = self._get_attributes_for_type(instance.context, "version")
        for key, value in all_version_data.items():
            if key in attr_defs:
                version_attributes[key] = value
            else:
                version_data[key] = value

        version_entity = new_version_entity(
            version_number,
            product_entity["id"],
            task_id=task_id,
            data=version_data,
            attribs=version_attributes,
            entity_id=version_id,
        )

        if existing_version:
            self.log.debug("Updating existing version ...")
            update_data = prepare_changes(existing_version, version_entity)
            op_session.update_entity(
                project_name,
                "version",
                version_entity["id"],
                update_data
            )
        else:
            self.log.debug("Creating new version ...")
            op_session.create_entity(
                project_name, "version", version_entity
            )

        self.log.debug(
            "Prepared version: v{0:03d}".format(version_entity["version"])
        )

        return version_entity

    def _validate_repre_files(self, files, is_sequence_representation):
        """Validate representation files before transfer preparation.

        Check if files contain only filenames instead of full paths and check
        if sequence don't contain more than one sequence or has remainders.

        Args:
            files (Union[str, List[str]]): Files from representation.
            is_sequence_representation (bool): Files are for sequence.

        Raises:
            KnownPublishError: If validations don't pass.
        """

        if not files:
            return

        if not is_sequence_representation:
            files = [files]

        if any(os.path.isabs(fname) for fname in files):
            raise KnownPublishError("Given file names contain full paths")

        if not is_sequence_representation:
            return

        src_collections, remainders = clique.assemble(files)
        if len(files) < 2 or len(src_collections) != 1 or remainders:
            raise KnownPublishError((
                "Files of representation does not contain proper"
                " sequence files.\nCollected collections: {}"
                "\nCollected remainders: {}"
            ).format(
                ", ".join([str(col) for col in src_collections]),
                ", ".join([str(rem) for rem in remainders])
            ))

    def prepare_representation(
        self,
        repre,
        template_name,
        existing_repres_by_name,
        version_entity,
        instance_stagingdir,
        instance
    ):
        # pre-flight validations
        if repre["ext"].startswith("."):
            raise KnownPublishError((
                "Extension must not start with a dot '.': {}"
            ).format(repre["ext"]))

        if repre.get("transfers"):
            raise KnownPublishError((
                "Representation is not allowed to have transfers"
                "data before integration. They are computed in "
                "the integrator. Got: {}"
            ).format(repre["transfers"]))

        # create template data for Anatomy
        template_data = copy.deepcopy(instance.data["anatomyData"])

        # required representation keys
        files = repre["files"]
        template_data["representation"] = repre["name"]
        template_data["ext"] = repre["ext"]

        # allow overwriting existing version
        template_data["version"] = version_entity["version"]

        # add template data for colorspaceData
        if repre.get("colorspaceData"):
            colorspace = repre["colorspaceData"]["colorspace"]
            # replace spaces with underscores
            # pipeline.colorspace.parse_colorspace_from_filepath
            # is checking it with underscores too
            colorspace = colorspace.replace(" ", "_")
            template_data["colorspace"] = colorspace

        stagingdir = repre.get("stagingDir")
        if not stagingdir:
            # Fall back to instance staging dir if not explicitly
            # set for representation in the instance
            self.log.debug((
                "Representation uses instance staging dir: {}"
            ).format(instance_stagingdir))
            stagingdir = instance_stagingdir

        if not stagingdir:
            raise KnownPublishError(
                "No staging directory set for representation: {}".format(repre)
            )

        # optionals
        # retrieve additional anatomy data from representation if exists
        for key, anatomy_key in {
            # Representation Key: Anatomy data key
            "resolutionWidth": "resolution_width",
            "resolutionHeight": "resolution_height",
            "fps": "fps",
            "outputName": "output",
            "originalBasename": "originalBasename"
        }.items():
            # Allow to take value from representation
            # if not found also consider instance.data
            value = repre.get(key)
            if value is None:
                value = instance.data.get(key)

            if value is not None:
                template_data[anatomy_key] = value

        self.log.debug("Anatomy template name: {}".format(template_name))
        anatomy = instance.context.data["anatomy"]
        publish_template = anatomy.get_template_item("publish", template_name)
        path_template_obj = publish_template["path"]
        template = path_template_obj.template.replace("\\", "/")

        is_udim = bool(repre.get("udim"))

        # handle publish in place
        if "{originalDirname}" in template:
            # store as originalDirname only original value without project root
            # if instance collected originalDirname is present, it should be
            # used for all represe
            # from temp to final
            original_directory = (
                instance.data.get("originalDirname") or instance_stagingdir)

            _rootless = self.get_rootless_path(anatomy, original_directory)
            if _rootless == original_directory:
                raise KnownPublishError((
                        "Destination path '{}' ".format(original_directory) +
                        "must be in project dir"
                ))
            relative_path_start = _rootless.rfind('}') + 2
            without_root = _rootless[relative_path_start:]
            template_data["originalDirname"] = without_root

        is_sequence_representation = isinstance(files, (list, tuple))
        self._validate_repre_files(files, is_sequence_representation)

        # Output variables of conditions below:
        # - transfers (List[Tuple[str, str]]): src -> dst filepaths to copy
        # - repre_context (Dict[str, Any]): context data used to fill template
        # - template_data (Dict[str, Any]): source data used to fill template
        #   - to add required data to 'repre_context' not used for
        #       formatting

        # Treat template with 'orignalBasename' in special way
        if "{originalBasename}" in template:
            # Remove 'frame' from template data
            template_data.pop("frame", None)

            # Find out first frame string value
            first_index_padded = None
            if not is_udim and is_sequence_representation:
                col = clique.assemble(files)[0][0]
                sorted_frames = tuple(sorted(col.indexes))
                # First frame used for end value
                first_frame = sorted_frames[0]
                # Get last frame for padding
                last_frame = sorted_frames[-1]
                # Use padding from collection of length of last frame as string
                padding = max(col.padding, len(str(last_frame)))
                first_index_padded = get_frame_padded(
                    frame=first_frame,
                    padding=padding
                )

            # Convert files to list for single file as remaining part is only
            #   transfers creation (iteration over files)
            if not is_sequence_representation:
                files = [files]

            repre_context = None
            transfers = []
            for src_file_name in files:
                template_data["originalBasename"], _ = os.path.splitext(
                    src_file_name)

                dst = path_template_obj.format_strict(template_data)
                src = os.path.join(stagingdir, src_file_name)
                transfers.append((src, dst))
                if repre_context is None:
                    repre_context = dst.used_values

            if not is_udim and first_index_padded is not None:
                repre_context["frame"] = first_index_padded

        elif is_sequence_representation:
            # Collection of files (sequence)
            src_collections, remainders = clique.assemble(files)

            src_collection = src_collections[0]
            destination_indexes = list(src_collection.indexes)
            # Use last frame for minimum padding
            #   - that should cover both 'udim' and 'frame' minimum padding
            destination_padding = len(str(destination_indexes[-1]))
            if not is_udim:
                # Change padding for frames if template has defined higher
                #   padding.
                template_padding = anatomy.templates_obj.frame_padding
                if template_padding > destination_padding:
                    destination_padding = template_padding

                # If the representation has `frameStart` set it renumbers the
                # frame indices of the published collection. It will start from
                # that `frameStart` index instead. Thus if that frame start
                # differs from the collection we want to shift the destination
                # frame indices from the source collection.
                # In case source are published in place we need to
                # skip renumbering
                repre_frame_start = repre.get("frameStart")
                if repre_frame_start is not None:
                    index_frame_start = int(repre_frame_start)
                    # Shift destination sequence to the start frame
                    destination_indexes = [
                        index_frame_start + idx
                        for idx in range(len(destination_indexes))
                    ]

            # To construct the destination template with anatomy we require
            # a Frame or UDIM tile set for the template data. We use the first
            # index of the destination for that because that could've shifted
            # from the source indexes, etc.
            first_index_padded = get_frame_padded(
                frame=destination_indexes[0],
                padding=destination_padding
            )

            # Construct destination collection from template
            repre_context = None
            dst_filepaths = []
            for index in destination_indexes:
                if is_udim:
                    template_data["udim"] = index
                else:
                    template_data["frame"] = index
                template_filled = path_template_obj.format_strict(
                    template_data
                )
                dst_filepaths.append(template_filled)
                if repre_context is None:
                    self.log.debug(
                        "Template filled: {}".format(str(template_filled))
                    )
                    repre_context = template_filled.used_values

            # Make sure context contains frame
            # NOTE: Frame would not be available only if template does not
            #   contain '{frame}' in template -> Do we want support it?
            if not is_udim:
                repre_context["frame"] = first_index_padded

            # Update the destination indexes and padding
            dst_collection = clique.assemble(dst_filepaths)[0][0]
            dst_collection.padding = destination_padding
            if len(src_collection.indexes) != len(dst_collection.indexes):
                raise KnownPublishError((
                    "This is a bug. Source sequence frames length"
                    " does not match integration frames length"
                ))

            # Multiple file transfers
            transfers = []
            for src_file_name, dst in zip(src_collection, dst_collection):
                src = os.path.join(stagingdir, src_file_name)
                transfers.append((src, dst))

        else:
            # Single file
            # Manage anatomy template data
            template_data.pop("frame", None)
            if is_udim:
                template_data["udim"] = repre["udim"][0]
            # Construct destination filepath from template
            template_filled = path_template_obj.format_strict(template_data)
            repre_context = template_filled.used_values
            dst = os.path.normpath(template_filled)

            # Single file transfer
            src = os.path.join(stagingdir, files)
            transfers = [(src, dst)]

        # todo: Are we sure the assumption each representation
        #       ends up in the same folder is valid?
        if not instance.data.get("publishDir"):
            template_obj = publish_template["directory"]
            template_filled = template_obj.format_strict(template_data)
            instance.data["publishDir"] = template_filled

        for key in self.db_representation_context_keys:
            # Also add these values to the context even if not used by the
            # destination template
            value = template_data.get(key)
            if value is not None:
                repre_context[key] = value

        # Explicitly store the full list even though template data might
        # have a different value because it uses just a single udim tile
        if repre.get("udim"):
            repre_context["udim"] = repre.get("udim")  # store list

        # Use previous representation's id if there is a name match
        existing = existing_repres_by_name.get(repre["name"].lower())
        repre_id = None
        if existing:
            repre_id = existing["id"]

        # Store first transferred destination as published path data
        # - used primarily for reviews that are integrated to custom modules
        # TODO we should probably store all integrated files
        #   related to the representation?
        published_path = transfers[0][1]
        repre["published_path"] = published_path

        # todo: `repre` is not the actual `representation` entity
        #       we should simplify/clarify difference between data above
        #       and the actual representation entity for the database
        attr_defs = self._get_attributes_for_type(
            instance.context, "representation"
        )
        attributes = {"path": published_path, "template": template}
        data = {"context": repre_context}
        for key, value in repre.get("data", {}).items():
            if key in attr_defs:
                attributes[key] = value
            else:
                data[key] = value

        # add colorspace data if any exists on representation
        if repre.get("colorspaceData"):
            data["colorspaceData"] = repre["colorspaceData"]

        repre_doc = new_representation_entity(
            repre["name"],
            version_entity["id"],
            # files are filled afterwards
            [],
            data=data,
            attribs=attributes,
            entity_id=repre_id
        )
        update_data = None
        if repre_id is not None:
            update_data = prepare_changes(existing, repre_doc)

        return {
            "representation": repre_doc,
            "repre_update_data": update_data,
            "anatomy_data": template_data,
            "transfers": transfers,
            # todo: avoid the need for 'published_files' used by Integrate Hero
            # backwards compatibility
            "published_files": [transfer[1] for transfer in transfers]
        }

    def create_version_data(self, instance):
        """Create the data dictionary for the version

        Args:
            instance: the current instance being published

        Returns:
            dict: the required information for version["data"]
        """

        context = instance.context

        # create relative source path for DB
        if "source" in instance.data:
            source = instance.data["source"]
        else:
            source = context.data["currentFile"]
            anatomy = instance.context.data["anatomy"]
            source = self.get_rootless_path(anatomy, source)
        self.log.debug("Source: {}".format(source))

        version_data = {
            "families": get_instance_families(instance),
            "time": context.data["time"],
            "author": context.data["user"],
            "source": source,
            "comment": instance.data["comment"],
            "machine": context.data.get("machine"),
            "fps": instance.data.get("fps", context.data.get("fps"))
        }

        # todo: preferably we wouldn't need this "if dict" etc. logic and
        #       instead be able to rely what the input value is if it's set.
        intent_value = context.data.get("intent")
        if intent_value and isinstance(intent_value, dict):
            intent_value = intent_value.get("value")

        if intent_value:
            version_data["intent"] = intent_value

        # Include optional data if present in
        optionals = [
            "frameStart", "frameEnd", "step",
            "handleEnd", "handleStart", "sourceHashes"
        ]
        for key in optionals:
            if key in instance.data:
                version_data[key] = instance.data[key]

        # Include instance.data[versionData] directly
        version_data_instance = instance.data.get("versionData")
        if version_data_instance:
            version_data.update(version_data_instance)

        return version_data

    def get_template_name(self, instance):
        """Return anatomy template name to use for integration"""

        # Anatomy data is pre-filled by Collectors
        context = instance.context
        project_name = context.data["projectName"]

        # Task can be optional in anatomy data
        host_name = context.data["hostName"]
        anatomy_data = instance.data["anatomyData"]
        product_type = instance.data["productType"]
        task_info = anatomy_data.get("task") or {}

        return get_publish_template_name(
            project_name,
            host_name,
            product_type,
            task_name=task_info.get("name"),
            task_type=task_info.get("type"),
            project_settings=context.data["project_settings"],
            logger=self.log
        )

    def get_rootless_path(self, anatomy, path):
        """Returns, if possible, path without absolute portion from root
            (eg. 'c:\' or '/opt/..')

         This information is platform dependent and shouldn't be captured.
         Example:
             'c:/projects/MyProject1/Assets/publish...' >
             '{root}/MyProject1/Assets...'

        Args:
            anatomy (Anatomy): Project anatomy.
            path (str): Absolute path.

        Returns:
            str: Path where root path is replaced by formatting string.

        """
        success, rootless_path = anatomy.find_root_template_from_path(path)
        if success:
            path = rootless_path
        else:
            self.log.warning((
                "Could not find root path for remapping \"{}\"."
                " This may cause issues on farm."
            ).format(path))
        return path

    def get_files_info(self, filepaths, anatomy):
        """Prepare 'files' info portion for representations.

        Arguments:
            filepaths (Iterable[str]): List of transferred file paths.
            anatomy (Anatomy): Project anatomy.

        Returns:
            list[dict[str, Any]]: Representation 'files' information.

        """
        file_infos = []
        for filepath in filepaths:
            file_info = self.prepare_file_info(filepath, anatomy)
            file_infos.append(file_info)
        return file_infos

    def prepare_file_info(self, path, anatomy):
        """ Prepare information for one file (asset or resource)

        Arguments:
            path (str): Destination url of published file.
            anatomy (Anatomy): Project anatomy part from instance.

        Returns:
            dict[str, Any]: Representation file info dictionary.

        """
        return {
            "id": create_entity_id(),
            "name": os.path.basename(path),
            "path": self.get_rootless_path(anatomy, path),
            "size": os.path.getsize(path),
            "hash": source_hash(path),
            "hash_type": "op3",
        }

    def _validate_path_in_project_roots(self, anatomy, file_path):
        """Checks if 'file_path' starts with any of the roots.

        Used to check that published path belongs to project, eg. we are not
        trying to publish to local only folder.
        Args:
            anatomy (Anatomy): Project anatomy.
            file_path (str): Filepath.

        Raises:
            KnownPublishError: When failed to find root for the path.
        """
        path = self.get_rootless_path(anatomy, file_path)
        if not path:
            raise KnownPublishError((
                "Destination path '{}' ".format(file_path) +
                "must be in project dir"
            ))

    def _get_attributes_for_type(self, context, entity_type):
        return self._get_attributes_by_type(context)[entity_type]

    def _get_attributes_by_type(self, context):
        attributes = context.data.get("ayonAttributes")
        if attributes is None:
            attributes = {}
            for key in (
                "project",
                "folder",
                "product",
                "version",
                "representation",
            ):
                attributes[key] = get_attributes_for_type(key)
            context.data["ayonAttributes"] = attributes
        return attributes
