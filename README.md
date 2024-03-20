# ci_cli
Tooling for a simple CI-CD (delivery) pipeline for Cisco IOS and IOS-XE devices using raw configurations instead of an IaC approach. Provides tooling to convert production configurations to lab configurations, deploy and maintain a lab in EVE-NG, create a pyATS testbed, and run predefined pyATS testscripts.
## Setup
This tool can either be ran on a standalone linux box, or within a Docker container. It is recommended to use the provided Dockerfile definition, especially if this tool is used within a CI pipeline
### Docker image build
If you would like to test the tool using the Docker container locally, follow these steps:
```sh
# clone this repo
git clone https://github.com/jamesduv9/ci_cli.git
# change directories the app
cd ci_cli
# build the docker image
docker image build -t ci_cli .
# start and exec into the docker container
docker run -it ci_cli /bin/bash
# Run the ci_cli.py tooling 
python3 ci_cli.py (command) (options)
```
## config.py
The included config.py file can be modified to meet your needs by adding/removing functionality. By default, the majority of these configs are self explanatory, however the following specific to your lab deployment and should be adjusted:

- `CSR_NODES` - This is a list of hostnames that you would like to deploy as a CSR node instead of a vios node. For example, if you have a router that emulates a Cisco CUBE, you'd want to include that device's hostname in the list, since iosv does not have that capability
- `MANAGEMENT_SUBNETS` - This is a dictionary that maps user id to management network, and is used during the create_configs command's --gitlab_user option. For example you can use the dictionary keys to represent gitlab users, and include that userid in the ci pipeline with ${GITLAB_USER_ID}. The management_network and management_default_gw keys are used to allocate "out of band" management through a Cloud0 interface in the lab, as well as provide SecureCRT session files for each device.
- `CSRV_IMAGE_TYPE` - Used to determine which template to use when deploying your CSR nodes. Only valid options are c8000v and csr1000vng
- `CSRV_IMAGE` and `IOSV_IMAGE` These should be a string containing the iosv image version and csrv image version. 

## Commands
The following cli options are available using `python ci_cli.py`, each of these commands can represent a different stage in a CI-CD pipeline.
```sh
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

### ENV Vars required
These commands require the following environmental variables set for EVE login.
- `EVE_USERNAME` - Should be your username for EVE
- `EVE_PASSWORD` - Should be your password for EVE
- `EVE_URL` - Full url for your local eve server (https://[eve-ip])
I recommend creating a new EVE account specifically for this purpose, otherwise you will get constant login conflicts

### create_configs command
```sh
# python3 ci_cli.py create_configs --help   
root        : INFO     Logging initiated
Usage: ci_cli.py create_configs [OPTIONS]

  Takes your passed in directory of configurations with various interfaces
  formats them to work in an EVE lab

Options:
  --source_path TEXT      MANDATORY: path to your configuration directory you
                          want to convert  [required]
  --output_path TEXT      MANDATORY: Provide the destination directory for the
                          configs, interface mapping, and tfvars json file.
                          Cannot equal source_path  [required]
  --vlan_seed INTEGER     OPTIONAL: Which vlan to start incrementing at, avoid
                          setting too high. Must be greater than 1  [default:
                          2]
  --config_file_ext TEXT  OPTIONAL: Tells the script which file extension your
                          configs will use inside the source_path directory
                          [default: .txt]
  --gitlab_user TEXT      GITLAB_USER_ID predefined var, used to find
                          management subnet for specific user  [required]
  --help                  Show this message and exit.
