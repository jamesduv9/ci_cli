import logging
from pyats import aetest


class BGPPeerTest(aetest.Testcase):

    @aetest.setup
    def setup_test(self):
        for device in self.parameters.get('devices'):
            if not device.is_connected():
                logging.info(f"Connecting to device {device.name}")
                device.connect(log_stdout=False)

    @aetest.test
    def test_peers(self, steps):
        for device in self.parameters['devices']:
            with steps.start(f"Testing required BGP peers exist on - {device.name}", continue_=True) as substep:
                specified_vrf = self.parameters.get(
                    "test_params", {}).get("test_params", {}).get("vrf")
                expected_neighbors = self.parameters.get(
                    "test_params", {}).get("test_params", {}).get("neighbors")
                address_family = self.parameters.get("test_params", {}).get(
                    "test_params", {}).get("address_family")
                logging.info(f"Testing with specified VRF - {specified_vrf}")
                logging.info(
                    f"Testing with address family  - {address_family}")
                if not specified_vrf:
                    specified_vrf = "default"
                if not address_family:
                    address_family = "ipv4_unicast"
                if specified_vrf == "default" and address_family == "ipv4_unicast":
                    out = device.parse("show bgp summary")
                elif specified_vrf != "default" and address_family == "vpnv4_unicast":
                    out = device.parse(
                        f"show bgp vpnv4 unicast vrf {specified_vrf} summary")
                elif specified_vrf == "default" and address_family == "vpnv4_unicast":
                    out = device.parse(f"show bgp vpnv4 unicast all summary")
                for neighbor_ip, neighbor_values in out.get("vrf", {}).get(specified_vrf).get("neighbor").items():
                    if neighbor_ip in expected_neighbors:
                        with steps.start(f"Verifying {neighbor_ip} is up", continue_=True):
                            expected_neighbors.remove(neighbor_ip)
                            assert neighbor_values.get("address_family", {}).get(
                                "", {}).get("up_down") != "never"

                with substep.start(f"Validate all neighbors were found", continue_=True):
                    if expected_neighbors:
                        logging.error(
                            f"These neighbors were not found to be configured - {expected_neighbors}")
                    assert not expected_neighbors
