import sys
from lib.tools.logger import logger
from importlib import import_module


def load_vm_flavor(name):
    """Attempts to load VM configuration from flavors/ directory by searching for file named
    as an argument provided. Found file must contain valid Python dictionary named flavor."""
    if name:
        try:
            module = import_module('flavors.{}'.format(name))
            # Check if flavor is dictionary
            if isinstance(module.flavor, dict):
                return module.flavor
            else:
                logger.error('Defined flavor does not contain valid Python dictionary! Aborting...')
                sys.exit(1)
        except ImportError as e:
            logger.error('No such flavor named {}!'.format(name))
            sys.exit(1)
    else:
        return {}