```
At a high level, here's how the create_configs command works:
1. Iterate through all configuration files in the provided --source_path directory
2. Collect interface names, ip addresses, and other interface configuration details from all devices
3. Compare all ip addresses and subnets of all interfaces, if two interfaces are seen to be in the same subnet, assign them a dedicated VLAN ID, starting at the provided vlan seed, and incrementing 1 per vlan
4. Once all interfaces are determined and vlans are allocated based on common subnets, replace all interface names and references in all configurations to GigabitEthernet0/1.[assigned vlanid] or GigabitEthernet1.[assigned vlanid] if using a CSRv. 
5. Given a management subnet assigned to a specific user, assigns a management address to GigabitEthernet0/2, GigabitEthernet2. This will later be connected to an external eve-ng bridge (cloud0)
6. Add appropriate encapsulation configuration to each interface
7. Remove all current aaa configurations on the device (config.py options)
8. Add username and password of admin:admin to all devices
9. Creates a labvars.json file that will later give instructions to `create_or_mod_lab` command
10. Creates an overall_interface_map.json file that provides a map between previous production interfaces, and lab interface. This is later used in the test_handler.py job file
11. Creates a folder called securecrt_sessions that provides a single securecrt ini file for each device in the topology with their new management GigabitEthernet2 address. Can easily drop this into your `%appdata%/roaming/VanDyke/sessions` folder 

### create_or_mod_lab command
```sh
# python3 ci_cli.py create_or_mod_lab --help
root        : INFO     Logging initiated
Usage: ci_cli.py create_or_mod_lab [OPTIONS]

  Use the EVEInterface class to create a lab in eve, or modify it and output
  health_targets.json source path MUST contain all the config files in a flat
  structure and the labvars.json file

Options:
  --source_path TEXT  MANDATORY: path to your configuration directory you want
                      to convert  [required]
  --lab_name TEXT     Name of the lab you want to create  [required]
  --help              Show this message and exit.
```
This command either creates a new lab, or modifies an existing lab to meet the provided configurations. 
For the create action the following steps take place:
1. Given the provided source path, retrieve the labvars.json file
2. Use the labvars.json as instructions to create an EVE-NG lab topology
3. Waits 10 minutes to ensure all devices are powered up

For the mod action the following steps take place:
1. An API call is made to EVE to determine if the currently requested lab exists, if so, we need to modify the lab instead of create
2. Grabs all the provided configurations and compares them with the saved startup configurations within EVE-NG
3. Any node that has a different configuration is stopped, loaded with the correct config, wiped,   and reloaded
4. Each of the nodes that did get reloaded are added to a special health_targets.json, which is used as an optional instruction in the `tb_and_health` command to narrow the scope of the health check

## tb_and_health command
```sh
# python3 ci_cli.py tb_and_health --help
root        : INFO     Logging initiated
Usage: ci_cli.py tb_and_health [OPTIONS]

  Builds a pyATS testbed and does the self healing health check.. Can either
  target all nodes in a lab, or a subset by providing a health_targets file
  created from a previous run. This scenario would happen if a small change
  happened to a lab after intial build, we don't want to recheck every device
  if only one rebooted

Options:
  --health_targets TEXT  Path to health targets, for testing specific nodes
  --lab_name TEXT        Name of the lab you want to generate testbed and self
                         heal  [required]
  --tb_output_path TEXT  Path that you want the testbed file saved to
                         [default: ./testbed.yml; required]
  --help                 Show this message and exit.
```
This command creates a pyats testbed file for a given EVE-NG lab, and attempts to login to each node to test it's health using pyATS. Any device that does not appear healthy will be rebooted. 
This command has an optional --health_targets option that can take in a json file from the `create_or_mod_lab` command that specifies to only test the health of certain nodes.

## teardown_lab command
```sh
# python3 ci_cli.py teardown_lab --help
root        : INFO     Logging initiated
Usage: ci_cli.py teardown_lab [OPTIONS]

  Stop all nodes and then delete the lab

Options:
  --lab_name TEXT  Name of the lab you want to delete  [required]
  --help           Show this message and exit.
```
Does what the command says, given the provided lab_name this command will iterate through all nodes in a lab and shut them down and finally delete the lab altogether. This would be ran for example, when a merge request is merged and deleted in a CI pipeline.