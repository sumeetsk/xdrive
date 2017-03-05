# -*- coding: utf-8 -*-
"""
configuration settings for xdrive package
"""
import os

# user for amazon linux AMI
user = "ec2-user"

# location of keyfile
keyfile = os.path.join(os.path.expanduser("~"), ".aws", "key.pem")

here = os.path.dirname(os.path.abspath(__file__))

# instance types
itypes = dict(gpu="p2.xlarge", free="t2.micro")

# cpu=amazon linux. gpu=amazon linux with nvidia CUDA 7.5
# these are in region eu-west-1
amis = dict(free="ami-c51e3eb6", gpu="ami-873e61e1")

# typical spot price 18c/hour. what is best setting for this???
spotprice = ".25"

# instance specification
base_spec = dict(ImageId=amis["free"],
                InstanceType=itypes["free"], 
                SecurityGroups=["simon"],
                KeyName="key",
                MinCount=1, MaxCount=1,
                BlockDeviceMappings=[])