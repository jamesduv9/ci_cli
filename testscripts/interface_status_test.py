import logging
from pyats import aetest


class InterfaceStatusTest(aetest.Testcase):

    @aetest.setup
    def setup_test(self):
        """
        Connect if not already connected
        """
        for device in self.parameters.get('devices'):
            if not device.is_connected():
                logging.info(f"Connecting to device {device.name}")
                device.connect(log_stdout=False)

    @aetest.test
    def test_interface_status(self, steps):
        """
        Validate that the interfaces on specific devices are up/up
        primary target of these tests are logical p2p tunnels based on gre keepalives
        """
        for device in self.parameters.get('devices'):
            with steps.start(f"Testing interfaces on device {device.name}", continue_=True) as substep:
                out = device.parse("show ip interface brief")
                test_params = self.parameters.get("test_params").get("test_params")
                for interface in test_params.get("interfaces"):
                    conv_int = self.parameters.get("mapper").mapper(device_name=device.name, interface_name=interface)
                    with substep.start(f"Testing if interface {interface} (converted interface - {conv_int}) is up/up", continue_=True):
                        logging.info(f"testing interface {interface}")
                        current_int_state = out.get("interface", {}).get(conv_int, {})
                        assert current_int_state, f"Interface {conv_int} not found"
                        assert current_int_state.get("status") == "up", f"Interface {conv_int} line status is not up"
                        assert current_int_state.get("protocol") == "up", f"Interface {conv_int} protocol status is not up"
