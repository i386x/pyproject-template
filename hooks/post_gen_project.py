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

import jinja2
from cookiecutter.utils import rmtree
from utils import (
    IDEN_RE,
    KWORD_RE,
    REMOVE_ME,
    WORD_RE,
    Config,
    VerificationError,
    YamlConfigItem,
    assert_item_type,
    assert_type,
    chmodx,
    error,
    find_license,
    last_mtime,
    load_classifiers,
    mkstamp,
    remove,
    render_file,
    runcmd,
    sanitize,
)

PACKAGE_NAME_KEY = "package_name"
NAMESPACE_KEY = "namespace"
CLASSIFIERS_KEY = "classifiers"
INTERPRETERS_KEY = "interpreters"
KEYWORDS_KEY = "keywords"
PLATFORMS_KEY = "platforms"
REQUIREMENTS_KEY = "requirements"
PROJECT_TYPE_KEY = "project_type"
PLUGIN_NAME_SPACE_KEY = "plugin_name_space"
ENTRY_POINT_NAME_KEY = "entry_point_name"
ENTRY_POINT_SOURCE_KEY = "entry_point_source"
ENTRY_POINT_SOURCE_DESCRIPTION_KEY = "entry_point_source_description"
ENTRY_POINT_FUNCTION_KEY = "entry_point_function"
INITIALIZE_WITH_GIT_KEY = "initialize_with_git"
LEAST_PYTHON3_KEY = "least_python3"
SUPPORTED_PYTHONS_KEY = "supported_pythons"
HAS_ENTRY_POINTS_KEY = "has_entry_points"
ENTRY_POINT_KIND_KEY = "entry_point_kind"
ENTRY_POINT_FQDN_KEY = "entry_point_fqdn"
PACKAGE = 0
PLUGIN = 1
CONSOLE_APP = 2
SUCCESS = 0
FAILURE = 1
PYVERS = ["3.6", "3.7", "3.8", "3.9"]
PYVER_RE = r"^[3]\.[0-9]+$"
GH_USER = "{{ cookiecutter.github_user }}"
GH_EMAIL = "{{ cookiecutter.github_email|replace(' AT ', '@') }}"
GH_REMOTE = f"git@github.com:{GH_USER}/{{ cookiecutter.project_name }}.git"


class Classifiers(YamlConfigItem):
    """PyPI classifiers config item."""

    __slots__ = ("__classifiers", "__mit_license")

    def __init__(self):
        """Initialize the item."""
        YamlConfigItem.__init__(self)
        self.load_classifiers()
        self.set_description("Specify PyPI classifiers [mandatory]")
        self.set_key(CLASSIFIERS_KEY)
        self.set_value(self.__classifiers, hint=True)

    def load_classifiers(self):
        """Load PyPI classifiers."""
        classifiers = load_classifiers(verbose=True)
        mit_license = find_license(classifiers, "MIT")
        if mit_license is None:
            error("MIT license not in PyPI classifiers?")
        self.__classifiers = [
            c for c in classifiers if not c.startswith("License ::")
        ]
        self.__mit_license = mit_license

    def verify(self, config):
        """Verify `config`."""
        assert_item_type(config, self.key, list)
        items = config[self.key]
        for i, item in enumerate(items):
            assert_type(item, str)
            sitem = sanitize(item)
            if sitem not in self.__classifiers:
                raise VerificationError(
                    f"Invalid classifier ({item})", item.line
                )
            items[i] = sitem
        items.append(self.__mit_license)
        config[self.key] = sorted(items)


class Interpreters(YamlConfigItem):
    """Supported Python interpreters config item."""

    __slots__ = ()

    def __init__(self):
        """Initialize the item."""
        YamlConfigItem.__init__(self)
        self.set_description(
            "Specify supported Python interpreters [mandatory]"
        )
        self.set_key(INTERPRETERS_KEY)
        self.set_value(PYVERS)

    @staticmethod
    def sorter(key):
        """Specify how to sort `key`."""
        return tuple(int(x) for x in key.split("."))

    def verify(self, config):
        """Verify `config`."""
        self.verify_list(config, PYVER_RE, "Python version")


class Keywords(YamlConfigItem):
    """Keywords list config item."""

    __slots__ = ()

    def __init__(self):
        """Initialize the item."""
        YamlConfigItem.__init__(self)
        self.set_description("Specify project keywords [mandatory]")
        self.set_key(KEYWORDS_KEY)
        self.set_value([])

    def verify(self, config):
        """Verify `config`."""
        self.verify_list(config, KWORD_RE, "keyword format")


