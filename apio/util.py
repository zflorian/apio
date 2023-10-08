"""DOC: TODO"""
# -*- coding: utf-8 -*-
# -- This file is part of the Apio project
# -- (C) 2016-2018 FPGAwars
# -- Author Jesús Arroyo
# -- Licence GPLv2
# -- Derived from:
# ---- Platformio project
# ---- (C) 2014-2016 Ivan Kravets <me@ikravets.com>
# ---- Licence Apache v2

import string
import sys
import os
import re
import json
import locale
import platform
import subprocess
from threading import Thread
from os.path import isdir, isfile, join, dirname, exists
from pathlib import Path

import click
import semantic_version
from serial.tools.list_ports import comports
import requests

from apio import LOAD_CONFIG_DATA

# ----------------------------------------
# -- Constants
# ----------------------------------------

# -- Packages names
# -- If you need to create new packages, you should
# -- define first the constants here
# --
OSS_CAD_SUITE = "oss-cad-suite"
GTKWAVE = "gtkwave"
ICOPROG = "icoprog"

# -- Name of the subfolder to store de executable files
BIN = "bin"

# -- Folder names. They are built from the
# -- packages names
OSS_CAD_SUITE_FOLDER = f"tools-{OSS_CAD_SUITE}"
GTKWAVE_FOLDER = f"tool-{GTKWAVE}"
ICOPROG_FOLDER = f"tool-{ICOPROG}"


# pylint: disable=E1101
requests.packages.urllib3.disable_warnings()


class ApioException(Exception):
    """DOC: TODO"""

    MESSAGE = None

    def __str__(self):  # pragma: no cover
        if self.MESSAGE:
            return self.MESSAGE.format(*self.args)

        return Exception.__str__(self)


class AsyncPipe(Thread):  # pragma: no cover
    """DOC: TODO"""

    def __init__(self, outcallback=None):
        Thread.__init__(self)
        self.outcallback = outcallback

        self._fd_read, self._fd_write = os.pipe()
        self._pipe_reader = os.fdopen(self._fd_read)
        self._buffer = []

        self.start()

    def get_buffer(self):
        """DOC: TODO"""

        return self._buffer

    def fileno(self):
        """DOC: TODO"""

        return self._fd_write

    def run(self):
        """DOC: TODO"""

        for line in iter(self._pipe_reader.readline, ""):
            line = line.strip()
            self._buffer.append(line)
            if self.outcallback:
                self.outcallback(line)
        self._pipe_reader.close()

    def close(self):
        """DOC: TODO"""

        os.close(self._fd_write)
        self.join()


# W0703: Catching too general exception Exception (broad-except)
# pylint: disable=W0703
def get_systype():
    """Return a String with the current platform:
    ex. linux_x86_64
    ex. windows_amd64"""

    # -- Get the platform: linux, windows, darwin
    type_ = platform.system().lower()
    platform_str = f"{type_}"

    # -- Get the architecture
    arch = platform.machine().lower()

    # -- Special case for windows
    # -- windows_amd64, windows_x86
    if type_ == "windows":
        arch = "amd64" if platform.architecture()[0] == "64bit" else "x86"

    # -- Add the architecture, if it exists
    if arch:
        platform_str += f"_{arch}"

    # -- Return the full platform
    return platform_str


try:
    codepage = locale.getdefaultlocale()[1]
    if "darwin" in get_systype():
        UTF = True
    else:
        UTF = codepage.lower().find("utf") >= 0
except Exception:
    # Incorrect locale implementation, assume the worst
    UTF = False


def _get_config_data():
    """Return the configuration data located in the /etc/apio.json file
    Only for Debian Distribution. It will return None otherwise"""

    # Default value
    _config_data = None

    # If the LOAD_CONFIG_DATA flag is set
    # Read the /etc/apio.json file and return its contents
    # as an object
    if LOAD_CONFIG_DATA:
        filepath = str(Path(os.sep) / "etc" / "apio.json")
        if isfile(filepath):
            with open(filepath, "r", encoding="utf8") as file:
                # Load the JSON file
                _config_data = json.loads(file.read())

    return _config_data


