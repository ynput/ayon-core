import os

import re
import pyblish.api
from ayon_core.pipeline.publish import KnownPublishError
from ayon_maya.api import lib
from ayon_maya.api import plugin
from maya import cmds

SETTINGS = {"renderDensity",
            "renderWidth",
            "renderLength",
            "increaseRenderBounds",
            "imageSearchPath",
            "cbId"}


class CollectYetiRig(plugin.MayaInstancePlugin):
    """Collect all information of the Yeti Rig"""

    order = pyblish.api.CollectorOrder + 0.4
    label = "Collect Yeti Rig"
    families = ["yetiRig"]

    def process(self, instance):

        assert "input_SET" in instance.data["setMembers"], (
            "Yeti Rig must have an input_SET")

        input_connections = self.collect_input_connections(instance)

        # Collect any textures if used
        yeti_resources = []
        yeti_nodes = cmds.ls(instance[:], type="pgYetiMaya", long=True)
        for node in yeti_nodes:
            # Get Yeti resources (textures)
            resources = self.get_yeti_resources(node)
            yeti_resources.extend(resources)

        instance.data["rigsettings"] = {"inputs": input_connections}

        instance.data["resources"] = yeti_resources

        # Force frame range for yeti cache export for the rig
        start = cmds.playbackOptions(query=True, animationStartTime=True)
        for key in ["frameStart", "frameEnd",
                    "frameStartHandle", "frameEndHandle"]:
            instance.data[key] = start
        instance.data["preroll"] = 0

    def collect_input_connections(self, instance):
        """Collect the inputs for all nodes in the input_SET"""

        # Get the input meshes information
        input_content = cmds.ls(cmds.sets("input_SET", query=True), long=True)

        # Include children
        input_content += cmds.listRelatives(input_content,
                                            allDescendents=True,
                                            fullPath=True) or []

        # Ignore intermediate objects
        input_content = cmds.ls(input_content, long=True, noIntermediate=True)
        if not input_content:
            return []

        # Store all connections
        connections = cmds.listConnections(input_content,
                                           source=True,
                                           destination=False,
                                           connections=True,
                                           # Only allow inputs from dagNodes
                                           # (avoid display layers, etc.)
                                           type="dagNode",
                                           plugs=True) or []
        connections = cmds.ls(connections, long=True)      # Ensure long names

        inputs = []
        for dest, src in lib.pairwise(connections):
            source_node, source_attr = src.split(".", 1)
            dest_node, dest_attr = dest.split(".", 1)

            # Ensure the source of the connection is not included in the
            # current instance's hierarchy. If so, we ignore that connection
            # as we will want to preserve it even over a publish.
            if source_node in instance:
                self.log.debug("Ignoring input connection between nodes "
                               "inside the instance: %s -> %s" % (src, dest))
                continue

            inputs.append({"connections": [source_attr, dest_attr],
                           "sourceID": lib.get_id(source_node),
                           "destinationID": lib.get_id(dest_node)})

        return inputs

    def get_yeti_resources(self, node):
        """Get all resource file paths

        If a texture is a sequence it gathers all sibling files to ensure
        the texture sequence is complete.

        References can be used in the Yeti graph, this means that it is
        possible to load previously caches files. The information will need
        to be stored and, if the file not publish, copied to the resource
        folder.

        Args:
            node (str): node name of the pgYetiMaya node

        Returns:
            list
        """
        resources = []

        image_search_paths = cmds.getAttr("{}.imageSearchPath".format(node))
        if image_search_paths:

            # TODO: Somehow this uses OS environment path separator, `:` vs `;`
            # Later on check whether this is pipeline OS cross-compatible.
            image_search_paths = [p for p in
                                  image_search_paths.split(os.path.pathsep) if p]

            # find all ${TOKEN} tokens and replace them with $TOKEN env. variable
            image_search_paths = self._replace_tokens(image_search_paths)

        # List all related textures
        texture_nodes = cmds.pgYetiGraph(
            node, listNodes=True, type="texture")
        texture_filenames = [
            cmds.pgYetiGraph(
                node, node=texture_node,
                param="file_name", getParamValue=True)
            for texture_node in texture_nodes
        ]
        self.log.debug("Found %i texture(s)" % len(texture_filenames))

        # Get all reference nodes
        reference_nodes = cmds.pgYetiGraph(node,
                                           listNodes=True,
                                           type="reference")
        self.log.debug("Found %i reference node(s)" % len(reference_nodes))

        # Collect all texture files
        # find all ${TOKEN} tokens and replace them with $TOKEN env. variable
        texture_filenames = self._replace_tokens(texture_filenames)
        for texture in texture_filenames:

            files = []
            if os.path.isabs(texture):
                self.log.debug("Texture is absolute path, ignoring "
                               "image search paths for: %s" % texture)
                files = lib.search_textures(texture)
            else:
                for root in image_search_paths:
                    filepath = os.path.join(root, texture)
                    files = lib.search_textures(filepath)
                    if files:
                        # Break out on first match in search paths..
                        break

            if not files:
                raise KnownPublishError(
                    "No texture found for: %s "
                    "(searched: %s)" % (texture, image_search_paths))

            item = {
                "files": files,
                "source": texture,
                "node": node
            }

            resources.append(item)

        # For now validate that every texture has at least a single file
        # resolved. Since a 'resource' does not have the requirement of having
        # a `files` explicitly mapped it's not explicitly validated.
        # TODO: Validate this as a validator
        invalid_resources = []
        for resource in resources:
            if not resource['files']:
                invalid_resources.append(resource)
        if invalid_resources:
            raise RuntimeError("Invalid resources")

        # Collect all referenced files
        for reference_node in reference_nodes:
            ref_file = cmds.pgYetiGraph(node,
                                        node=reference_node,
                                        param="reference_file",
                                        getParamValue=True)

            # Create resource dict
            item = {
                "source": ref_file,
                "node": node,
                "graphnode": reference_node,
                "param": "reference_file",
                "files": []
            }

            ref_file_name = os.path.basename(ref_file)
            if "%04d" in ref_file_name:
                item["files"] = lib.get_sequence(ref_file)
            else:
                if os.path.exists(ref_file) and os.path.isfile(ref_file):
                    item["files"] = [ref_file]

            if not item["files"]:
                self.log.warning("Reference node '%s' has no valid file "
                                 "path set: %s" % (reference_node, ref_file))
                # TODO: This should allow to pass and fail in Validator instead
                raise RuntimeError("Reference node  must be a full file path!")

            resources.append(item)

        return resources

    def _replace_tokens(self, strings):
        env_re = re.compile(r"\$\{(\w+)\}")

        replaced = []
        for s in strings:
            matches = re.finditer(env_re, s)
            for m in matches:
                try:
                    s = s.replace(m.group(), os.environ[m.group(1)])
                except KeyError:
                    msg = "Cannot find requested {} in environment".format(
                        m.group(1))
                    self.log.error(msg)
                    raise RuntimeError(msg)
            replaced.append(s)
        return replaced