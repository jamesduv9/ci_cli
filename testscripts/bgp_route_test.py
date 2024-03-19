import logging
from pyats import aetest


class BGPRouteTest(aetest.Testcase):

    @aetest.setup
    def setup_test(self):
        """
        Connect if not already connected
        """
        for device in self.parameters.get('devices'):
            #While I don't like this solution it seems to be the best way to unlock more parsers natively
            device.os = "iosxe"
            if not device.is_connected():
                logging.info(f"Connecting to device {device.name}")
                device.connect(log_stdout=False)

    @aetest.test
    def test_bgp_routes(self, steps):
        """
        Iterate through all devices and verify that the BGP routes for a specific NLRI match the expected attributes.
        """
        for device in self.parameters['devices']:
            with steps.start(f"Testing BGP routes on {device.name}", continue_=True) as substep:

                test_params = self.parameters.get("test_params").get("test_params")
                vrf = test_params.get("vrf")
                if not vrf:
                    vrf = "default"
                out = device.parse(f"sho bgp vpnv4 unicast vrf {vrf}") if vrf != "default" else device.parse("show ip bgp")
                logging.info(out)
                if not vrf or vrf == "default":
                    prefixes = out.get("vrf").get(vrf).get("address_family").get("").get("routes")
                else:
                    prefixes = out.get("vrf").get(vrf).get("address_family").get(f"vpnv4 unicast RD {test_params.get('rd')}").get("routes")


                for route in test_params.get("routes"):
                    network = route.get("network")
                    with substep.start(f"Testing route {network}", continue_=True) as subsubstep:
                        assert network in prefixes, f"Route {network} not found in BGP table"
                        route_details = prefixes[network]

                        # Check if the route appears the expected number of times
                        test_route_count = sum(1 for r in test_params.get("routes") if r.get("network") == network)

                        real_route_count = len(prefixes.get(route.get("network")).get("index").keys())
                        with subsubstep.start(f"Assert route {network} appears the expected number of times", continue_=True):
                            assert test_route_count == real_route_count, f"Mismatch in route count for {network}: expected {test_route_count}, found {real_route_count}"

                        # Check other attributes like metric and localpref
                        for _, details in route_details.get("index").items():
                            if "next_hop" in route and route.get("next_hop") == details.get("next_hop"):
                                logging.info(f"Found real route cooresponding with - {route}")
                                if "metric" in route and route["metric"] is not None and details.get("metric"):
                                    real_metric = int(details.get("metric", 0))
                                    logging.info(f"real metric {real_metric}")
                                    logging.info(f"desired metric - {route['metric']}")
                                    with subsubstep.start(f"Asserting the actual metric of the route matches the desired metric", continue_=True):
                                        assert route["metric"] == real_metric, f"Mismatch in metric for route {network} with next hop {route['next_hop']}"

                                if "localpref" in route and route.get("localpref") is not None and details.get("localpref"):
                                    real_localpref = int(details.get("localpref", 0))
                                    logging.info(f"real localpref - {real_localpref}")
                                    logging.info(f"desired localpref - {route['localpref'] }")
                                    with subsubstep.start(f"Asserting the real localpref of the route matches the desired localpref", continue_=True):
                                        assert route["localpref"] == real_localpref, f"Mismatch in local preference for route {network} with next hop {route['next_hop']}"

                                #Cisco parser makes aspath == route_info weird name but it works out
                                if "aspath" in route and route.get("aspath") is not None and details.get("route_info"):
                                    real_aspath = str(details.get("route_info", ""))
                                    logging.info(f"real aspath - {real_aspath}")
                                    logging.info(f"desired aspath - {str(route['aspath'])}")
                                    with subsubstep.start(f"Asserting the real aspath of the route matches the desired aspath", continue_=True):
                                        assert str(route["aspath"]) == real_aspath, f"Mismatch in aspath for route {network} with next hop {route['next_hop']}"
                                
                                if route.get("status_codes") and details.get("status_codes"):
                                    real_status_code = details.get("status_codes")
                                    logging.info(f"real status code - {real_status_code}")
                                    with subsubstep.start(f"Asserting the status code matches our desired status codes", continue_=True):
                                        
                                        if route.get("status_codes", {}).get("best_path") == True:
                                            assert ">" in real_status_code, "route should be best path, however it is not installed"
                                        elif route.get("status_codes", {}).get("best_path") == False:
                                            assert ">" not in real_status_code, "route should not be best path, however it is"

                                        if route.get("status_codes", {}).get("valid") == True:
                                            assert "*" in real_status_code, "Route should be considered a valid route, however it is not"
                                        elif route.get("status_codes", {}).get("valid") == False:
                                            assert "*" not in real_status_code, "route should not be valid, however it is"

                                        if route.get("status_codes", {}).get("learned_via_ibgp") == True:
                                            assert "i" in real_status_code, "Route should be learned via IBGP, however it is not"
                                        elif route.get("status_codes", {}).get("valid") == False:
                                            assert "i" not in real_status_code, "Route should not be learned via IBGP however it is"

                                        if route.get("status_codes", {}).get("multipath") == True:
                                            assert "m" in real_status_code, "Route should be multipathed, however it is not"
                                        elif route.get("status_codes", {}).get("multipath") == False:
                                            assert "m" not in real_status_code, "Route should not be multipath, however it is"
