# Copyright Epic Games, Inc. All Rights Reserved

# Built-In
import os
import subprocess
import logging
import tempfile

# Best-effort import for type annotations
try:
    from typing import Any, List, Optional, Tuple, Union
except ImportError:
    pass

logger = logging.getLogger("DeadlineCommand")

class DeadlineCommand:
    """
    Class to manage use of DeadlineCommand
    """
    def __init__(self):
        self.deadlineCommand = self._get_DeadlineCommand()

    def _get_DeadlineCommand(self):
        # type: () -> str
        deadlineBin = "" # type: str
        try:
            deadlineBin = os.environ['DEADLINE_PATH']
        except KeyError:
            #if the error is a key error it means that DEADLINE_PATH is not set. however Deadline command may be in the PATH or on OSX it could be in the file /Users/Shared/Thinkbox/DEADLINE_PATH
            pass
            
        # On OSX, we look for the DEADLINE_PATH file if the environment variable does not exist.
        if deadlineBin == "" and  os.path.exists( "/Users/Shared/Thinkbox/DEADLINE_PATH" ):
            with open( "/Users/Shared/Thinkbox/DEADLINE_PATH" ) as f:
                deadlineBin = f.read().strip()

        deadlineCommand = os.path.join(deadlineBin, "deadlinecommand") # type: str
        
        return deadlineCommand

    def get_repository_path(self, subdir = None):
    
        startupinfo = None

        args = [self.deadlineCommand, "-GetRepositoryPath "]   
        if subdir != None and subdir != "":
            args.append(subdir)

        # Specifying PIPE for all handles to workaround a Python bug on Windows. The unused handles are then closed immediatley afterwards.
        logger.debug(f"Getting repository path via deadlinecommand with subprocess args: {args}")
        proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo)

        proc.stdin.close()
        proc.stderr.close()

        output = proc.stdout.read()

        path = output.decode("utf_8")
        path = path.replace("\r","").replace("\n","").replace("\\","/")

        return path
    
    def get_pools(self):
        startupinfo = None

        args = [self.deadlineCommand, "-GetPoolNames"]   

        # Specifying PIPE for all handles to workaround a Python bug on Windows. The unused handles are then closed immediatley afterwards.
        logger.debug(f"Getting pools via deadlinecommand with subprocess args: {args}")
        proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo)

        proc.stdin.close()
        proc.stderr.close()

        output = proc.stdout.read()

        path = output.decode("utf_8")

        return path.split(os.linesep)
    
    def get_groups(self):
        startupinfo = None

        args = [self.deadlineCommand, "-GetGroupNames"]   

        # Specifying PIPE for all handles to workaround a Python bug on Windows. The unused handles are then closed immediatley afterwards.
        logger.debug(f"Getting groupsvia deadlinecommand with subprocess args: {args}")
        proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo)

        proc.stdin.close()
        proc.stderr.close()

        output = proc.stdout.read()

        path = output.decode("utf_8")

        return path.split(os.linesep)
    
    def submit_job(self, job_data):
        startupinfo = None

        # cast dict to list of strings equivilent to job file and plugin file
        job_info = [k+'='+v.replace("\n","").replace("\r","").replace("\t","")+'\n' for k, v in job_data["JobInfo"].items()]
        plugin_info = [k+'='+v.replace("\n","").replace("\r","").replace("\t","")+'\n' for k, v in job_data["PluginInfo"].items()]

        with tempfile.NamedTemporaryFile(mode = "w", delete=False) as f_job, tempfile.NamedTemporaryFile(mode = "w", delete=False) as f_plugin:
            logger.debug(f"Creating temporary job file {f_job.name}")
            logger.debug(f"Creating temporary plugin file {f_plugin.name}")
            f_job.writelines(job_info)
            f_plugin.writelines(plugin_info)
            
            f_job.close()
            f_plugin.close()

            args = [self.deadlineCommand, "-SubmitJob", f_job.name, f_plugin.name]   
            args.extend(job_data["aux_files"]) if "aux_files" in job_data else None  #  If aux files present extend args
            # Specifying PIPE for all handles to workaround a Python bug on Windows. The unused handles are then closed immediatley afterwards.
            logger.debug(f"Submitting job via deadlinecommand with subprocess args: {args}")
            proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo)
            
            # On windows machines Temproary files cannot be opened by multiple processes so we cann use the delete=True flag and must clean up the tmp files ourselves.
            # https://docs.python.org/3/library/tempfile.html#tempfile.NamedTemporaryFile
            proc.wait()
            os.remove(f_job.name)
            os.remove(f_plugin.name)
            logger.debug(f"Removed temporary job file {f_job.name}")
            logger.debug(f"Removed temporary plugin file {f_plugin.name}")


        proc.stdin.close()
        proc.stderr.close()

        output = proc.stdout.read()
        job_ids = []
        for line in output.decode("utf_8").split(os.linesep):
            if line.startswith("JobID"):
                job_ids.append(line.split("=")[1].strip())

        return min(job_ids)
