""" minimal setup """
from setuptools import setup
setup(name='xdrive',
      version='1.1.3',
      url='http://github.com/simonm3/xdrive',
      setup_requires=[ "setuptools_git >= 0.3", ],
      description="Portable drive that can be moved between AWS instances",
      py_modules=[],
      install_requires=["simonm3", "fabric3", "pandas", "boto3"])