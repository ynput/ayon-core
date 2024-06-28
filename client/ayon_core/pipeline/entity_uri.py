from typing import Optional, Union
from urllib.parse import urlparse, parse_qs


def parse_ayon_entity_uri(uri: str) -> Optional[dict]:
    """Parse AYON entity URI into individual components.

    URI specification:
        ayon+entity://{project}/{folder}?product={product}
            &version={version}
            &representation={representation}
    URI example:
        ayon+entity://test/hero?product=modelMain&version=2&representation=usd

    However - if the netloc is `ayon://` it will by default also resolve as
    `ayon+entity://` on AYON server, thus we need to support both. The shorter
    `ayon://` is preferred for user readability.

    Example:
    >>> parse_ayon_entity_uri(
    >>>     "ayon://test/char/villain?product=modelMain&version=2&representation=usd"  # noqa: E501
    >>> )
    {'project': 'test', 'folderPath': '/char/villain',
     'product': 'modelMain', 'version': 1,
     'representation': 'usd'}
    >>> parse_ayon_entity_uri(
    >>>     "ayon+entity://project/folder?product=renderMain&version=3&representation=exr"  # noqa: E501
    >>> )
    {'project': 'project', 'folderPath': '/folder',
     'product': 'renderMain', 'version': 3,
     'representation': 'exr'}

    Returns:
        dict[str, Union[str, int]]: The individual key with their values as
            found in the ayon entity URI.

    """

    if not (uri.startswith("ayon+entity://") or uri.startswith("ayon://")):
        return {}

    parsed = urlparse(uri)
    if parsed.scheme not in {"ayon+entity", "ayon"}:
        return {}

    result = {
        "project": parsed.netloc,
        "folderPath": "/" + parsed.path.strip("/")
    }
    query = parse_qs(parsed.query)
    for key in ["product", "version", "representation"]:
        if key in query:
            result[key] = query[key][0]

    # Convert version to integer if it is a digit
    version = result.get("version")
    if version is not None and version.isdigit():
        result["version"] = int(version)

    return result


def construct_ayon_entity_uri(
        project_name: str,
        folder_path: str,
        product: str,
        version: Union[int, str],
        representation_name: str
) -> str:
    """Construct AYON entity URI from its components

    Returns:
        str: AYON Entity URI to query entity path.
    """
    if isinstance(version, int) and version < 0:
        version = "hero"
    if not (isinstance(version, int) or version in {"latest", "hero"}):
        raise ValueError(
            "Version must either be integer, 'latest' or 'hero'. "
            "Got: {}".format(version)
        )
    return (
        "ayon://{project}/{folder_path}?product={product}&version={version}"
        "&representation={representation}".format(
            project=project_name,
            folder_path=folder_path,
            product=product,
            version=version,
            representation=representation_name
        )
    )
