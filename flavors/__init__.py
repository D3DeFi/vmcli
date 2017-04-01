import sys
import yaml
from lib.tools.logger import logger


def load_vm_flavor(name):
    """Attempts to load VM configuration from flavors/ directory by searching for file named
    as an argument provided. Found file must contain valid YAML directives."""
    if name:
        try:
            module = yaml.safe_load(file('flavors/{}.yml'.format(name)))
            # Ensure returned object is dictionary
            return dict(module)
        except IOError as e:
            logger.error('No such flavor named {}!'.format(name))
            sys.exit(1)
        except yaml.scanner.ScannerError as e:
            logger.error('Flavor syntax error {}'.format(str(e.context_mark).lstrip()))
            sys.exit(1)
        except ValueError:
            logger.error('Unable to convert flavor {} into dictionary object'.format(name))
            sys.exit(1)
    else:
        return {}
