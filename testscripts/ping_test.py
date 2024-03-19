import logging
from pyats import aetest
from unicon.core.errors import SubCommandFailure


class PingTest(aetest.Testcase):

    @aetest.setup
    def setup_test(self):
        """
        Connect if not already connected
        """
        for device in self.parameters.get('devices'):
            device.os = "iosxe"
            if not device.is_connected():
                
                logging.info(f"Connecting to device {device.name}")
                device.connect(log_stdout=False)

    @aetest.test
    def ping_test(self, steps):
        """
        Directly pass in the test params to the ping api, simply pass/fail
        """
        for device in self.parameters.get("devices"):
            test_params = self.parameters.get("test_params").get("test_params")
            mapper = self.parameters.get("mapper")
            with steps.start(f"Conducting ping tests from device {device}", continue_=True) as steps:
                for p_test in test_params.get("pings"):
                    if p_test.get("source"):
                        p_test["source"] = mapper.mapper(device.name, p_test["source"])
                    try:
                        device.ping(**p_test)
                    except SubCommandFailure:
                        self.failed(f"Unable to ping destination with params - {p_test}")