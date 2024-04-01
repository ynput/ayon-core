
AYON Core Addon
===============

AYON core provides the base building blocks for all other AYON addons and integrations and is responsible for discovery and initialization of other addons.

- Some of its key functions include:
- It is used as the main command line handler in [ayon-launcher](https://github.com/ynput/ayon-launcher) application.
- Provides publishing plugins that are available to all AYON integrations.
- Defines the base classes for new pipeline integrations
- Provides global hooks
- Provides universally available loaders and launcher actions
- Defines pipeline API used by other integrations
- Provides all graphical tools for artists
- Defines AYON QT styling
- A bunch more things

Together with [ayon-launcher](https://github.com/ynput/ayon-launcher) , they form the base of AYON pipeline and is one of few compulsory addons for AYON pipeline to be useful in a meaningful way.

AYON-core is a successor to [OpenPype repository](https://github.com/ynput/OpenPype) (minus all the addons) and still in the process of cleaning up of all references. Please bear with us during this transitional phase.

Development and testing notes
-----------------------------
There is `pyproject.toml` file in the root of the repository. This file is used to define the development environment and is used by `poetry` to create a virtual environment.
This virtual environment is used to run tests and to develop the code, to help with
linting and formatting. Dependencies defined here are not used in actual addon
deployment - for that you need to edit `./client/pyproject.toml` file. That file
will be then processed [ayon-dependencies-tool](https://github.com/ynput/ayon-dependencies-tool)
to create dependency package.

Right now, this file needs to by synced with dependencies manually, but in the future
we plan to automate process of development environment creation.
