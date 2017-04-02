import lib.config as conf

from lib.modules import COMMANDS
from flavors import load_vm_flavor


# mappings between command-line arguments and lib.config.VALUES are stored here
__args_mappings = {}


def args(*args, **kwargs):
    """Attaches argument to a __dict__ attribute within a specific function or method. The __dict__
    attribute is later used in command line argument parsing from every submodule's methods."""
    # decorator for argument definitions
    def _decorator(func):
        # If map arguments is present in @args decorator, pop it and create mapping between lib.config.VALUE and arg
        if 'map' in kwargs:
            # if argument does not have 'dest' parameter, it's name will be used instead
            dest = kwargs.get('dest', None) or args[0].lstrip('-')
            __args_mappings[dest.replace('-', '_')] = kwargs.pop('map')

        func.__dict__.setdefault('args', []).insert(0, (args, kwargs))
        return func
    return _decorator


def get_arg_subparsers(parser):
    """Iterates over function's or method's __dict__['args'] variable to load arguments into arg parser."""
    subparsers = parser.add_subparsers(help='sub-command help', dest='subcommand')
    for command in COMMANDS:
        # spawn empty object for method iteration and docstring retrieval
        obj = COMMANDS[command]()
        # use docstring as a help and define subcommand in argument parser
        desc = getattr(obj, '__doc__', None)
        sub_parser = subparsers.add_parser(command, help=desc)

        # get all class public methods
        command_methods = [getattr(obj, m) for m in dir(obj) if callable(getattr(obj, m)) and not m.startswith('_')]
        # iterate over callable methods and load defined arguments
        arguments = dict()
        for method in command_methods:
            for args, kwargs in getattr(method, 'args', []):
                # if argument does not have 'dest' parameter, it's name will be used instead
                dest = kwargs.get('dest', None) or args[0].lstrip('-')
                if dest not in arguments:
                    sub_parser.add_argument(*args, **kwargs)
                # make sure only first argument is used if two or more are found with the same name
                arguments.setdefault(dest, [args, kwargs])

    return parser


def argument_loader(args):
    """Iterates over loaded command line arguments and fills any unprovided arguments from other sources.
    Arguments are filled in this order: command-line arguments, flavors, env variables, config file, defaults."""
    flavor = {}
    # First check if we can lookup values in flavor
    if hasattr(args, 'flavor') and args.flavor:
        flavor = load_vm_flavor(args.flavor)

    # Iterate over command line arguments
    for argument in [x for x in dir(args) if not x.startswith('_')]:
        value = getattr(args, argument, None)
        if not value:
            # If value for argument was not provided from cmd line, try flavor
            if flavor and flavor.get(argument, None):
                val = flavor.get(argument)
                setattr(args, argument, val)
            # if both cmd line and flavor haven't provided value, try defaults in lib.config
            elif argument in __args_mappings:
                val = getattr(conf, __args_mappings[argument])
                setattr(args, argument, val)

    return args
