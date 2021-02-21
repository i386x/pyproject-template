#!/usr/bin/python3
#                                                         -*- coding: utf-8 -*-
# File:    ./hooks/post_gen_project.py
# Author:  Jiří Kučera <sanczes AT gmail.com>
# Date:    2021-01-30 15:08:47 +0100
# Project: pyproject-template: A cookiecutter template for Python projects
#
# SPDX-License-Identifier: MIT
#
"""Hook that runs after the project is generated."""

import os
import pathlib
import subprocess  # nosec
import sys

import click
import jinja2
from cookiecutter.utils import rmtree
from utils import (
    IDEN_RE,
    REMOVE_ME,
    WORD_RE,
    ClassifierCompleter,
    Completer,
    ReadEditLoop,
    chmodx,
    choice_prompt,
    error,
    find_license,
    last_mtime,
    load_classifiers,
    mkstamp,
    remove,
    render_file,
    runcmd,
    selection_prompt,
    simple_prompt,
)

SUCCESS = 0
FAILURE = 1
ALL_PYTHONS = ["3.6", "3.7", "3.8", "3.9"]
GH_USER = "{{ cookiecutter.github_user }}"
GH_EMAIL = "{{ cookiecutter.github_email|replace(' AT ', '@') }}"
GH_REMOTE = f"https://github.com/{GH_USER}/{{ cookiecutter.project_name }}"


def get_classifiers():
    """Get a list of PyPI classifiers from the user."""
    choices = load_classifiers(verbose=True)
    # Keep MIT license classifier
    mit_license = find_license(choices, "MIT")
    if mit_license is None:
        error("MIT license not in PyPI classifiers?")
    # As generated project is MIT licensed, remove all License classifiers
    choices = [c for c in choices if not c.startswith("License ::")]
    # Ask for classifiers
    choices = selection_prompt("PyPI classifier", choices, ClassifierCompleter)
    choices.append(mit_license)
    return sorted(choices)


def get_interpreters(choices):
    """Get a list of supported Python interpreters."""
    selected = selection_prompt("Python interpreter", choices, Completer)
    selected = sorted([tuple(x.split(".")) for x in selected])
    return [".".join(x) for x in selected]


def get_keywords():
    """Get a list of keywords from the user."""
    reloop = ReadEditLoop(hint="enter project keywords", label="keyword")
    return sorted(reloop.run(min_items=1))


def get_platforms():
    """Get a list of platforms from the user."""
    hints = "[any, linux, macos, nt, os2, posix, unix, win32, windows, ...]"
    reloop = ReadEditLoop(
        hint=f"enter supported platforms {hints}", label="platform"
    )
    return sorted(reloop.run(min_items=1))


def get_requirements():
    """Get a list of install requirements from the user."""
    return ReadEditLoop(
        hint="enter install requirements", label="requirement"
    ).run()


