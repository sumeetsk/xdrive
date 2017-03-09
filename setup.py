""" minimal setup """
from setuptools import setup
import autosetup

params = autosetup.defaults()

params.update(
   description="Portable drive that can be moved between AWS instances")

# remove spurious packages identified by pipreqs
params["install_requires"] = [x for x in params["install_requires"]
                if not x in ["Fabric", "simonm3.egg", "logconfig"]]

# add required by notebook
params["install_requires"].extend(["simonm3"])

print(params)
setup(**params)