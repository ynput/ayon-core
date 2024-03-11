# Copyright Epic Games, Inc. All Rights Reserved

"""
Deadline Job object used to submit jobs to the render farm
"""

# Built-In
import logging

# Third-party
import unreal

# Internal
from deadline_utils import merge_dictionaries, get_deadline_info_from_preset

from deadline_enums import DeadlineJobStatus

logger = logging.getLogger("DeadlineJob")


class DeadlineJob:
    """ Unreal Deadline Job object """

    # ------------------------------------------------------------------------------------------------------------------
    # Magic Methods

    def __init__(self, job_info=None, plugin_info=None, job_preset: unreal.DeadlineJobPreset=None):
        """ Constructor """
        self._job_id = None
        self._job_info = {}
        self._plugin_info = {}
        self._aux_files = []
        self._job_status: DeadlineJobStatus = DeadlineJobStatus.UNKNOWN
        self._job_progress = 0.0

        # Jobs details updated by server after submission
        self._job_details = None

        # Update the job, plugin and aux file info from the data asset
        if job_info and plugin_info:
            self.job_info = job_info
            self.plugin_info = plugin_info

        if job_preset:
            self.job_info, self.plugin_info = get_deadline_info_from_preset(job_preset=job_preset)

    def __repr__(self):
        return f"{self.__class__.__name__}({self.job_name}, {self.job_id})"

    # ------------------------------------------------------------------------------------------------------------------
    # Public Properties

    @property
    def job_info(self):
        """
        Returns the Deadline job info
        :return: Deadline job Info as a dictionary
        :rtype: dict
        """
        return self._job_info

    @job_info.setter
    def job_info(self, value: dict):
        """
        Sets the Deadline Job Info
        :param value:  Value to set on the job info.
        """
        if not isinstance(value, dict):
            raise TypeError(f"Expected `dict` found {type(value)}")

        self._job_info = merge_dictionaries(self.job_info, value)

        if "AuxFiles" in self._job_info:
            # Set the auxiliary files for this instance
            self._aux_files = self._job_info.get("AuxFiles", [])

            # Remove the aux files array from the dictionary, doesn't belong there
            self._job_info.pop("AuxFiles")

    @property
    def plugin_info(self):
        """
        Returns the Deadline plugin info
        :return: Deadline plugin Info as a dictionary
        :rtype: dict
        """
        return self._plugin_info

    @plugin_info.setter
    def plugin_info(self, value: dict):
        """
        Sets the Deadline Plugin Info
        :param value: Value to set on plugin info.
        """
        if not isinstance(value, dict):
            raise TypeError(f"Expected `dict` found {type(value)}")

        self._plugin_info = merge_dictionaries(self.plugin_info, value)

    @property
    def job_id(self):
        """
        Return the deadline job ID. This is the ID returned by the service after the job has been submitted
        """
        return self._job_id

    @property
    def job_name(self):
        """
        Return the deadline job name.
        """
        return self.job_info.get("Name", "Unnamed Job")

    @job_name.setter
    def job_name(self, value):
        """
        Updates the job name on the instance. This also updates the job name in the job info dictionary
        :param str value: job name
        """
        self.job_info.update({"Name": value})

    @property
    def aux_files(self):
        """
        Returns the Auxiliary files for this job
        :return: List of Auxiliary files
        """
        return self._aux_files

    @property
    def job_status(self):
        """
        Return the current job status
        :return: Deadline status
        """

        if not self.job_details:
            return DeadlineJobStatus.UNKNOWN

        if "Job" not in self.job_details and "Status" not in self.job_details["Job"]:
            return DeadlineJobStatus.UNKNOWN

        # Some Job statuses are represented as "Rendering (1)" to indicate the
        # current status of the job and the number of tasks performing the
        # current status. We only care about the job status so strip out the
        # extra information. Task details are returned to the job details
        # object which can be queried in a different implementation
        return self.get_job_status_enum(self.job_details["Job"]["Status"].split()[0])

    @job_status.setter
    def job_status(self, value):
        """
        Return the current job status
        :param DeadlineJobStatus value: Job status to set on the object.
        :return: Deadline status
        """

        # Statuses are expected to live in the job details object. Usually this
        # property is only explicitly set if the status of a job is unknown.
        # for example if the service detects a queried job is non-existent on
        # the farm

        # NOTE: If the structure of how job status are represented in the job
        #  details changes, this implementation will need to be updated.
        #  Currently job statuses are represented in the jobs details as
        #  {"Job": {"Status": "Unknown"}}

        # "value" is expected to be an Enum so get the name of the Enum and set
        # it on the job details. When the status property is called,
        # this will be re-translated back into an enum. The reason for this is,
        # the native job details object returned from the service has no
        # concept of the job status enum. This is an internal
        # representation which allows for more robust comparison operator logic
        if self.job_details and isinstance(self.job_details, dict):
            self.job_details.update({"Job": {"Status": value.name}})

    @property
    def job_progress(self):
        """
        Returns the current job progress
        :return: Deadline job progress as a float value
        """

        if not self.job_details:
            return 0.0

        if "Job" in self.job_details and "Progress" in self.job_details["Job"]:
            progress_str = self._job_details["Job"]["Progress"]
            progress_str = progress_str.split()[0]

            return float(progress_str) / 100  # 0-1 progress

    @property
    def job_details(self):
        """
        Returns the job details from the deadline service.
        :return: Deadline Job details
        """
        return self._job_details

    @job_details.setter
    def job_details(self, value):
        """
        Sets the job details from the deadline service. This is typically set
        by the service, but can be used as a general container for job
        information.
        """
        self._job_details = value

    # ------------------------------------------------------------------------------------------------------------------
    # Public Methods

    def get_submission_data(self):
        """
        Returns the submission data used by the Deadline service to submit a job
        :return: Dictionary with job, plugin, auxiliary info
        :rtype: dict
        """
        return {
            "JobInfo": self.job_info,
            "PluginInfo": self.plugin_info,
            "AuxFiles": self.aux_files
        }

    # ------------------------------------------------------------------------------------------------------------------
    # Protected Methods

    @staticmethod
    def get_job_status_enum(job_status):
        """
        This method returns an enum representing the job status from the server
        :param job_status: Deadline job status
        :return: Returns the job_status as an  enum
        :rtype DeadlineJobStatus
        """
        # Convert this job status returned by the server into the job status
        # enum representation

        # Check if the job status name has an enum representation, if not check
        # the value of the job_status.
        # Reference: https://docs.thinkboxsoftware.com/products/deadline/10.1/1_User%20Manual/manual/rest-jobs.html#job-property-values
        try:
            status = DeadlineJobStatus(job_status)
        except ValueError:
            try:
                status = getattr(DeadlineJobStatus, job_status)
            except Exception as exp:
                raise RuntimeError(f"An error occurred getting the Enum status type of {job_status}. Error: \n\t{exp}")

        return status
