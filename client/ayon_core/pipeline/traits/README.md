OpenAsssetIO Traits and Specifications
======================================

This directory contains the traits and specifications for the OpenAssetIO
used across the pipeline.

They are defined in yml files and [OpenAssetIo-traitgen tool](https://github.com/OpenAssetIO/OpenAssetIO-TraitGen/)
is used for generating the code from the yml files. This code
is placed in the `generated` directory along with the `__init__.py` file
that allows importing traits wherever needed.

You can use these traits in pipeline by importing them and using them like so:

```python
from ayon_core.pipeline.traits.generated.openassetio_mediacreation import traits as mediacreation_traits
from openassetio.trait import TraitsData


data = TraitsData()
frame_ranged = mediacreation_traits.timeDomain.FrameRangedTrait(data)
frame_ranged.setStartFrame(1001)
frame_ranged.setEndFrame(1025)
frame_ranged.setFramesPerSecond(24.0)
frame_ranged.setStep(1)

data.hasTrait(mediacreation_traits.timeDomain.FrameRangedTrait.kId)  # True

# ImageTrait has no properties, it is just a "family" trait
mediacreation_traits.twoDimensional.ImageTrait(data)

pixel_based = mediacreation_traits.twoDimensional.PixelBasedTrait(data)
pixel_based.setDisplayWindowHeight(1080)
pixel_based.setDisplayWindowWidth(1920)
pixel_based.setPixelAspectRatio(1.0)

data.hasTrait(mediacreation_traits.timeDomain.FrameRangedTrait.kId)  # True
data.hasTrait(mediacreation_traits.twoDimensional.ImageTrait.kId)  # True
data.hasTrait(mediacreation_traits.twoDimensional.PixelBasedTrait.kId)  # True
data.hasTrait(mediacreation_traits.color.OCIOColorManagedTrait.kId)  # False

```

You can regenerate those traits from YML files by running the script
from `/scrits/generate_traits.ps1`.
