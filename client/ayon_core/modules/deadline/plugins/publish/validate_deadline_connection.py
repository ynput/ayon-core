import pyblish.api

from ayon_core.pipeline import PublishXmlValidationError

from openpype_modules.deadline.abstract_submit_deadline import requests_get


class ValidateDeadlineConnection(pyblish.api.InstancePlugin):
    """Validate Deadline Web Service is running"""

    label = "Validate Deadline Web Service"
    order = pyblish.api.ValidatorOrder
    hosts = ["maya", "nuke"]
    families = ["renderlayer", "render"]

    # cache
    responses = {}

    def process(self, instance):
        context = instance.context
        # get default deadline webservice url from deadline module
        deadline_url = context.data["defaultDeadline"]
        # if custom one is set in instance, use that
        if instance.data.get("deadlineUrl"):
            deadline_url = instance.data.get("deadlineUrl")
            self.log.debug(
                "We have deadline URL on instance {}".format(deadline_url)
            )
        assert deadline_url, "Requires Deadline Webservice URL"

        kwargs = {}
        if context.data["deadline_require_authentication"]:
            kwargs["auth"] = context.data["deadline_auth"]

            if not context.data["deadline_auth"][0]:
                raise PublishXmlValidationError(
                    self,
                    "Deadline requires authentication. "
                    "At least username is required to be set in "
                    "Site Settings.")

        if deadline_url not in self.responses:
            self.responses[deadline_url] = requests_get(deadline_url, **kwargs)

        response = self.responses[deadline_url]
        if response.status_code == 401:
            raise PublishXmlValidationError(
                self,
                "Deadline requires authentication. "
                "Provided credentials are not working. "
                "Please change them in Site Settings")
        assert response.ok, "Response must be ok"
        assert response.text.startswith("Deadline Web Service "), (
            "Web service did not respond with 'Deadline Web Service'"
        )
