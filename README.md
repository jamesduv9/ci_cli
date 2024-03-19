# ci_cli
Tooling for a simple CI-CD pipeline using Cisco IOS and IOS-XE devices. Converts production configurations straight from a Cisco box into lab configs and deploys them into an EVE-NG lab.

## Commands
The following cli options are available using `python ci_cli.py`, each of these commands can represent a different stage in a CI-CD pipeline.
```
# python3 ci_cli.py 
Usage: ci_cli.py [OPTIONS] COMMAND [ARGS]...

  Main group for all commands, uses Click's context feature to set logging for
  all other commands Determine the logging level and setup logger for commands

Options:
  --debug_level [DEBUG|INFO|WARNING]
  --help                          Show this message and exit.

Commands:
  build_ines         With self.source_path, open all configurations and...
  create_configs     Takes your passed in directory of configurations...
  create_or_mod_lab  Use the EVEInterface class to create a lab in eve,...
  tb_and_health      Builds a pyATS testbed and does the self healing...
  teardown_lab       Stop all nodes and then delete the lab
```

### create_configs command
At a high level, here's how the create_configs command works:
1. Iterate through all configuration files in the provided --source_path directory
2. If the configuration ends in `TL.yml`, template the configuration and save the new configuration in the source_path
3. Collect interface names, ip addresses, and other configuration details from all devices
4. Compare all ip addresses and subnets of all interfaces, if two interfaces are seen to be in the same subnet, assign them a dedicated VLAN ID, starting at 2, and incrementing 1 per vlan
5. Once all interfaces are determined and vlans are allocated based on common subnets, replace all interface names and references in all configurations to GigabitEthernet0/1.[assigned vlanid] or GigabitEthernet1.[assigned vlanid] if using a CSRv. 
6. Given a management subnet assigned to a specific user, assigns a management address to GigabitEthernet0/2 | 2. This will later be connected to an external eve-ng bridge (cloud0)
7. Add appropriate encapsulation configuration to each interface
8. Remove all current aaa configurations on the device
9. Add username and password of admin:admin to all devices
10. Creates a labvars.json file that will later give instructions to `create_or_mod_lab` command
11. Creates an overall_interface_map.json file that provides a map between previous production interfaces, and lab interface. This is later used in the test_handler.py job file
12. Creates a folder called securecrt_sessions that provides a single securecrt ini file for each device in the topology with their GigabitEthernet2 address. Can easily drop this into your `%appdata%/roaming/VanDyke/sessions` folder