# Global variable with the configuration data
# Only for Debian distributions
config_data = _get_config_data()


def _get_projconf_option_dir(name, default=None):
    """Return the project option with the given name
    These options are place either on environment variables or
    into the /etc/apio.json file in the case of debian distributions

    All the APIO environment variables have the prefix "APIO_"

    Project options:

    * home_dir : APIO home directory
    """

    # -- Get the full name of the environment variable
    _env_name = f"APIO_{name.upper()}"

    # -- Check if the environment variable
    # -- is defined
    if _env_name in os.environ:
        # -- Read the value of the environmental variable
        _env_value = os.getenv(_env_name)

        # -- On window systems the environmental variables can
        # -- include the quotes (""). But not in Linux
        # -- If there are quotes, remove them
        if _env_value.startswith('"') and _env_value.endswith('"'):
            _env_value = _env_value[1:-1]

        # -- Debug: Print the environment variable (without quotes)
        # print(f"DEBUG: {_env_name}: {_env_value}")

        return _env_value

    # -- Check if the config option is defined in the
    # -- configuration file (Only Debian systems)
    if config_data and _env_name in config_data.keys():
        # -- Return the value of the option
        return config_data.get(_env_name)

    # -- Return the default home_dir
    return default


def get_home_dir():
    """Get the APIO Home dir. This is the apio folder where the profle is
    located and the packages installed. The APIO Home dir can be set in the
    APIO_HOME_DIR environment varible or in the /etc/apio.json file (in
    Debian). If not set, the user_HOME/.apio folder is used by default:
    Ej. Linux:  /home/obijuan/.apio
    If the folders does not exist, they are created
    It returns a list with all the folders
    """

    # -- Get the APIO_HOME_DIR env variable
    # -- It returns None if it was not defined
    apio_home_dir_env = _get_projconf_option_dir("home_dir")

    # -- Get the home dir. It is what the APIO_HOME_DIR env variable
    # -- says, or the default folder if None
    if apio_home_dir_env:
        home_dir = Path(apio_home_dir_env)
    else:
        home_dir = Path.home() / ".apio"

    # -- Create the folders if they do not exist
    try:
        home_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        click.secho(f"Error: no usable home directory {home_dir}", fg="red")
        sys.exit(1)

    # Return the home_dir as a string
    # In the future it should return the path object
    return str(home_dir)


def get_package_dir(pkg_name):
    """Return the APIO package dir of a given package
    Packages are installed in the following folder:
    * Default: $APIO_HOME_DIR/packages
    * $APIO_PKG_DIR/packages: if the APIO_PKG_DIR env variable is set
    * Return a String
    """

    # -- Get the apio home dir:
    apio_home_dir = get_home_dir()

    # -- Get the APIO_PKG_DIR env variable
    # -- It returns None if it was not defined
    apio_pkg_dir_env = _get_projconf_option_dir("pkg_dir")

    # -- Get the pkg base dir. It is what the APIO_PKG_DIR env variable
    # -- says, or the default folder if None
    if apio_pkg_dir_env:
        pkg_home_dir = Path(apio_pkg_dir_env)

    # -- Default value
    else:
        pkg_home_dir = Path(apio_home_dir)

    # -- Create the package folder
    package_dir = pkg_home_dir / "packages" / pkg_name

    # -- Return the folder if it exists
    if package_dir.exists():
        return str(package_dir)

    # -- Show an error message (for debugging)
    # click.secho(f"Folder does not exists: {package_dir}", fg="red")
    # sys.exit(1)

    # -- Return a null string if the folder does not exist
    return ""


def get_project_dir():
    """DOC: TODO"""

    return os.getcwd()


def call(cmd):
    """Execute the given command from the installed apio packages"""

    # -- Set the PATH environment variable for finding the
    # -- executables on the apio package folders first
    setup_environment()

    # -- Execute the command from the shell
    result = subprocess.call(cmd, shell=True)

    # -- Command not found
    if result == 127:
        message = f"ERROR. Comand not found!: {cmd}"
        click.secho(message, fg="red")

    return result


