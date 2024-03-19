"""
Author: James Duvall
Purpose: Configuration object used in converter, contains the logic to replace,
modify, or remove lines in a cisco ios config.
"""

import sys
import re
import logging
import ipaddress
from jinja2 import Template
from ciscoconfparse import CiscoConfParse

if 'pytest' in sys.modules:
    logging.warning("Running under pytest")
    from tests.config import (
        CSR_NODES,
    )
else:
    from config import (
        CSR_NODES,
    )


L3_INT_CISCOCONFPARSE: str = r"^int(erface) (Gi|Fa|Se|Te|Tw|Eth|Fo|Vlan|BDI|Po)"
# Attempt to match all common interface types, in shorthand or full notation
ALL_INTERFACE_FLAVORS_REGEX: str = (
    r"\b(?:Gi(gabitEthernet)|Eth(ernet)|Vl(an)|Fa(stEthernet)|BDI|Se(rial)|Te(nGigabitEthernet)|Twe(GigabitEthernet)|Po(rt-channel))\d+(?:\.\d+)*(?:\/\d+)*(?:\:\d+)*(?:\.\d+)*(?:\/\d+)?\b"
)
# Used to find L3 interfaces with the specific line - ip address (address) (mask)
L3_INT_REGEX: str = r"ip address \d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3} \d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$"
IP_ADDR_REGEX: str = r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}"

