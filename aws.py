# -*- coding: utf-8 -*-
"""
collection of functions for managing AWS
    create key, security group, server
    various tools
    
manual steps
    create AWS account
    create config and credentials on local client
    request gpu limit increase
    create pdata volume and upload data

optional
    create elastic ip address
    assign ip address to servers as required
"""
import logging as log
import pandas as pd
import boto3
import os

### parameters ####################################################

keyfile = os.path.join(os.path.expanduser("~"), ".aws", "key.pem")

specs=dict()

# amazon deep learning = "ami-cb97d5b8"
# fastai = "ami-b43d1ec7"

# amazon linux
base_spec = dict(ImageId="ami-c51e3eb6",
                InstanceType="t2.micro", 
                SecurityGroups=["simon"],
                KeyName="key",
                MinCount=1, MaxCount=1,
                BlockDeviceMappings=[])

gpu_type = "p2.xlarge"

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

def create_instance(rootsize=None, gpu=False, data=False, spot=False):
    """ create main types of instance needed for deep learning
    
        rootsize=size of root volume
        gpu=use gpu OR t2.micro
        data=attach pdata snapshot OR not
        spot=use spot OR on-demand
    """
    spec = base_spec.copy()
    
    # set size of root volume
    if rootsize:
        bdm = dict(DeviceName="/dev/xvda",
                   Ebs=dict(VolumeType="gp2",
                           VolumeSize=rootsize))
        spec["BlockDeviceMappings"].append(bdm)
        
    # processor
    if gpu:
        spec.update(InstanceType=gpu_type)
    
    # data volume
    if data:
        vol = getResource("pdata", ec2.volumes)
        if vol:
            raise "volume already exists. manually request instance "\
                    "and attach volume"
        # attach latest snapshot at launch
        snapshots = getResources("pdata", ec2.snapshots)
        latest = sorted(snapshots, key=lambda s:s.start_time, reverse=True)[0]
        
        bdm = dict(DeviceName="/dev/xvdf",
                   Ebs=dict(SnapshotId=latest.id,
                            DeleteOnTermination=False,
                            VolumeType="gp2"))
        spec["BlockDeviceMappings"].append(bdm)

    # spot
    if spot:
        del spec["MinCount"]
        del spec["MaxCount"]
        log.info("spot instance has been requested")
        return client.request_spot_instances(
                    DryRun=False, SpotPrice=".5", **spec)[0]
    # on-demand
    else:
        r = ec2.create_instances(**spec)[0]
        setName(r)
        log.info("instance requested. waiting for start")
        r.wait_until_running()
        log.info("instance started")
        return r
    
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
            namecount += 1
    instance.create_tags(Tags=[dict(Key="Name", Value=name)])
    
def getName(instance):
    try:
        tags = {tag["Key"]:tag["Value"] for tag in instance.tags}
        return tags["Name"]
    except:
        return "unknown"

def tagdict(tags):
    """ convert tags to dict """
    tags = tags or dict()
    return {tag["Key"]:tag["Value"] for tag in tags}
    
def getResources(values, collections=None):
    """ gets list of resources by tag value
        values and collections can be item or list
    """
    if collections is None:
        collections = [ec2.instances, ec2.volumes, ec2.snapshots]
    
    if not isinstance(values, list):
        values = [values]
    if not isinstance(collections, list):
        collections = [collections]
    r = []
    for collection in collections:
        try:
            # snapshots collection includes the worlds snapshots!
            owned = list(collection.all().filter(OwnerIds=["self"]))
        except:
            owned = list(collection.all())
        for res in owned:
            tags = tagdict(res.tags)
            if len(set(values) & set(tags.values())) > 0:
                r.append(res)
    return r

def getResource(values, collections=None):
    """ gets unique resource with tag value """
    r = getResources(values, collections)
    if len(r) == 0:
        return None
    if len(r) > 1:
        raise Exception("More than one resource found:\n%s"%r)
    return r[0]

def getIps():   
    return [ip["PublicIp"] for ip in client.describe_addresses()["Addresses"]]