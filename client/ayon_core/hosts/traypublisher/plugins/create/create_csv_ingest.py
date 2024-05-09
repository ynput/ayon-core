import os
import re
import csv
import clique
from io import StringIO
from copy import deepcopy, copy

from ayon_api import get_folder_by_path, get_task_by_name
from ayon_core.pipeline.create import get_product_name
from ayon_core.pipeline import CreatedInstance
from ayon_core.lib import FileDef, BoolDef
from ayon_core.lib.transcoding import (
    VIDEO_EXTENSIONS, IMAGE_EXTENSIONS
)
from ayon_core.pipeline.create import CreatorError
from ayon_core.hosts.traypublisher.api.plugin import (
    TrayPublishCreator
)


class IngestCSV(TrayPublishCreator):
    """CSV ingest creator class"""

    icon = "fa.file"

    label = "CSV Ingest"
    product_type = "csv_ingest_file"
    identifier = "io.ayon.creators.traypublisher.csv_ingest"

    default_variants = ["Main"]

    description = "Ingest products' data from CSV file"
    detailed_description = """
Ingest products' data from CSV file following column and representation
configuration in project settings.
"""

    # Position in the list of creators.
    order = 10

    # settings for this creator
    columns_config = {}
    representations_config = {}

    def create(self, subset_name, instance_data, pre_create_data):
        """Create an product from each row found in the CSV.

        Args:
            subset_name (str): The subset name.
            instance_data (dict): The instance data.
            pre_create_data (dict):
        """

        csv_filepath_data = pre_create_data.get("csv_filepath_data", {})

        folder = csv_filepath_data.get("directory", "")
        if not os.path.exists(folder):
            raise CreatorError(
                f"Directory '{folder}' does not exist."
            )
        filename = csv_filepath_data.get("filenames", [])
        self._process_csv_file(subset_name, instance_data, folder, filename[0])

    def _process_csv_file(
            self, subset_name, instance_data, staging_dir, filename):
        """Process CSV file.

        Args:
            subset_name (str): The subset name.
            instance_data (dict): The instance data.
            staging_dir (str): The staging directory.
            filename (str): The filename.
        """

        # create new instance from the csv file via self function
        self._pass_data_to_csv_instance(
            instance_data,
            staging_dir,
            filename
        )

        csv_instance = CreatedInstance(
            self.product_type, subset_name, instance_data, self
        )
        self._store_new_instance(csv_instance)

        csv_instance["csvFileData"] = {
            "filename": filename,
            "staging_dir": staging_dir,
        }

        # from special function get all data from csv file and convert them
        # to new instances
        csv_data_for_instances = self._get_data_from_csv(
            staging_dir, filename)

        # create instances from csv data via self function
        self._create_instances_from_csv_data(
            csv_data_for_instances, staging_dir
        )

    def _create_instances_from_csv_data(
        self,
        csv_data_for_instances,
        staging_dir
    ):
        """Create instances from csv data"""

        for folder_path, prepared_data in csv_data_for_instances.items():
            project_name = self.create_context.get_current_project_name()
            products = prepared_data["products"]

            for instance_name, product_data in products.items():
                # get important instance variables
                task_name = product_data["task_name"]
                task_type = product_data["task_type"]
                variant = product_data["variant"]
                product_type = product_data["product_type"]
                version = product_data["version"]

                # create subset/product name
                product_name = get_product_name(
                    project_name,
                    task_name,
                    task_type,
                    self.host_name,
                    product_type,
                    variant
                )

                # make sure frame start/end is inherited from csv columns
                # expected frame range data are handles excluded
                for _, repre_data in product_data["representations"].items():  # noqa: E501
                    frame_start = repre_data["frameStart"]
                    frame_end = repre_data["frameEnd"]
                    handle_start = repre_data["handleStart"]
                    handle_end = repre_data["handleEnd"]
                    fps = repre_data["fps"]
                    break

                # try to find any version comment in representation data
                version_comment = next(
                    iter(
                        repre_data["comment"]
                        for repre_data in product_data["representations"].values()  # noqa: E501
                        if repre_data["comment"]
                    ),
                    None
                )

                # try to find any slate switch in representation data
                slate_exists = any(
                    repre_data["slate"]
                    for _, repre_data in product_data["representations"].items()  # noqa: E501
                )

                # get representations from product data
                representations = product_data["representations"]
                label = f"{folder_path}_{product_name}_v{version:>03}"

                families = ["csv_ingest"]
                if slate_exists:
                    # adding slate to families mainly for loaders to be able
                    # to filter out slates
                    families.append("slate")

                # make product data
                product_data = {
                    "name": instance_name,
                    "folderPath": folder_path,
                    "families": families,
                    "label": label,
                    "task": task_name,
                    "variant": variant,
                    "source": "csv",
                    "frameStart": frame_start,
                    "frameEnd": frame_end,
                    "handleStart": handle_start,
                    "handleEnd": handle_end,
                    "fps": fps,
                    "version": version,
                    "comment": version_comment,
                }

                # create new instance
                new_instance = CreatedInstance(
                    product_type, product_name, product_data, self
                )
                self._store_new_instance(new_instance)

                if not new_instance.get("prepared_data_for_repres"):
                    new_instance["prepared_data_for_repres"] = []

                base_thumbnail_repre_data = {
                    "name": "thumbnail",
                    "ext": None,
                    "files": None,
                    "stagingDir": None,
                    "stagingDir_persistent": True,
                    "tags": ["thumbnail", "delete"],
                }
                # need to populate all thumbnails for all representations
                # so we can check if unique thumbnail per representation
                # is needed
                thumbnails = [
                    repre_data["thumbnailPath"]
                    for repre_data in representations.values()
                    if repre_data["thumbnailPath"]
                ]
                multiple_thumbnails = len(set(thumbnails)) > 1
                explicit_output_name = None
                thumbnails_processed = False
                for filepath, repre_data in representations.items():
                    # check if any review derivate tag is present
                    reviewable = any(
                        tag for tag in repre_data.get("tags", [])
                        # tag can be `ftrackreview` or `review`
                        if "review" in tag
                    )
                    # since we need to populate multiple thumbnails as
                    # representation with outputName for (Ftrack instance
                    # integrator) pairing with reviewable video representations
                    if (
                        thumbnails
                        and multiple_thumbnails
                        and reviewable
                    ):
                        # multiple unique thumbnails per representation needs
                        # grouping by outputName
                        # mainly used in Ftrack instance integrator
                        explicit_output_name = repre_data["representationName"]
                        relative_thumbnail_path = repre_data["thumbnailPath"]
                        # representation might not have thumbnail path
                        # so ignore this one
                        if not relative_thumbnail_path:
                            continue
                        thumb_dir, thumb_file = \
                            self._get_refactor_thumbnail_path(
                                staging_dir, relative_thumbnail_path)
                        filename, ext = os.path.splitext(thumb_file)
                        thumbnail_repr_data = deepcopy(
                            base_thumbnail_repre_data)
                        thumbnail_repr_data.update({
                            "name": "thumbnail_{}".format(filename),
                            "ext": ext[1:],
                            "files": thumb_file,
                            "stagingDir": thumb_dir,
                            "outputName": explicit_output_name,
                        })
                        new_instance["prepared_data_for_repres"].append({
                            "type": "thumbnail",
                            "colorspace": None,
                            "representation": thumbnail_repr_data,
                        })
                        # also add thumbnailPath for ayon to integrate
                        if not new_instance.get("thumbnailPath"):
                            new_instance["thumbnailPath"] = (
                                os.path.join(thumb_dir, thumb_file)
                            )
                    elif (
                        thumbnails
                        and not multiple_thumbnails
                        and not thumbnails_processed
                        or not reviewable
                    ):
                        """
                        For case where we have only one thumbnail
                        and not reviewable medias. This needs to be processed
                        only once per instance.
                        """
                        if not thumbnails:
                            continue
                        # here we will use only one thumbnail for
                        # all representations
                        relative_thumbnail_path = repre_data["thumbnailPath"]
                        # popping last thumbnail from list since it is only one
                        # and we do not need to iterate again over it
                        if not relative_thumbnail_path:
                            relative_thumbnail_path = thumbnails.pop()
                        thumb_dir, thumb_file = \
                            self._get_refactor_thumbnail_path(
                                staging_dir, relative_thumbnail_path)
                        _, ext = os.path.splitext(thumb_file)
                        thumbnail_repr_data = deepcopy(
                            base_thumbnail_repre_data)
                        thumbnail_repr_data.update({
                            "ext": ext[1:],
                            "files": thumb_file,
                            "stagingDir": thumb_dir
                        })
                        new_instance["prepared_data_for_repres"].append({
                            "type": "thumbnail",
                            "colorspace": None,
                            "representation": thumbnail_repr_data,
                        })
                        # also add thumbnailPath for ayon to integrate
                        if not new_instance.get("thumbnailPath"):
                            new_instance["thumbnailPath"] = (
                                os.path.join(thumb_dir, thumb_file)
                            )

                        thumbnails_processed = True

                    # get representation data
                    representation_data = self._get_representation_data(
                        filepath, repre_data, staging_dir,
                        explicit_output_name
                    )

                    new_instance["prepared_data_for_repres"].append({
                        "type": "media",
                        "colorspace": repre_data["colorspace"],
                        "representation": representation_data,
                    })

    def _get_refactor_thumbnail_path(
            self, staging_dir, relative_thumbnail_path):
        thumbnail_abs_path = os.path.join(
            staging_dir, relative_thumbnail_path)
        return os.path.split(
            thumbnail_abs_path)

    def _get_representation_data(
        self, filepath, repre_data, staging_dir, explicit_output_name=None
    ):
        """Get representation data

        Args:
            filepath (str): Filepath to representation file.
            repre_data (dict): Representation data from CSV file.
            staging_dir (str): Staging directory.
            explicit_output_name (Optional[str]): Explicit output name.
                For grouping purposes with reviewable components.
                Defaults to None.
        """

        # get extension of file
        basename = os.path.basename(filepath)
        extension = os.path.splitext(filepath)[-1].lower()

        # validate filepath is having correct extension based on output
        repre_name = repre_data["representationName"]
        repre_config_data = None
        for repre in self.representations_config["representations"]:
            if repre["name"] == repre_name:
                repre_config_data = repre
                break

        if not repre_config_data:
            raise CreatorError(
                f"Representation '{repre_name}' not found "
                "in config representation data."
            )

        validate_extensions = repre_config_data["extensions"]
        if extension not in validate_extensions:
            raise CreatorError(
                f"File extension '{extension}' not valid for "
                f"output '{validate_extensions}'."
            )

        is_sequence = (extension in IMAGE_EXTENSIONS)
        # convert ### string in file name to %03d
        # this is for correct frame range validation
        # example: file.###.exr -> file.%03d.exr
        if "#" in basename:
            padding = len(basename.split("#")) - 1
            basename = basename.replace("#" * padding, f"%0{padding}d")
            is_sequence = True

        # make absolute path to file
        absfilepath = os.path.normpath(os.path.join(staging_dir, filepath))
        dirname = os.path.dirname(absfilepath)

        # check if dirname exists
        if not os.path.isdir(dirname):
            raise CreatorError(
                f"Directory '{dirname}' does not exist."
            )

        # collect all data from dirname
        paths_for_collection = []
        for file in os.listdir(dirname):
            filepath = os.path.join(dirname, file)
            paths_for_collection.append(filepath)

        collections, _ = clique.assemble(paths_for_collection)

        if collections:
            collections = collections[0]
        else:
            if is_sequence:
                raise CreatorError(
                    f"No collections found in directory '{dirname}'."
                )

        frame_start = None
        frame_end = None
        if is_sequence:
            files = [os.path.basename(file) for file in collections]
            frame_start = list(collections.indexes)[0]
            frame_end = list(collections.indexes)[-1]
        else:
            files = basename

        tags = deepcopy(repre_data["tags"])
        # if slate in repre_data is True then remove one frame from start
        if repre_data["slate"]:
            tags.append("has_slate")

        # get representation data
        representation_data = {
            "name": repre_name,
            "ext": extension[1:],
            "files": files,
            "stagingDir": dirname,
            "stagingDir_persistent": True,
            "tags": tags,
        }
        if extension in VIDEO_EXTENSIONS:
            representation_data.update({
                "fps": repre_data["fps"],
                "outputName": repre_name,
            })

        if explicit_output_name:
            representation_data["outputName"] = explicit_output_name

        if frame_start:
            representation_data["frameStart"] = frame_start
        if frame_end:
            representation_data["frameEnd"] = frame_end

        return representation_data

    def _get_data_from_csv(
        self, package_dir, filename
    ):
        """Generate instances from the csv file"""
        # get current project name and code from context.data
        project_name = self.create_context.get_current_project_name()

        csv_file_path = os.path.join(
            package_dir, filename
        )

        # make sure csv file contains columns from following list
        required_columns = [
            column["name"] for column in self.columns_config["columns"]
            if column["required_column"]
        ]

        # read csv file
        with open(csv_file_path, "r") as csv_file:
            csv_content = csv_file.read()

        # read csv file with DictReader
        csv_reader = csv.DictReader(
            StringIO(csv_content),
            delimiter=self.columns_config["csv_delimiter"]
        )

        # fix fieldnames
        # sometimes someone can keep extra space at the start or end of
        # the column name
        all_columns = [
            " ".join(column.rsplit()) for column in csv_reader.fieldnames]

        # return back fixed fieldnames
        csv_reader.fieldnames = all_columns

        # check if csv file contains all required columns
        if any(column not in all_columns for column in required_columns):
            raise CreatorError(
                f"Missing required columns: {required_columns}"
            )

        csv_data = {}
        # get data from csv file
        for row in csv_reader:
            # Get required columns first
            # TODO: will need to be folder path in CSV
            # TODO: `context_asset_name` is now `folder_path`
            folder_path = self._get_row_value_with_validation(
                "Folder Path", row)
            task_name = self._get_row_value_with_validation(
                "Task Name", row)
            version = self._get_row_value_with_validation(
                "Version", row)

            # Get optional columns
            variant = self._get_row_value_with_validation(
                "Variant", row)
            product_type = self._get_row_value_with_validation(
                "Product Type", row)

            pre_product_name = (
                f"{task_name}{variant}{product_type}"
                f"{version}".replace(" ", "").lower()
            )

            # get representation data
            filename, representation_data = \
                self._get_representation_row_data(row)

            # TODO: batch query of all folder paths and task names

            # get folder entity from folder path
            folder_entity = get_folder_by_path(
                project_name, folder_path)

            # make sure asset exists
            if not folder_entity:
                raise CreatorError(
                    f"Asset '{folder_path}' not found."
                )

            # first get all tasks on the folder entity and then find
            task_entity = get_task_by_name(
                project_name, folder_entity["id"], task_name)

            # check if task name is valid task in asset doc
            if not task_entity:
                raise CreatorError(
                    f"Task '{task_name}' not found in asset doc."
                )

            # get all csv data into one dict and make sure there are no
            # duplicates data are already validated and sorted under
            # correct existing asset also check if asset exists and if
            # task name is valid task in asset doc and representations
            # are distributed under products following variants
            if folder_path not in csv_data:
                csv_data[folder_path] = {
                    "folder_entity": folder_entity,
                    "products": {
                        pre_product_name: {
                            "task_name": task_name,
                            "task_type": task_entity["taskType"],
                            "variant": variant,
                            "product_type": product_type,
                            "version": version,
                            "representations": {
                                filename: representation_data,
                            },
                        }
                    }
                }
            else:
                csv_products = csv_data[folder_path]["products"]
                if pre_product_name not in csv_products:
                    csv_products[pre_product_name] = {
                        "task_name": task_name,
                        "task_type": task_entity["taskType"],
                        "variant": variant,
                        "product_type": product_type,
                        "version": version,
                        "representations": {
                            filename: representation_data,
                        },
                    }
                else:
                    csv_representations = \
                        csv_products[pre_product_name]["representations"]
                    if filename in csv_representations:
                        raise CreatorError(
                            f"Duplicate filename '{filename}' in csv file."
                        )
                    csv_representations[filename] = representation_data

        return csv_data

    def _get_representation_row_data(self, row_data):
        """Get representation row data"""
        # Get required columns first
        file_path = self._get_row_value_with_validation(
            "File Path", row_data)
        frame_start = self._get_row_value_with_validation(
            "Frame Start", row_data)
        frame_end = self._get_row_value_with_validation(
            "Frame End", row_data)
        handle_start = self._get_row_value_with_validation(
            "Handle Start", row_data)
        handle_end = self._get_row_value_with_validation(
            "Handle End", row_data)
        fps = self._get_row_value_with_validation(
            "FPS", row_data)

        # Get optional columns
        thumbnail_path = self._get_row_value_with_validation(
            "Version Thumbnail", row_data)
        colorspace = self._get_row_value_with_validation(
            "Representation Colorspace", row_data)
        comment = self._get_row_value_with_validation(
            "Version Comment", row_data)
        repre = self._get_row_value_with_validation(
            "Representation", row_data)
        slate_exists = self._get_row_value_with_validation(
            "Slate Exists", row_data)
        repre_tags = self._get_row_value_with_validation(
            "Representation Tags", row_data)

        # convert tags value to list
        tags_list = copy(self.representations_config["default_tags"])
        if repre_tags:
            tags_list = []
            tags_delimiter = self.representations_config["tags_delimiter"]
            # strip spaces from repre_tags
            if tags_delimiter in repre_tags:
                tags = repre_tags.split(tags_delimiter)
                for _tag in tags:
                    tags_list.append(("".join(_tag.strip())).lower())
            else:
                tags_list.append(repre_tags)

        representation_data = {
            "colorspace": colorspace,
            "comment": comment,
            "representationName": repre,
            "slate": slate_exists,
            "tags": tags_list,
            "thumbnailPath": thumbnail_path,
            "frameStart": int(frame_start),
            "frameEnd": int(frame_end),
            "handleStart": int(handle_start),
            "handleEnd": int(handle_end),
            "fps": float(fps),
        }
        return file_path, representation_data

    def _get_row_value_with_validation(
        self, column_name, row_data, default_value=None
    ):
        """Get row value with validation"""

        # get column data from column config
        column_data = None
        for column in self.columns_config["columns"]:
            if column["name"] == column_name:
                column_data = column
                break

        if not column_data:
            raise CreatorError(
                f"Column '{column_name}' not found in column config."
            )

        # get column value from row
        column_value = row_data.get(column_name)
        column_required = column_data["required_column"]

        # check if column value is not empty string and column is required
        if column_value == "" and column_required:
            raise CreatorError(
                f"Value in column '{column_name}' is required."
            )

        # get column type
        column_type = column_data["type"]
        # get column validation regex
        column_validation = column_data["validation_pattern"]
        # get column default value
        column_default = default_value or column_data["default"]

        if column_type in ["number", "decimal"] and column_default == 0:
            column_default = None

        # check if column value is not empty string
        if column_value == "":
            # set default value if column value is empty string
            column_value = column_default

        # set column value to correct type following column type
        if column_type == "number" and column_value is not None:
            column_value = int(column_value)
        elif column_type == "decimal" and column_value is not None:
            column_value = float(column_value)
        elif column_type == "bool":
            column_value = column_value in ["true", "True"]

        # check if column value matches validation regex
        if (
            column_value is not None and
            not re.match(str(column_validation), str(column_value))
        ):
            raise CreatorError(
                f"Column '{column_name}' value '{column_value}' "
                f"does not match validation regex '{column_validation}' \n"
                f"Row data: {row_data} \n"
                f"Column data: {column_data}"
            )

        return column_value

    def _pass_data_to_csv_instance(
        self, instance_data, staging_dir, filename
    ):
        """Pass CSV representation file to instance data"""

        representation = {
            "name": "csv",
            "ext": "csv",
            "files": filename,
            "stagingDir": staging_dir,
            "stagingDir_persistent": True,
        }

        instance_data.update({
            "label": f"CSV: {filename}",
            "representations": [representation],
            "stagingDir": staging_dir,
            "stagingDir_persistent": True,
        })

    def get_instance_attr_defs(self):
        return [
            BoolDef(
                "add_review_family",
                default=True,
                label="Review"
            )
        ]

    def get_pre_create_attr_defs(self):
        """Creating pre-create attributes at creator plugin.

        Returns:
            list: list of attribute object instances
        """
        # Use same attributes as for instance attributes
        attr_defs = [
            FileDef(
                "csv_filepath_data",
                folders=False,
                extensions=[".csv"],
                allow_sequences=False,
                single_item=True,
                label="CSV File",
            ),
        ]
        return attr_defs
