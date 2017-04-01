Description
-----------
Vmcli aims to provide command line tool to allow virtual machine management and delivery by interacting with VMware's vSphere API. It implements simple methods and classes for modules expansion, making addition of new vmcli subcommands easy as inheriting classes in the Python programming language.

Other aim is to make as much directives configurable as possible. Options can be provided via default values, command line arguments, configuration file directives and environment variables. For the create or clone subcommands there are flavors too, these represents templates for virtual machine's hardware configuration.

Installation
------------

To begin using vmcli you need to have python2.7, python-virtualenv and python-pip packages installed. Then execute the following steps:
```
  virtualenv env
  source env/bin/activate
  pip install -r requirements.txt
  vmcli.py --help
```

If you plan to use --net-cfg option during clone/create subcommands, ensure appropriate script is present in your template (/usr/share/vmcli/provision-interfaces.sh). Example of this script can be found in this repository in examples/provision-interfaces.sh

Configuration directives
------------------------

Options can be provided and overriden in a variety of ways. Foremost being command line arguments. Specific ways to provide configuration to the vmcli program are explained below <strong>in the exact order as they are prioritized.</strong>

### 1. Command line arguments

Arguments being most straightforward way to pass configuration options to the running program. All the available command line arguments can be found via --help argument passed to the program like this - ```vmcli.py --help```.

Help argument (--help) can be passed to any subcommand as well. Available subcommands of the vmcli program are listed in the positional arguments section of the help output delivered by main program (shown with the command above).

### 2. Flavors (For clone and create operations only)

Flavors are specific feature for virtual machine deploy operations such as create, create-empty or clone. They work similar to flavors used in any other tools or virtualization platforms (OpenStack's flavors, AWS's instance types, etc.) and can be defined by the user himself.

To define custom flavor, **start with copying file** examples/flavor.yml.example into flavors/**some-name**.yml. The name you choose will be later used when pointing vmcli program to flavor you wish to use. This file contains only Python dictionary representation of data.


**Fill each row** as you desire respecting formatting in example. If you want to omit some directives, simply delete entire row or type in None as a value: ```folder: None``` and that value will be fetched from other sources listed in this section.

When flavor is finally defined, you can provide ```--flavor some-name``` option to one of the subcommands which support flavors. For example: ```./vmcli.py create --flavor m1_tiny```

### 3. Environment variables

When vmcli program does not find any cmd line argument or flavor directive for particular setting, it tries to load its value from environment variable, which name is hardcoded in the source code itself. For now, to get list of available environment variables and use some of them, simply run:
<pre>grep -o "'VMCLI[_A-Z]*'" lib/config.py
export VMCLI_LOG_PATH=/var/log/vmcli.log</pre>

If you are unsure what data to fill to a specific ENV variable you can study simple lib/config.py file and its ```get_config(category, name, env_variable, data_type, default_value)``` function calls.

There is one special environment variable ```VMCLI_CONFIG_FILE```, which points program to a specific vmcli.yml config file. This way, you can define multiple config files (e.g. ~/.dev.yaml, ~/.prod.yaml).

### 4. Config file (yaml)
### 5. Default values

Examples
--------

Adding new/modifying commands
-----------------------------

TODO
----

 - implement cache to speed up get_obj calls
