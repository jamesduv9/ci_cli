"""
Author: James Duvall
Purpose: Interacts with EVE-NG to create, destroy, and manage the labs
WARNING: Some of the APIs used in this code are not well documented by EVE-NG and possibly will change in the future
This was all validated to work on EVE-NG version 5.0.1-129
"""

import os
import copy
import json
import time
import logging
import difflib
import sys
from functools import wraps
from concurrent import futures

import requests
import yaml
from pyats.topology import loader
from unicon.core.errors import ConnectionError as CE
from config import CSRV_IMAGE, IOSV_IMAGE, CSRV_IMAGE_TYPE
requests.packages.urllib3.disable_warnings()
yaml.Dumper.ignore_aliases = lambda *args: True

def handle_http_errors(func):
    """
    A decorator that wraps the passed-in function, allowing it to execute and handle
    any raised HTTP errors post-execution. Assumes that the decorated function will
    call `raise_for_status()` on its own.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            # Execute the decorated function, which is expected to call raise_for_status() on its own
            return func(*args, **kwargs)
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code
            if status_code == 400:
                logging.error(
                    f"400 Conflict (likely already exists): {e.request.url} - {e}")
            elif status_code == 401:
                logging.error(f"No longer authenticated - {e}")
                raise
            elif status_code == 404:
                logging.error(f"404 Not Found: {e.request.url} - {e}")
            elif status_code == 412:
                logging.error(
                    f"I believe EVE throws 412 for unauth; relogin and attempt again - {e}")
            elif status_code == 429:
                logging.error(f"429 Too many requests: {e.request.url} - {e}")
            elif str(status_code)[0] == "5":
                logging.error(f"5XX Server Error at: {e.request.url} - {e}")
            else:
                logging.error(f"HTTP Error {status_code}: {e.request.url} - {e}")
        except requests.exceptions.RequestException as e:
            logging.error(f"Request Error: {str(e)}")
        # pylint: disable=W0718
        except Exception as e:
            # Handle any other exceptions
            logging.error(f"Unexpected error: {str(e)}")
    return wrapper

#pylint: disable=R0904
class EVEInterface:
    """
    Interface for interacting with labs we create from the pipeline
    """

    def __init__(self, lab_name: str, source_path: str = None):
        self.lab_name: str = lab_name
        self.source_path: str = source_path
        self.lab_r_session = requests.Session()
        self.headers: dict[str, str] = {"accept": "application/json"}
        # ENV vars provided on the gitlab runner
        self.eve_url: str = os.getenv("EVE_URL")
        self.eve_username: str = os.getenv("EVE_USERNAME")
        self.eve_password: str = os.getenv("EVE_PASSWORD")
        self.login()

    @handle_http_errors
    def start_all_nodes(self) -> None:
        """
        Starts all nodes in the eve topology
        """
        logging.info(
            "Grabbing all nodes, then iterating over all to start them")
        url: str = f"{self.eve_url}/api/labs/{self.lab_name}.unl/nodes?_={self.get_current_epoch_time_ms()}"
        response: dict[str, dict] = self.lab_r_session.get(url, verify=False).json()
        for node_id in response["data"]:
            logging.info(f"Starting Node {node_id}")
            url: str = f"{self.eve_url}/api/labs/{self.lab_name}.unl/nodes/{node_id}/start?_={self.get_current_epoch_time_ms()}"
            response: str = self.lab_r_session.get(url, verify=False)
            logging.debug(response.json())
            response.raise_for_status()

    @handle_http_errors
    def stop_all_nodes(self) -> None:
        """
        Iterate through all nodes in a lab, stops them one by one.
        Should result in knowing when all nodes are stopped
        """
        url: str = f"{self.eve_url}/api/labs/{self.lab_name}.unl/nodes?_={self.get_current_epoch_time_ms()}"
        logging.info("Grabbing all nodes and iterating over them to stop them")
        response: dict[str, dict] = self.lab_r_session.get(url, verify=False).json()
        logging.debug(response)

        for node_id, _ in response["data"].items():
            logging.info(f"Stopping Node {node_id}")
            url: str = f"{self.eve_url}/api/labs/{self.lab_name}.unl/nodes/{node_id}/stop/stopmode=3?_={self.get_current_epoch_time_ms()}"
            response: str = self.lab_r_session.get(url, verify=False)
            logging.debug(response.json())
            response.raise_for_status()

    @handle_http_errors
    def delete_lab(self):
        """
        Deletes the lab from EVE
        """
        url = f"{self.eve_url}/api/labs/{self.lab_name}.unl"
        logging.info(f"Deleting lab at url - {url}")
        response = self.lab_r_session.delete(
            url, headers=self.headers, verify=False)
        response.raise_for_status()

    @handle_http_errors
    def add_router_to_lab(self, device_name: str, left: int, top: int, device_type: str) -> str:
        """
        Create csrv or iosv nodes in the eve-ng lab
        uses config.py values to determine API post payload
        """
        data: dict[str, str] = {
            "template": CSRV_IMAGE_TYPE if device_type == "csrv" else "vios",
            "type": "qemu",
            "count": "1",
            "image": CSRV_IMAGE if device_type == "csrv" else IOSV_IMAGE,
            "name": device_name,
            "icon": "CSRv1000.png" if device_type == "csrv" else "Router.png",
            "cpu": "1",
            "ram": "4096" if device_type == "csrv" else "2048",
            "ethernet": "2" if device_type == "csrv" else "3",
            # Non default setting - 1 enforces the startup config to read from text that we send later
            "config": "1",
            "sat": "-1",
            "console": "telnet",
            "left": int(left),
            "top": int(top),
        }
        response = self.lab_r_session.post(
            f"{self.eve_url}/api/labs/{self.lab_name}.unl/nodes",
            data=json.dumps(data),
            headers=self.headers,
            verify=False,
        )
        response.raise_for_status()
        logging.debug(response.json())
        node_id = response.json().get("data", {}).get("id")
        return node_id

    @handle_http_errors
    def create_lab(self) -> None:
        """
        Creates an eve-ng lab
        """
        data = {
            "path": "/",
            "name": self.lab_name,
            "version": "1",
        }
        logging.info(f"payload : {data}")
        response = self.lab_r_session.post(
            f"{self.eve_url}/api/labs",
            data=json.dumps(data),
            headers=self.headers,
            verify=False,
        )
        logging.debug(response.json())
        response.raise_for_status()

    @handle_http_errors
    def exists(self) -> bool:
        """
        Simple check to see if the lab already exists or not
        """
        url = f"{self.eve_url}/api/labs/{self.lab_name}.unl"
        response = self.lab_r_session.get(
            url, headers=self.headers, verify=False)
        if response.status_code == 200:
            return True
        
        return False

    @handle_http_errors
    def delete_lab(self) -> None:
        """
        Deletes the lab
        """
        url = f"{self.eve_url}/api/labs/{self.lab_name}.unl"
        response = self.lab_r_session.delete(url, verify=False)
        logging.debug(response.json())
        response.raise_for_status()

    @handle_http_errors
    def login(self) -> None:
        """
        Logins into EVE, uses the objects request session to save auth token for future requests
        ran during the objects constructor
        """
        # html5 not being set to -1 in payload results in bad responses when creating testbed. The url is http instead of telnet
        data = {"username": self.eve_username,
                "password": self.eve_password, 'html5': '-1'}

        response = self.lab_r_session.post(
            f"{self.eve_url}/api/auth/login",
            data=json.dumps(data),
            headers=self.headers,
            verify=False
        )
        logging.debug(response.json())
        response.raise_for_status()

    @handle_http_errors
    def start_node(self, node_id: str) -> None:
        """
        Fires up an individual node
        """
        url = f"{self.eve_url}/api/labs/{self.lab_name}.unl/nodes/{node_id}/start?_={self.get_current_epoch_time_ms()}"
        logging.info(f"start url - {url}")
        response = self.lab_r_session.get(url, verify=False)
        logging.debug(response.json())
        response.raise_for_status()

    @handle_http_errors
    def stop_node(self, node_id: str) -> None:
        """
        shuts down an individual node
        """
        url = f"{self.eve_url}/api/labs/{self.lab_name}.unl/nodes/{node_id}/stop/stopmode=3?_={self.get_current_epoch_time_ms()}"
        #Sleeping here for 5 seconds to allow eve to really power the node down
        time.sleep(5)
        logging.info(f"stop url - {url}")
        response = self.lab_r_session.get(url, verify=False)

        response.raise_for_status()
        logging.debug(response.json())

    @handle_http_errors
    def wipe_node(self, node_id: str) -> None:
        """
        wipe an individual node
        """
        url = f"{self.eve_url}/api/labs/{self.lab_name}.unl/nodes/{node_id}/wipe?_={self.get_current_epoch_time_ms()}"
        logging.info(f"wipe url - {url}")
        response = self.lab_r_session.get(url, verify=False)
        logging.debug(response.json())
        response.raise_for_status()

    @handle_http_errors
    def create_network(self, left: int, top: int, network_type: str, name: str, icon: str) -> str:
        """
        Creates a network object that can be used to connect devices together through a bridge
        or outside network through a internet bridge
        """
        url = f"{self.eve_url}/api/labs/{self.lab_name}.unl/networks"
        data_dict = {
            "count": "1",
            "visibility": "1",
            "name": name,
            "icon": icon,
            "type": network_type,
            "left": left,
            "top": top,
            "postfix": 0,
        }
        data = json.dumps(data_dict)
        response = self.lab_r_session.post(url, data=data, verify=False)
        response.raise_for_status()
        logging.debug(response.json())
        network_id = response.json().get("data", {}).get("id")
        return network_id

    @handle_http_errors
    def connect_network_to_interface(self, node_id: int, network_id: int, interface: int) -> None:
        """
        Given a network's id and node's id, connect the two on a specified interface
        """
        url = f"{self.eve_url}/api/labs/{self.lab_name}.unl/nodes/{node_id}/interfaces"
        data_dict = {f"{interface}": f"{network_id}"}
        data = json.dumps(data_dict)
        response = self.lab_r_session.put(url, data=data, verify=False)
        logging.debug(response.json())
        response.raise_for_status()

    @handle_http_errors
    def deploy_config(self, node_id: int, config_file: str) -> None:
        """
        Reads a config file, deploys the config to specified device
        This only works in conjunction with node being set with param config: 1
        """
        with open(config_file, "r", encoding="UTF-8") as file:
            config = file.read()
        data_dict = {
            "id": f"{node_id}",
            "data": f"{config}",
            "cfsid": "default",
        }
        data = json.dumps(data_dict)

        url = f"{self.eve_url}/api/labs/{self.lab_name}.unl/configs/{node_id}"

        response = self.lab_r_session.put(url, data=data, verify=False)
        logging.debug(response.json())
        response.raise_for_status()

    @handle_http_errors
    def wait_for_boot(self) -> None:
        """
        Need to rethink this function, is there a better way to tell if a node is fully booted?
        """
        sleeptime = 0
        while sleeptime < 600:
            time.sleep(10)
            sleeptime += 10
            logging.info(
                f"Waiting for devices to boot.. - {sleeptime}/600 seconds waited")

    def open_and_validate_labvars(self) -> None:
        """
        Grabs the labvars from file, saves them as a LabInterface property (self.labvars)
        Does some basic validation that required information exists. Didn't feel like adding pydantic would be worth for small usecase
        """
        with open(f"{self.source_path}/labvars.json", encoding="UTF-8") as labvars:
            self.labvars = json.loads(labvars.read())
            try:
                assert self.labvars.get("nodes")
                assert len(self.labvars.get("nodes")) >= 1
            except AssertionError:
                logging.error(
                    "labvars did not contain the nodes key, or the key held no values")
                sys.exit(1)
            for node in self.labvars.get("nodes"):
                try:
                    assert node.get("nodedefinition")
                    assert node.get("left") or node.get("left") == 0
                    assert node.get("top") or node.get("top") == 0
                    assert node.get("hostname")
                    assert node.get("config_file")
                    assert node.get("label")
                except AssertionError:
                    logging.error(
                        f"node within labvars did not contain required values. must contain ['nodedefinition', 'left', 'top', 'hostname', 'config_file', 'label'], found {node}")
                    sys.exit(1)

    def health_check(self, target_devices=None):
        """
        Use pyats to connect to each device. If a device is not stable... shutdown/wipe/restart
        """
        loaded_testbed = loader.load(self.yaml_testbed)
        bad_devices = []
        with futures.ThreadPoolExecutor() as pp:
            for device in loaded_testbed.devices.values():
                # Temp set the 'mit' value to True in memory, speeds up connections
                device.connections.cli.arguments['mit'] = True
                try:
                    if target_devices is not None:
                        if device.name in [dev.get("device_name") for dev in target_devices]:
                            logging.info(
                                f"Targetted run - Connecting to device - {device.name}")
                            pp.submit(device.connect(log_stdout=True))
                        else:
                            logging.info(
                                f"Skipping device {device.name} as this is a targetted run, this node already healthy")
                    else:
                        logging.info(f"Connecting to device - {device.name}")
                        pp.submit(device.connect(log_stdout=False))
                except CE as e:
                    logging.debug(e)
                    logging.error(f"Device {device.name} failed to connect")
                    bad_devices.append(
                        {"device_name": device.name, "node_id": int(device.custom.node_id)})

        if not bad_devices:
            logging.info("All look healthy and ready to go")
            return
        logging.warning(
            f"These devices seem to be misbehaving.. rebooting {bad_devices}")
        # Relogin, seems like eve times out randomly?...
        self.login()
        time.sleep(5)
        for bad_device in bad_devices:
            self.stop_node(bad_device.get("node_id"))
            time.sleep(1)
            self.wipe_node(bad_device.get("node_id"))
            time.sleep(1)
            self.start_node(bad_device.get("node_id"))
            time.sleep(1)

        # rebuild testbed, port numbers change on reboot
        self.build_testbed()

        # Now wait 5 minutes and try again... this might be a bad idea
        logging.warning(
            "Waiting 5 minutes and rerunning health check. Please be patient, however If this process loops multiple times, it may never work")
        time.sleep(300)
        self.health_check(target_devices=bad_devices)

    @handle_http_errors
    def build_testbed(self, tb_output_path: str):
        """
        create a pyATS testbed from a lab
        """
        logging.info(f"Creating testbed for lab {self.lab_name}")
        url = f"{self.eve_url}/api/labs/{self.lab_name}.unl/nodes?={self.get_current_epoch_time_ms()}"
        #Required cookies to get the correct output from eve
        cookies = {'html5': '-1'}
        response = self.lab_r_session.get(url, headers=self.headers, verify=False, cookies=cookies)
        response.raise_for_status()
        logging.debug(response.json())

        testbed_template = {"devices": {}}
        device_template = {
            "custom": {},
            "connections": {
                "cli": {
                    "protocol": "telnet",
                    "arguments": {"connection_timeout": 120, "mit": False},
                    "settings": {"ESCAPE_CHAR_PROMPT_WAIT": .5, "ESCAPE_CHAR_PROMPT_WAIT_RETRIES": 3}
                }
            },
            "credentials": {"default": {"username": "admin", "password": "admin"}},
            "os": "ios",
            "platform": "iosv",
            "type": "router"
        }

        for device_id, device_values in response.json().get("data").items():
            logging.info(f"Adding device {device_values.get('name')}")
            ip, port = device_values.get("url").split("telnet://")[1].split(":")
            device_config = copy.deepcopy(device_template)
            device_config["custom"]["node_id"] = device_id
            device_config["connections"]["cli"]["ip"] = ip
            device_config["connections"]["cli"]["port"] = int(port)

            if device_values.get("template") == "c8000v":
                device_config["os"] = "iosxe"
                device_config["platform"] = "csr1000v"

            testbed_template['devices'][device_values.get("name")] = device_config

        logging.debug(testbed_template)
        yaml_testbed = yaml.dump(testbed_template, default_flow_style=False)
        self.yaml_testbed = yaml_testbed

        with open(tb_output_path, 'w', encoding="UTF-8") as testbed_file:
            testbed_file.write(yaml_testbed)
            logging.info(f"Testbed created for lab {self.lab_name}, file saved as testbed.yml")

    def build_lab_from_cicd(self):
        """
        The main function that will be called from the cicd_tool that acts as a lab builder.
        """
        self.open_and_validate_labvars()
        self.create_lab()
        logging.info("Creating bridge network")
        bridge_network_id: str = self.create_network(
            top=400, left=800, network_type="bridge", name="Local Bridge", icon="Dot_black.png")
        logging.info("Creating management network")
        cloud_network_id: str = self.create_network(
            top=400, left=1600, network_type="pnet0", name="Management", icon="Dot_blue.png")

        for node in self.labvars.get("nodes"):
            logging.info(
                f"Creating and connecting node {node.get('hostname')}")
            # Start node based on type
            # iosv uses interface 1 for GigabitEthernet0/1
            if node.get("nodedefinition") == "iosv":
                node_id = self.add_router_to_lab(device_name=node.get(
                    "hostname"), left=node.get("left"), top=node.get("top"), device_type=node.get("nodedefinition"))
                self.connect_network_to_interface(
                    node_id=node_id, network_id=bridge_network_id, interface=1)
                self.connect_network_to_interface(
                    node_id=node_id, network_id=cloud_network_id, interface=2)
            # csrv uses interface 0 for GigabitEthernet1
            elif node.get("nodedefinition") == "csrv":
                node_id = self.add_router_to_lab(device_name=node.get(
                    "hostname"), left=node.get("left"), top=node.get("top"), device_type=node.get("nodedefinition"))
                self.connect_network_to_interface(
                    node_id=node_id, network_id=bridge_network_id, interface=0)
                self.connect_network_to_interface(
                    node_id=node_id, network_id=cloud_network_id, interface=1)
            self.deploy_config(
                node_id=node_id, config_file=f"{self.source_path}/{node.get('config_file')}")
        self.start_all_nodes()
        self.wait_for_boot()
        self.wait_for_noshut()

    def teardown_lab_from_cicd(self):
        """
        Stops nodes, and deletes lab
        """
        self.stop_all_nodes()
        self.delete_lab()
        logging.info("Successfully stopped and deleted lab")

    @handle_http_errors
    def mod_lab_from_cicd(self):
        """
        If the lab exists, cicd_tool will run this instead
        Determines diffs between lab configs and target configs
        redeploys the nodes with differences into the lab
        """
        logging.info("Getting values from labvars")
        self.open_and_validate_labvars()
        url = f"{self.eve_url}/api/labs/{self.lab_name}.unl/configs"
        payload = '{"cfsid": "default"}'
        logging.info("Getting all configs")
        response = self.lab_r_session.post(
            url=url, data=payload, headers=self.headers, verify=False)
        response.raise_for_status()
        all_configs = response.json()
        health_targets = []
        for node_id, config_values in all_configs.get("data").items():
            target_node = [node for node in self.labvars.get(
                "nodes") if node.get("hostname") == config_values.get("name")][0]
            logging.info(f"target node == {target_node}")
            config_file_path = f"{self.source_path}/{target_node.get('config_file')}"
            with open(config_file_path, 'r', encoding="UTF-8") as config:
                local_config = config.read().strip()
                api_config = config_values.get("configdata", "").strip()
                # Check if the configurations are different
                if local_config != api_config:
                    # Use difflib to find differences
                    diff = difflib.unified_diff(
                        local_config.splitlines(keepends=True),
                        api_config.splitlines(keepends=True),
                        fromfile="local_config",
                        tofile="api_config",
                    )
                    diff_text = ''.join(diff)
                    logging.info(
                        f"Differences found for node {target_node.get('hostname')}:\n{diff_text}")
                    logging.info(
                        "Stopping, deploying new config, wiping config, and starting back the node")
                    self.stop_node(node_id)
                    self.deploy_config(node_id, config_file_path)
                    self.wipe_node(node_id)
                    self.start_node(node_id)
                    health_targets.append(
                        {"device_name": target_node.get('hostname'), "node_id": node_id})
                else:
                    logging.info("Configurations are identical.")

        if health_targets:
            logging.info(
                "Since we rebooted some node(s), waiting 5 minutes and will conduct a health check on that node")
            with open("health_targets.json", "w", encoding="UTF-8") as ht_file:
                ht_file.write(json.dumps(health_targets))
            time.sleep(300)
        else:
            logging.info(
                "Nothing seemed to change, ensuring health_targets.json still exists to prevent tb_and_health from executing")
            with open("health_targets.json", "w", encoding="UTF-8") as ht_file:
                ht_file.write(json.dumps(health_targets))

    @staticmethod
    def wait_for_noshut() -> None:
        """
        Each router has an EEM script that will start after ~60 seconds
        Creating this function just for documentation purposes
        """
        logging.info(
            "Waiting 60 seconds to hopefully let the router EEM script kick off")
        time.sleep(60)

    @staticmethod
    def get_current_epoch_time_ms() -> int:
        """
        Needed for various API calls to eveng
        returns current epoch time
        """
        return int(time.time() * 1000)
