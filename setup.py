#!/usr/bin/env python3
from setuptools import setup, find_packages
import os

# Read the README for long description
with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

# Read requirements
with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="bob-framework",
    version="0.1.0",
    author="yelkhamra",
    author_email="yelkhamra@users.noreply.github.com",
    description="Build Orchestration Bot - A generalized autonomous coding framework",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yye00/bob",
    packages=find_packages(exclude=["tests", "tests.*", "examples", "docs"]),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Code Generators",
        "Topic :: Software Development :: Build Tools",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.10",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "bob=bob.cli.main:cli",
        ],
    },
    include_package_data=True,
    package_data={
        "bob": [
            "prompts/*.md",
            "database/schema.sql",
        ],
    },
    keywords="autonomous-coding ai-agents code-generation anthropic claude orchestration",
    project_urls={
        "Bug Reports": "https://github.com/yye00/bob/issues",
        "Source": "https://github.com/yye00/bob",
        "Documentation": "https://docs.bob-framework.dev",
    },
)
