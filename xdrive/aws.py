# -*- coding: utf-8 -*-
"""
manage aws resources
    manage tags
    list resources used
    
NOTE: This is a set of functions not a class
"""
import logging as log
import pandas as pd
import boto3
import fabric.api as fab
from time import sleep
import pyperclip

### connection #############################################################

ec2 = boto3.resource('ec2')
client = boto3.client('ec2')

### manage tags ##############################################
    
def get_tags(res):
    """ get tags as a normal dict rather than cryptic boto3 format """
    tags = res.tags or dict()
    return {tag["Key"]:tag["Value"] for tag in tags}
        
def get_tag(res, key):
    """ return tag from resource/key """
    return get_tags(res).get(key, "")

def set_tag(res, key, value):
    """ set tag from resource/key/value """
    res.create_tags(Tags=[dict(Key=key, Value=value)])
    
def get_name(res):
    """ return name from resource. more friendly than using id """
    return get_tag(res, "Name")
    
def set_name(res, value):
    """ set name for resource. more friendly than using id """
    set_tag(res, "Name", value)

def get(name=None, collections=None, unique=True):
    """ get resource by name
        if unique=True then raise exception if more than one
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
        reslist.extend([res for res in owned if name is None 
                               or name == get_name(res)])
    # cleanup outputs
    if len(reslist) == 0:
        return None
    if unique:
        if len(reslist) == 1:
            return reslist[0]
        raise Exception("More than one resource found:\n%s"%reslist)
    return reslist

def associate_address(instance, ip=None):
    """ associates instance with ip address """
    if isinstance(instance, str):
        instance = get(instance)
    
    if ip == None:
        ip = get_ip()
    
    fab.env.host_string = ip
    try:
        pyperclip.copy(ip)
    except:
        log.warning("pyperclip cannot find copy/paste mechanism")

    # associate elastic ip
    client.associate_address(InstanceId=instance.id, PublicIp=ip)
    while True:
        instance = ec2.Instance(instance.id)
        if instance.public_ip_address == ip:
            break
        log.info("waiting for ip address to be associated")
        sleep(2)
    name = get_name(instance)
    log.info(f"{name} ready at {fab.env.host_string} (clipboard)")

### get all resources ####################################################

def get_instances():
    """ get dataframe of instances """
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

def get_ip():
    return get_ips()[0]