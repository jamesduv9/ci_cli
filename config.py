"""
Purpose: Configurable values for configuration builds
This can be modified in the future to add more commands to each converted configuration
"""

# Temp fix for dhcp happening when not desired on management int
NO_DHCP_PLEASE = """
ip access-list extended no_dhcp_please
 10 deny udp any any eq bootps
 20 deny udp any any eq bootpc
 30 permit ip any any
"""

# Appended to start of config to add our admin:admin
AAA_COMMANDS = """
aaa new-model
aaa authentication login default local
aaa authentication enable default none
aaa authorization exec default local
username admin privilege 15 secret admin
"""
#Lines added for LAB_MGMT vrf
LAB_MGMT = """
vrf definition LAB_MGMT
 address-family ipv4 unicast
"""

# Add telnet input on line vty 0 4
LINE_VTY = """
line vty 0 4
 exec-timeout 0 0
 transport input telnet
"""

#Remove logging console to speed up boot (without tunnel interfaces take forever to log state)
NO_LOGGING_CON = """
no logging console
"""

#Required on CSR8000v nodes in order to boot at highest license level without a reboot
LICENSE_BOOT = """
license boot level network-premier addon dna-premier
"""

# Appended to start of config to automatically no shut GigabitEthernet0/1 on boot
INT_AUTO_NOSHUT_IOSV = """
event manager applet on-boot
event timer cron cron-entry "@reboot"
action 1.0 cli command "enable"
action 1.1 cli command "configure terminal"
action 1.2 cli command "interface range GigabitEthernet0/1-2"
action 1.3 cli command "no shutdown"
action 1.4 cli command "no logging console"
action 1.5 cli command "exit"
"""

# Appended to start of config to automatically no shut GigabitEthernet1 on boot
INT_AUTO_NOSHUT_CSRV = """
event manager applet on-boot
event timer cron cron-entry "@reboot"
action 1.0 cli command "enable"
action 1.1 cli command "configure terminal"
action 1.2 cli command "interface range GigabitEthernet1-2"
action 1.3 cli command "no shutdown"
action 1.4 cli command "no logging console"
action 1.5 cli command "exit"
"""

# Combine the above configs for CSRV
CSRV_CONFIGS = INT_AUTO_NOSHUT_CSRV + NO_DHCP_PLEASE + AAA_COMMANDS + NO_LOGGING_CON + LICENSE_BOOT + LAB_MGMT + LINE_VTY

#Combine the above configs for iosv
IOSV_CONFIGS = INT_AUTO_NOSHUT_IOSV + NO_DHCP_PLEASE + NO_LOGGING_CON + AAA_COMMANDS + LAB_MGMT + LINE_VTY

#Any lines in the config matching these patterns will be removed along with their child configs if any
BAD_SECTIONS = [
    "line vty",
    "crypto pki",
    "aaa",
    "username",
    "enable secret",
    "logging console",
    "logging buffered"
]
# Hostname of nodes that should be deployed as a CSR8000v
# WARNING - Only do this for nodes that absolutely need to be 8ks, these are extremely resource intensive
CSR_NODES = [
    "CSRvRouterHostname"
]

#Management subnets, will allocate an address to each device on port 2
#The dictionary key is your Gitlab User ID - https://gitlab.com/-/profile - User ID field
MANAGEMENT_SUBNETS = {
    #James homelab
    "1": {
        "management_network": "192.168.1.0/24",
        "management_default_gw": "192.168.1.254"
    },
}

#Type of CSRv image
#VALID VALUES csr1000vng or c8000v
CSRV_IMAGE_TYPE = "c8000v"

#The CSRv and vIOS node image that you have loaded and installed for EVE-NG
CSRV_IMAGE = "c8000v-17.09.04a"
IOSV_IMAGE = "vios-adventerprisek9-m.SPA.159-3.M6"