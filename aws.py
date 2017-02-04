# -*- coding: utf-8 -*-
"""
collection of functions for managing AWS
    create key, security group, server, ip address
    various tools
    
manual steps before running scripts
    create AWS account
    create config and credentials on local client
    request gpu access
"""
import logging as log
import pandas as pd
import boto3
import os

### parameters ####################################################

user = 'ec2-user'
keyfile = os.path.join(os.path.expanduser("~"), ".aws", "key.pem")

ec2 = boto3.resource('ec2')
client = boto3.client('ec2')

### create resource ####################################################
    
def create_key():
    """ creates keypair and saves private key to file """
    try:
        key = ec2.create_key_pair(KeyName="key")
        with open(keyfile, "w") as f:
            f.write(key.key_material)
    except Exception as e:
        log.warning(e)

def create_securityGroup():
    """ create security group with inbound access for http, jupyter and ssh """
    sec = ec2.create_security_group(GroupName="simon", 
                                    Decription="wordpress, jupyter, ssh")
    sec.authorize_ingress(
          IpPermissions=[dict(IpProtocol='tcp', FromPort=80, ToPort=80),
                         dict(IpProtocol='tcp', FromPort=443, ToPort=443),
                         dict(IpProtocol='tcp', FromPort=8888, ToPort=8888),
                         dict(IpProtocol='tcp', FromPort=22, ToPort=22)])
    return sec

def create_server(image_id="ami-c51e3eb6", servertype="free", disksize=30):
    """ create instance using ami for amazon linux """
    servers = dict(free="t2.micro", gpu="p2.xlarge")
    launch_spec = dict(ImageId=image_id,
                        MinCount=1, MaxCount=1, 
                        InstanceType=servers[servertype], 
                        SecurityGroups=["simon"],
                        KeyName="key",
                        BlockDeviceMappings=
                                [dict(DeviceName="/dev/xvda", 
                                 Ebs=dict(VolumeSize=disksize))])
    if servertype == "free":
        instances = ec2.create_instances(**launch_spec)
    elif servertype =="gpu":
        instances = client.request_spot_instances(DryRun=True, 
                                                  launch_spec=launch_spec)
    setName(instances[0])
    instances[0].wait_until_running()
    return instances[0]

def create_staticIP(instancename):
    """ create a new elastic IP address and assigns to instance """
    elasticip = client.allocate_address()
    client.associate_address(InstanceId=getId(instancename),
                             PublicIp=elasticip["PublicIp"])

def create_ami(instancename):
    """ copy server to ami """
    return client.create_image(InstanceId=getId(instancename), 
                               Name="ami1")
    
### tools ##############################################################

def getInstances():
    """ show list of instances """
    a=[]
    for i in ec2.instances.all():
        a.append([getName(i), i.instance_id, i.image.image_id,
                  i.instance_type, i.state["Name"],
                  i.public_ip_address])
    return pd.DataFrame(a, columns=["name", "instance_id","image","type",
                                       "state","ip"])

def setName(instance, name=None):
    """ sets unique name of an instance """
    if not name:
        instances = getInstances()
        namecount = 0
        while True:
            name = "sm"+str(namecount)
            if name not in list(instances.name):
                break
    instance.create_tags(Tags=[dict(Key="Name", Value=name)])
    
def getName(instance):
    try:
        tags = {tag["Key"]:tag["Value"] for tag in instance.tags}
        return tags["Name"]
    except:
        return "unknown"
            
def getId(name, collection=ec2.instances):
    """ get resource by name """
    for i in collection.all():
        if name == getName(i):
            return i.id