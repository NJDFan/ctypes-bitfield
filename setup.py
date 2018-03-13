from setuptools import setup, find_packages  # Always prefer setuptools over distutils
from codecs import open  # To use a consistent encoding
from os import path

here = path.abspath(path.dirname(__file__))

# Get the long description from the relevant file
with open(path.join(here, 'README.txt'), encoding='utf-8') as f:
	long_description = f.read()

setup(
	name='ctypes-bitfield',

	# Versions should comply with PEP440.  For a discussion on single-sourcing
	# the version across setup.py and the project code, see
	# http://packaging.python.org/en/latest/tutorial.html#version
	description='Ctypes Register Bitfields',
	version='0.3.2',
	
	long_description=long_description,

	# The project's main homepage.
	url='https://github.com/NJDFan/ctypes-bitfield/',

	# Author details
	author='Rob Gaddi',
	author_email='rgaddi@highlandtechnology.com',

	# Choose your license
	license='MIT',

	# See https://pypi.python.org/pypi?%3Aaction=list_classifiers
	classifiers=[
		# How mature is this project? Common values are
		#   3 - Alpha
		#   4 - Beta
		#   5 - Production/Stable
		'Development Status :: 5 - Production/Stable',

		# Indicate who your project is intended for
		'Intended Audience :: Developers',
		'Topic :: System :: Hardware',

		# Pick your license as you wish (should match "license" above)
		'License :: OSI Approved :: MIT License',

		# Specify the Python versions you support here. In particular, ensure
		# that you indicate whether you support Python 2, Python 3 or both.
		'Programming Language :: Python :: 2',
		'Programming Language :: Python :: 2.7',
		'Programming Language :: Python :: 3',
		'Programming Language :: Python :: 3.2',
		'Programming Language :: Python :: 3.3',
		'Programming Language :: Python :: 3.4',
	],

	# What does your project relate to?
	keywords='sample bitfield register memory',

	packages=['bitfield', 'remotestruct'],
	test_suite='tests',
)
