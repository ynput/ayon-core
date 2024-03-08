import ayon_api


class _GlobalCache:
    initialized = False


def get_ayon_server_api_connection():
    return ayon_api.get_server_api_connection()
