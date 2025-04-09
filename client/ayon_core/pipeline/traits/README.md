# Representations and traits

## Introduction

The Representation is the lowest level entity, describing the concrete data chunk that
pipeline can act on. It can be specific file or just a set of metadata. Idea is that one
product version can have multiple representations - **Image** product can be jpeg or tiff, both formats are representation of the same source.

### Brief look into the past (and current state)

So far, representation was defined as dict-like structure:
```python
{
    "name": "foo",
    "ext": "exr",
    "files": ["foo_001.exr", "foo_002.exr"],
    "stagingDir": "/bar/dir"
}
```

This is minimal form, but it can have additional keys like `frameStart`, `fps`, `resolutionWidth`, and more. Thare is also `tags` key that can hold `review`, `thumbnail`, `delete`, `toScanline` and other tag that are controlling the processing.

This will be *"translated"* to similar structure in database:

```python
{
    "name": "foo",
    "version_id": "...",
    "files": [
        {
            "id": ...,
            "hash": ...,
            "name": "foo_001.exr",
            "path": "{root[work]}/bar/dir/foo_001.exr",
            "size": 1234,
            "hash_type": "...",
        },
        ...
    ],
    "attrib": {
        "path": "root/bar/dir/foo_001.exr",
        "template": "{root[work]}/{project[name]}...",
    },
    "data": {
        "context": {
            "ext": "exr",
            "root": {...},
            ...
    },
    "active": True
    ...

}
```

There are also some assumptions and limitations - like that if `files` in the
representation are list they need to be sequence of files (it can't be a bunch of
unrelated files).

This system is very flexible in one way, but it lacks few very important things:

- it is not clearly defined - you can add easily keys, values, tags but without 
unforeseeable
consequences
- it cannot handle "bundles" - multiple files that needs to be versioned together and 
belong together
- it cannot describe important information that you can't get from the file itself, or
it is very expensive (like axis orientation and units from alembic files)


### New Representation model

The idea about new representation model is obviously around solving points mentioned
above and also adding some benefits, like consistent IDE hints, typing, built-in
 validators and much more.

### Design

The new representation is "just" a dictionary of traits. Trait can be anything provided
it is based on `TraitBase`. It shouldn't really duplicate information that is
available in a moment of loading (or any usage) by other means. It should contain 
information that couldn't be determined by the file, or the AYON context. Some of 
those traits are aligned with [OpenAssetIO Media Creation](https://github.com/OpenAssetIO/OpenAssetIO-MediaCreation) with hopes of maintained compatibility (it 
should be easy enough to convert between OpenAssetIO Traits and AYON Traits).

#### Details: Representation

`Representation` has methods to deal with adding, removing, getting
traits. It has all the usual stuff like `get_trait()`, `add_trait()`,
`remove_trait()`, etc. But it also has plural forms so you can get/set
several traits at the same time with `get_traits()` and so on.
`Representation` also behaves like dictionary. so you can access/set
traits in the same way as you would do with dict:

```python
# import Image trait
from ayon_core.pipeline.traits import Image, Tagged, Representation


# create new representation with name "foo" and add Image trait to it
rep = Representation(name="foo", traits=[Image()])

# you can add another trait like so
rep.add_trait(Tagged(tags=["tag"]))

# or you can
rep[Tagged.id] = Tagged(tags=["tag"])

# and getting them in analogous
image = rep.get_trait(Image)

# or
image = rep[Image.id]
```

> [!NOTE]
> Trait and their ids - every Trait has its id as a string with
> version appended - so **Image** has `ayon.2d.Image.v1`. This is used on
> several places (you see its use above for indexing traits). When querying,
> you can also omit the version at the end, and it will try its best to find
> the latest possible version. More on that in [Traits]()

You can construct the `Representation` from dictionary (for example
serialized as JSON) using `Representation.from_dict()`, or you can
serialize `Representation` to dict to store with `Representation.traits_as_dict()`.

Every time representation is created, new id is generated. You can pass existing
id when creating new representation instance.

##### Equality

Two Representations are equal if:
- their names are the same
- their IDs are the same
- they have the same traits
- the traits have the same values

##### Validation

Representation has `validate()` method that will run `validate()` on
all it's traits.

#### Details: Traits

As mentioned there are several traits defined directly in **ayon-core**. They are namespaced
to different packages based on their use:

