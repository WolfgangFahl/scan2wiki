# ! important
# see https://stackoverflow.com/a/27868004/1497139
from setuptools import setup

# read the contents of your README file
from os import path
this_directory = path.abspath(path.dirname(__file__))
with open(path.join(this_directory, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='scan2wiki',
    version='0.0.9',

    packages=['scan',],
    classifiers=[
            'Programming Language :: Python',
            'Programming Language :: Python :: 3.7',
            'Programming Language :: Python :: 3.8',
            'Programming Language :: Python :: 3.9'
    ],

    install_requires=[
      'gitpython',
      'jinja2',
      'pywikibot',
      'pycrypto',
      'mwclient',
    ],
    entry_points={
      'console_scripts': [
        'scan2wiki = web.webserver:main',
      ],
    },
    author='Wolfgang Fahl',
    maintainer='Wolfgang Fahl',
    url='https://github.com/WolfgangFahl/scan2wiki',
    license='Apache License',
    description='Scan from Scanner to Wiki',
    long_description=long_description,
    long_description_content_type='text/markdown'
)
