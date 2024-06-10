# Copyright Epic Games, Inc. All Rights Reserved

"""
Thinkbox Deadline REST API service plugin used to submit and query jobs from a Deadline server
"""

# Built-in
import json
import logging
import platform

from getpass import getuser
from threading import Thread, Event

# Internal
from deadline_job import DeadlineJob
from deadline_http import DeadlineHttp
from deadline_enums import DeadlineJobState, DeadlineJobStatus, HttpRequestType
from deadline_utils import get_editor_deadline_globals
from deadline_command import DeadlineCommand

# Third-party
import unreal

logger = logging.getLogger("DeadlineService")
logger.setLevel(logging.INFO)


class _Singleton(type):
    """
    Singleton metaclass for the Deadline service
    """
    # ------------------------------------------------------------------------------------------------------------------
    # Class Variables

    _instances = {}

    # ------------------------------------------------------------------------------------------------------------------
    # Magic Methods

    def __call__(cls, *args, **kwargs):
        """
        Determines the initialization behavior of this class
        """
        if cls not in cls._instances:
            cls._instances[cls] = super(_Singleton, cls).__call__(*args, **kwargs)

        return cls._instances[cls]


# TODO: Make this a native Subsystem in the editor
class DeadlineService(metaclass=_Singleton):
    """
    Singleton class to handle Deadline submissions.
    We are using a singleton class as there is no need to have multiple instances of the service. This allows job
    queries and submissions to be tracked by a single entity and be a source of truth on the client about all jobs
    created in the current session.
    """

    # ------------------------------------------------------------------------------------------------------------------
    # Magic Methods

    def __init__(self, host=None, auto_start_job_updates=False, service_update_interval=1.0):
        """
        Deadline service class for submitting jobs to deadline and querying data from deadline
        :param str host: Deadline host
        :param bool auto_start_job_updates: This flag auto starts processing jobs when the service is initialized
            tracked by the service
        :param float service_update_interval: Interval(seconds) for job update frequency. Default is 2.0 seconds
        """

        # Track a dictionary of jobs registered with the service. This dictionary contains job object instance ID and a
        # reference to the job instance object and deadline job ID.
        # i.e {"instance_object_id": {"object": <job class instance>, "job_id": 0001 or None}}
        self._current_jobs = {}
        self._submitted_jobs = {} # Similar to the current jobs, this tracks all jobs submitted
        self._failed_jobs = set()
        self._completed_jobs = set()

        # This flag determines if the service should deregister a job when it fails on the server
        self.deregister_job_on_failure = True

        # Thread execution variables
        self._event_thread = None
        self._exit_auto_update = False
        self._update_thread_event = Event()

        self._service_update_interval = service_update_interval

        # A timer for executing job update functions on an interval
        self._event_timer_manager = self.get_event_manager()
        self._event_handler = None

        # Use DeadlineCommand by defaut
        self._use_deadline_command = self._get_use_deadline_cmd() # True  # TODO: hardcoded for testing, change to project read setting

        # Get/Set service host
        self._host = host or self._get_deadline_host()

        # Get deadline https instance
        self._http_server = DeadlineHttp(self.host)

        if auto_start_job_updates:
            self.start_job_updates()

    # ------------------------------------------------------------------------------------------------------------------
    # Public Properties

    @property
    def pools(self):
        """
        Returns the current list of pools found on the server
        :return: List of pools on the server
        """
        return self._get_pools()

    @property
    def groups(self):
        """
        Returns the current list of groups found on the server
        :return: List of groups  on the server
        """
        return self._get_groups()

    @property
    def use_deadline_command(self):
        """
        Returns the current value of the use deadline command flag
        :return: True if the service uses the deadline command, False otherwise
        """
        return self._use_deadline_command

    @use_deadline_command.setter
    def use_deadline_command(self, value):
        """
        Sets the use deadline command flag
        :param value: True if the service uses the deadline command, False otherwise
        """
        self._use_deadline_command = value

    @property
    def host(self):
        """
        Returns the server url used by the service
        :return: Service url
        """
        return self._host

    @host.setter
    def host(self, value):
        """
        Set the server host on the service
        :param value: host value
        """
        self._host = value

        # When the host service is updated, get a new connection to that host
        self._http_server = DeadlineHttp(self._host)

    @property
    def current_jobs(self):
        """
        Returns the global current jobs tracked by the service
        :return: List of Jobs tracked by the service
        """
        return [value["object"] for value in self._current_jobs.values()]

    @property
    def failed_jobs(self):
        """
        Returns the failed jobs tracked by the service
        :return: List of failed Jobs tracked by the service
        """
        return self._failed_jobs

    @property
    def completed_jobs(self):
        """
        Returns the completed jobs tracked by the service
        :return: List of completed Jobs tracked by the service
        """
        return self._completed_jobs

    # ------------------------------------------------------------------------------------------------------------------
    # Protected Methods

    def _get_pools(self):
        """
        This method updates the set of pools tracked by the service
        """
        if self._get_use_deadline_cmd(): # if self._use_deadline_command:
            return DeadlineCommand().get_pools()
        else:
            response = self.send_http_request(
                HttpRequestType.GET,
                "api/pools",
                headers={'Content-Type': 'application/json'}
            )
            return json.loads(response.decode('utf-8'))

    def _get_groups(self):
        """
        This method updates the set of groups tracked by the service
        """
        if self._get_use_deadline_cmd(): # if self._use_deadline_command:
            return DeadlineCommand().get_groups()
        else:
            response = self.send_http_request(
                HttpRequestType.GET,
                "api/groups",
                headers={'Content-Type': 'application/json'}
            )
            return json.loads(response.decode('utf-8'))

    def _register_job(self, job_object, deadline_job_id=None):
        """
        This method registers the job object with the service
        :param DeadlineJob job_object: Deadline Job object
        :param str deadline_job_id: ID of job returned from the server
        """

        # Set the job Id on the job. The service
        # should be allowed to set this protected property on the job object as this property should natively
        # not be allowed to be set externally
        job_object._job_id = deadline_job_id

        job_data = {
            str(id(job_object)):
                {
                    "object": job_object,
                    "job_id": deadline_job_id
                }
        }

        self._submitted_jobs.update(job_data)
        self._current_jobs.update(job_data)

    def _deregister_job(self, job_object):
        """
        This method removes the current job object from the tracked jobs
        :param DeadlineJob job_object: Deadline job object
        """

        if str(id(job_object)) in self._current_jobs:
            self._current_jobs.pop(str(id(job_object)), f"{job_object} could not be found")

    def _update_tracked_job_by_status(self, job_object, job_status, update_job=False):
        """
        This method moves the job object from the tracked list based on the current job status
        :param DeadlineJob job_object: Deadline job object
        :param DeadlineJobStatus job_status: Deadline job status
        :param bool update_job: Flag to update the job object's status to the passed in job status
        """

        # Convert the job status into the appropriate enum. This will raise an error if the status enum does not exist.
        # If a valid enum is passed into this function, the enum is return
        job_status = job_object.get_job_status_enum(job_status)

        # If the job has an unknown status, remove it from the currently tracked jobs by the service. Note we are not
        # de-registering failed jobs unless explicitly set, that's because a failed job can be re-queued and
        # completed on the next try.
        # So we do not want to preemptively remove this job from the tracked jobs by the service.
        if job_status is DeadlineJobStatus.UNKNOWN:
            self._deregister_job(job_object)
            self._failed_jobs.add(job_object)

        elif job_status is DeadlineJobStatus.COMPLETED:
            self._deregister_job(job_object)
            self._completed_jobs.add(job_object)

        elif job_status is DeadlineJobStatus.FAILED:
            if self.deregister_job_on_failure:
                self._deregister_job(job_object)
                self._failed_jobs.add(job_object)

        if update_job:
            job_object.job_status = job_status

    # ------------------------------------------------------------------------------------------------------------------
    # Public Methods

    def send_http_request(self, request_type, api_url, payload=None, fields=None, headers=None, retries=0):
        """
        This method is used to upload or receive data from the Deadline server.
        :param HttpRequestType request_type: HTTP request verb. i.e GET/POST/PUT/DELETE
        :param str api_url: URL relative path queries. Example: /jobs , /pools, /jobs?JobID=0000
        :param payload: Data object to POST/PUT to Deadline server
        :param dict fields: Request fields. This is typically used in files and binary uploads
        :param dict headers: Header data for request
        :param int retries: The number of retries to attempt before failing request. Defaults to 0.
        :return: JSON object response from the server
        """

        # Make sure we always have the most up-to-date host
        if not self.host or (self.host != self._get_deadline_host()):
            self.host = self._get_deadline_host()

        try:
            response = self._http_server.send_http_request(
                request_type,
                api_url,
                payload=payload,
                fields=fields,
                headers=headers,
                retries=retries
            )

        except Exception as err:
            raise DeadlineServiceError(f"Communication with {self.host} failed with err: \n{err}")
        else:
            return response

    def submit_job(self, job_object):
        """
        This method submits the tracked job to the Deadline server
        :param DeadlineJob job_object: Deadline Job object
        :returns: Deadline `JobID` if an id was returned from the server
        """
        self._validate_job_object(job_object)

        logger.debug(f"Submitting {job_object} to {self.host}..")

        if str(id(job_object)) in self._current_jobs:
            logger.warning(f"{job_object} has already been added to the service")

            # Return the job ID of the submitted job
            return job_object.job_id

        job_id = None

        job_data = job_object.get_submission_data()

        # Set the job data to return the job ID on submission
        job_data.update(IdOnly="true")

        # Update the job data to include the user and machine submitting the job
        # Update the username if one is not supplied
        if "UserName" not in job_data["JobInfo"]:

            # NOTE: Make sure this matches the expected naming convention by the server else the user will get
            #  permission errors on job submission
            # Todo: Make sure the username convention matches the username on the server
            job_data["JobInfo"].update(UserName=getuser())

        job_data["JobInfo"].update(MachineName=platform.node())

        self._validate_job_info(job_data["JobInfo"])

        if self._get_use_deadline_cmd(): # if self._use_deadline_command:
            # Submit the job to the Deadline server using the Deadline command
            # Todo: Add support for the Deadline command
            job_id = DeadlineCommand().submit_job(job_data)

        else:
            # Submit the job to the Deadline server using the HTTP API
            try:
                response = self.send_http_request(
                    HttpRequestType.POST,
                    "api/jobs",
                    payload=json.dumps(job_data).encode('utf-8'),
                    headers={'Content-Type': 'application/json'}
                )

            except DeadlineServiceError as exp:
                logger.error(
                    f"An error occurred submitting {job_object} to Deadline host `{self.host}`.\n\t{str(exp)}"
                )
                self._failed_jobs.add(job_object)

            else:
                try:
                    response = json.loads(response.decode('utf-8'))

                # If an error occurs trying to decode the json data, most likely an error occurred server side thereby
                # returning a string instead of the data requested.
                # Raise the decoded error
                except Exception as err:
                    raise DeadlineServiceError(f"An error occurred getting the server data:\n\t{response.decode('utf-8')}")

                job_id = response.get('_id', None)
            if not job_id:
                logger.warning(
                    f"No JobId was returned from the server for {job_object}. "
                    f"The service will not be able to get job details for this job!"
                )
            else:
                # Register the job with the service.
                self._register_job(job_object, job_id)

            logger.info(f"Submitted `{job_object.job_name}` to Deadline. JobID: {job_id}")

        return job_id

    def get_job_details(self, job_object):
        """
        This method gets the job details for the Deadline job
        :param DeadlineJob job_object: Custom Deadline job object
        :return: Job details object returned from the server. Usually a Json object
        """

        self._validate_job_object(job_object)

        if str(id(job_object)) not in self._current_jobs:
            logger.warning(
                f"{job_object} is currently not tracked by the service. The job has either not been submitted, "
                f"its already completed or there was a problem with the job!"
            )
        elif not job_object.job_id:
            logger.error(
                f"There is no JobID for {job_object}!"
            )
        else:

            try:
                job_details = self._http_server.get_job_details(job_object.job_id)

            except (Exception, RuntimeError):
                # If an error occurred, most likely the job does not exist on the server anymore. Mark the job as
                # unknown
                self._update_tracked_job_by_status(job_object, DeadlineJobStatus.UNKNOWN, update_job=True)
            else:
                # Sometimes Deadline returns a status with a parenthesis after the status indicating the number of tasks
                # executing. We only care about the status here so lets split the number of tasks out.
                self._update_tracked_job_by_status(job_object, job_details["Job"]["Status"].split()[0])
                return job_details

    def send_job_command(self, job_object, command):
        """
        Send a command to the Deadline server for the job
        :param DeadlineJob job_object: Deadline job object
        :param dict command: Command to send to the Deadline server
        :return: Returns the response from the server
        """
        self._validate_job_object(job_object)

        if not job_object.job_id:
            raise RuntimeError("There is no Deadline job ID to send this command for.")

        try:
            response = self._http_server.send_job_command(
                job_object.job_id,
                command
            )
        except Exception as exp:
            logger.error(
                f"An error occurred getting the command result for {job_object} from Deadline host {self.host}. "
                f"\n{exp}"
            )
            return "Fail"
        else:
            if response != "Success":
                logger.error(f"An error occurred executing command for {job_object}. \nError: {response}")
                return "Fail"

            return response

    def change_job_state(self, job_object, state):
        """
        This modifies a submitted job's state on the Deadline server. This can be used in job orchestration. For example
        a job can be submitted as suspended/pending and this command can be used to update the state of the job to
        active after submission.
        :param DeadlineJob job_object: Deadline job object
        :param DeadlineJobState state: State to set the job
        :return: Submission results
        """

        self._validate_job_object(job_object)

        # Validate jobs state
        if not isinstance(state, DeadlineJobState):
            raise ValueError(f"`{state}` is not a valid state.")

        return self.send_job_command(job_object, {"Command": state.value})

    def start_job_updates(self):
        """
        This method starts an auto update on jobs in the service.

        The purpose of this system is to allow the service to automatically update the job details from the server.
        This allows you to submit a job from your implementation and periodically poll the changes on the job as the
        service will continuously update the job details.
        Note: This function must explicitly be called or the `auto_start_job_updates` flag must be passed to the service
        instance for this functionality to happen.
        """
        # Prevent the event from being executed several times in succession
        if not self._event_handler:
            if not self._event_thread:

                # Create a thread for the job update function. This function takes the current list of jobs
                # tracked by the service. The Thread owns an instance of the http connection. This allows the thread
                # to have its own pool of http connections separate from the main service. A thread event is passed
                # into the thread which allows the process events from the timer to reactivate the function. The
                # purpose of this is to prevent unnecessary re-execution while jobs are being processed.
                # This also allows the main service to stop function execution within the thread and allow it to cleanly
                # exit.

                # HACK: For some odd reason, passing an instance of the service into the thread seems to work as
                # opposed to passing in explicit variables. I would prefer explicit variables as the thread does not
                # need to have access to the entire service object

                # Threading is used here as the editor runs python on the game thread. If a function call is
                # executed on an interval (as this part of the service is designed to do), this will halt the editor
                # every n interval to process the update event. A separate thread for processing events allows the
                # editor to continue functions without interfering with the editor

                # TODO: Figure out a way to have updated variables in the thread vs passing the whole service instance
                self._event_thread = Thread(
                    target=self._update_all_jobs,
                    args=(self,),
                    name="deadline_service_auto_update_thread",
                    daemon=True
                )

                # Start the thread
                self._event_thread.start()

            else:
                # If the thread is stopped, restart it.
                if not self._event_thread.is_alive():
                    self._event_thread.start()

            def process_events():
                """
                Function ran by the tick event for monitoring function execution inside of the auto update thread.
                """
                # Since the editor ticks at a high rate, this monitors the current state of the function execution in
                # the update thread. When a function is done executing, this resets the event on the function.
                logger.debug("Processing current jobs.")
                if self._update_thread_event.is_set():

                    logger.debug("Job processing complete, restarting..")
                    # Send an event to tell the thread to start the job processing loop
                    self._update_thread_event.clear()

            # Attach the thread executions to a timer event
            self._event_timer_manager.on_timer_interval_delegate.add_callable(process_events)

            # Start the timer on an interval
            self._event_handler = self._event_timer_manager.start_timer(self._service_update_interval)

            # Allow the thread to stop when a python shutdown is detected
            unreal.register_python_shutdown_callback(self.stop_job_updates)

    def stop_job_updates(self):
        """
        This method stops the auto update thread. This method should be explicitly called to stop the service from
        continuously updating the current tracked jobs.
        """
        if self._event_handler:

            # Remove the event handle to the tick event
            self.stop_function_timer(self._event_timer_manager, self._event_handler)
            self._event_handler = None

            if self._event_thread and self._event_thread.is_alive():
                # Force stop the thread
                self._exit_auto_update = True

                # immediately stop the thread. Do not wait for jobs to complete.
                self._event_thread.join(1.0)

                # Usually if a thread is still alive after a timeout, then something went wrong
                if self._event_thread.is_alive():
                    logger.error("An error occurred closing the auto update Thread!")

                # Reset the event, thread and tick handler
                self._update_thread_event.set()
                self._event_thread = None

    def get_job_object_by_job_id(self, job_id):
        """
        This method returns the job object tracked by the service based on the deadline job ID
        :param job_id: Deadline job ID
        :return: DeadlineJob object
        :rtype DeadlineJob
        """

        job_object = None

        for job in self._submitted_jobs.values():
            if job_id == job["job_id"]:
                job_object = job["object"]
                break

        return job_object

    # ------------------------------------------------------------------------------------------------------------------
    # Static Methods

    @staticmethod
    def _validate_job_info(job_info):
        """
        This method validates the job info dictionary to make sure
        the information provided meets a specific standard
        :param dict job_info: Deadline job info dictionary
        :raises ValueError
        """

        # validate the job info plugin settings
        if "Plugin" not in job_info or (not job_info["Plugin"]):
            raise ValueError("No plugin was specified in the Job info dictionary")

    @staticmethod
    def _get_use_deadline_cmd():
        """
        Returns the deadline command flag settings from the unreal project settings
        :return: Deadline command settings unreal project
        """
        try:
            # This will be set on the deadline editor project settings
            deadline_settings = unreal.get_default_object(unreal.DeadlineServiceEditorSettings)

        # Catch any other general exceptions
        except Exception as exc:
            unreal.log(
                f"Caught Exception while getting use deadline command flag. Error: {exc}"
            )

        else:
            return deadline_settings.deadline_command
    
    @staticmethod
    def _get_deadline_host():
        """
        Returns the host settings from the unreal project settings
        :return: Deadline host settings unreal project
        """
        try:
            # This will be set on the deadline editor project settings
            deadline_settings = unreal.get_default_object(unreal.DeadlineServiceEditorSettings)

        # Catch any other general exceptions
        except Exception as exc:
            unreal.log(
                f"Caught Exception while getting deadline host. Error: {exc}"
            )

        else:
            return deadline_settings.deadline_host

    @staticmethod
    def _validate_job_object(job_object):
        """
        This method ensures the object passed in is of type DeadlineJob
        :param DeadlineJob job_object: Python object
        :raises: RuntimeError if the job object is not of type DeadlineJob
        """
        # Using type checking instead of isinstance to prevent cyclical imports
        if not isinstance(job_object, DeadlineJob):
            raise DeadlineServiceError(f"Job is not of type DeadlineJob. Found {type(job_object)}!")

    @staticmethod
    def _update_all_jobs(service):
        """
        This method updates current running job properties in a thread.
        :param DeadlineService service: Deadline service instance
        """
        # Get a Deadline http instance inside for this function. This function is expected to be executed in a thread.
        deadline_http = DeadlineHttp(service.host)

        while not service._exit_auto_update:

            while not service._update_thread_event.is_set():

                # Execute the job update properties on the job object
                for job_object in service.current_jobs:

                    logger.debug(f"Updating {job_object} job properties")

                    # Get the job details for this job and update the job details on the job object. The service
                    # should be allowed to set this protected property on the job object as this property should
                    # natively not be allowed to be set externally
                    try:
                        if job_object.job_id:
                            job_object.job_details = deadline_http.get_job_details(job_object.job_id)

                    # If a job fails to get job details, log it, mark it unknown
                    except Exception as err:
                        logger.exception(f"An error occurred getting job details for {job_object}:\n\t{err}")
                        service._update_tracked_job_by_status(
                            job_object,
                            DeadlineJobStatus.UNKNOWN,
                            update_job=True
                        )

                # Iterate over the jobs and update the tracked jobs by the service
                for job in service.current_jobs:
                    service._update_tracked_job_by_status(job, job.job_status)

                service._update_thread_event.set()

    @staticmethod
    def get_event_manager():
        """
        Returns an instance of an event timer manager
        """
        return unreal.DeadlineServiceTimerManager()

    @staticmethod
    def start_function_timer(event_manager, function, interval_in_seconds=2.0):
        """
        Start a timer on a function within an interval
        :param unreal.DeadlineServiceTimerManager event_manager: Unreal Deadline service timer manager
        :param object function: Function to execute
        :param float interval_in_seconds: Interval in seconds between function execution. Default is 2.0 seconds
        :return: Event timer handle
        """
        if not isinstance(event_manager, unreal.DeadlineServiceTimerManager):
            raise TypeError(
                f"The event manager is not of type `unreal.DeadlineServiceTimerManager`. Got {type(event_manager)}"
            )

        event_manager.on_timer_interval_delegate.add_callable(function)

        return event_manager.start_timer(interval_in_seconds)

    @staticmethod
    def stop_function_timer(event_manager, time_handle):
        """
        Stops the timer event
        :param unreal.DeadlineServiceTimerManager event_manager: Service Event manager
        :param time_handle: Time handle returned from the event manager
        """
        event_manager.stop_timer(time_handle)


class DeadlineServiceError(Exception):
    """
    General Exception class for the Deadline Service
    """
    pass


def get_global_deadline_service_instance():
    """
    This method returns an instance of the service from
    the interpreter globals.
    :return:
    """
    # This behavior is a result of unreal classes not able to store python object
    # directly on the class due to limitations in the reflection system.
    # The expectation is that uclass's that may not be able to store the service
    # as a persistent attribute on a class can use the global service instance.

    # BEWARE!!!!
    # Due to the nature of the DeadlineService being a singleton, if you get the
    # current instance and change the host path for the service, the connection will
    # change for every other implementation that uses this service

    deadline_globals = get_editor_deadline_globals()

    if '__deadline_service_instance__' not in deadline_globals:
        deadline_globals["__deadline_service_instance__"] = DeadlineService()

    return deadline_globals["__deadline_service_instance__"]