| namespace         | trait                | description                                                                                              |
|-------------------|----------------------|----------------------------------------------------------------------------------------------------------|
| color             | ColorManaged         | hold color management information                                                                        |
| content           | MimeType             | use MIME type (RFC 2046) to describe content (like image/jpeg)                                           |
|                   | LocatableContent     | describe some location (file or URI)                                                                     |
|                   | FileLocation         | path to file, with size and checksum                                                                     |
|                   | FileLocations        | list of `FileLocation`                                                                                   |
|                   | RootlessLocation     | Path where root is replaced with AYON root token                                                         |
|                   | Compressed           | describes compression (of file or other)                                                                 |
|                   | Bundle               | list of list of Traits - compound of inseparable "sub-representations"                                   |
|                   | Fragment             | compound type marking the representation as a part of larger group of representations                    |
| cryptography      | DigitallySigned      | Type traits marking data to be digitally signed                                                          |
|                   | PGPSigned            | Representation is signed by [PGP](https://www.openpgp.org/)                                              |
| lifecycle         | Transient            | Marks the representation to be temporary - not to be stored.                                             |
|                   | Persistent           | Representation should be integrated (stored). Opposite of Transient.                                     |
| meta              | Tagged               | holds list of tag strings.                                                                               |
|                   | TemplatePath         | Template consisted of tokens/keys and data to be used to resolve the template into string                |
|                   | Variant              | Used to differentiate between data variants of the same output (mp4 as h.264 and h.265 for example)      |
|                   | KeepOriginalLocation | Marks the representation to keep the original location of the file                                       |
|                   | KeepOriginalName     | Marks the representation to keep the original name of the file                                           |
|                   | SourceApplication    | Holds information about producing application, about it's version, variant and platform.                 |
|                   | IntendedUse          | For specifying the intended use of the representation if it cannot be easily determined by other traits. |
| three dimensional | Spatial              | Spatial information like up-axis, units and handedness.                                                  |
|                   | Geometry             | Type trait to mark the representation as a geometry.                                                     |
|                   | Shader               | Type trait to mark the representation as a Shader.                                                       |
|                   | Lighting             | Type trait to mark the representation as Lighting.                                                       |
|                   | IESProfile           | States that the representation is IES Profile.                                                           |
| time              | FrameRanged          | Contains start and end frame information with in and out.                                                |                                                
|                   | Handless             | define additional frames at the end or beginning and if those frames are inclusive of the range or not.  |  
|                   | Sequence             | Describes sequence of frames and how the frames are defined in that sequence.                            |                            
|                   | SMPTETimecode        | Adds timecode information in SMPTE format.                                                               |                                                               
|                   | Static               | Marks the content as not time-variant.                                                                   |                                                                   
| two dimensional   | Image                | Type traits of image.                                                                                    |                                                                                    
|                   | PixelBased           | Defines resolution and pixel aspect for the image data.                                                  |                                                  
|                   | Planar               | Whether pixel data is in planar configuration or packed.                                                 |                                            
|                   | Deep                 | Image encodes deep pixel data.                                                                           |                                                                           
|                   | Overscan             | holds overscan/underscan information (added pixels to bottom/sides).                                     |                                      
|                   | UDIM                 | Representation is UDIM tile set.                                                                         |                                                                          

Traits are Python data classes with optional
validation and helper methods. If they implement `TraitBase.validate(Representation)` method, they can validate against all other traits
in the representation if needed. 

> [!NOTE]
> They could be easily converted to [Pydantic models](https://docs.pydantic.dev/latest/) but since this must run in diverse Python environments inside DCC, we cannot
> easily resolve pydantic-core dependency (as it is binary written in Rust).

> [!NOTE]
> Every trait has id, name and some human-readable description. Every trait
> also has `persistent` property that is by default set to True. This
> Controls whether this trait should be stored with the persistent representation
> or not. Useful for traits to be used just to control the publishing process.

## Examples

Create simple image representation to be integrated by AYON:

```python
from pathlib import Path
from ayon_core.pipeline.traits import (
    FileLocation,
    Image,
    PixelBased,
    Persistent,
    Representation,
    Static,

    TraitValidationError,
)
    
rep = Representation(name="reference image", traits=[
    FileLocation(
        file_path=Path("/foo/bar/baz.exr"),
        file_size=1234,
        file_hash="sha256:...",
    ),
    Image(),
    PixelBased(
        display_window_width=1920,
        display_window_height=1080,
        pixel_aspect_ratio=1.0,
    ),
    Persistent(),
    Static()
])

# validate the representation

try:
    rep.validate()
except TraitValidationError as e:
    print(f"Representation {rep.name} is invalid: {e}")

```

To work with the resolution of such representation:

```python

try:
    width = rep.get_trait(PixelBased).display_window_width
    # or like this:
    height = rep[PixelBased.id].display_window_height
except MissingTraitError:
    print(f"resolution isn't set on {rep.name}")
```

Accessing non-existent traits will result in exception. To test if
representation has some specific trait, you can use `.contains_trait()` method.


You can also prepare the whole representation data as a dict and
create it from it:

```python
rep_dict = {
        "ayon.content.FileLocation.v1": {
            "file_path": Path("/path/to/file"),
            "file_size": 1024,
            "file_hash": None,
        },
        "ayon.two_dimensional.Image": {},
        "ayon.two_dimensional.PixelBased": {
            "display_window_width": 1920,
            "display_window_height": 1080,
            "pixel_aspect_ratio": 1.0,
        },
        "ayon.two_dimensional.Planar": {
            "planar_configuration": "RGB",
        }
}

rep = Representation.from_dict(name="image", rep_dict)

```


## Addon specific traits

Addon can define its own traits. To do so, it needs to implement `ITraits` interface:

```python
from ayon_core.pipeline.traits import TraitBase
from ayon_core.addon import (
    AYONAddon,
    ITraits,
)

class MyTraitFoo(TraitBase):
    id = "myaddon.mytrait.foo.v1"
    name = "My Trait Foo"
    description = "This is my trait foo"
    persistent = True


class MyTraitBar(TraitBase):
    id = "myaddon.mytrait.bar.v1"
    name = "My Trait Bar"
    description = "This is my trait bar"
    persistent = True

    
class MyAddon(AYONAddon, ITraits):
    def __init__(self):
        super().__init__()

    def get_addon_traits(self):
        return [
            MyTraitFoo,
            MyTraitBar,
        ]
```
## Usage in Loaders

In loaders, you can implement `is_compatible_loader()` method to check if the
representation is compatible with the loader. You can use `Representation.from_dict()` to
create the representation from the context. You can also use `Representation.contains_traits()`
to check if the representation contains the required traits. You can even check for specific
values in the traits.

You can use similar concepts directly in the `load()` method to get the traits. Here is
an example of how to use the traits in the hypothetical Maya loader:

```python
"""Alembic loader using traits."""
from __future__ import annotations
import json
from typing import Any, TypeVar, Type
from ayon_maya.api.plugin import MayaLoader
from ayon_core.pipeline.traits import (
    FileLocation,
    Spatial,

    Representation,
    TraitBase,
)

T = TypeVar("T", bound=TraitBase)


class AlembicTraitLoader(MayaLoader):
    """Alembic loader using traits."""
    label = "Alembic Trait Loader"
    ...

    required_traits: list[T] = [
        FileLocation,
        Spatial,
    ]

    @staticmethod
    def is_compatible_loader(context: dict[str, Any]) -> bool:
        traits_raw = context["representation"].get("traits")
        if not traits_raw:
            return False

        # construct Representation object from the context
        representation = Representation.from_dict(
            name=context["representation"]["name"],
            representation_id=context["representation"]["id"],
            trait_data=json.loads(traits_raw),
        )

        # check if the representation is compatible with this loader
        if representation.contains_traits(AlembicTraitLoader.required_traits):
            # you can also check for specific values in traits here
            return True
        return False

    ...
```

## Usage Publishing plugins

You can create the representations in the same way as mentioned in the examples above.
Straightforward way is to use `Representation` class and add the traits to it. Collect
traits in list and then pass them to the `Representation` constructor. You should add
the new Representation to the instance data using `add_trait_representations()` function.

```python
class SomeExtractor(Extractor):
    """Some extractor."""
    ...

    def extract(self, instance: Instance) -> None:
        """Extract the data."""
        # get the path to the file
        path = self.get_path(instance)

        # create the representation
        traits: list[TraitBase] = [
            Geometry(),
            MimeType(mime_type="application/abc"),
            Persistent(),
            Spatial(
                up_axis=cmds.upAxis(q=True, axis=True),
                meters_per_unit=maya_units_to_meters_per_unit(
                    instance.context.data["linearUnits"]),
                handedness="right",
            ),
        ]

        if instance.data.get("frameStart"):
            traits.append(
                FrameRanged(
                    frame_start=instance.data["frameStart"],
                    frame_end=instance.data["frameEnd"],
                    frames_per_second=instance.context.data["fps"],
                )
            )

        representation = Representation(
            name="alembic",
            traits=[
                FileLocation(
                    file_path=Path(path),
                    file_size=os.path.getsize(path),
                    file_hash=get_file_hash(Path(path))
                ),
                *traits],
        )

        add_trait_representations(
            instance,
            [representation],
        )
        ...
```

## Developer notes

Adding new trait based representations in to publish Instance and working with them is using
set of helper function defined in `ayon_core.pipeline.publish` module. These are:

* add_trait_representations
* get_trait_representations
* has_trait_representations
* set_trait_representations

And their main purpose is to handle the key under which the representation
is stored in the instance data. This is done to avoid name clashes with
other representations. The key is defined in the `AYON_PUBLISH_REPRESENTATION_KEY`.
It is strongly recommended to use those functions instead of
directly accessing the instance data. This is to ensure that the
code will work even if the key is changed in the future.