def setup_environment():
    """Set the environment variables and the system PATH"""

    # --- Get the table with the paths of all the apio packages
    base_dir = get_base_dir()

    # --- Get the table with the paths of all the executables
    # --- of the apio packages
    bin_dir = get_bin_dir_table(base_dir)

    # --- Set the system env. variables
    set_env_variables(base_dir, bin_dir)

    return bin_dir


def set_env_variables(base_dir, bin_dir):
    """Set the environment variables"""

    # -- Get the current system PATH
    path = os.environ["PATH"]

    # -- Add the packages to the path. The first packages added
    # -- have the lowest priority. The latest the highest

    # -- Add the gtkwave to the path if installed,
    # -- but only for windows platforms
    if platform.system() == "Windows":
        # -- Gtkwave package is installed
        if bin_dir[GTKWAVE] != "":
            path = os.pathsep.join([bin_dir.get(GTKWAVE), path])
        if bin_dir[ICOPROG] != "":
            path = os.pathsep.join([bin_dir.get(ICOPROG), path])

    # -- Add the binary folders of the installed packages
    # -- to the path, except for the OSS_CAD_SUITE package
    for pack in base_dir:
        if base_dir[pack] != "" and pack != OSS_CAD_SUITE:
            path = os.pathsep.join([bin_dir[pack], path])

    # -- Add the OSS_CAD_SUITE package to the path
    # -- if installed (Maximum priority)
    if base_dir[OSS_CAD_SUITE] != "":
        # -- Get the lib folder (where the shared libraries are located)
        oss_cad_suite_lib = str(Path(base_dir[OSS_CAD_SUITE]) / "lib")

        # -- Add the lib folder
        path = os.pathsep.join([oss_cad_suite_lib, path])
        path = os.pathsep.join([bin_dir[OSS_CAD_SUITE], path])

    # Add the virtual python environment to the path
    os.environ["PATH"] = path

    # print(f" get_bin_dir(): {get_bin_dir()}")

    # -- DEBUG
    print()
    print(f"PATH: {os.environ['PATH']}")
    print()

    # Add other environment variables

    os.environ["IVL"] = str(Path(base_dir[OSS_CAD_SUITE]) / "lib" / "ivl")

    os.environ["ICEBOX"] = str(
        Path(base_dir[OSS_CAD_SUITE]) / "share" / "icebox"
    )

    os.environ["TRELLIS"] = str(
        Path(base_dir[OSS_CAD_SUITE]) / "share" / "trellis"
    )

    os.environ["YOSYS_LIB"] = str(
        Path(base_dir[OSS_CAD_SUITE]) / "share" / "yosys"
    )


def resolve_packages(packages, installed_packages, spec_packages):
    """Check the given packages.
    * Check that they are installed
    * Check that the versions are ok"""

    # --- Get the table with the paths of all the apio packages
    base_dir = get_base_dir()

    # --- Get the table with the paths of all the executables
    # --- of the apio packages
    bin_dir = get_bin_dir_table(base_dir)

    # -- Check packages
    check = True
    for package in packages:
        version = installed_packages.get(package, {}).get("version", "")

        spec_version = spec_packages.get(package, "")

        check &= check_package(
            package, version, spec_version, bin_dir.get(package)
        )

    # -- Load packages
    if check:
        # --- Set the system env. variables
        set_env_variables(base_dir, bin_dir)

    return check


def get_base_dir():
    """Return the table with the local paths of the apio packages
    installed on the system. If the packages is not installed,
    the path is ''
    """

    # -- Create the table:
    # --  Package Name  :  Folder (string)
    base_dir = {
        OSS_CAD_SUITE: get_package_dir(OSS_CAD_SUITE_FOLDER),
        GTKWAVE: get_package_dir(GTKWAVE_FOLDER),
        ICOPROG: get_package_dir(ICOPROG_FOLDER),
    }

    return base_dir