class ProjectDetails:
    """Keeps additional details about project."""

    PACKAGE = (0, "package", "package")
    PLUGIN = (1, "plugin", "plugin")
    CONSOLE_APP = (2, "console application", "script")
    __slots__ = (
        "project_type",
        "entry_point_kind",
        "entry_point_name",
        "entry_point_source",
        "entry_point_source_description",
        "entry_point_function",
        "entry_point_fqdn",
    )

    def __init__(self):
        """Initialize the instance."""
        self.project_type = type(self).PACKAGE
        self.entry_point_kind = ""
        self.entry_point_name = ""
        self.entry_point_source = ""
        self.entry_point_source_description = ""
        self.entry_point_function = "main"
        self.entry_point_fqdn = ""

    def to_dict(self):
        """Return a dictionary with project details."""
        details = {}
        for attr in self.__slots__:
            if attr.startswith("entry_point_"):
                details[attr] = getattr(self, attr)
        return details

    def has_entry_points(self):
        """Return `True` if the project has entry points."""
        return self.project_type[0] > type(self).PACKAGE[0]

    @staticmethod
    def project_type_to_str(project_type):
        """Convert `project_type` to string."""
        return project_type[1]

    def ask_project_type(self):
        """Ask the user to select project type."""
        cls = type(self)
        return choice_prompt(
            "project type",
            [cls.PACKAGE, cls.PLUGIN, cls.CONSOLE_APP],
            self.project_type_to_str,
        )

    def ask_ep_kind(self):
        """Ask the user for the entry point kind."""
        cls = type(self)
        if self.project_type == cls.PLUGIN:
            return simple_prompt(
                "Please, enter the plugin name space", IDEN_RE
            )
        if self.project_type == cls.CONSOLE_APP:
            return "console_scripts"
        return ""

    def ask_ep_name(self):
        """Ask the user for the entry point name."""
        return simple_prompt(
            f"Please, enter the {self.project_type[2]} name", WORD_RE
        )

    @staticmethod
    def ask_ep_source():
        """Ask the user for the source file with entry point."""
        lines = [
            "Please, enter the name of module with entry point definition.",
            "Module name",
        ]
        return simple_prompt("\n".join(lines), IDEN_RE)

    def ask_ep_src_desc(self):
        """Ask the user for the description of entry point source file."""
        lines = [
            f"Please, enter the {self.entry_point_source}'s description.",
            "Description",
        ]
        text = simple_prompt("\n".join(lines))
        if len(text) > 0 and text[-1] != ".":
            text += "."
        return text

    def ask_ep_function(self):
        """Ask the user for the entry point function name."""
        return simple_prompt(
            "Please, enter the entry point function name",
            IDEN_RE,
            self.entry_point_function,
        )

    def ask(self):
        """Ask the user about additional project information."""
        self.project_type = self.ask_project_type()
        self.entry_point_kind = self.ask_ep_kind()
        if self.has_entry_points():
            self.entry_point_name = self.ask_ep_name()
            self.entry_point_source = self.ask_ep_source()
            self.entry_point_fqdn = self.entry_point_source
            self.entry_point_source_description = self.ask_ep_src_desc()
        if self.project_type == type(self).CONSOLE_APP:
            self.entry_point_function = self.ask_ep_function()
            self.entry_point_fqdn += f":{self.entry_point_function}"
        return self


def remove_file(path):
    """Remove the file at `path`."""
    try:
        remove(path)
    except OSError as exc:
        print(str(exc))
        return FAILURE
    return SUCCESS


def render_prjfile(prjdir, prjfile, env=None, newname=None, chmod_x=False):
    """Render project file."""
    env = env or {}
    src, dest = prjdir / f"{prjfile}.j2", prjdir / (newname or prjfile)
    try:
        env["stamp"] = mkstamp(last_mtime(src))
        render_file(src, dest, env)
        if chmod_x:
            chmodx(dest)
        remove(src)
    except (OSError, jinja2.TemplateError) as exc:
        print(str(exc))
        return FAILURE
    return SUCCESS


def init_repo(prjdir, should_init):
    """Initialize repository with git init."""
    if not should_init:
        return SUCCESS
    try:
        runcmd("git", ["init"], prjdir)
        runcmd("git", ["config", "user.name", GH_USER], prjdir)
        runcmd("git", ["config", "user.email", GH_EMAIL], prjdir)
        runcmd("git", ["remote", "add", "origin", GH_REMOTE], prjdir)
        runcmd("git", ["add", "."], prjdir)
        runcmd("git", ["commit", "-m", "Initial commit"], prjdir)
        runcmd("git", ["branch", "-M", "main"], prjdir)
    except subprocess.SubprocessError as exc:
        print(str(exc))
        return FAILURE
    return SUCCESS


