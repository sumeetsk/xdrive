# -*- coding: utf-8 -*-
import os
from subprocess import check_output, CalledProcessError
import shlex
import sys

# location of configuration files
aws = os.path.join(os.path.expanduser("~"), ".aws")
config = os.path.join(os.path.expanduser("~"), ".xdrive")
print(aws)
print(config)

if "-d" in sys.argv:
    # delete existing container even if running
    try:
        r = check_output(shlex.split("docker rm -f xdrive"))
        print("existing xdrive container deleted")
    except:
        pass

# ~/.aws (if you want aws access)
# ~/.xdrive/config.yaml (if you want a region other than eu-west)
cmd = "docker run --rm --name xdrive -d -p 8888:8888 "\
    "-v '{aws}':/root/.aws "\
    "-v '{config}':/root/.xdrive "\
    "simonm3/xdriveclient".format(**locals())
print(cmd)
try:
    r = check_output(shlex.split(cmd))
    print("running container xdrive with notebook at port 8888")
except:
    print("You can rerun xdriveclient with -d to remove existing container.\n "\
          "*** EXISTING CONTAINER AND ALL ITS DATA WILL BE DELETED ***")
    pass