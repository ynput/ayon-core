import os

import semver
import ayon_api

from .local_settings import get_local_site_id


class _Cache:
    initialized = False


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
    fix_last_version_by_product_name = ayon_api_version < (1, 0, 2)
    # Monkey patching to fix 'get_last_version_by_product_name'
    if fix_last_version_by_product_name:
        ayon_api.ServerAPI.get_last_version_by_product_name = (
            _new_get_last_version_by_product_name
        )

    site_id = get_local_site_id()
    version = os.getenv("AYON_VERSION")
    if ayon_api.is_connection_created():
        con = ayon_api.get_server_api_connection()
        # Monkey patching to fix 'get_last_version_by_product_name'
        if fix_last_version_by_product_name:
            def _con_wrapper(*args, **kwargs):
                return _new_get_last_version_by_product_name(
                    con, *args, **kwargs
                )
            con.get_last_version_by_product_name = _con_wrapper
        con.set_site_id(site_id)
        con.set_client_version(version)
    else:
        ayon_api.create_connection(site_id, version)
