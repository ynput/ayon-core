# Copyright Epic Games, Inc. All Rights Reserved

"""
This is a commandline script that can be used to execute local and remote renders from Unreal.
This script can be executed in Editor or via commandline.

This script has several modes:

    manifest:
        This mode allows you to specify a full path to manifest file and a queue will be created from the manifest.

        Command:
            .. code-block:: shell

                $ py mrq_cli.py manifest "Full/Path/To/Manifest.utxt"
        Options:
            *--load*: This allows you to only load the manifest file without executing a render.

    sequence:
        This mode allows you to specify a specific level sequence, map and movie render queue preset to render.

        Command:
            .. code-block:: shell

                $ py mrq_cli.py sequence my_level_sequence_name my_map_name my_mrq_preset_name

    queue:
        This mode allows you to load and render a queue asset.

        Command:
            .. code-block:: shell

               $ py mrq_cli.py queue "/Game/path/to/queue/asset"
        Options:
            *--load*: This allows you to only load the queue asset without executing a render.

            *--jobs*: A queue can have more than one job. This allows you to specify particular jobs in the queue and render its current state

    render:
        This mode allows you to render the jobs in the current loaded queue. This is useful when you what to execute
        renders in multi steps. For example, executing in a farm context, you can load a manifest file and trigger
        multiple different shots for the current worker machine based on some database without reloading the
        manifest file everytime. By default, the queue is rendered in its current state if no other arguments are
        specified.

        Command:
            .. code-block:: shell

                $ py mrq_cli.py render
        Options:
            *--jobs*: The current queue can have more than one job. This allows you to specify a particular list of jobs in the queue and render in its current state


**Optional Arguments**:

    There a few optional arguments that can be supplied to the script and are global to the modes

    *--shots*: This option allows you to specify a list of shots to render in the queue. This optional argument can be used with both modes of the script.

    *--all-shots*: This options enables all shots on all jobs. This is useful when you want to render everything in a queue.

    *--user*: This options sets the author on the render job. If None is provided, the current logged-in user is used.

    *--remote/-r*: This option submits the render to a remote process. This remote process is whatever is set in the
    MRQ remote executor option. This script is targeted for Deadline. However, it can still support
    the default "Out-of-Process" executor. This flag can be used with both modes of the script.
    When specifying a remote command for deadline, you'll need to also supply these commands:

        *--batch_name*: This sets the batch name on the executor.

        *--deadline_job_preset*: The deadline preset for Deadline job/plugin info


Editor CMD window:
    .. code-block:: shell

        $ py mrq_cli.py <--remote> sequence sequence_name map mrq_preset_name

Editor Commandline:
    .. code-block:: shell

        UnrealEditor.exe uproject_name/path <startup-args> -execcmds="py mrq_cli.py sequence sequence_name map mrq_preset_name --cmdline"

In a commandline interface, it is very important to append `--cmdline` to the script args as this will tell the editor
to shut down after a render is complete. Currently, this is the only method to keep the editor open till a render is
complete due to the default python commandlet assuming when a python script ends, the editor needs to shut down.
This behavior is not ideal as PIE is an asynchronous process we need to wait for during rendering.
"""

import argparse

from mrq_cli_modes import render_manifest, render_sequence, render_queue, render_queue_jobs


if __name__ == "__main__":

    # A parser to hold all arguments we want available on sub parsers.
    global_parser = argparse.ArgumentParser(
        description="This parser contains any global arguments we would want available on subparsers",
        add_help=False
    )
    # Determine if the editor was run from a commandline
    global_parser.add_argument(
        "--cmdline",
        action="store_true",
        help="Flag for noting execution from commandline. "
        "This will shut the editor down after a render is complete or failed."
    )

    global_parser.add_argument(
        "-u",
        "--user",
        type=str,
        help="The user the render job will be submitted as."
    )

    # Group the flags for remote rendering. This is just a conceptual group
    # and not a logical group. It is mostly shown in the help interface
    remote_group = global_parser.add_argument_group("remote")

    # Determine if this is a local render or a remote render. If the remote
    # flag is present, it's a remote render
    remote_group.add_argument(
        "-r",
        "--remote",
        action="store_true",
        help="Determines if the render should be executed remotely."
    )

    # Option flag for remote renders. This will fail if not provided along
    # with the --remote flag
    remote_group.add_argument(
        "--batch_name",
        type=str,
        help="The batch render name for the current remote render job."
    )

    remote_group.add_argument(
        "--deadline_job_preset",
        help="The remote job preset to use when rendering the current job."
    )

    # Setup output override groups for the jobs
    output_group = global_parser.add_argument_group("output")
    output_group.add_argument(
        "--output_override",
        type=str,
        help="Output folder override for the queue asset"
    )
    output_group.add_argument(
        "--filename_override",
        type=str,
        help="Filename override for the queue asset"
    )

    # Shots group
    shots_group = global_parser.add_argument_group("shots")
    # Shots to render in a Queue
    shots_group.add_argument(
        "-s",
        "--shots",
        type=str,
        nargs="+",
        help="A list of shots to render in the level sequence. "
        "If no shots are provided, all shots in the level sequence will be rendered."
    )
    shots_group.add_argument(
        "--all-shots",
        action="store_true",
        help="Render all shots in the queue. This will enable all shots for all jobs."
    )

    # Create the main entry parser
    parser = argparse.ArgumentParser(
        prog="PYMoviePipelineCLI",
        description="Commandline Interface for rendering MRQ jobs"
    )

    # Create sub commands
    sub_commands = parser.add_subparsers(help="Sub-commands help")

    # Create a sub command for rendering with a manifest file
    manifest_parser = sub_commands.add_parser(
        "manifest",
        parents=[global_parser],
        help="Command to load and render queue from a manifest file."
    )

    # Add arguments for the manifest parser
    render_manifest.setup_manifest_parser(manifest_parser)

    # Create a sub command used to render a specific sequence with a map and
    # mrq preset
    sequence_parser = sub_commands.add_parser(
        "sequence",
        parents=[global_parser],
        help="Command to render a specific sequence, map, and mrq preset."
    )

    # Add arguments for the sequence parser
    render_sequence.setup_sequence_parser(sequence_parser)

    # Setup a parser for rendering a specific queue asset
    queue_parser = sub_commands.add_parser(
        "queue",
        parents=[global_parser],
        help="Command to render a movie pipeline queue."
    )

    # Add arguments for the queue parser
    render_queue.setup_queue_parser(queue_parser)

    # Add arguments for the rendering the current queue
    render_parser = sub_commands.add_parser(
        "render",
        parents=[global_parser],
        help="Command to render the current loaded render queue."
    )

    # Add arguments for the queue parser
    render_queue_jobs.setup_render_parser(render_parser)

    # Process the args using the argument execution functions.
    # Parse known arguments returns a tuple of arguments that are recognized
    # and others. Get the recognized arguments and execute their set defaults
    args, _ = parser.parse_known_args()
    print(args)
    args.func(args)
