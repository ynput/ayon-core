import os

import semver
import ayon_api

from .local_settings import get_local_site_id


class _Cache:
    initialized = False


def _new_get_last_versions(
    self,
    project_name,
    product_ids,
    active=True,
    fields=None,
    own_attributes=False
):
    """Query last version entities by product ids.

    Args:
        project_name (str): Project where to look for representation.
        product_ids (Iterable[str]): Product ids.
        active (Optional[bool]): Receive active/inactive entities.
            Both are returned when 'None' is passed.
        fields (Optional[Iterable[str]]): fields to be queried
            for representations.
        own_attributes (Optional[bool]): Attribute values that are
            not explicitly set on entity will have 'None' value.

    Returns:
        dict[str, dict[str, Any]]: Last versions by product id.

    """
    if fields:
        fields = set(fields)
        fields.add("productId")

    versions = self.get_versions(
        project_name,
        product_ids=product_ids,
        latest=True,
        hero=False,
        active=active,
        fields=fields,
        own_attributes=own_attributes
    )
    return {
        version["productId"]: version
        for version in versions
    }


def _new_get_last_version_by_product_id(
    self,
    project_name,
    product_id,
    active=True,
    fields=None,
    own_attributes=False
):
    """Query last version entity by product id.

    Args:
        project_name (str): Project where to look for representation.
        product_id (str): Product id.
        active (Optional[bool]): Receive active/inactive entities.
            Both are returned when 'None' is passed.
        fields (Optional[Iterable[str]]): fields to be queried
            for representations.
        own_attributes (Optional[bool]): Attribute values that are
            not explicitly set on entity will have 'None' value.

    Returns:
        Union[dict[str, Any], None]: Queried version entity or None.

    """
    versions = self.get_versions(
        project_name,
        product_ids=[product_id],
        latest=True,
        hero=False,
        active=active,
        fields=fields,
        own_attributes=own_attributes
    )
    for version in versions:
        return version
    return None


def _new_get_last_version_by_product_name(
    self,
    project_name,
    product_name,
    folder_id,
    active=True,
    fields=None,
    own_attributes=False
):
    """Query last version entity by product name and folder id.

    Args:
        project_name (str): Project where to look for representation.
        product_name (str): Product name.
        folder_id (str): Folder id.
        active (Optional[bool]): Receive active/inactive entities.
            Both are returned when 'None' is passed.
        fields (Optional[Iterable[str]]): fields to be queried
            for representations.
        own_attributes (Optional[bool]): Attribute values that are
            not explicitly set on entity will have 'None' value.

    Returns:
        Union[dict[str, Any], None]: Queried version entity or None.

    """
    if not folder_id:
        return None

    product = self.get_product_by_name(
        project_name, product_name, folder_id, fields={"id"}
    )
    if not product:
        return None
    return self.get_last_version_by_product_id(
        project_name,
        product["id"],
        active=active,
        fields=fields,
        own_attributes=own_attributes
    )


def initialize_ayon_connection(force=False):
    """Initialize global AYON api connection.

    Create global connection in ayon_api module and set site id
        and client version.
    Is silently skipped if already happened.

    Args:
        force (Optional[bool]): Force reinitialize connection.
            Defaults to False.

    """
    if not force and _Cache.initialized:
        return

    _Cache.initialized = True
    ayon_api_version = (
        semver.VersionInfo.parse(ayon_api.__version__).to_tuple()
    )
    # TODO remove mokey patching after when AYON api is safely updated
    fix_before_1_0_2 = ayon_api_version < (1, 0, 2)
    # Monkey patching to fix 'get_last_version_by_product_name'
    if fix_before_1_0_2:
        ayon_api.ServerAPI.get_last_versions = (
            _new_get_last_versions
        )
        ayon_api.ServerAPI.get_last_version_by_product_id = (
            _new_get_last_version_by_product_id
        )
        ayon_api.ServerAPI.get_last_version_by_product_name = (
            _new_get_last_version_by_product_name
        )

    site_id = get_local_site_id()
    version = os.getenv("AYON_VERSION")
    if ayon_api.is_connection_created():
        con = ayon_api.get_server_api_connection()
        # Monkey patching to fix 'get_last_version_by_product_name'
        if fix_before_1_0_2:
            def _lvs_wrapper(*args, **kwargs):
                return _new_get_last_versions(
                    con, *args, **kwargs
                )
            def _lv_by_pi_wrapper(*args, **kwargs):
                return _new_get_last_version_by_product_id(
                    con, *args, **kwargs
                )
            def _lv_by_pn_wrapper(*args, **kwargs):
                return _new_get_last_version_by_product_name(
                    con, *args, **kwargs
                )
            con.get_last_versions = _lvs_wrapper
            con.get_last_version_by_product_id = _lv_by_pi_wrapper
            con.get_last_version_by_product_name = _lv_by_pn_wrapper
        con.set_site_id(site_id)
        con.set_client_version(version)
    else:
        ayon_api.create_connection(site_id, version)