def get_bin_dir_table(base_dir):
    """Return a table with the package name and the folder were
    the executable files are stored
    * Input: Table with the package base_dir
    """

    bin_dir = {
        OSS_CAD_SUITE: str(Path(base_dir.get(OSS_CAD_SUITE)) / BIN),
        GTKWAVE: str(Path(base_dir.get(GTKWAVE)) / BIN),
        ICOPROG: str(Path(base_dir.get(ICOPROG)) / BIN),
    }

    return bin_dir


def check_package(name, version, spec_version, path):
    """Check if the given package is installed
    * name: Package name
    * path: path where the binary files of the package are stored
    """

    # Apio package 'gtkwave' only exists for Windows.
    # Linux and MacOS user must install the native GTKWave.
    if name == "gtkwave" and platform.system() != "Windows":
        return True

    # Check package path
    if not isdir(path):
        show_package_path_error(name)
        show_package_install_instructions(name)
        return False

    # Check package version
    if not check_package_version(version, spec_version):
        show_package_version_warning(name, version, spec_version)
        show_package_install_instructions(name)
        return False

    return True


def check_package_version(version, spec_version):
    """DOC: TODO"""

    spec = semantic_version.SimpleSpec(spec_version)
    try:
        semver = semantic_version.Version(version)
    except ValueError:
        return False

    return semver in spec


def show_package_version_warning(name, version, spec_version):
    """DOC: TODO"""

    message = (
        f"Warning: package '{name}' version {version}\n"
        f"does not match the semantic version {spec_version}"
    )
    click.secho(message, fg="yellow")


def show_package_path_error(name):
    """DOC: TODO"""

    message = f"Error: package '{name}' is not installed"
    click.secho(message, fg="red")


def show_package_install_instructions(name):
    """DOC: TODO"""

    if config_data and _check_apt_get():  # /etc/apio.json file exists
        click.secho(
            f"Please run:\n   apt-get install apio-{name}",
            fg="yellow",
        )
    else:
        click.secho(f"Please run:\n   apio install {name}", fg="yellow")


def _check_apt_get():
    """Check if apio can be installed through apt-get"""
    check = False
    if "TESTING" not in os.environ:
        result = exec_command(["dpkg", "-l", "apio"])
        if result and result.get("returncode") == 0:
            match = re.findall(r"rc\s+apio", result.get("out")) + re.findall(
                r"ii\s+apio", result.get("out")
            )
            check = len(match) > 0
    return check


def get_package_version(name, profile):
    """DOC: TODO"""

    version = ""
    if name in profile.packages:
        version = profile.packages.get(name).get("version")
    return version


def get_package_spec_version(name, resources):
    """DOC: TODO"""

    spec_version = ""
    if name in resources.distribution.get("packages"):
        spec_version = resources.distribution.get("packages").get(name)
    return spec_version


def change_filemtime(path, time):
    """DOC: TODO"""

    os.utime(path, (time, time))


# W0703: Catching too general exception Exception (broad-except)
# pylint: disable=W0703
def exec_command(*args, **kwargs):  # pragma: no cover
    """DOC: TODO"""

    result = {"out": None, "err": None, "returncode": None}

    default = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "shell": False,
    }
    default.update(kwargs)
    kwargs = default

    # R1732: Consider using 'with' for resource-allocating operations
    # (consider-using-with)
    # pylint: disable=R1732
    try:
        proc = subprocess.Popen(*args, **kwargs)
        result["out"], result["err"] = proc.communicate()
        result["returncode"] = proc.returncode
    except KeyboardInterrupt:
        click.secho("Aborted by user", fg="red")
        sys.exit(1)
    except Exception as exc:
        click.secho(str(exc), fg="red")
        sys.exit(1)
    finally:
        for std in ("stdout", "stderr"):
            if isinstance(kwargs[std], AsyncPipe):
                kwargs[std].close()

    _parse_result(kwargs, result)

    return result


def _parse_result(kwargs, result):
    for std in ("stdout", "stderr"):
        if isinstance(kwargs[std], AsyncPipe):
            result[std[3:]] = "\n".join(kwargs[std].get_buffer())

    for k, value in result.items():
        if value and isinstance(value, str):
            result[k].strip()


