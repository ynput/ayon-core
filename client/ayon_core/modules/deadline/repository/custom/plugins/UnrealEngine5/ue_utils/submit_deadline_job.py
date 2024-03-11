# Copyright Epic Games, Inc. All Rights Reserved
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

from System.Collections.Specialized import StringCollection
from System.IO import StreamWriter, Path
from System.Text import Encoding

from Deadline.Scripting import ClientUtils


def submit_job(name, job_info, plugin_info, aux_files=None):
    """
    Creates a job and plugin file and submits it to deadline as a job
    :param name: Name of the plugin
    :param job_info: The job dictionary
    :type job_info dict
    :param plugin_info: The plugin dictionary
    :type plugin_info dict
    :param aux_files: The files submitted to the farm
    :type aux_files list
    """

    # Create a job file
    JobInfoFilename = Path.Combine(
        ClientUtils.GetDeadlineTempPath(),
        "{name}_job_info.job".format(name=name),
    )
    # Get a job info file writer
    writer = StreamWriter(JobInfoFilename, False, Encoding.Unicode)

    for key, value in job_info.items():
        writer.WriteLine("{key}={value}".format(key=key, value=value))

    writer.Close()

    # Create a plugin file
    PluginInfoFilename = Path.Combine(
        ClientUtils.GetDeadlineTempPath(),
        "{name}_plugin_info.job".format(name=name),
    )
    # Get a plugin info file writer
    writer = StreamWriter(PluginInfoFilename, False, Encoding.Unicode)

    for key, value in plugin_info.items():
        writer.WriteLine("{key}={value}".format(key=key, value=value))

    # Add Aux Files if any
    if aux_files:
        for index, aux_files in enumerate(aux_files):
            writer.WriteLine(
                "File{index}={val}".format(index=index, val=aux_files)
            )

    writer.Close()

    # Create the commandline arguments
    args = StringCollection()

    args.Add(JobInfoFilename)
    args.Add(PluginInfoFilename)

    # Add aux files to the plugin data
    if aux_files:
        for scene_file in aux_files:
            args.Add(scene_file)

        
    results = ClientUtils.ExecuteCommandAndGetOutput(args)
    
    # TODO: Return the Job ID and results

    return results
