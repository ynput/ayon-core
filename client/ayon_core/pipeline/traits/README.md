OpenAsssetIO Traits and Specifications
======================================

Introduction
------------

**A trait** represents a concrete characteristic manifest by the thing in question. A trait may have one or more properties associated with it.

**Specifications** are a convenience used to define well-known sets of traits. They are used at runtime to ensure consistent handling of traits between different hosts and managers.

When a Specification combines traits into a Trait Set - they are additive. Each additional trait narrows the set's focus. Combining two traits does not mean "either/or".

At a programming level, traits are "views" on specification
data. They provide concrete, strongly typed access to the
open-ended data structures handled by the core API.
In some languages, they extend to providing IDE-level or compile-time checks of their use.


Directory Structure
-------------------

This directory contains the traits and specifications for the OpenAssetIO
used across the pipeline.

They are defined in the YAML files and [OpenAssetIo-traitgen tool](https://github.com/OpenAssetIO/OpenAssetIO-TraitGen/)
is used to generate the code from them. This code
is placed in the `generated` directory along with the `__init__.py` file
that allows importing traits wherever needed.

Usage
-----

You can use traits and specifications in pipeline by importing them and using them like so:

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

# ImageTrait has no properties, it is just a "type" trait
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
from `/scripts/generate_traits.ps1`.