class Platforms(YamlConfigItem):
    """Platforms list config item."""

    __slots__ = ()

    def __init__(self):
        """Initialize the item."""
        YamlConfigItem.__init__(self)
        self.set_description(
            "Specify supported platforms (any, linux, macos, nt, os2, posix,",
            "unix, win32, windows, ...) [mandatory]",
        )
        self.set_key(PLATFORMS_KEY)
        self.set_value([])

    def verify(self, config):
        """Verify `config`."""
        self.verify_list(config, WORD_RE, "platform name")


class Requirements(YamlConfigItem):
    """Requirements list config item."""

    __slots__ = ()

    def __init__(self):
        """Initialize the item."""
        YamlConfigItem.__init__(self)
        self.set_description(
            "Specify the list of project requirements (in pip format)"
        )
        self.set_key(REQUIREMENTS_KEY)
        self.set_value([])

    def verify(self, config):
        """Verify `config`."""
        self.verify_list(
            config, WORD_RE, "requirement name", empty=True, sort=False
        )


class ProjectType(YamlConfigItem):
    """Project type config item."""

    __slots__ = ()

    def __init__(self):
        """Initialize the item."""
        YamlConfigItem.__init__(self)
        self.set_description(
            "Specify the project type. Choices are:",
            "  0 - package",
            "  1 - plugin",
            "  2 - console application",
        )
        self.set_key(PROJECT_TYPE_KEY)
        self.set_value(PACKAGE)

    def verify(self, config):
        """Verify `config`."""
        self.verify_int(config, PACKAGE, CONSOLE_APP)


class PluginNameSpace(YamlConfigItem):
    """Plugin name space config item."""

    __slots__ = ()

    def __init__(self):
        """Initialize the item."""
        YamlConfigItem.__init__(self)
        self.set_description(
            "If you selected as a project_type plugin (1), please provide the",
            "plugin name space (i.e. if you are developing a tox plugin, the",
            'plugin name space is conventionally "tox")',
        )
        self.set_key(PLUGIN_NAME_SPACE_KEY)
        self.set_value(None)

    def verify(self, config):
        """Verify `config`."""
        project_type = config[PROJECT_TYPE_KEY]
        if project_type != PLUGIN:
            return
        self.verify_str(config, IDEN_RE)


class EntryPointName(YamlConfigItem):
    """Entry point name config item."""

    __slots__ = ()

    def __init__(self):
        """Initialize the item."""
        YamlConfigItem.__init__(self)
        self.set_description(
            "If your project has entry points (project_type > 0), please",
            "provide the entry point name (this should be plugin or script",
            "name)",
        )
        self.set_key(ENTRY_POINT_NAME_KEY)
        self.set_value(None)

    def verify(self, config):
        """Verify `config`."""
        project_type = config[PROJECT_TYPE_KEY]
        if project_type == PACKAGE:
            return
        self.verify_str(config, WORD_RE)


class EntryPointSource(YamlConfigItem):
    """Entry point source config item."""

    __slots__ = ()

    def __init__(self):
        """Initialize the item."""
        YamlConfigItem.__init__(self)
        self.set_description(
            "If your project has entry points (project_type > 0), please",
            "provide the name of the source file (without extension) that",
            "contains the entry point's code",
        )
        self.set_key(ENTRY_POINT_SOURCE_KEY)
        self.set_value(None)

    def verify(self, config):
        """Verify `config`."""
        project_type = config[PROJECT_TYPE_KEY]
        if project_type == PACKAGE:
            return
        self.verify_str(config, IDEN_RE)


class EntryPointSourceDescription(YamlConfigItem):
    """Entry point source file description config item."""

    __slots__ = ()

    def __init__(self):
        """Initialize the item."""
        YamlConfigItem.__init__(self)
        self.set_description(
            "If your project has entry points (project_type > 0), please",
            "provide the description of the entry point source file (what",
            "should go inside doc string)",
        )
        self.set_key(ENTRY_POINT_SOURCE_DESCRIPTION_KEY)
        self.set_value(None)

    def verify(self, config):
        """Verify `config`."""
        project_type = config[PROJECT_TYPE_KEY]
        if project_type == PACKAGE:
            return
        self.verify_str(config)
        if config[self.key][-1] != ".":
            config[self.key] += "."


