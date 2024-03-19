"""
tests against the Configuration class
"""
import pytest
from ipaddress import IPv4Network, IPv4Address


@pytest.mark.parametrize("expected_interface_names", [[
    "GigabitEthernet1/0",
    "GigabitEthernet1/0/0",
    "GigabitEthernet1/5/1.1234",
    "TenGigabitEthernet1",
    "TenGigabitEthernet1/0",
    "TenGigabitEthernet1/0/0",
    "TenGigabitEthernet1/5/1.1234",
    "Ethernet1",
    "Ethernet1/0",
    "Ethernet1/0/0",
    "Ethernet1/5/1.1234",
    "FastEthernet1",
    "FastEthernet1/0",
    "FastEthernet1/0/0",
    "FastEthernet1/5/1.1234",
    "Serial1",
    "Serial1/0",
    "Serial1/0/0",
    "Serial1/5/1.1234",
    "TweGigabitEthernet1",
    "TweGigabitEthernet1/0",
    "TweGigabitEthernet1/0/0",
    "TweGigabitEthernet1/5/1.1234",
    "PortChannel1",
    "PortChannel1/0",
    "PortChannel1/0/0",
    "PortChannel1/5/1.1234",
    "BDI123",
    "Vlan20"
]])
def test_interface_conversion(r1_initiated: object, expected_interface_names: list):
    """
    Iterate over known interfaces and assert they have correct key of correct type.
    """
    assert isinstance(r1_initiated.l3_interfaces, list), "l3 interfaces not returning a list"
    for interface in expected_interface_names:
        interface_names = [interface['if_name'] for interface in r1_initiated.l3_interfaces]
        assert interface in interface_names, f"Expect interface {interface} not found"
    
    for present_interface in r1_initiated.l3_interfaces:
        assert isinstance(present_interface["ip_subnet"],  IPv4Network), "ip_subnet not an IPv4Network object"
        assert isinstance(present_interface["ip_address"], IPv4Address), "ip_address not an IPv4Address object"

    for interface in r1_initiated.l3_interfaces:
        assert isinstance(interface, dict), "Interface within l3_interfaces not a dict"

def test_bad_word(r1_initiated: object):
    """
    Test that a bad word is not present in the configuration
    """
    
