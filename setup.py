from setuptools import setup, find_packages

setup(name='xdrive',
      version='1.0',
      description="Puts programs and data on an external drive rather than "\
                  "on the boot drive. This can then be moved between "\
                  "different types of server including spot instances.",
      url='http://github.com/simonm3/xdrive',
      author='Simon Mackenzie',
      author_email='simonm3@gmail.com',
      license='MIT',
      setup_requires=[ "setuptools_git >= 0.3", ],
      packages=find_packages(),
      install_requires=["simonm3", "fabric3", "pandas", "boto3"])