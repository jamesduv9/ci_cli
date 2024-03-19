import logging
from ntc_templates.parse import parse_output
from pyats import aetest


class OSPFNeighborTest(aetest.Testcase):

    @aetest.setup
    def setup_test(self):
        for device in self.parameters.get('devices'):
            if not device.is_connected():
                logging.info(f"Connecting to device {device.name}")
                device.connect(log_stdout=False)

    @aetest.test
    def test_neighbors(self, steps):
        for device in self.parameters['devices']:
            with steps.start(f"Testing required OSPF neighbors exist on - {device.name}", continue_=True) as substep:
                test_params = self.parameters.get("test_params").get("test_params")
                out = device.execute("show ip ospf neighbor")
                out = parse_output(platform="cisco_ios",
                                   command="show ip ospf neighbor", data=out)

                for neighbor_ip in test_params.get("neighbors"):
                    with substep.start(f"Testing {neighbor_ip} exists and in FULL state", continue_=True):
                        correct_neighbor = [neigh for neigh in out if neigh.get("ip_address") == neighbor_ip]
                        assert correct_neighbor
                        correct_neighbor = correct_neighbor[0]
                        assert correct_neighbor.get("state").split("/")[0] == "FULL"

