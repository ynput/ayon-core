import collections
import hashlib
import inspect
import json
from pathlib import Path

import deal

from .generated.Ayon.traits.meta import FilesBundleTrait


@deal.post(lambda result: len(result) > 0)
def get_available_traits_ids() -> set:
    """
    Get the list of available trait ids.

    Returns:
        set: set of trait ids
    """

    import ayon_core.pipeline.traits.generated as traits

    queue = collections.deque()
    queue.append(traits)
    traits = set()
    while queue:
        item = queue.popleft()
        for name in dir(item):
            value = getattr(item, name)
            if inspect.ismodule(value):
                queue.append(value)
                continue
            if inspect.isclass(value) and hasattr(value, "kId"):
                traits.add(value.kId)

    return traits


def update_file_bundle_data(traits_data):
    """Update FileBundle traits data with missing information.

    This will fill in the missing information for the FileBundle
    traits data if they are missing. It will go over the list of
    files and calculate their size and checksum.

    """
    if not FilesBundleTrait.isImbuedTo(traits_data):
        raise ValueError(
            "The traits data is not imbued with FilesBundleTrait")

    trait = FilesBundleTrait(traits_data)
    files = json.loads(trait.getFiles())
    sizes = []
    hashes = []
    for file in files:
        file = Path(file)
        if not file.exists():
            raise ValueError(f"File {file} does not exist")
        sizes.append(file.stat().st_size)
        hashes.append(
            hashlib.sha256(file.read_bytes()).hexdigest())
    if files:
        trait.setSizes(json.dumps(sizes))
        trait.setHashes(json.dumps(hashes))
