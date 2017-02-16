# -*- coding: utf-8 -*-
"""
manage aws resources
    create key, security group
    manage tags
    list resources used
    
NOTE: This is a set of functions not a class
    
manual steps
    create AWS account
    create config and credentials on local client
    request gpu limit increase
    
    wget https://repo.continuum.io/miniconda/Miniconda3-latest-Linux-x86_64.sh
    bash Miniconda3-latest-Linux-x86_64.sh
    exit/login
    pip install kaggle-cli
    kg config -u simonm3@gmail.com -p <password>
    kg config -c dogs-vs-cats-redux-kernels-edition
    kg download
"""
import logging as log
import pandas as pd
import boto3
import os
import fabric.api as fab
log.getLogger("paramiko").setLevel(log.ERROR)

### parameters ####################################################

fab.env.key_filename = os.path.join(os.path.expanduser("~"), ".aws", "key.pem")

### connection #############################################################

ec2 = boto3.resource('ec2')
client = boto3.client('ec2')

### create resource  ##############################################

def create_key():
    """ creates keypair and saves private key to file """
    try:
        key = ec2.create_key_pair(KeyName="key")
        with open(fab.env.key_filename, "w") as f:
            f.write(key.key_material)
    except Exception as e:
        log.warning(e)

def create_security_group():
    """ create security group with inbound access for http, jupyter and ssh """
    sec = ec2.create_security_group(GroupName="simon", 
                                    Decription="wordpress, jupyter, ssh")
    sec.authorize_ingress(
          IpPermissions=[dict(IpProtocol='tcp', FromPort=80, ToPort=80),
                         dict(IpProtocol='tcp', FromPort=443, ToPort=443),
                         dict(IpProtocol='tcp', FromPort=8888, ToPort=8888),
                         dict(IpProtocol='tcp', FromPort=22, ToPort=22)])

### manage tags ##############################################
    
def get_tags(res):
    """ get tags as a normal dict rather than cryptic boto3 format """
    tags = res.tags or dict()
    return {tag["Key"]:tag["Value"] for tag in tags}
        
def get_tag(res, key):
    return get_tags(res).get(key, "")

def set_tag(res, key, value):
    res.create_tags(Tags=[dict(Key=key, Value=value)])
    
def get_name(res):
    return get_tag(res, "Name")
    
def set_name(res, value):
    set_tag(res, "Name", value)

def get(name=None, collections=None, unique=True):
    """ gets resource by name
        if unique=false then gets all resources with name
        if name=None then gets all resources
        collections can be collection or list of collections
        collections=None returns instances, volumes, snapshots
    """
    # cleanup inputs
    if collections is None:
        collections = [ec2.instances, ec2.volumes, ec2.snapshots]
    if not isinstance(collections, list):
        collections = [collections]

    # get
    reslist = []
    for collection in collections:
        try:
            # snapshots collection includes the worlds snapshots!
            owned = list(collection.all().filter(OwnerIds=["self"]))
        except:
            owned = list(collection.all())
        for res in owned:
            if name is None or name == get_name(res):
                reslist.append(res)
    
    if len(reslist) == 0:
        return None
    if unique:
        if len(reslist) == 1:
            return reslist[0]
        raise Exception("More than one resource found:\n%s"%reslist)
    return reslist

### get all resources ####################################################

def get_instances():
    """ show list of instances """
    a=[]
    for i in ec2.instances.all():
        a.append([get_name(i), i.instance_id, i.image.image_id,
                  i.instance_type, i.state["Name"],
                  i.public_ip_address])
    return pd.DataFrame(a, columns=["name", "instance_id","image","type",
                                       "state","ip"])
    
def get_ips():
    """ get list of elastic ips """
    return [ip["PublicIp"] for ip in client.describe_addresses()["Addresses"]]
    
### No longer required???? ###########################################
    
#def get_resources(tagvalues=None, collections=None):
#    """ gets list of resources by tag value (ignores tag key)
#        tagvalues and collections can be item or list
#        tagvalues=None returns all resources
#        collections=None returns instances, volumes, snapshots
#    """
#    # cleanup inputs
#    if collections is None:
#        collections = [ec2.instances, ec2.volumes, ec2.snapshots]
#    if tagvalues and not isinstance(tagvalues, list):
#        tagvalues = [tagvalues]
#    if not isinstance(collections, list):
#        collections = [collections]
#    # get tagvalues
#    reslist = []
#    for collection in collections:
#        try:
#            # snapshots collection includes the worlds snapshots!
#            owned = list(collection.all().filter(OwnerIds=["self"]))
#        except:
#            owned = list(collection.all())
#        for res in owned:
#            tags = get_tags(res)
#            if tagvalues is None:
#                reslist.append(res)
#            elif len(set(tagvalues) & set(tags.values())) > 0:
#                reslist.append(res)
#    return reslist
#
#def get_resource(tagvalues, collections=None):
#    """ gets unique resource with tag value """
#    r = get_resources(tagvalues, collections)
#    if len(r) == 0:
#        return None
#    if len(r) > 1:
#        raise Exception("More than one resource found:\n%s"%r)
#    return r[0]
   