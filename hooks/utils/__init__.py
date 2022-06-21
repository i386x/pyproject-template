#
# File:    ./hooks/utils/__init__.py
# Author:  Jiří Kučera <sanczes AT gmail.com>
# Date:    2021-01-31 23:34:42 +0100
# Project: pyproject-template: A cookiecutter template for Python projects
#
# SPDX-License-Identifier: MIT
#
"""Cookiecutter hooks utilities."""

import collections
import importlib
import os
import pathlib
import re
import stat
import subprocess  # nosec
import sys
import tempfile
import time

import click
import jinja2
import requests
import yaml

from .classifiers import PYPI_CLASSIFIERS

WORD_RE = r"^[a-zA-Z][-_0-9a-zA-Z]{2,}$"
KWORD_RE = r"^[a-zA-Z][-_0-9a-zA-Z]{2,}([ ][a-zA-Z][-_0-9a-zA-Z]{2,})*$"
IDEN_RE = r"^[a-zA-Z][_0-9a-zA-Z]{2,}$"
EMAIL_RE = r"^\S+@\S+$"
REMOVE_ME = ".remove.me"
GENCTORS = (
    "construct_yaml_omap",
    "construct_yaml_pairs",
    "construct_yaml_set",
    "construct_yaml_seq",
    "construct_yaml_map",
    "construct_yaml_object",
)
TYPEMAP = {}


def sanitize(sinput):
    """Sanitize `sinput`."""
    return " ".join(sinput.split())


def pinfo(msg, verbose=False, label="INFO"):
    """Print `msg` to standard output only if `verbose` is true."""
    if verbose:
        sys.stdout.write(f"{label}: {msg}\n")


def perror(emsg, label="ERROR"):
    """Print `emsg` to standard error output."""
    sys.stderr.write(f"{label}: {emsg}\n")


def error(emsg, exit_code=1):
    """Print `emsg` and exit with `exit_code`."""
    perror(f"{emsg}")
    sys.exit(exit_code)


def verify_not_empty(name, value):
    """Verify if `value` is not empty."""
    if len(value) == 0:
        error(f"'{name}' must not be empty!")


def verify_value(name, regex, value, emsg=None):
    """Verify if `value` matches `regex`."""
    if not re.match(regex, value):
        error(emsg or f"'{name}' must match '{regex}'!")


def verify_email(name, value):
    """Verify if `value` is an e-mail address."""
    verify_value(
        name,
        EMAIL_RE,
        value,
        f"'{name}' must be an e-mail address!",
    )


def chmodx(path):
    """Perform ``chmod a+x`` on a file at `path`."""
    mode = os.stat(path).st_mode
    mode |= stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    os.chmod(path, mode)


def remove(path):
    """Remove a file at `path` from the file system."""
    if os.path.exists(path):
        os.remove(path)


def mkstamp(secs):
    """Make time date stamp function from `secs`."""

    def stamp(fmtspec="%Y-%m-%d %H:%M:%S %z"):
        return time.strftime(fmtspec, time.localtime(secs))

    return stamp


def last_mtime(path):
    """Return the last modification time of file at `path`."""
    return int(os.stat(path).st_mtime)


def read_file(path):
    """Read the content of a file at `path`."""
    with open(path) as fobj:
        return fobj.read()


def write_file(path, content):
    """Write `content` to a file at `path`."""
    with open(path, "w") as fobj:
        fobj.write(content)


def render_string(template, env):
    """Render the `template`."""
    return jinja2.Template(
        template,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    ).render(**env)


def render_file(src, dest, env):
    """Render file from Jinja2 template at `src`."""
    write_file(dest, render_string(read_file(src), env))


def runcmd(cmd, args=None, cwd=None):
    """Run `cmd` with `args`."""
    cmd = [cmd]
    cmd.extend(args or [])
    subprocess.run(cmd, cwd=cwd, check=True)  # nosec


def load_from_package(name, attr):
    """Load `attr` from the package `name`."""
    try:
        module = importlib.import_module(name)
        if module is None:
            return None
        return getattr(module, attr, None)
    except ImportError:
        pass
    return None


def load_text_lines_from_url(url):
    """Load lines of text from `url`."""
    try:
        response = requests.get(url)
        response.raise_for_status()
        content = response.text.split("\n")
        return [x.strip() for x in content if len(x.strip()) > 0]
    except requests.RequestException:
        pass
    return None