# W0703: Catching too general exception Exception (broad-except)
# pylint: disable=W0703
def get_pypi_latest_version():
    """DOC: TODO"""

    req = None
    version = None
    try:
        req = requests.get("https://pypi.python.org/pypi/apio/json", timeout=5)
        version = req.json().get("info").get("version")
        req.raise_for_status()
    except requests.exceptions.ConnectionError as exc:
        error_message = str(exc)
        if "NewConnectionError" in error_message:
            click.secho(
                "Error: could not connect to Pypi.\n"
                "Check your internet connection and try again",
                fg="red",
            )
        else:
            click.secho(error_message, fg="red")
    except Exception as exc:
        click.secho("Error: " + str(exc), fg="red")
    finally:
        if req:
            req.close()
    return version


def get_full_path(folder: string):
    """Get the full path to the given folder
    Inputs:
      * folder: String with the folder name

    Returns:
      * The full path as a PosixPath() object

    Example: folder="commands"
    Output: PosixPath('/home/obijuan/.../apio/commands')
    """

    # -- Get the full path of this file (util.py)
    # -- Ex: /home/obijuan/.../site-packages/apio/util.py
    current_python_file = Path(__file__)

    # -- The parent folder is the apio root folder
    # -- Ex: /home/obijuan/.../site-packages/apio
    apio_path = current_python_file.parent

    # -- Add the given folder to the path
    new_path = apio_path / folder

    # -- Return the path
    return new_path


def mkdir(path):
    """DOC: TODO"""

    path = dirname(path)
    if not exists(path):
        try:
            os.makedirs(path)
        except OSError:
            pass


def check_dir(_dir):
    """Check if the given path is a folder. If no path is given
    the current path is used"""

    # -- If no path is given, get the current working directory
    if _dir is None:
        _dir = os.getcwd()

    # -- Check if the path is a file or a folder
    if isfile(_dir):
        # -- It is a file! Error! Exit!
        click.secho(
            f"Error: project directory is already a file: {_dir}", fg="red"
        )

        sys.exit(1)

    # -- If the folder does not exist....
    if not exists(_dir):
        # -- Warning
        click.secho(f"Warning: The path does not exist: {_dir}", fg="yellow")

        # -- Create the folder
        click.secho(f"Creating folder: {_dir}")
        os.makedirs(_dir)

    # -- Return the path
    return _dir


# W0703: Catching too general exception Exception (broad-except)
# pylint: disable=W0703
# pylint: disable=W0150
def command(function):
    """Command decorator"""

    def decorate(*args, **kwargs):
        exit_code = 1
        try:
            exit_code = function(*args, **kwargs)

        except Exception as exc:
            if str(exc):
                click.secho("Error: " + str(exc), fg="red")

        return exit_code

    return decorate


def get_serial_ports():
    """DOC: TODO"""

    result = []

    for port, description, hwid in comports():
        if not port:
            continue
        if "VID:PID" in hwid:
            result.append(
                {"port": port, "description": description, "hwid": hwid}
            )

    return result


# W0703: Catching too general exception Exception (broad-except)
# pylint: disable=W0703
def get_tinyprog_meta():
    """DOC: TODO"""

    _command = join(get_bin_dir(), "tinyprog")
    result = exec_command([_command, "--pyserial", "--meta"])
    try:
        out = result.get("out", "")
        if out:
            return json.loads(out)
    except Exception as exc:
        print(exc)
        return []
    return []


def get_bin_dir():
    """DOC: TODO"""

    candidate = dirname(sys.modules["__main__"].__file__)
    # Windows + virtualenv = 💩
    # In this case the main file is: venv/Scripts/apio.exe/__main__.py!
    # This is not good because venv/Scripts/apio.exe is not a directory
    # So here we go with the workaround:
    if candidate.endswith(".exe"):
        return dirname(candidate)

    return candidate


def get_python_version():
    """Return a string with the python version"""

    return f"{sys.version_info[0]}.{sys.version_info[1]}"
