"""
Author: James Duvall
Purpose: Parses through unstructured text of Cisco IOS and extracts 
all l3 interfaces across many different config files. Uses the subnets 
on the interfaces to determine what needs to be connected to what. Then 
assigns these connections to a subinterface. Export with new configs using 
subinterface to make virtual links to all devices. Also add a few lines 
for no shut, stripping aaa, etc
"""
import os
import sys
import logging
import json
import ipaddress
import time
from .configuration import Configuration
# Importing the config.py file, depending on pytest or not
# Uses sys.modules to determine how it's being ran
if 'pytest' in sys.modules:
    logging.warning("Running under pytest")
    from tests.config import (
        CSRV_CONFIGS,
        IOSV_CONFIGS,
        BAD_SECTIONS,
        MANAGEMENT_SUBNETS
    )
else:
    from config import (
        CSRV_CONFIGS,
        IOSV_CONFIGS,
        BAD_SECTIONS,
        MANAGEMENT_SUBNETS
    )

class Converter:
    """
    Responsible for directing the configuration conversion
    Holds all Configuration objects and performs bulk actions on the configs
    """
    # pylint: disable=R0902
    # pylint: disable=R0913
    def __init__(
        self,
        source_path: str,
        gitlab_user: str,
        configs: list[Configuration] = None,
        config_file_ext: str = ".txt",
        vlan_seed: int = 2,
        output_path: str = "",
    ) -> None:
        if configs is None:
            self.configs: list[Configuration] = []
        else:
            self.configs: list[Configuration] = configs
        self.source_path: str = source_path
        self.config_file_ext: str = config_file_ext
        self.vlan_seed: int = vlan_seed
        self.output_path: str = output_path
        self.gitlab_user: str = gitlab_user
        try:
            self.management_subnet = ipaddress.IPv4Network(
                MANAGEMENT_SUBNETS[self.gitlab_user]["management_network"])
            self.management_gateway = ipaddress.IPv4Address(
                MANAGEMENT_SUBNETS[self.gitlab_user]["management_default_gw"])
        except KeyError:
            logging.error("User's management network not found in config.py")
            sys.exit(1)
        self.create_output_directories()

    def create_output_directories(self) -> None:
        """
        Create directories for output
        provided output path and securecrt_sessions
        """
        try:
            os.mkdir(self.output_path)
        except FileExistsError:
            logging.debug("Output folder already exists")
        try:
            os.mkdir(f"{self.output_path}/securecrt_sessions")
        except FileExistsError:
            logging.debug("securecrt_sessions folder already exists")

    def load_configs(self) -> None:
        """
        With self.source_path, open all configurations and build the config classes associated with each.
        """
        for dirpath, _, filenames in os.walk(self.source_path):
            for file_ in filenames:
                if file_.endswith(self.config_file_ext) and "LAB" not in file_:
                    # Combine dirpath and file to get full path
                    full_path: str = os.path.join(dirpath, file_)
                    self.configs.append(
                        Configuration(
                            file_=file_, file_path=full_path
                        )
                    )

    def save_securecrt_sessions(self) -> None:
        """
        Runs the render_securecrt_session on each configuration, saves the output to the output_path/securecrt_sessions folder
        To be used as an artifact in CI
        """
        for configuration in self.configs:
            securecrt_session: str = configuration.render_securecrt_session()
            if not securecrt_session:
                logging.error("Failed to create securecrt session template")
            logging.debug(
                f"Saving securecrt session for host {configuration.hostname}")
            self.save_output(file_=f"{configuration.hostname}.ini",
                             save_me=securecrt_session, type_="securecrt")

    def save_interface_mapping(self) -> None:
        """
        Saves the interface mapping to an output file
        """
        overall_mapping: dict[str, dict] = {"devices": {}}
        for config in self.configs:
            overall_mapping["devices"][config.hostname] = config.interface_mapping

        self.save_output(file_="overall_interface_map.json",
                         save_me=overall_mapping, type_="json")

    def create_lab_vars(self) -> None:
        """
        Create the tfiles file that we can reference with our terraform file
        """
        lab_var_template: dict[str, dict] = {
            "nodes": []
        }
        for idx, config in enumerate(self.configs):
            # Each node will have exactly these values:
            # nodedefinition results in type of router we deploy
            # left and top are coordinates in the lab topology
            # hostname is the devices configured hostname
            # config_file is the file where the configs are located
            # label is currently unused, but may be used later for lab notes
            working_dict: dict = {}
            working_dict['nodedefinition'] = config.device_type
            working_dict['left'], working_dict['top'] = self._calculate_coords(
                idx=idx + 1, total=len(self.configs))
            logging.debug(
                f"Coords = {working_dict['left']}, {working_dict['top']}")
            working_dict['hostname'] = f"{config.hostname}"
            working_dict['config_file'] = f"LAB-{config.file_}"
            working_dict['label'] = config.file_

            lab_var_template['nodes'].append(working_dict)

        self.save_output(file_="labvars.json",
                         save_me=lab_var_template, type_="json")

    def save_output(self, file_: str, save_me: str|list, type_: str="config", config: Configuration=None) -> None:
        """
        Save the configuration to the provided destination path
        """
        if type_ == "config":
            with open(f"{self.output_path}/{file_}", "w", encoding="UTF-8") as opened_file:
                logging.debug(f"Saving config {self.output_path}/{file_}")
                if config.device_type == "csrv":
                    # Uses CSRV_CONFIGS from config.py file
                    final_config: str = CSRV_CONFIGS + '\n'.join(save_me)
                else:
                    # Uses IOSV_CONFIGS from config.py file
                    final_config: str = IOSV_CONFIGS + '\n'.join(save_me)

                opened_file.write(final_config)

        elif type_ == "json":
            with open(f"{self.output_path}/{file_}", "w", encoding="UTF-8") as opened_file:
                logging.debug(f"Saving json {self.output_path}/{file_}")
                final_map: dict = json.dumps(save_me, indent=2)
                opened_file.write(final_map)

        elif type_ == "securecrt":
            with open(f"{self.output_path}/securecrt_sessions/{file_}", "w", encoding="UTF-8") as opened_file:
                logging.debug(f"Saving securecrt {self.output_path}/{file_}")
                opened_file.write(save_me)

    def subnet_compare(self) -> None:
        """
        Group interfaces by their subnets across all configurations and assigns vlanids
        Modifies each configuration's l3_interfaces properties to add key new_vlanid
        """

        all_interfaces: list[dict] = [
            intf for config in self.configs for intf in config.l3_interfaces]

        processed_ip_addresses = set()
        for interface in all_interfaces:
            # If we've already seen this ip, skip it
            if interface["ip_address"] in processed_ip_addresses:
                continue

            # Get all interfaces within the current interface's lan segment
            # intf["ip_address"] is an IPv4Address object, and interface["ip_subnet"] is an IPv4 Network Object
            matched_interfaces: list[dict] = [intf for intf in all_interfaces if intf["ip_address"]
                                              in interface["ip_subnet"] and intf != interface]

            # Find the corresponding Configuration object for the interface
            # This is needed for interface assignment
            config_obj = next(
                config for config in self.configs if config.file_path == interface["config"])

            # If there are any interfaces in the same lan segment
            # Choose a unique vlan ID
            if matched_interfaces:
                interface["new_vlanid"] = self.vlan_seed
                logging.debug(
                    f"Interface {interface['if_name']} is being assigned to new interface {config_obj.interface_name}.{self.vlan_seed}")
                # Update the Configuration's l3_interfaces property matching each matched_interface
                # Give them a dedicated vlan
                for matched_intf in matched_interfaces:
                    matched_intf["new_vlanid"] = self.vlan_seed
                    # Since we've seen this intf's ip, add it to the processed_ip_addresses set
                    processed_ip_addresses.add(matched_intf["ip_address"])

                # Increment vlan seed so the next interface group is different
                self.vlan_seed += 1
                processed_ip_addresses.add(interface["ip_address"])

            # If the interface is lonely in its own lan segment, still give it a unique vlanid (simulates interface up/up)
            else:
                interface["new_vlanid"] = self.vlan_seed
                logging.debug(
                    f"Interface {interface['if_name']} is being assigned to new interface {config_obj.interface_name}.{self.vlan_seed}")
                self.vlan_seed += 1
                processed_ip_addresses.add(interface["ip_address"])

    def manipulate_configs(self) -> None:
        """
        Make new configurations from the old and place them in an output directory
        """
        # Create a list of management addresses to allocate
        mgmt_ips: list[ipaddress.IPv4Address] = list(self.management_subnet)
        # Reverse so that we allocate addresses in sequence 1,2,3,4...etc
        mgmt_ips.reverse()
        # Remove .0, assuming it's a network address
        mgmt_ips.pop()
        for configuration in self.configs:
            logging.debug(f"Manipulate config for {configuration.hostname}")
            # Assign the configuration object a management_ip that is popped from the mgmt_ips list
            configuration.management_ip = mgmt_ips.pop()
            configuration.new_configuration= configuration.replace_interfaces()
            configuration.new_configuration = configuration.add_encap()
            configuration.new_configuration = configuration.add_mgmt_intf(self.management_subnet.netmask, self.management_gateway)

            # This returns in a different format, keep these bad sections last
            # every specified bad section in the provided config.py is removed
            configuration.new_configuration= configuration.remove_sections(BAD_SECTIONS)
            # Removes the undesired interfaces that did not have an IP address
            start_time = time.perf_counter()
            configuration.new_configuration = configuration.remove_undesired_interfaces(
                [interface.get("if_name") for interface in configuration.undesired_interfaces]
            )
            logging.debug(f"{configuration.hostname} took {time.perf_counter() - start_time:.2f} to convert")
            # Save the new configuration to the output directory
            self.save_output(file_=f"LAB-{configuration.file_}",
                             save_me=configuration.new_configuration, type_="config", config=configuration)

    @staticmethod
    def _calculate_coords(idx: int, total: int) -> tuple:
        """
        Based on the index of the configuration, calculate the x and y coordinates for the lab topology
        Total is the total number of configurations in the Converter
        Space the configurations out evenly across the top and bottom of the lab topology
        """
        # top row
        if idx < total / 2:
            return int(idx * 150), 0

        # bottom row
        idx = idx - (total / 2)
        return int(idx * 150), 900
