# Copyright Epic Games, Inc. All Rights Reserved

# Built-In
import logging
import json
logger = logging.getLogger("DeadlineHTTP")
try:
    # Third-party
    from urllib.parse import urljoin
    from urllib3 import PoolManager
    from urllib3.exceptions import HTTPError
except ImportError:
    logger.info("module 'urllib3' not found")
# Internal
from deadline_enums import HttpRequestType




class DeadlineHttp:
    """
    Class to send requests to deadline server
    """

    # ------------------------------------------------------------------------------------------------------------------
    # Magic Methods

    def __init__(self, host):
        """
        Constructor
        :param str host: Deadline server host
        """
        self.host = host
        

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
        :return: JSON object response from the server.
        """
        self._http_manager = PoolManager(cert_reqs='CERT_NONE')   # Disable SSL certificate check
        # Validate request type
        if not isinstance(request_type, HttpRequestType):
            raise ValueError(f"Request type must be of type {type(HttpRequestType)}")

        response = self._http_manager.request(
            request_type.value,
            urljoin(self.host, api_url),
            body=payload,
            fields=fields,
            headers=headers,
            retries=retries
        )

        return response.data

    def get_job_details(self, job_id):
        """
        This method gets the job details for the deadline job
        :param str job_id: Deadline JobID
        :return: Job details object returned from the server. Usually a Json object
        """

        if not job_id:
            raise ValueError(f"A JobID is required to get job details from Deadline. Got {job_id}.")

        api_query_string = f"api/jobs?JobID={job_id}&Details=true"

        job_details = self.send_http_request(
            HttpRequestType.GET,
            api_query_string
        )

        try:
            job_details = json.loads(job_details.decode('utf-8'))[job_id]

        # If an error occurs trying to decode the json data, most likely an error occurred server side thereby
        # returning a string instead of the data requested.
        # Raise the decoded error
        except Exception as err:
            raise RuntimeError(
                f"An error occurred getting the server data for {job_id}: \n{job_details.decode('utf-8')}"
            )
        else:
            return job_details

    def send_job_command(self, job_id, command):
        """
        Send a command to the Deadline server for the job
        :param str job_id: Deadline JobID
        :param dict command: Command to send to the deadline server
        :return: Returns the response from the server
        """
        api_string = urljoin(self.host, "/api/jobs")

        if not job_id:
            raise RuntimeError("There is no deadline job ID to send this command for.")

        # Add the job id to the command dictionary
        command.update(JobID=job_id)

        response = self.send_http_request(
            HttpRequestType.PUT,
            api_string,
            payload=json.dumps(command).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )

        return response.decode('utf-8')
