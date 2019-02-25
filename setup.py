import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="dorkbot",
    version="0.0.3",
    author="jgor",
    author_email="jgor@utexas.edu",
    description="Command-line tool to scan search results for vulnerabilities",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="http://dorkbot.io",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python",
        "License :: Free for non-commercial use",
        "Operating System :: OS Independent",
    ],
    install_requires = [
        "psycopg2",
    ],
    entry_points = {
        "console_scripts": ["dorkbot=dorkbot.dorkbot:main"],
    },
    include_package_data=True,
)

