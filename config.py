# -*- coding: utf-8 -*-
"""
Created on Sat Feb 18 15:53:27 2017

@author: s
"""
import os

user = "ec2-user"
keyfile = os.path.join(os.path.expanduser("~"), ".aws", "key.pem")
here = os.path.dirname(os.path.abspath(__file__))

# instance types
itypes = dict(gpu="p2.xlarge", free="t2.micro")

# cpu=amazon linux
# gpu=amazon linux with nvidia CUDA 7.5 = "ami-873e61e1"
amis = dict(gpu="ami-873e61e1", free="ami-c51e3eb6")

# what is best setting for this????
spotprice = ".25"

# instance specification
base_spec = dict(ImageId=amis["free"],
                InstanceType=itypes["free"], 
                SecurityGroups=["simon"],
                KeyName="key",
                MinCount=1, MaxCount=1,
                BlockDeviceMappings=[])

"""
note that currently scripts are written for amazon linux
    centos based
    user = "ec2_user"

alternative AMIs
    amazon deep learning = "ami-cb97d5b8"
    fastai_course_1 "ami-b43d1ec7"
    amazon linux = "ami-c51e3eb6"
"""