def load_classifiers(verbose=False):
    """Load a list of PyPI classifiers."""
    classifiers_pkg = ("trove_classifiers", "classifiers")
    classifiers_url = "https://pypi.org/pypi?%3Aaction=list_classifiers"

    pinfo("Loading PyPI classifiers...", verbose)
    classifiers = load_from_package(*classifiers_pkg)
    if classifiers:
        return classifiers
    pinfo(
        f"Package '{classifiers_pkg[0]}' is not installed, "
        f"fallback to <{classifiers_url}>.",
        verbose,
    )
    classifiers = load_text_lines_from_url(classifiers_url)
    if classifiers:
        return classifiers
    pinfo(
        f"PyPI classifiers cannot be retrieved from <{classifiers_url}>, "
        "fallback to builtins.",
        verbose,
    )
    return PYPI_CLASSIFIERS


def find_license(classifiers, license_name):
    """Find `license_name` in `classifiers`."""
    for classifier in classifiers:
        if classifier.startswith("License ::") and license_name in classifier:
            return classifier
    return None


class NullType:
    """Auxiliary class to represent yaml null."""

    def __str__(self):
        """Implement `str(obj)`."""
        return "null"

    def __repr__(self):
        """Implement `repr(obj)`."""
        return str(self)


class Result:
    """Holds result."""

    __slots__ = ("value", "line", "detail")

    def __init__(self, value=None, line=-1, detail=""):
        """Initialize result."""
        self.value = value
        self.line = line
        self.detail = detail

    @staticmethod
    def is_valid():
        """Return `True` if the result is valid."""
        return True


class Error(Result):
    """Holds error."""

    __slots__ = ()

    def __init__(self, line, detail):
        """Initialize error."""
        Result.__init__(self, None, line, detail)

    @staticmethod
    def is_valid():
        """Return `True` if the result is valid."""
        return False


def gctor2newc(name, args):
    """Create a new container object based on generator-constructor name."""
    if name == "construct_yaml_set":
        return set()
    if name == "construct_yaml_map":
        return {}
    if name == "construct_yaml_object":
        return args[0].__new__(args[0])
    return []


def copy_data(dest, src):
    """Copy the `src` data to `dest`."""
    if isinstance(src, list):
        dest.extend(src)
    elif isinstance(src, (set, dict)):
        dest.update(src)
    else:
        dest.__dict__.update(src.__dict__)


def wrap_yaml_obj(obj):
    """Wrap yaml `obj` to be extensible."""
    if obj is None:
        return NullType()
    cls = type(obj)
    if cls not in TYPEMAP:
        TYPEMAP[cls] = type(cls.__name__.capitalize(), (cls,), {})
    return TYPEMAP[cls](obj)


def wrap_yaml_ctor(loader, name):
    """Wrap the `construct_*` method."""
    if name == "construct_undefined" or not name.startswith("construct_"):
        return

    def cwrapper(node, *args, **kwargs):
        method = getattr(yaml.constructor.SafeConstructor, name)
        data = method(loader, node, *args, **kwargs)
        if not hasattr(data, "line"):
            data = wrap_yaml_obj(data)
        setattr(data, "line", node.start_mark.line + 1)
        return data

    def gwrapper(node, *args, **kwargs):
        data = wrap_yaml_obj(gctor2newc(name, args))
        setattr(data, "line", node.start_mark.line + 1)
        yield data
        method = getattr(yaml.constructor.SafeConstructor, name)
        generator = method(loader, node, *args, **kwargs)
        gdata = {}
        for item in generator:
            gdata = item
        copy_data(data, gdata)

    wrapper = gwrapper if name in GENCTORS else cwrapper

    def ywrapper(_, node, *args, **kwargs):
        return wrapper(node, *args, **kwargs)

    setattr(loader, name, wrapper)
    if name.startswith("construct_yaml_"):
        tag = name.replace("construct_yaml_", "tag:yaml.org,2002:")
        loader.yaml_constructors[tag] = ywrapper


def load_yaml(stream):
    """Load yaml from `stream`."""
    loader = yaml.SafeLoader(stream)
    for member in dir(loader):
        wrap_yaml_ctor(loader, member)
    try:
        return loader.get_single_data()
    finally:
        loader.dispose()


