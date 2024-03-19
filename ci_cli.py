"""
cicd_tool.py
Author: James Duvall
Purpose: Core CLI tool that will be the primary interface for the cicd pipeline to interact with lab deployment/management 
and config conversion
"""

import click
import os
import sys
import json
import logging
from tqdm import tqdm
from datetime import datetime
from ci_cli.converter import Converter
from ci_cli.ine_config_builder import INEConfigBuilder
from ci_cli import eve_interface


@click.group(name="main")
@click.pass_context
@click.option("--debug_level", default="INFO",  type=click.Choice(["DEBUG", "INFO", "WARNING"]))
def main(ctx, debug_level):
    """
    Main group for all commands, uses Click's context feature to set logging for all other commands
    Determine the logging level and setup logger for commands
    """

    console = logging.StreamHandler()
    formatter = logging.Formatter('%(name)-12s: %(levelname)-8s %(message)s')
    console.setFormatter(formatter)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_filename = f"logs/log_{timestamp}.log"

    file_handler = logging.FileHandler(log_filename)
    file_handler.setFormatter(formatter)

    # Set level for console handler based on debug_level
    if debug_level == "DEBUG":
        console.setLevel(logging.DEBUG)
    elif debug_level == "INFO":
        console.setLevel(logging.INFO)
    else:
        console.setLevel(logging.WARNING)
    logging.getLogger('').addHandler(console)
    file_handler.setLevel(logging.DEBUG)
    logging.getLogger('').addHandler(file_handler)
    if debug_level in ["DEBUG", "INFO"]:
        logging.getLogger('').setLevel(
            logging.DEBUG if debug_level == "DEBUG" else logging.INFO)
    else:
        logging.getLogger('').setLevel(logging.WARNING)

    logger = logging.getLogger(__name__)
    ctx.obj = logger

    # This log will be processed by the root logger and then by the console handler if its level allows it
    logging.info("Logging initiated")


@main.command(name="create_configs")
@click.pass_obj
@click.option(
    "--source_path",
    help="MANDATORY: path to your configuration directory you want to convert",
    required=True,
)
@click.option(
    "--output_path",
    help="MANDATORY: Provide the destination directory for the configs, interface mapping, and tfvars json file. Cannot equal source_path",
    required=True,
)
@click.option(
    "--vlan_seed",
    help="OPTIONAL: Which vlan to start incrementing at, avoid setting too high. Must be greater than 1",
    default=2, show_default=True
)
@click.option(
    "--config_file_ext",
    help="OPTIONAL: Tells the script which file extension your configs will use inside the source_path directory",
    default=".txt", show_default=True
)
@click.option(
    "--gitlab_user", help="GITLAB_USER_ID predefined var, used to find management subnet for specific user", required=True, type=click.STRING
)
def create_configs(
    logger, source_path: str, output_path: str, vlan_seed: str, config_file_ext: str, gitlab_user: str
) -> None:
    """
    Takes your passed in directory of configurations with various interfaces formats them to work in an EVE lab
    """
    if output_path == source_path:
        logging.warning(
            "Please provide a unique directory to create for the output files. Hint: Cannot be the same as config source directory"
        )
        sys.exit(1)
    if vlan_seed <= 1:
        logging.warning("The vlan seed cannot be less than 2.")
        sys.exit(1)
    conv = Converter(
        source_path=source_path,
        output_path=output_path,
        vlan_seed=vlan_seed,
        config_file_ext=config_file_ext,
        gitlab_user=gitlab_user
    )
    
    # load all files with specified extension
    conv.load_configs()
    # parse out all l3 interfaces in the config files
    print("Initializing Configurations")
    for config in tqdm(conv.configs):
        
        config.get_current_parsed_config()
        config.get_hostname()
        config.get_device_type()
        config.get_l3_interfaces()
        

    # Finds common subnets and assigns vlanids
    conv.subnet_compare()
    # replaces the old configuration interfaces with new subintf
    conv.manipulate_configs()
    for config in tqdm(conv.configs):
        config.create_interface_mapping()

    # Builds the interface mapping to show old vs new
    conv.save_interface_mapping()
    conv.create_lab_vars()
    conv.save_securecrt_sessions()
    print("Completed")


@main.command("build_ines")
@click.pass_obj
@click.option(
    "--source_path",
    help="MANDATORY: path to your configuration directory you want to convert",
    required=True,
)
def build_ines(logger, source_path):
    """
    With self.source_path, open all configurations and build the config classes associated with each.
    This will create a new txt file in the provided source path. Generally this is ran before create configs if INEs are in play
    """
    logger.info("Initialized Logger")
    for dirpath, _, filenames in os.walk(source_path):
        for file_ in filenames:
            if file_.endswith("INE.yml"):
                INEConfigBuilder(file_path=dirpath, file_=file_)


@main.command("create_or_mod_lab")
@click.pass_obj
@click.option(
    "--source_path",
    help="MANDATORY: path to your configuration directory you want to convert",
    required=True,
    type=click.STRING
)
@click.option("--lab_name", required=True, type=click.STRING, help="Name of the lab you want to create")
def create_or_mod_lab(logger, lab_name: str, source_path: str):
    """
    Use the EVEInterface class to create a lab in eve, or modify it and output health_targets.json
    source path MUST contain all the config files in a flat structure and the labvars.json file
    """
    logger.info("Lab creation started")
    try:
        assert os.path.isfile(f"{source_path}/labvars.json")
    except AssertionError:
        logging.error(
            f"labvars.json not found at path {source_path}/labvars.json")
        sys.exit(1)
    
    lab = eve_interface.EVEInterface(
        lab_name=lab_name, source_path=source_path)
    if lab.exists():
        print(f"Building lab from scratch with name {lab_name}")
        lab.mod_lab_from_cicd()
    else:
        print(f"Lab already exists, modifying lab {lab_name} to meet intended state")
        lab.build_lab_from_cicd()


@main.command("tb_and_health")
@click.pass_obj
@click.option("--health_targets", type=click.STRING, help="Path to health targets, for testing specific nodes")
@click.option("--lab_name", required=True, type=click.STRING, help="Name of the lab you want to generate testbed and self heal")
@click.option("--tb_output_path", required=True, default="./testbed.yml", show_default=True, type=click.STRING, help="Path that you want the testbed file saved to")
def tb_and_health(logger, health_targets: str, lab_name: str, tb_output_path: str):
    """
    Builds a pyATS testbed and does the self healing health check..
    Can either target all nodes in a lab, or a subset by providing a health_targets file created from a previous run.
    This scenario would happen if a small change happened to a lab after intial build, we don't want to recheck every device
    if only one rebooted
    """
    lab = eve_interface.EVEInterface(lab_name=lab_name)
    lab.build_testbed(tb_output_path=tb_output_path)
    if health_targets:
        with open(health_targets, 'r') as ht_file:
            target_devices = json.loads(ht_file.read())

        lab.health_check(target_devices=target_devices)
    else:
        lab.health_check()


@main.command("teardown_lab")
@click.pass_obj
@click.option("--lab_name", required=True, type=click.STRING, help="Name of the lab you want to delete")
def teardown_lab(logger, lab_name: str):
    """
    Stop all nodes and then delete the lab
    """
    lab = eve_interface.EVEInterface(lab_name=lab_name)
    lab.teardown_lab_from_cicd()


if __name__ == "__main__":
    main()
