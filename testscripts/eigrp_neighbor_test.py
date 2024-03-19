import logging
from pyats import aetest


class EigrpNeighborTest(aetest.Testcase):

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
    def test_neighbors(self, steps):
        """
        Iterate through all devices
        Run eigrp neighbor command collect output as json
        validate neighbors exist and health
        """
        for device in self.parameters['devices']:
            with steps.start(f"Testing required EIGRP neighbors exist on - {device.name}", continue_=True) as substep:
                test_params = self.parameters.get("test_params").get("test_params")
                as_number = test_params.get("as")
                vrf = test_params.get("vrf", "default")
                if not vrf:
                    vrf = "default"
                if vrf != "default":
                    logging.info(f"Not using default VRF, using vrf {vrf} instead")
                    out = device.parse(f"show ip eigrp vrf {vrf} neighbors")
                else:
                    logging.info(f"Using default vrf")
                    out = device.parse(f"show ip eigrp neighbors")
                eigrp_interfaces = out.get("eigrp_instance", {}).get(str(as_number)).get("vrf").get(vrf).get("address_family").get("ipv4").get("eigrp_interface")
                for neighbor in test_params.get("neighbors"):
                    with substep.start(f"Testing neighbor {neighbor.get('address', 'Missing IP')} exists and up", continue_=True):
                        #Does the neighbor's interface exist?
                        neighbor_int = self.parameters["mapper"].mapper(device.name, neighbor.get("interface"))
                        logging.info(f"Interface converted to - {neighbor_int}")
                        assert neighbor_int in eigrp_interfaces.keys()
                        #Does the address of the neighbor match the interface?
                        assert neighbor.get("address") in eigrp_interfaces.get(neighbor_int).get("eigrp_nbr").keys()
                    with substep.start(f"Testing neighbor {neighbor.get('address', 'Missing IP')} Q count", continue_=True):
                        assert int(eigrp_interfaces.get(neighbor_int).get("eigrp_nbr").get(neighbor.get("address")).get("q_cnt")) == 0
