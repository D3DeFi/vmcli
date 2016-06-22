#!/usr/bin/env python

import sys
import argparse

from lib.tools.logger import logger
from lib.tools.argparser import get_arg_subparsers
from lib.connector import connect
from lib.modules import module_loader
from lib.exceptions import VmCLIException

from lib.constants import LOG_LEVEL_CHOICES

# test if pyVmomi package is installed
try:
    from pyVmomi import vim, vmodl
except ImportError as e:
    logger.critical('{}, make sure it is installed!'.format(e.message))
    sys.exit(1)


if __name__ == '__main__':
    # load subcommands from modules
    commands = module_loader(__file__)

    parser = argparse.ArgumentParser(description='Command line utility to interact with VMware vSphere API')
    parser.add_argument('--log-level', help='set log level', choices=LOG_LEVEL_CHOICES)
    parser.add_argument('-q', '--quiet', help='quiet mode, no messages are shown', action='store_true')
    parser.add_argument('-u', '--username', help='login name to use for vcenter', default=None)
    parser.add_argument('-p', '--password', help='password for specified login', default=None)
    parser.add_argument('-s', '--vcenter', help='name of vcenter, which to connect to', default=None)
    parser.add_argument('-i', '--insecure', help='skip SSL verification', action='store_true')
    # Load in options from Command classes
    parser = get_arg_subparsers(parser)
    args = parser.parse_args()

    if args.log_level:
        logger.setLevel(args.log_level)
    if args.quiet:
        logger.quiet()

    connection = connect(args.vcenter, args.username, args.password, args.insecure)

    # load appropiate command, argparse will handle correct input for us
    command = commands[args.subcommand](connection=connection)

    try:
        command.execute(args)
    except VmCLIException as e:
        logger.critical(e.message)
        sys.exit(1)