class EntryPointFunction(YamlConfigItem):
    """Entry point function config item."""

    __slots__ = ()

    def __init__(self):
        """Initialize the item."""
        YamlConfigItem.__init__(self)
        self.set_description(
            "If you selected as a project_type console application (2),",
            "please provide the name of function that should be an",
            "application entry point",
        )
        self.set_key(ENTRY_POINT_FUNCTION_KEY)
        self.set_value("main")

    def verify(self, config):
        """Verify `config`."""
        project_type = config[PROJECT_TYPE_KEY]
        if project_type != CONSOLE_APP:
            return
        self.verify_str(config, IDEN_RE)


class InitializeWithGit(YamlConfigItem):
    """Initialize with git config item."""

    __slots__ = ()

    def __init__(self):
        """Initialize the item."""
        YamlConfigItem.__init__(self)
        self.set_description(
            "Initialize the project with git? (choose yes, no, y, n, true,",
            "false, t, f, 1, 0)",
        )
        self.set_key(INITIALIZE_WITH_GIT_KEY)
        self.set_value("yes")

    def verify(self, config):
        """Verify `config`."""
        self.verify_bool(config)


class ProjectConfig(Config):
    """Holds project configuration."""

    __slots__ = ()

    def __init__(self):
        """Initialize the config."""
        Config.__init__(self)
        self.set_items(
            Classifiers,
            Interpreters,
            Keywords,
            Platforms,
            Requirements,
            ProjectType,
            PluginNameSpace,
            EntryPointName,
            EntryPointSource,
            EntryPointSourceDescription,
            EntryPointFunction,
            InitializeWithGit,
        )
        self.set_editor(f"vim +{Config.LINE_ARG} {Config.NAME_ARG}")

    def render(self):
        """Render project configuration."""
        lines = ["---", ""]
        lines.extend(Config.render(self))
        return lines


def render_prjfile(prjdir, prjfile, env=None, newname=None, chmod_x=False):
    """Render project file."""
    env = env or {}
    src, dest = prjdir / f"{prjfile}.j2", prjdir / (newname or prjfile)
    env["stamp"] = mkstamp(last_mtime(src))
    render_file(src, dest, env)
    if chmod_x:
        chmodx(dest)
    remove(src)


def init_repo(prjdir, should_init):
    """Initialize repository with git init."""
    if not should_init:
        return
    runcmd("git", ["init"], prjdir)
    runcmd("git", ["config", "user.name", GH_USER], prjdir)
    runcmd("git", ["config", "user.email", GH_EMAIL], prjdir)
    runcmd("git", ["remote", "add", "origin", GH_REMOTE], prjdir)
    runcmd("git", ["add", "."], prjdir)
    runcmd("git", ["commit", "-m", "Initial commit"], prjdir)
    runcmd("git", ["branch", "-M", "main"], prjdir)


