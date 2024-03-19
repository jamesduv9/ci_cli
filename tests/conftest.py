"""
Tests WIP
"""

import pytest
import os
from ci_cli.converter import Converter
from ci_cli.configuration import Configuration
from ciscoconfparse import CiscoConfParse


@pytest.fixture(scope="session", autouse=True)
def set_env_variable():
    print("running")
    os.environ["cicd_context"] = "TEST"


@pytest.fixture(scope="module")
def t_converter():
    conv = Converter(
        source_path="tests/test_source",
        output_path="tests/test_dest",
        vlan_seed=2,
        config_file_ext=".txt",
        gitlab_user="1234"
    )
    return conv

@pytest.fixture(scope="module")
def r1_config():
    return Configuration("r1.txt", "tests/test_source/r1.txt")

@pytest.fixture(scope="module")
def r1_initiated(r1_config):
    r1_config.get_current_parsed_config()
    assert isinstance(r1_config.current_parsed_config, CiscoConfParse), "current_parsed_config property is  not a CiscoConfParse object"
    r1_config.get_hostname()
    assert r1_config.hostname == "r1", "Hostname does not reflect config"
    r1_config.get_device_type()
    if r1_config.device_type == "csrv":
        assert r1_config.interface_name == "GigabitEthernet1", "csrv but not g1 for main interface"
        assert r1_config.management_interface == "GigabitEthernet2", "csrv not but g2 for management"
    elif r1_config.device_type == "iosv":
        assert r1_config.interface_name == "GigabitEthernet0/1", "iosv but not g0/1 for main interface"
        assert r1_config.management_interface == "GigabitEthernet0/2", "iosv but not g0/2 for management"
    r1_config.get_l3_interfaces()

    return r1_config


@pytest.fixture(scope="module")
def r2_config():
    return Configuration("r2.txt", "tests/test_source/r2.txt")

@pytest.fixture(scope="module")
def r2_initiated(r2_config):
    """
    Creates a Configuration object for r2 and initiates it
    """
    r2_config.get_current_parsed_config()
    assert isinstance(r2_config.current_parsed_config, CiscoConfParse), "current_parsed_config property is  not a CiscoConfParse object"
    r2_config.get_hostname()
    assert r2_config.hostname == "r2", "Hostname does not reflect config"
    r2_config.get_device_type()
    if r2_config.device_type == "csrv":
        assert r2_config.interface_name == "GigabitEthernet1", "csrv but not g1 for main interface"
        assert r2_config.management_interface == "GigabitEthernet2", "csrv not but g2 for management"
    elif r2_config.device_type == "iosv":
        assert r2_config.interface_name == "GigabitEthernet0/1", "iosv but not g0/1 for main interface"
        assert r2_config.management_interface == "GigabitEthernet0/2", "iosv but not g0/2 for management"
    r2_config.get_l3_interfaces()

    return r2_config

@pytest.fixture(scope="module")
def loaded_converter(t_converter, r1_initiated, r2_initiated):
    """
    Creates a Converter object and loads it with the initiated Configuration objects
    """
    t_converter.configs.append(r1_initiated)
    t_converter.configs.append(r2_initiated)
    assert len(t_converter.configs) == 2, "Configs not present in converter"
    return t_converter