# ! important
# see https://stackoverflow.com/a/27868004/1497139
from setuptools import setup
from scan.version import Version
import pathlib
here = pathlib.Path(__file__).parent.resolve()
requirements     = (here / 'requirements.txt').read_text(encoding='utf-8').split("\n")
long_description = (here / 'README.md'       ).read_text(encoding='utf-8')

setup(
    name=Version.name,
    version=Version.version,

    packages=['scan'],
    classifiers=[
            'Programming Language :: Python',
            'Programming Language :: Python :: 3.7',
            'Programming Language :: Python :: 3.8',
            'Programming Language :: Python :: 3.9'
            'Programming Language :: Python :: 3.10'
    ],
    install_requires=requirements,
    entry_points={
      'console_scripts': [
        'scan2wiki = scan.webserver:main',
      ],
    },
    author='Wolfgang Fahl',
    maintainer='Wolfgang Fahl',
    url='https://github.com/WolfgangFahl/scan2wiki',
    license='Apache License',
    description=Version.description,
    long_description=long_description,
    long_description_content_type='text/markdown'
)
