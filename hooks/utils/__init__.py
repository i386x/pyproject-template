#                                                         -*- coding: utf-8 -*-
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
import re
import readline
import stat
import subprocess  # nosec
import sys
import time

import click
import jinja2
import requests

from .classifiers import PYPI_CLASSIFIERS

WORD_RE = r"^[a-zA-Z][-_0-9a-zA-Z]{2,}$"
IDEN_RE = r"^[a-zA-Z][_0-9a-zA-Z]{2,}$"
EMAIL_RE = r"^\S+@\S+$"
REMOVE_ME = ".remove.me"


def identity(arg):
    """Return its argument."""
    return arg


def to_int(number):
    """Convert `number` as string to integer."""
    try:
        return int(number)
    except ValueError:
        pass
    return None


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
        template, trim_blocks=True, keep_trailing_newline=True
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


class Catalog(collections.OrderedDict):
    """Implements a classifier catalog."""

    __slots__ = ()

    def __init__(self):
        """Initialize catalog."""
        collections.OrderedDict.__init__(self)

    def insert(self, item):
        """Insert `item` into the catalog."""
        if len(item) == 0:
            return

        head, tail = item[0], item[1:]
        if head not in self:
            self[head] = Catalog()
        self[head].insert(tail)

    def find_catalog(self, path):
        """Return a sub-catalog at `path`."""
        catalog = self
        for part in path:
            if part not in catalog:
                return None
            catalog = catalog[part]
        return catalog

    def select(self, query):
        """Return a list of classifier parts matching `query`."""
        if len(query) == 0:
            return []
        catalog = self.find_catalog(query[:-1])
        if catalog is None:
            return []
        return [k for k in catalog.keys() if k.startswith(query[-1])]


class Completer:
    """Completion helper."""

    __slots__ = ("root", "catalog", "candidates")

    def __init__(self, words):
        """Create a catalog for `words`."""
        self.root = self.catalog = Catalog()
        for word in sorted(words):
            word = word.strip()
            if len(word) == 0:
                continue
            self.insert(word)
        self.candidates = []

    def insert(self, word):
        """Insert `word` into the catalog."""
        self.root.insert([word])

    def use_catalog(self, path):
        """For completion, use catalog at `path`."""
        self.catalog = self.root.find_catalog(path)
        return self.catalog

    def complete(self, text, state):
        """Return a candidate for auto-completion."""
        if state == 0:
            # First call, build a list of candidates
            self.candidates = self.catalog.select([text])
        if state >= len(self.candidates):
            return None
        return self.candidates[state]


class ClassifierCompleter(Completer):
    """Helps with PyPI classifiers completion."""

    def __init__(self, classifiers):
        """Create a catalog of `classifiers`."""
        Completer.__init__(self, classifiers)

    def insert(self, word):
        """Insert `word` into the catalog."""
        self.root.insert([x.strip() for x in word.split("::")])


class ReadlineContextManager:
    """Context manager for ``readline``."""

    __slots__ = ("__old_completer", "__old_delims", "__completer")

    def __init__(self, completer):
        """Initialize context manager."""
        self.__old_completer = readline.get_completer()
        self.__old_delims = readline.get_completer_delims()
        self.__completer = completer

    def __enter__(self):
        """Set the completer."""
        readline.set_completer(self.__completer)
        readline.set_completer_delims("")
        readline.parse_and_bind("tab: complete")

    def __exit__(self, exc_type, exc_value, traceback):
        """Restore the original completer."""
        readline.set_completer(self.__old_completer)
        readline.set_completer_delims(self.__old_delims)
        readline.parse_and_bind("set editing-mode vi")


