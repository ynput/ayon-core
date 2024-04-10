# TODO This plugin is not converted for AYON
#
# import collections
# import os
# import uuid
#
# import clique
# import ayon_api
# from pymongo import UpdateOne
# import qargparse
# from qtpy import QtWidgets, QtCore
#
# from ayon_core import style
# from ayon_core.addon import AddonsManager
# from ayon_core.lib import format_file_size
# from ayon_core.pipeline import load, Anatomy
# from ayon_core.pipeline.load import (
#     get_representation_path_with_anatomy,
#     InvalidRepresentationContext,
# )
#
#
# class DeleteOldVersions(load.ProductLoaderPlugin):
#     """Deletes specific number of old version"""
#
#     is_multiple_contexts_compatible = True
#     sequence_splitter = "__sequence_splitter__"
#
#     representations = {"*"}
#     product_types = {"*"}
#     tool_names = ["library_loader"]
#
#     label = "Delete Old Versions"
#     order = 35
#     icon = "trash"
#     color = "#d8d8d8"
#
#     options = [
#         qargparse.Integer(
#             "versions_to_keep", default=2, min=0, help="Versions to keep:"
#         ),
#         qargparse.Boolean(
#             "remove_publish_folder", help="Remove publish folder:"
#         )
#     ]
#
#     def delete_whole_dir_paths(self, dir_paths, delete=True):
#         size = 0
#
#         for dir_path in dir_paths:
#             # Delete all files and fodlers in dir path
#             for root, dirs, files in os.walk(dir_path, topdown=False):
#                 for name in files:
#                     file_path = os.path.join(root, name)
#                     size += os.path.getsize(file_path)
#                     if delete:
#                         os.remove(file_path)
#                         self.log.debug("Removed file: {}".format(file_path))
#
#                 for name in dirs:
#                     if delete:
#                         os.rmdir(os.path.join(root, name))
#
#             if not delete:
#                 continue
#
#             # Delete even the folder and it's parents folders if they are empty
#             while True:
#                 if not os.path.exists(dir_path):
#                     dir_path = os.path.dirname(dir_path)
#                     continue
#
#                 if len(os.listdir(dir_path)) != 0:
#                     break
#
#                 os.rmdir(os.path.join(dir_path))
#
#         return size
#
#     def path_from_representation(self, representation, anatomy):
#         try:
#             context = representation["context"]
#         except KeyError:
#             return (None, None)
#
#         try:
#             path = get_representation_path_with_anatomy(
#                 representation, anatomy
#             )
#         except InvalidRepresentationContext:
#             return (None, None)
#
#         sequence_path = None
#         if "frame" in context:
#             context["frame"] = self.sequence_splitter
#             sequence_path = get_representation_path_with_anatomy(
#                 representation, anatomy
#             )
#
#         if sequence_path:
#             sequence_path = sequence_path.normalized()
#
#         return (path.normalized(), sequence_path)
#
#     def delete_only_repre_files(self, dir_paths, file_paths, delete=True):
#         size = 0
#
#         for dir_id, dir_path in dir_paths.items():
#             dir_files = os.listdir(dir_path)
#             collections, remainders = clique.assemble(dir_files)
#             for file_path, seq_path in file_paths[dir_id]:
#                 file_path_base = os.path.split(file_path)[1]
#                 # Just remove file if `frame` key was not in context or
#                 # filled path is in remainders (single file sequence)
#                 if not seq_path or file_path_base in remainders:
#                     if not os.path.exists(file_path):
#                         self.log.debug(
#                             "File was not found: {}".format(file_path)
#                         )
#                         continue
#
#                     size += os.path.getsize(file_path)
#
#                     if delete:
#                         os.remove(file_path)
#                         self.log.debug("Removed file: {}".format(file_path))
#
#                     if file_path_base in remainders:
#                         remainders.remove(file_path_base)
#                     continue
#
#                 seq_path_base = os.path.split(seq_path)[1]
#                 head, tail = seq_path_base.split(self.sequence_splitter)
#
#                 final_col = None
#                 for collection in collections:
#                     if head != collection.head or tail != collection.tail:
#                         continue
#                     final_col = collection
#                     break
#
#                 if final_col is not None:
#                     # Fill full path to head
#                     final_col.head = os.path.join(dir_path, final_col.head)
#                     for _file_path in final_col:
#                         if os.path.exists(_file_path):
#
#                             size += os.path.getsize(_file_path)
#
#                             if delete:
#                                 os.remove(_file_path)
#                                 self.log.debug(
#                                     "Removed file: {}".format(_file_path)
#                                 )
#
#                     _seq_path = final_col.format("{head}{padding}{tail}")
#                     self.log.debug("Removed files: {}".format(_seq_path))
#                     collections.remove(final_col)
#
#                 elif os.path.exists(file_path):
#                     size += os.path.getsize(file_path)
#
#                     if delete:
#                         os.remove(file_path)
#                         self.log.debug("Removed file: {}".format(file_path))
#                 else:
#                     self.log.debug(
#                         "File was not found: {}".format(file_path)
#                     )
#
#         # Delete as much as possible parent folders
#         if not delete:
#             return size
#
#         for dir_path in dir_paths.values():
#             while True:
#                 if not os.path.exists(dir_path):
#                     dir_path = os.path.dirname(dir_path)
#                     continue
#
#                 if len(os.listdir(dir_path)) != 0:
#                     break
#
#                 self.log.debug("Removed folder: {}".format(dir_path))
#                 os.rmdir(dir_path)
#
#         return size
#
#     def message(self, text):
#         msgBox = QtWidgets.QMessageBox()
#         msgBox.setText(text)
#         msgBox.setStyleSheet(style.load_stylesheet())
#         msgBox.setWindowFlags(
#             msgBox.windowFlags() | QtCore.Qt.FramelessWindowHint
#         )
#         msgBox.exec_()
#
#     def get_data(self, context, versions_count):
#         product_entity = context["product"]
#         folder_entity = context["folder"]
#         project_name = context["project"]["name"]
#         anatomy = Anatomy(project_name)
#
#         versions = list(ayon_api.get_versions(
#             project_name, product_ids=[product_entity["id"]]
#         ))
#
#         versions_by_parent = collections.defaultdict(list)
#         for ent in versions:
#             versions_by_parent[ent["productId"]].append(ent)
#
#         def sort_func(ent):
#             return int(ent["version"])
#
#         all_last_versions = []
#         for _parent_id, _versions in versions_by_parent.items():
#             for idx, version in enumerate(
#                 sorted(_versions, key=sort_func, reverse=True)
#             ):
#                 if idx >= versions_count:
#                     break
#                 all_last_versions.append(version)
#
#         self.log.debug("Collected versions ({})".format(len(versions)))
#
#         # Filter latest versions
#         for version in all_last_versions:
#             versions.remove(version)
#
#         # Update versions_by_parent without filtered versions
#         versions_by_parent = collections.defaultdict(list)
#         for ent in versions:
#             versions_by_parent[ent["productId"]].append(ent)
#
#         # Filter already deleted versions
#         versions_to_pop = []
#         for version in versions:
#             version_tags = version["data"].get("tags")
#             if version_tags and "deleted" in version_tags:
#                 versions_to_pop.append(version)
#
#         for version in versions_to_pop:
#             msg = "Folder: \"{}\" | Product: \"{}\" | Version: \"{}\"".format(
#                 folder_entity["path"],
#                 product_entity["name"],
#                 version["version"]
#             )
#             self.log.debug((
#                 "Skipping version. Already tagged as `deleted`. < {} >"
#             ).format(msg))
#             versions.remove(version)
#
#         version_ids = [ent["id"] for ent in versions]
#
#         self.log.debug(
#             "Filtered versions to delete ({})".format(len(version_ids))
#         )
#
#         if not version_ids:
#             msg = "Skipping processing. Nothing to delete on {}/{}".format(
#                 folder_entity["path"], product_entity["name"]
#             )
#             self.log.info(msg)
#             print(msg)
#             return
#
#         repres = list(ayon_api.get_representations(
#             project_name, version_ids=version_ids
#         ))
#
#         self.log.debug(
#             "Collected representations to remove ({})".format(len(repres))
#         )
#
#         dir_paths = {}
#         file_paths_by_dir = collections.defaultdict(list)
#         for repre in repres:
#             file_path, seq_path = self.path_from_representation(
#                 repre, anatomy
#             )
#             if file_path is None:
#                 self.log.debug((
#                     "Could not format path for represenation \"{}\""
#                 ).format(str(repre)))
#                 continue
#
#             dir_path = os.path.dirname(file_path)
#             dir_id = None
#             for _dir_id, _dir_path in dir_paths.items():
#                 if _dir_path == dir_path:
#                     dir_id = _dir_id
#                     break
#
#             if dir_id is None:
#                 dir_id = uuid.uuid4()
#                 dir_paths[dir_id] = dir_path
#
#             file_paths_by_dir[dir_id].append([file_path, seq_path])
#
#         dir_ids_to_pop = []
#         for dir_id, dir_path in dir_paths.items():
#             if os.path.exists(dir_path):
#                 continue
#
#             dir_ids_to_pop.append(dir_id)
#
#         # Pop dirs from both dictionaries
#         for dir_id in dir_ids_to_pop:
#             dir_paths.pop(dir_id)
#             paths = file_paths_by_dir.pop(dir_id)
#             # TODO report of missing directories?
#             paths_msg = ", ".join([
#                 "'{}'".format(path[0].replace("\\", "/")) for path in paths
#             ])
#             self.log.debug((
#                 "Folder does not exist. Deleting it's files skipped: {}"
#             ).format(paths_msg))
#
#         return {
#             "dir_paths": dir_paths,
#             "file_paths_by_dir": file_paths_by_dir,
#             "versions": versions,
#             "folder": folder_entity,
#             "product": product_entity,
#             "archive_product": versions_count == 0
#         }
#
#     def main(self, project_name, data, remove_publish_folder):
#         # Size of files.
#         size = 0
#         if not data:
#             return size
#
#         if remove_publish_folder:
#             size = self.delete_whole_dir_paths(data["dir_paths"].values())
#         else:
#             size = self.delete_only_repre_files(
#                 data["dir_paths"], data["file_paths_by_dir"]
#             )
#
#         mongo_changes_bulk = []
#         for version in data["versions"]:
#             orig_version_tags = version["data"].get("tags") or []
#             version_tags = [tag for tag in orig_version_tags]
#             if "deleted" not in version_tags:
#                 version_tags.append("deleted")
#
#             if version_tags == orig_version_tags:
#                 continue
#
#             update_query = {"id": version["id"]}
#             update_data = {"$set": {"data.tags": version_tags}}
#             mongo_changes_bulk.append(UpdateOne(update_query, update_data))
#
#         if data["archive_product"]:
#             mongo_changes_bulk.append(UpdateOne(
#                 {
#                     "id": data["product"]["id"],
#                     "type": "subset"
#                 },
#                 {"$set": {"type": "archived_subset"}}
#             ))
#
#         if mongo_changes_bulk:
#             dbcon = AvalonMongoDB()
#             dbcon.Session["AYON_PROJECT_NAME"] = project_name
#             dbcon.install()
#             dbcon.bulk_write(mongo_changes_bulk)
#             dbcon.uninstall()
#
#         self._ftrack_delete_versions(data)
#
#         return size
#
#     def _ftrack_delete_versions(self, data):
#         """Delete version on ftrack.
#
#         Handling of ftrack logic in this plugin is not ideal. But in OP3 it is
#         almost impossible to solve the issue other way.
#
#         Note:
#             Asset versions on ftrack are not deleted but marked as
#                 "not published" which cause that they're invisible.
#
#         Args:
#             data (dict): Data sent to product loader with full context.
#         """
#
#         # First check for ftrack id on folder entity
#         #   - skip if ther is none
#         ftrack_id = data["folder"]["attrib"].get("ftrackId")
#         if not ftrack_id:
#             self.log.info((
#                 "Folder does not have filled ftrack id. Skipped delete"
#                 " of ftrack version."
#             ))
#             return
#
#         # Check if ftrack module is enabled
#         addons_manager = AddonsManager()
#         ftrack_addon = addons_manager.get("ftrack")
#         if not ftrack_addon or not ftrack_addon.enabled:
#             return
#
#         import ftrack_api
#
#         session = ftrack_api.Session()
#         product_name = data["product"]["name"]
#         versions = {
#             '"{}"'.format(version_doc["name"])
#             for version_doc in data["versions"]
#         }
#         asset_versions = session.query(
#             (
#                 "select id, is_published from AssetVersion where"
#                 " asset.parent.id is \"{}\""
#                 " and asset.name is \"{}\""
#                 " and version in ({})"
#             ).format(
#                 ftrack_id,
#                 product_name,
#                 ",".join(versions)
#             )
#         ).all()
#
#         # Set attribute `is_published` to `False` on ftrack AssetVersions
#         for asset_version in asset_versions:
#             asset_version["is_published"] = False
#
#         try:
#             session.commit()
#
#         except Exception:
#             msg = (
#                 "Could not set `is_published` attribute to `False`"
#                 " for selected AssetVersions."
#             )
#             self.log.error(msg)
#             self.message(msg)
#
#     def load(self, contexts, name=None, namespace=None, options=None):
#         try:
#             size = 0
#             for count, context in enumerate(contexts):
#                 versions_to_keep = 2
#                 remove_publish_folder = False
#                 if options:
#                     versions_to_keep = options.get(
#                         "versions_to_keep", versions_to_keep
#                     )
#                     remove_publish_folder = options.get(
#                         "remove_publish_folder", remove_publish_folder
#                     )
#
#                 data = self.get_data(context, versions_to_keep)
#                 if not data:
#                     continue
#
#                 project_name = context["project"]["name"]
#                 size += self.main(project_name, data, remove_publish_folder)
#                 print("Progressing {}/{}".format(count + 1, len(contexts)))
#
#             msg = "Total size of files: {}".format(format_file_size(size))
#             self.log.info(msg)
#             self.message(msg)
#
#         except Exception:
#             self.log.error("Failed to delete versions.", exc_info=True)
#
#
# class CalculateOldVersions(DeleteOldVersions):
#     """Calculate file size of old versions"""
#     label = "Calculate Old Versions"
#     order = 30
#     tool_names = ["library_loader"]
#
#     options = [
#         qargparse.Integer(
#             "versions_to_keep", default=2, min=0, help="Versions to keep:"
#         ),
#         qargparse.Boolean(
#             "remove_publish_folder", help="Remove publish folder:"
#         )
#     ]
#
#     def main(self, project_name, data, remove_publish_folder):
#         size = 0
#
#         if not data:
#             return size
#
#         if remove_publish_folder:
#             size = self.delete_whole_dir_paths(
#                 data["dir_paths"].values(), delete=False
#             )
#         else:
#             size = self.delete_only_repre_files(
#                 data["dir_paths"], data["file_paths_by_dir"], delete=False
#             )
#
#         return size