class Configuration:
    """
    Responsible for parsing the configuration and creating a new configuration
    """
    # pylint: disable=too-many-instance-attributes

    def __init__(self, file_: str, file_path: str) -> None:
        self.file_path: str = file_path
        self.file_: str = file_
        self.l3_interfaces: list[dict] = []
        self.undesired_interfaces: list[dict] = []
        try:
            with open(self.file_path, "r", encoding="UTF-8") as opened_file:
                self.unparsed_config: str = opened_file.readlines()
        except (FileNotFoundError, PermissionError) as e:
            logging.error(f"Error opening file (not found or permissions issue) - {e}")
            sys.exit(1)
        self.new_configuration = str()
        self.current_parsed_config: CiscoConfParse = None
        self.interface_mapping: dict[str, dict] = {}
        self.hostname = str()
        self.device_type = str()
        self.interface_name = str()
        self.management_interface = str()
        self.management_ip: ipaddress.IPv4Address = None
        try:
            with open("ci_cli/templates/securecrt.j2", "r", encoding="UTF-8") as securecrt_temp:
                self.securecrt_template = Template(securecrt_temp.read())
        except (FileNotFoundError, PermissionError) as e:
            logging.error(f"Error opening file (not found or permissions issue) - {e}")
            sys.exit(1)

    def get_current_parsed_config(self) -> None:
        """
        Turn the current network configuration into a parsed CiscoConfParse Object
        """
        self.current_parsed_config = CiscoConfParse(self.file_path)

    def get_hostname(self) -> None:
        """
        Look at current config and find hostname
        """
        hn = self.current_parsed_config.find_lines("hostname")
        if hn:
            hn_line = hn[0]
            self.hostname: str = hn_line.split(" ")[1]

    def get_device_type(self) -> None:
        """
        Determine by the hostname if the device should be iosv or csrv
        Also sets the interface name depending on the device
        """
        # CSRV_NODES from config.py, set specific values for each flavour of Cisco ios
        if self.hostname in CSR_NODES:
            self.device_type = "csrv"
            self.interface_name = "GigabitEthernet1"
            self.management_interface = "GigabitEthernet2"
        else:
            self.device_type = "iosv"
            self.interface_name = "GigabitEthernet0/1"
            self.management_interface = "GigabitEthernet0/2"

    def get_l3_interfaces(self) -> None:
        """
        Parses through the config to find existing layer 3 interfaces
        Retrieves the Primary IP and will use that in the future for comparison
        Appends a dictionary to the l3_interfaces array
        """
        interfaces = self.current_parsed_config.find_lines(
            L3_INT_CISCOCONFPARSE)
        for interface in interfaces:
            ip_config: list[str] = self.current_parsed_config.find_children_w_parents(
                f"^{interface}$",
                L3_INT_REGEX,
            )
            # if we do not find an ip address on the interface, go to the next iteration
            if ip_config:
                ip_addr = ip_config[0]
            else:
                int_dict: dict[str, str] = {
                    "config": self.file_path,
                    "if_name": re.search("interface (.*)", interface).group(1) 
                }
                self.undesired_interfaces.append(int_dict)
                continue

            # Create l3_interfaces dictionary, will be updated with new_vlanid in the 
            # converter's subnet_compare method
            int_dict: dict[str, str] = {
                "config": self.file_path,
                "if_name": re.search("interface (.*)", interface).group(1),
                "ip_subnet": self._build_ip_network(ip_addr),
                "ip_address": self._build_ip_addr(ip_addr),
            }
            self.l3_interfaces.append(int_dict)

    def create_interface_mapping(self) -> None:
        """
        Look at the current Configurations and determine 1:1 old intf to subintf mapping
        This is used for pyATS tests, mapping lab<->production interfaces during the tests
        """
        retdict: dict = {}
        for config in self.l3_interfaces:
            retdict[config['if_name']
                    ] = f"{self.interface_name}.{config['new_vlanid']}"

        self.interface_mapping: dict[str, str] = retdict

    def render_securecrt_session(self) -> str:
        """
        renders the securecrt template to create a session dynamically
        Creates txt for files that can be dropped into %appdata%/VanDyke/Config/Sessions
        """
        templated_session = self.securecrt_template.render(
            ip_address=self.management_ip)
        logging.debug(
            f"Creating securecrt session template for - {self.hostname}")
        return templated_session

    def remove_sections(self, sections: list) -> list:
        """
        Use CiscoConfigParse to remove specific BAD_SECTIONS from config.py
        """
        logging.debug(f"Removing sections from {self.hostname}")
        fixed_new_config: list[str] = []
        #Use cisco conf parse to get a parsed copy of the passed in config
        current_config_parsed = CiscoConfParse(self.new_configuration)
        #Also store list equivalent for comparison
        #CiscoConfParse supports delete_lines, but I do not like the implementation
        current_config_raw: list[str] = current_config_parsed.ioscfg
        bad_lines: list[str] = [line for section in sections for line in current_config_parsed.find_all_children(section)]
        for line in current_config_raw:
            if line in bad_lines:
                #If the line is found in bad_lines goes to the next item
                continue
            fixed_new_config.append(line)

        return fixed_new_config
    
    def remove_undesired_interfaces(self, interfaces: list) -> list:
        """
        Try to handle the issue with CiscoConfigParse adding additional interfaces in find_all_children
        TODO - fix this... Seems to... kinda work... Some interface are skipped even in interfaces list
        """
        current_config_parsed = CiscoConfParse(self.new_configuration, factory=True)
        current_config_raw = current_config_parsed.ioscfg
        for interface in interfaces:
            interface_objects = current_config_parsed.find_interface_objects(interface)
            for obj in interface_objects:
                obj.delete()
        return current_config_parsed.ioscfg

    def add_encap(self) -> list:
        """
        With the new configuration, go through and remove all previous instances of "encapsulation" and replace it with the correct vlan encap
        """
        logging.debug(f"Adding encap to interfaces of {self.hostname}")

        self.new_configuration = [
            line for line in self.new_configuration if "encapsulation" not in line]

        for i, line in enumerate(self.new_configuration):
            # Find all interfaces configuration lines, with or without additional spaces at end..
            match = re.search(
                f"^interface {ALL_INTERFACE_FLAVORS_REGEX}.*$", line)
            if match:
                matched_interface = match.group(0)
                for interface in self.l3_interfaces:
                    if not interface.get("new_vlanid"):
                        logging.error(
                            f"Interface {interface} does not have a new_vlanid")
                    try:
                        # Loose check to validate that the vlanid is in the interface name
                        # Without this, we could potentially add the wrong vlanid to the wrong interface
                        if str(interface.get('new_vlanid')) in matched_interface:
                            self.new_configuration[i] += f" encapsulation dot1q {interface['new_vlanid']}\n"
                    except KeyError:
                        logging.error(f"Issue with {interface}")

        logging.debug(f"New config: {self.new_configuration}")
        return self.new_configuration

    def add_mgmt_intf(
            self,
            mgmt_netmask: str,
            mgmt_gateway: ipaddress.IPv4Address,
            vrf_name: str = "LAB_MGMT",
            description: str = "Lab external management interface"
    ) -> list[str]:
        # pylint: disable=R0913
        """
        Add the management interface's configuration to the config
        """
        mgmt_interface_template = [
            "\n",
            f"interface {self.management_interface}\n",
            f" vrf forwarding {vrf_name}\n",
            " ip access-group no_dhcp_please in\n",
            " ip access-group no dhcp_please out\n",
            f" description {description}\n",
            " no ip address dhcp\n",
            f" ip address {self.management_ip} {mgmt_netmask}\n",
            "!\n",
            f"ip route vrf {vrf_name} 0.0.0.0 0.0.0.0 {mgmt_gateway}\n",
            "!\n",
            "\n"
        ]
        self.new_configuration: list[str] = mgmt_interface_template + self.new_configuration
        return self.new_configuration

    def replace_interfaces(
        self
    ) -> list:
        """
        Parse through the device configuration and replace the interface IDs with the subinterface
        """
        logging.debug(
            f"Replacing all interfaces as needed from {self.hostname}")
        new_config = []
        for line in self.unparsed_config:
            config_flag = False
            match = re.search(ALL_INTERFACE_FLAVORS_REGEX, line)
            if match:
                for interface in self.l3_interfaces:
                    new_if_name = f"{self.interface_name}.{interface.get('new_vlanid')}"
                    if interface.get("if_name") == match.group():
                        new_config.append(
                            line.replace(match.group(), new_if_name)
                        )
                        config_flag = True
                        break
            if not config_flag:
                new_config.append(line)
        logging.debug(f"New config: {new_config}")
        return new_config

    @staticmethod
    def _build_ip_addr(ip: str) -> ipaddress.IPv4Address:
        """
        helper function to take a ip address and convert it to a IPv4Address Object
        """
        ip = re.search(IP_ADDR_REGEX, ip).group(0)
        return ipaddress.IPv4Address(ip)

    @staticmethod
    def _build_ip_network(ip: str) -> ipaddress.IPv4Network:
        """
        helper function to take a create a network from the cisco router ip address format
        """
        ip: str = ip.split("ip address")[1]
        ip: str = ip.strip()
        ip: str = "/".join(ip.split(" "))
        return ipaddress.IPv4Network(ip, strict=False)

    def __str__(self):
        return str(self.l3_interfaces)