class Project:
    """Implements project creation logic."""

    NAMESPACE = "{{ cookiecutter.namespace }}"
    PACKAGE_NAME = "{{ cookiecutter.package_name }}"
    METADATA = ("classifiers", "keywords", "platforms", "requirements")
    __slots__ = (
        "metadata",
        "project_details",
        "supported_pythons",
        "initialize_with_git",
        "project_dir",
    )

    def __init__(self):
        """Set project defaults."""
        self.metadata = {}
        self.project_details = ProjectDetails()
        self.supported_pythons = []
        self.initialize_with_git = False
        self.project_dir = pathlib.Path(os.getcwd())

    def ask(self):
        """Ask for user input."""
        for name in type(self).METADATA:
            self.metadata[name] = globals()[f"get_{name}"]()
        self.project_details = ProjectDetails().ask()
        supported_pythons = get_interpreters(ALL_PYTHONS)
        if len(supported_pythons) == 0:
            supported_pythons = ALL_PYTHONS
        print(f"Supported pythons: {', '.join(supported_pythons)}")
        self.supported_pythons = supported_pythons
        self.initialize_with_git = click.prompt(
            "Initialize with git init?", default="n", type=click.BOOL
        )

    def render_topdir_files(self):
        """Render files under top level directory."""
        cls = type(self)
        env = {
            "least_python3": self.supported_pythons[0],
            "has_entry_points": self.project_details.has_entry_points(),
            "package_name": cls.PACKAGE_NAME,
            "namespace": cls.NAMESPACE if cls.NAMESPACE != REMOVE_ME else "",
        }
        env.update(self.metadata)
        if self.project_details.has_entry_points():
            env.update(self.project_details.to_dict())
        tox_supported_pythons = [
            x.replace(".", "") for x in self.supported_pythons
        ]
        tox_supported_pythons = "{" f"{','.join(tox_supported_pythons)}" "}"
        env.update({"supported_pythons": tox_supported_pythons})

        result = render_prjfile(self.project_dir, "LICENSE")
        result |= render_prjfile(self.project_dir, "MANIFEST.in")
        result |= render_prjfile(self.project_dir, "pyproject.toml")
        result |= render_prjfile(self.project_dir, "setup.cfg", env)
        result |= render_prjfile(self.project_dir, "setup.py", chmod_x=True)
        return result | render_prjfile(self.project_dir, "tox.ini", env)

    def render_sources(self):
        """Render files under src directory."""
        cls = type(self)
        package_dir = self.project_dir / "src"
        if cls.NAMESPACE != REMOVE_ME:
            rmtree(package_dir / cls.PACKAGE_NAME)
            package_dir = package_dir / cls.NAMESPACE
        else:
            rmtree(package_dir / REMOVE_ME)
        package_dir = package_dir / cls.PACKAGE_NAME
        env = self.project_details.to_dict()
        epsrc = f"{env['entry_point_source']}.py"

        result = render_prjfile(package_dir, "__init__.py")
        if self.project_details.project_type == ProjectDetails.CONSOLE_APP:
            result |= render_prjfile(package_dir, "__main__.py", env)
            result |= render_prjfile(
                package_dir, "main.py", env, newname=epsrc
            )
        elif self.project_details.project_type == ProjectDetails.PLUGIN:
            result |= render_prjfile(
                package_dir, "plugin.py", env, newname=epsrc
            )
        for name in ("__main__", "main", "plugin"):
            result |= remove_file(package_dir / f"{name}.py.j2")
        return result | render_prjfile(package_dir, "version.py")

    def render_tests(self):
        """Render files under tests directory."""
        utests_dir = self.project_dir / "tests" / "unit"
        env = self.project_details.to_dict()

        result = render_prjfile(utests_dir, "__init__.py")
        if self.project_details.project_type == ProjectDetails.CONSOLE_APP:
            result |= render_prjfile(
                utests_dir,
                "test_main.py",
                env,
                newname=f"test_{env['entry_point_source']}.py",
            )
        result |= remove_file(utests_dir / "test_main.py.j2")
        return result | render_prjfile(utests_dir, "test_version.py")

    def create(self):
        """Create a project."""
        self.ask()
        result = self.render_topdir_files()
        result |= self.render_sources()
        result |= self.render_tests()
        if result != SUCCESS:
            return result
        return init_repo(self.project_dir, self.initialize_with_git)


if __name__ == "__main__":
    sys.exit(Project().create())
