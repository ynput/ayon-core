import pyblish.api

from ayon_core.pipeline import PublishXmlValidationError

from ayon_deadline.abstract_submit_deadline import requests_get


class ValidateDeadlineConnection(pyblish.api.InstancePlugin):
    """Validate Deadline Web Service is running"""

    label = "Validate Deadline Web Service"
    order = pyblish.api.ValidatorOrder
    hosts = ["maya", "nuke", "aftereffects", "harmony", "fusion"]
    families = ["renderlayer", "render", "render.farm"]

    # cache
    responses = {}

    def process(self, instance):
        if not instance.data.get("farm"):
            self.log.debug("Should not be processed on farm, skipping.")
            return

        deadline_url = instance.data["deadline"]["url"]
        assert deadline_url, "Requires Deadline Webservice URL"

        kwargs = {}
        if instance.data["deadline"]["require_authentication"]:
            auth = instance.data["deadline"]["auth"]
            kwargs["auth"] = auth

            if not auth[0]:
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
