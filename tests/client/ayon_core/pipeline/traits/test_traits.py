import json
import hashlib
from pathlib import Path

import ayon_core.pipeline.traits as traits
import ayon_core.pipeline.traits.generated as traits_generated
import pytest
from openassetio.trait import TraitsData


@pytest.fixture
def file_sequence(tmp_path):
    files = []
    for x in range(5):
        file = tmp_path / f"file_{x}.txt"
        file.write_text(f"Hello {x}")
        files.append(file)
    return files


def _print_data(data):
    as_dict = {
        trait_id: {
            property_key: data.getTraitProperty(trait_id, property_key)
            for property_key in data.traitPropertyKeys(trait_id)
        }
        for trait_id in data.traitSet()
    }
    print(json.dumps(as_dict))


def test_traits_data():
    mc = traits_generated.openassetio_mediacreation
    data = TraitsData()
    lc = mc.traits.content.LocatableContentTrait(data)
    lc.setLocation("https://www.google.com")
    assert data.hasTrait(mc.traits.content.LocatableContentTrait.kId)
    _print_data(data)


def test_generated_traits():
    data = TraitsData()
    mc = traits_generated.openassetio_mediacreation

    assert hasattr(traits, "openassetio_mediacreation"), "The module should have openassetio_mediacreation"
    version_t = mc.traits.lifecycle.StableTrait

    version_t.imbueTo(data)
    assert data.hasTrait(mc.traits.lifecycle.StableTrait.kId)


def test_get_available_traits_ids(printer):
    trait_ids = traits.get_available_traits_ids()
    assert len(trait_ids) > 0, "There should be at least one trait"
    assert "ayon:usage.Subset" in trait_ids
    for trait_id in sorted(trait_ids):
        printer(trait_id)


def test_update_file_bundle_data(printer, file_sequence):
    data = TraitsData()
    ayon = traits_generated.Ayon
    fb = ayon.traits.meta.FilesBundleTrait(data)
    files = list(file_sequence)  # type: list[Path]
    fb.setFiles(json.dumps([file.as_posix() for file in files]))
    traits.update_file_bundle_data(data)
    assert fb.getSizes() is not None
    assert fb.getHashes() is not None
    for idx, file in enumerate(json.loads(fb.getFiles())):
        file = Path(file)
        calc_hash = hashlib.sha256(file.read_bytes()).hexdigest()
        size = file.stat().st_size
        assert json.loads(fb.getSizes())[idx] == size
        assert json.loads(fb.getHashes())[idx] == calc_hash