class ReadEditLoop:
    """Read-edit loop."""

    __slots__ = ("__hint", "__label", "__command_map")

    def __init__(self, hint, label=""):
        """Initialize instance."""
        self.__hint = hint
        self.__label = label
        self.__command_map = {
            "h": ReadEditLoop.show_help,
            "l": ReadEditLoop.list_items,
            "d": ReadEditLoop.delete_item,
            "r": ReadEditLoop.replace_item,
            "q": ReadEditLoop.pass_command,
        }

    @staticmethod
    def show_help(command, _):
        """Print help to the terminal."""
        print(":h     - print this help")
        print(":l     - list items")
        print(":d n   - delete nth item")
        print(":r n t - replace nth item with text t")
        print(":q     - quit read-edit loop")
        return command[0]

    @staticmethod
    def list_items(command, items):
        """Enumerate `items`."""
        for i, item in enumerate(items):
            print(f"{i} - {item}")
        return command[0]

    @staticmethod
    def getargs(args, nargs, items):
        """Extract and verify `command` arguments."""
        if len(args) < nargs:
            print("Insufficient number of arguments.")
            return None
        i = to_int(args[0])
        if i is None:
            print(f"{args[0]} must be an integer.")
            return None
        if i < 0 or i >= len(items):
            print(f"{i} is out of range.")
            return None
        args[0] = i
        return args

    @staticmethod
    def delete_item(command, items):
        """Delete item."""
        args = ReadEditLoop.getargs(command[1:], 1, items)
        if args:
            del items[args[0]]
        return command[0]

    @staticmethod
    def replace_item(command, items):
        """Replace item."""
        args = ReadEditLoop.getargs(command[1:], 2, items)
        if args:
            items[args[0]] = args[1]
        return command[0]

    @staticmethod
    def pass_command(command, _):
        """Only pass `command` name."""
        return command[0]

    @staticmethod
    def unknown_command(command, _):
        """Complain about unknown `command`."""
        print(f"Unknown command: {command[0]}")
        return command[0]

    def process_line(self, line, items):
        """Process `line`."""
        if line[0] != ":":
            items.append(line)
            return ""
        command = line[1:].split(maxsplit=2)
        if len(command) == 0:
            return ""
        return self.__command_map.get(
            command[0], ReadEditLoop.unknown_command
        )(command, items)

    def run(self, min_items=0):
        """Run the read-edit loop."""
        items = []
        print(f"Please, {self.__hint} (:h - show help).")
        while True:
            line = input(f"{self.__label}> ").strip()
            if len(line) == 0:
                continue
            if self.process_line(line, items) == "q":
                if len(items) < min_items:
                    print(f"Please, enter at least {min_items} items.")
                    continue
                break
        return items


def simple_prompt(prompt, validation_re=None, default=None):
    """Perform a simple prompt with validation."""
    while True:
        answer = click.prompt(prompt, default=default).strip()
        if validation_re is None or re.match(validation_re, answer):
            return answer
        print(f"'{answer}' does not match '{validation_re}'.")


def choice_prompt(hint, choices, choice2str=identity):
    """Ask the user to choose from `choices`."""
    print(f"Please, select {hint}.")
    print(
        "  "
        + ", ".join(
            [f"{i} - {choice2str(c)}" for i, c in enumerate(choices, 1)]
        )
    )
    while True:
        answer = int(simple_prompt(hint, r"^[0-9]+$", "1").strip())
        if 1 <= answer <= len(choices):
            return choices[answer - 1]
        print("Incorrect choice!")


def selection_prompt(hint, choices, completer_class):
    """Ask the user to select multiple values from `choices`."""
    selections = []
    completer = completer_class(choices)
    catalog_path = []
    with ReadlineContextManager(completer.complete):
        while True:
            choice = " :: ".join(catalog_path)
            catalog = completer.use_catalog(catalog_path)
            if catalog is None:
                error(f"Invalid catalog path: {choice}")
            print(
                f"Please, select {hint} "
                "(<Enter>: confirm; <dot (.)>: abort; <two dots (..)>: undo; "
                "<:l>: list choices)."
            )
            answer = input(f"{choice}> ").strip()
            if answer == ".":
                break
            if answer == "..":
                catalog_path = catalog_path[:-1]
                continue
            if answer == ":l":
                for item in choices:
                    if item.startswith(choice):
                        print(item)
                continue
            if answer == "" and choice in choices:
                if choice not in selections:
                    selections.append(choice)
                    print(f"'{choice}' has been selected.")
                catalog_path = []
                continue
            if answer in catalog:
                catalog_path.append(answer)
    return selections
