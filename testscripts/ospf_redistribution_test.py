import logging
from pyats import aetest


class OSPFRIBTest(aetest.Testcase):

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
    def ospf_db_test(self, steps):
        """
        Test ospf db for specific values
        """
        for device in self.parameters.get("devices"):
            test_params = self.parameters.get("test_params").get("test_params")
            with steps.start(f"Testing OSPF DB of device {device}", continue_=True) as steps:
                out = device.parse("show ip ospf rib redistribution")
                logging.info(out)
                tested_instances = [int(network['process_id']) for network in test_params.get("ospf_processes")]
                logging.info(f"testing instances.. {tested_instances}")
                for instance in tested_instances:
                    with steps.start(f"Testing instance - {instance} for redistributed routes", continue_=True) as substep:
                        current_instance_networks = out.get("instance", {}).get(instance, {}).get("network", {})
                        assert current_instance_networks, f"Instance {instance} is not redistributing any routes"
                        tested_networks = [test_instance.get("networks") for test_instance in test_params.get("ospf_processes") if int(test_instance.get("process_id")) == instance][0]
                        assert tested_networks, "No networks found to test"
                        logging.info(f"testable routes.. {tested_networks}")
                        for tested_network in tested_networks:
                            logging.info(f"tested_network - {tested_network}")
                            with substep.start(f"Testing network - {tested_network.get('network')} against current network state", continue_=True) as subsubstep:
                                assert tested_network.get("network") in current_instance_networks.keys()
                                if tested_network.get("origin_protocol"):
                                    with subsubstep.start(f"Testing network - {tested_network.get('network')} origin protocol matches expected protocol", continue_=True):
                                        #Sometimes the origin value is a unformatted string like - "origin": "BGP Router 65222 (MPLS VPN)"
                                        #Just doing a loose validation of protocol name vs live device origin
                                        assert tested_network.get("origin_protocol").lower() in current_instance_networks.get(tested_network.get("network")).get("origin").lower(), "Origin protocol provided is not the origin of the redistribution"