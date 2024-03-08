import os

import ayon_api

from .local_settings import get_local_site_id


class _Cache:
    initialized = False


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
    site_id = get_local_site_id()
    version = os.getenv("AYON_VERSION")
    if ayon_api.is_connection_created():
        con = ayon_api.get_server_api_connection()
        con.set_site_id(site_id)
        con.set_client_version(version)
    else:
        ayon_api.create_connection(site_id, version)