class VerificationError(Exception):
    """Raised when config verification fails."""

    __slots__ = ("line", "detail")

    def __init__(self, detail, line=-1):
        """Initialize exception object."""
        Exception.__init__(self, detail, line)
        self.line = line
        self.detail = detail if line < 0 else f"at line {line}: {detail}"

    def __str__(self):
        """Return the error description."""
        return self.detail


def assert_type(value, vtype):
    """Assert `value` is of the type `vtype`."""
    if not isinstance(value, vtype):
        raise VerificationError(
            f"expected {vtype.__name__}", getattr(value, "line", -1)
        )


def key_line(cfgmap, key):
    """Get the line number of `key` in `cfgmap`."""
    if not hasattr(cfgmap, "key2line"):
        key2line = {}
        for cfgkey in cfgmap:
            key2line[cfgkey] = getattr(cfgkey, "line", -1)
        cfgmap.key2line = key2line
    return cfgmap.key2line.get(key, -1)


def assert_item_type(config, key, itype):
    """Assert `config[key]` is of the type `itype`."""
    if not isinstance(config[key], itype):
        raise VerificationError(
            f"{key}: expected {itype.__name__}", key_line(config, key)
        )


def assert_item_nonempty(config, key):
    """Assert `config[key]` is not empty."""
    if len(config[key]) == 0:
        raise VerificationError(f"{key} is empty", key_line(config, key))


class ConfigItem:
    """Base class for the project config item."""

    __slots__ = ("description", "key", "value", "hint")

    def __init__(self):
        """Initialize the config item."""
        self.description = ()
        self.key = ""
        self.value = None
        self.hint = False

    def set_description(self, *lines):
        """Set description."""
        self.description = lines

    def set_key(self, name):
        """Set the key name."""
        self.key = name

    def set_value(self, value, hint=False):
        """Attach the value to the key."""
        self.value = value
        self.hint = hint

    def render(self):
        """Render the item."""
        raise NotImplementedError

    @staticmethod
    def sorter(key):
        """Specify how to sort `key`."""
        return key

    def verify_bool(self, config):
        """Verify bool."""
        value = config[self.key]
        if isinstance(value, bool):
            return
        if isinstance(value, int):
            if value not in (0, 1):
                raise VerificationError(f"Invalid value ({value})", value.line)
            config[self.key] = value == 1
            return
        assert_item_type(config, self.key, str)
        svalue = value.strip().lower()
        if svalue in ("yes", "y", "true", "t", "1"):
            config[self.key] = True
        elif svalue in ("no", "n", "false", "f", "0"):
            config[self.key] = False
        else:
            raise VerificationError(f"Invalid value ({value})", value.line)

    def verify_int(self, config, vmin=None, vmax=None):
        """Verify integer."""
        assert_item_type(config, self.key, int)
        value = config[self.key]
        if (vmin is not None and value < vmin) or (
            vmax is not None and value > vmax
        ):
            raise VerificationError(f"Invalid value ({value})", value.line)

    def verify_str(self, config, regexp=None):
        """Verify string."""
        assert_item_type(config, self.key, str)
        assert_item_nonempty(config, self.key)
        value = config[self.key]
        svalue = value.strip()
        if regexp and not re.match(regexp, svalue):
            raise VerificationError(
                f"Invalid value format ({value})", value.line
            )
        config[self.key] = svalue

    def verify_list(self, config, regexp, item_name="item", **kwargs):
        """Verify list."""
        assert_item_type(config, self.key, list)
        if not kwargs.get("empty", False):
            assert_item_nonempty(config, self.key)
        items = config[self.key]
        for i, item in enumerate(items):
            assert_type(item, str)
            sitem = sanitize(item)
            if not re.match(regexp, sitem):
                raise VerificationError(
                    f"Invalid {item_name} ({item})", item.line
                )
            items[i] = sitem
        if kwargs.get("sort", False):
            config[self.key] = sorted(items, self.sorter)

    def verify(self, config):
        """Verify `config`."""


