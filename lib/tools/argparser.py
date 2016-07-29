from lib.modules import COMMANDS


def args(*args, **kwargs):
    """Attaches argument to a __dict__ attribute within a specific function or method. The __dict__
    attribute is later used in command line argument parsing from every submodule's methods."""
    # decorator for argument definitions
    def _decorator(func):
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
