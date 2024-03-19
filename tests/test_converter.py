import pytest
from ipaddress import IPv4Address, IPv4Network


@pytest.mark.parametrize("expected_keys", [["config", "if_name", "ip_address", "ip_subnet"]])
def test_l3_interfaces_pre_compare(loaded_converter: object, expected_keys: list):
    """
    Tests that the l3_interfaces of each config have the required keys before subnet compare
    """
    for config in loaded_converter.configs:
        for l3_interface in config.l3_interfaces:
            for key_ in l3_interface.keys():
                assert key_ in expected_keys


@pytest.mark.parametrize("expected_keys", [["config", "if_name", "ip_address", "ip_subnet", "new_vlanid"]])
def test_l3_interfaces_post_compare(loaded_converter: object, expected_keys: list):
    """
    Tests that the l3_interfaces of each config have the required keys post subnet compare
    """
    loaded_converter.subnet_compare()
    for config in loaded_converter.configs:
        for l3_interface in config.l3_interfaces:
            for key_ in l3_interface.keys():
                assert key_ in expected_keys


@pytest.mark.parametrize("matching_ints", [{2: [{'config': 'tests/test_source/r1.txt', 'if_name': 'GigabitEthernet1', 'ip_subnet': IPv4Network('10.1.1.0/30'), 'ip_address': IPv4Address('10.1.1.1'), 'new_vlanid': 2}, {'config': 'tests/test_source/r2.txt', 'if_name': 'GigabitEthernet0/3/2', 'ip_subnet': IPv4Network('10.1.1.0/30'), 'ip_address': IPv4Address('10.1.1.2'), 'new_vlanid': 2}],
                                            31: [{'config': 'tests/test_source/r1.txt', 'if_name': 'Vlan20', 'ip_subnet': IPv4Network('10.2.8.0/30'), 'ip_address': IPv4Address('10.2.8.1'), 'new_vlanid': 31}, {'config': 'tests/test_source/r2.txt', 'if_name': 'Vlan21', 'ip_subnet': IPv4Network('10.2.8.0/30'), 'ip_address': IPv4Address('10.2.8.2'), 'new_vlanid': 31},]}])
def test_l3_interfaces_match(loaded_converter: object, matching_ints):
    """
    Go over a couple known matching interfaces to see if they are assigned the same vlanid
    """
    for vlan_id, int_values in matching_ints.items():
        matching_l3_ints = [
            interface for config in loaded_converter.configs for interface in config.l3_interfaces if interface["new_vlanid"] == vlan_id]
        assert matching_l3_ints == int_values, f"vlan {vlan_id} does not have the correct values we expected"

