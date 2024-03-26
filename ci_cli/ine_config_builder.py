"""
Author: James Duvall
Purpose: Templates the ine yaml files into ios configs, 
allowing them to convert into real lab configs
"""

import os
import sys
import ipaddress
import logging
import yaml
from jinja2 import Template

class INEConfigBuilder:
    """
    Builds the configuration files for ines using the template ine.j2
    Stores the file back in the same path it was found automatically
    """
    # pylint: disable=too-many-instance-attributes
    def __init__(self, file_path: str, file_: str):
        self.file_path: str = file_path
        self.file_: str = file_
        self.combined_path: str = os.path.join(self.file_path, self.file_)
        try:
            with open("ci_cli/templates/ine.j2", "r", encoding="UTF-8") as kg_template_file:
                self.template = Template(kg_template_file.read())
        except (FileNotFoundError, PermissionError) as e:
            logging.error(f"Error opening file (not found or permissions issue) - {e}")
            sys.exit(1)
        self.y_config: dict[str, str] = self.get_yaml_config()
        self.ios_config: str = self.template_config()
        self.save_path, self.save_file = self.save_config()

    def get_yaml_config(self):
        """
        Open the config file, parse to work with as python dictionary
        """
        logging.info(
            f"Opening the provided ine yml file - {self.combined_path}")
        with open(self.combined_path, 'r', encoding="UTF-8") as y_file:
            return yaml.safe_load(y_file.read())

    def template_config(self):
        """
        Render the ine config template
        """
        logging.info(f"Rendering j2 template for {self.combined_path}")
        return self.template.render(config=self.y_config, convert_ip_format=self.convert_ip_format)

    def save_config(self):
        """
        Use same filename as the provided yml, save templated config as .txt
        """
        config: list[str] = self.file_.split(".yml")[0]
        config_txt: str = f"{config}.txt"
        save_path: str = f"{self.file_path}/{config_txt}"
        logging.info(f"Saving file as {save_path}")
        with open(save_path, 'w', encoding="UTF-8") as file_:
            file_.write(self.ios_config)
        return save_path, config_txt

    @staticmethod
    def convert_ip_format(ip_with_prefix, net=False):
        """
        Helper for the jinja template, converts CIDR input to ios format
        """
        logging.info(f"Coverting subnet {ip_with_prefix}")
        ip = ipaddress.IPv4Network(ip_with_prefix, strict=False)
        if net:
            logging.info("--Returing the network address")
            return f"{ip.network_address} {ip.netmask}"
        logging.info("--Returning the original IP")
        return f"{ip_with_prefix.split('/')[0]} {ip.netmask}"