class YamlConfigItem(ConfigItem):
    """Implements configuration item rendering to yaml."""

    __slots__ = ()

    def __init__(self):
        """Initialize the config item."""
        ConfigItem.__init__(self)

    @staticmethod
    def val2yml(value):
        """Convert value to its yaml representation."""
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, str):
            value = value.replace('"', '\\"')
            return f'"{value}"'
        if isinstance(value, list) and len(value) > 0:
            # Nonempty lists are expanded across multiple lines
            return ""
        return repr(value)

    def render(self):
        """Render the item."""
        lines = []
        for item in self.description:
            lines.append(f"# {item.strip()}")
        value = self.value
        if isinstance(value, (list, tuple)) and self.hint:
            value = []
        lines.append(f"{self.key}: {self.val2yml(value).strip()}")
        if isinstance(self.value, (list, tuple)):
            comment = "#" if self.hint else ""
            for item in self.value:
                lines.append(f"  {comment}- {self.val2yml(item).strip()}")
        lines.append("")
        return lines


class Config:
    """Configuration container."""

    NAME_ARG = "@NAME@"
    LINE_ARG = "@LINE@"
    __slots__ = ("__name2item", "__editor", "__editor_args", "__data")

    def __init__(self):
        """Initialize the container."""
        self.__name2item = None
        self.__editor = None
        self.__editor_args = []
        self.__data = None

    def set_items(self, *items):
        """Set configuration items."""
        name2item = collections.OrderedDict()
        for item in items:
            obj = item()
            name2item[obj.key] = obj
        self.__name2item = name2item

    def set_editor(self, editor):
        """Set editor for configuration editing."""
        editor = editor.split()
        if not editor:
            error("Missing editor.")
        self.__editor = editor[0]
        args = editor[1:]
        cls = type(self)
        if cls.NAME_ARG not in args:
            args.append(cls.NAME_ARG)
        self.__editor_args = args

    def render(self):
        """Render configuration lines."""
        if not self.__name2item:
            error("Configuration items are not set.")
        lines = []
        for _, item in self.__name2item.items():
            lines.extend(item.render())
        return lines

    def write_config(self, fpath):
        """Write config to `fpath`."""
        write_file(fpath, "\n".join(self.render()))

    def edit(self, fpath, at_line=-1):
        """Launch editor for `fpath` at line `at_line`."""
        if not self.__editor:
            error("Editor is not set.")
        cls = type(self)
        sline, sname = cls.LINE_ARG, cls.NAME_ARG
        args = [
            x.replace(sline, f"{at_line}").replace(sname, f"{fpath}")
            for x in self.__editor_args
            if not (at_line < 0 and sline in x)
        ]
        runcmd(self.__editor, args)

    def verify_keys(self, config):
        """Verify that `config` has valid keys."""
        if not self.__name2item:
            error("Configuration items are not set.")
        assert_type(config, dict)
        for key in config:
            if key not in self.__name2item:
                raise VerificationError(f"Invalid key ({key})", key.line)

    def verify(self, fpath):
        """Load and verify the config at `fpath`."""
        try:
            config = load_yaml(read_file(fpath))
            self.verify_keys(config)
            for _, item in self.__name2item.items():
                item.verify(config)
        except yaml.YAMLError as exc:
            line = -1
            if hasattr(exc, "problem_mark"):
                # Make pylint happy
                line = getattr(exc, "problem_mark").line + 1
            return Error(line, str(exc))
        except VerificationError as exc:
            return Error(exc.line, exc.detail)
        return Result(config)

    def edit_verify_loop(self, fpath):
        """Run edit-verify loop."""
        at_line = -1
        while True:
            self.edit(fpath, at_line)
            result = self.verify(fpath)
            if result.is_valid():
                return result.value
            print(result.detail)
            if not click.prompt(
                "Continue in editing?", default="y", type=click.BOOL
            ):
                break
            at_line = result.line
        return None

    def read_config(self, tempdir=None):
        """Request project config from the user."""
        with tempfile.TemporaryDirectory(prefix=tempdir) as tmpdir:
            fpath = pathlib.Path(tmpdir) / "config.yaml"
            self.write_config(fpath)
            self.__data = self.edit_verify_loop(fpath)

    def __len__(self):
        """Return the config size."""
        return len(self.__data) if self.__data else 0

    def __getitem__(self, key):
        """Get the config item."""
        if not self.__data:
            raise KeyError(key)
        return self.__data[key]
