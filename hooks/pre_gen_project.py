#!/usr/bin/python3
#                                                         -*- coding: utf-8 -*-
# File:    ./hooks/pre_gen_project.py
# Author:  Jiří Kučera <sanczes AT gmail.com>
# Date:    2021-01-30 15:08:47 +0100
# Project: pyproject-template: A cookiecutter template for Python projects
#
# SPDX-License-Identifier: MIT
#
"""Hook that runs before the project is generated."""

from utils import (
    IDEN_RE,
    REMOVE_ME,
    WORD_RE,
    verify_email,
    verify_not_empty,
    verify_value,
)

PROJECT_NAME = "{{ cookiecutter.project_name }}".strip()
PACKAGE_NAME = "{{ cookiecutter.package_name }}".strip()
NAMESPACE = "{{ cookiecutter.namespace }}".strip()
AUTHOR_FULL_NAME = "{{ cookiecutter.author_full_name }}".strip()
AUTHOR_EMAIL = "{{ cookiecutter.author_email }}".strip().replace(" AT ", "@")
GITHUB_USER = "{{ cookiecutter.github_user }}".strip()
GITHUB_EMAIL = "{{ cookiecutter.github_email }}".strip().replace(" AT ", "@")
COPYRIGHT_HOLDER = "{{ cookiecutter.copyright_holder }}".strip()
TEAM_NAME = "{{ cookiecutter.team_name }}".strip()
TEAM_EMAIL = "{{ cookiecutter.team_email }}".strip().replace(" AT ", "@")
PROJECT_DESCRIPTION = "{{ cookiecutter.project_description }}".strip()


if __name__ == "__main__":
    verify_value("project_name", WORD_RE, PROJECT_NAME)
    verify_value("package_name", IDEN_RE, PACKAGE_NAME)
    if NAMESPACE != REMOVE_ME:
        verify_value("namespace", IDEN_RE, NAMESPACE)
    verify_not_empty("author_full_name", AUTHOR_FULL_NAME)
    verify_email("author_email", AUTHOR_EMAIL)
    verify_value("github_user", WORD_RE, GITHUB_USER)
    verify_email("github_email", GITHUB_EMAIL)
    verify_not_empty("copyright_holder", COPYRIGHT_HOLDER)
    verify_not_empty("team_name", TEAM_NAME)
    verify_email("team_email", TEAM_EMAIL)
    verify_not_empty("project_description", PROJECT_DESCRIPTION)
