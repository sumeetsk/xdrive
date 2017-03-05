from setuptools import setup

setup(name='xdrive',
      version='1.0',
      description="Puts programs and data on a portable drive rather than an "\
                  "on the AWS server. The drive can then be moved between"\
                  "different types of server including spot instances.",
      url='http://github.com/simonm3/basics',
      author='Simon Mackenzie',
      author_email='simonm3@gmail.com',
      license='MIT',
      packages=[],
      py_modules=["xdrive"],
      install_requires=["simonm3"])