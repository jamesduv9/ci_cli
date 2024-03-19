"""
Author: James Duvall
Purpose: easypy script to dynamically determine the tests needed to run against the lab environment 
"""
import argparse
import sys
import os
import json
import logging
import yaml
from ipaddress import IPv4Address, AddressValueError
from pyats.reporter.exceptions import DuplicateIDError
from pyats import easypy

parser = argparse.ArgumentParser(description = "test_handler CLI tool")
parser.add_argument("--test_directory", required=True)
parser.add_argument("--interface_map_file", required=True)

class IntBackwardsConverter:
    """
    Helper class we will use in the testscripts
    Takes in the interface file
    """
    def __init__(self, interface_map_file: str):
        with open(interface_map_file, "r") as int_map:
            self.json_int_map = json.loads(int_map.read())

    def mapper(self, device_name: str, interface_name: str):
        """
        helper method, provies the converted interface
        """
        if self.is_ip(interface_name):
            logging.info("IP provided to mapper function, passing gracefully")
            return interface_name
        target_device_d = self.json_int_map["devices"][device_name]
        converted_interface = target_device_d.get(interface_name)
        if not converted_interface:
            logging.warning("Specified interface not found, using interface name found in test instead (This is expected for logical interfaces [loopbacks/tunnels])")
            return interface_name
        
        return converted_interface

    @staticmethod
    def is_ip(interface_name: str):
        """
        In some cases we may pass an IP into this mapper, for example when sourcing either ip or int
        I want to fail gracefully if a valid IP is added
        """
        try:
            IPv4Address(interface_name)
            return True
        except AddressValueError:
            return False

def grab_tests(test_directory: str) -> dict:
    """
    Grab tests and return test dict
    """
    tests = {
        "bgp_peer_test": [],
        "ospf_neighbor_test": [],
        "eigrp_neighbor_test": [],
        "bgp_route_test": [],
        "interface_status_test": [],
        "ospf_redistribution_test": [],
        "ping_test": []
    }
    for directory, _, files in os.walk(test_directory):
        for file in files:
            if file.endswith(".yml"):
                with open(f"{directory}/{file}") as opened_test:
                    new_test = yaml.safe_load(opened_test.read())
                    if new_test.get("type") in tests.keys():
                        tests[new_test.get("type")].append(new_test)
                        logging.info(f"Added test {file} to tests lists")
                    else:
                        logging.warning(f"Test with filename {file}, does not have a valid test type value")

    return tests

def run_tests(runtime, tests: dict, test_type:str, mapper: IntBackwardsConverter):
    """
    Iterate through all the tests of a specified type
    """
    for test in tests.get(test_type, []):
        test_devices=[device for device in runtime.testbed.devices.values() if device.name in test.get("devices")]
        try:
            easypy.run(testscript=f"testscripts/{test_type}.py", taskid=test.get("test_description"), test_params=test, devices=test_devices, mapper=mapper)
        except DuplicateIDError:
            logging.warning("Two tests have the same description, please correct for the second test to take effect")


def main(runtime):
    """
    pyATS required main function
    """
    args, _ = parser.parse_known_args(sys.argv[1:])
    args = vars(args)
    #Create our production <-> Lab converter class
    mapper = IntBackwardsConverter(interface_map_file=args.get("interface_map_file"))
    tests = grab_tests(args.get("test_directory"))
    for test_name in tests.keys():
        logging.info(f"Running test - {test_name}")
        run_tests(runtime, tests, test_name, mapper)