class Project:
    """Implements project creation logic."""

    NAMESPACE = "{{ cookiecutter.namespace }}"
    PACKAGE_NAME = "{{ cookiecutter.package_name }}"
    __slots__ = ("config", "j2env", "project_dir")

    def __init__(self):
        """Set project defaults."""
        config = ProjectConfig()
        config.set_editor(
            os.getenv("EDITOR", f"vim +{Config.LINE_ARG} {Config.NAME_ARG}")
        )
        self.config = config
        self.j2env = {}
        self.project_dir = pathlib.Path(os.getcwd())

    def configure(self):
        """Configure the project."""
        self.config.read_config("pyproject")
        if len(self.config) == 0:
            return False
        self.init_j2env()
        return True

    def init_j2env(self):
        """Initialize Jinja2 environment."""
        cls, config, j2env = type(self), self.config, {}
        j2env[PACKAGE_NAME_KEY] = cls.PACKAGE_NAME
        j2env[NAMESPACE_KEY] = (
            cls.NAMESPACE if cls.NAMESPACE != REMOVE_ME else ""
        )
        j2env[CLASSIFIERS_KEY] = config[CLASSIFIERS_KEY]
        interpreters = config[INTERPRETERS_KEY]
        j2env[LEAST_PYTHON3_KEY] = interpreters[0]
        tox_envlist = ",".join([x.replace(".", "") for x in interpreters])
        j2env[SUPPORTED_PYTHONS_KEY] = "{" f"{tox_envlist}" "}"
        j2env[KEYWORDS_KEY] = config[KEYWORDS_KEY]
        j2env[PLATFORMS_KEY] = config[PLATFORMS_KEY]
        j2env[REQUIREMENTS_KEY] = config[REQUIREMENTS_KEY]
        project_type = config[PROJECT_TYPE_KEY]
        j2env[HAS_ENTRY_POINTS_KEY] = project_type > PACKAGE
        if project_type == PACKAGE:
            j2env[ENTRY_POINT_KIND_KEY] = ""
        elif project_type == PLUGIN:
            j2env[ENTRY_POINT_KIND_KEY] = config[PLUGIN_NAME_SPACE_KEY]
        else:
            j2env[ENTRY_POINT_KIND_KEY] = "console_scripts"
        j2env[ENTRY_POINT_NAME_KEY] = config[ENTRY_POINT_NAME_KEY]
        fqdn = j2env[ENTRY_POINT_SOURCE_KEY] = config[ENTRY_POINT_SOURCE_KEY]
        j2env[ENTRY_POINT_SOURCE_DESCRIPTION_KEY] = config[
            ENTRY_POINT_SOURCE_DESCRIPTION_KEY
        ]
        if project_type == CONSOLE_APP:
            epfunc = config[ENTRY_POINT_FUNCTION_KEY]
            j2env[ENTRY_POINT_FUNCTION_KEY] = epfunc
            fqdn += f":{epfunc}"
        j2env[ENTRY_POINT_FQDN_KEY] = fqdn
        j2env[INITIALIZE_WITH_GIT_KEY] = config[INITIALIZE_WITH_GIT_KEY]
        self.j2env = j2env

    def render_topdir_files(self):
        """Render files under top level directory."""
        env, project_dir = self.j2env, self.project_dir
        render_prjfile(project_dir, "LICENSE")
        render_prjfile(project_dir, "MANIFEST.in")
        render_prjfile(project_dir, "pyproject.toml")
        render_prjfile(project_dir, "setup.cfg", env)
        render_prjfile(project_dir, "setup.py", chmod_x=True)
        render_prjfile(project_dir, "tox.ini", env)

    def render_sources(self):
        """Render files under src directory."""
        cls = type(self)
        env = self.j2env
        package_dir = self.project_dir / "src"
        if cls.NAMESPACE != REMOVE_ME:
            rmtree(package_dir / cls.PACKAGE_NAME)
            package_dir = package_dir / cls.NAMESPACE
        else:
            rmtree(package_dir / REMOVE_ME)
        package_dir = package_dir / cls.PACKAGE_NAME
        project_type = self.config[PROJECT_TYPE_KEY]
        epsrc = f"{env[ENTRY_POINT_SOURCE_KEY]}.py"

        render_prjfile(package_dir, "__init__.py")
        if project_type == CONSOLE_APP:
            render_prjfile(package_dir, "__main__.py", env)
            render_prjfile(package_dir, "main.py", env, newname=epsrc)
        elif project_type == PLUGIN:
            render_prjfile(package_dir, "plugin.py", env, newname=epsrc)
        for name in ("__main__", "main", "plugin"):
            remove(package_dir / f"{name}.py.j2")
        render_prjfile(package_dir, "version.py")

    def render_tests(self):
        """Render files under tests directory."""
        utests_dir = self.project_dir / "tests" / "unit"
        env = self.j2env
        project_type = self.config[PROJECT_TYPE_KEY]
        epsrctest = f"test_{env[ENTRY_POINT_SOURCE_KEY]}.py"

        render_prjfile(utests_dir, "__init__.py")
        if project_type == CONSOLE_APP:
            render_prjfile(utests_dir, "test_main.py", env, newname=epsrctest)
        elif project_type == PLUGIN:
            render_prjfile(
                utests_dir, "test_plugin.py", env, newname=epsrctest
            )
        for name in ("main", "plugin"):
            remove(utests_dir / f"test_{name}.py.j2")
        render_prjfile(utests_dir, "test_version.py")

    def create(self):
        """Create a project."""
        try:
            if not self.configure():
                return FAILURE
            self.render_topdir_files()
            self.render_sources()
            self.render_tests()
            init_repo(self.project_dir, self.j2env[INITIALIZE_WITH_GIT_KEY])
        except (
            OSError,
            jinja2.TemplateError,
            subprocess.SubprocessError,
        ) as exc:
            print(str(exc))
            return FAILURE
        return SUCCESS


if __name__ == "__main__":
    sys.exit(Project().create())
