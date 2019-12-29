import setuptools
import os

pkg_vars = {}
pkg_dir = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(pkg_dir, "dorkbot", "_version.py"), "r") as fh:
    exec(fh.read(), pkg_vars)

with open(os.path.join(pkg_dir, "README.md"), "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="dorkbot",
    version=pkg_vars['__version__'],
    author="jgor",
    author_email="jgor@utexas.edu",
    description="Command-line tool to scan search results for vulnerabilities",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="http://dorkbot.io",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: Free for non-commercial use",
        "Operating System :: OS Independent",
    ],
    entry_points = {
        "console_scripts": ["dorkbot=dorkbot.dorkbot:main"],
    },
    include_package_data=True,
)

