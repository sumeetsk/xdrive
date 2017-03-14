# -*- coding: utf-8 -*-
"""
create and manage server instances

NOTE: This is a set of functions not a class
"""
from .drive import Drive
from . import apps, aws
import logging as log
import os

import fabric.api as fab
from time import sleep
import pandas as pd
import yaml
import sys
import _creds

# configure
for path in [os.path.join(os.path.expanduser("~"), ".xdrive"),
             os.getcwd(),
             os.path.join(sys.prefix, "etc", "xdrive")]:
    try:
        conf = yaml.load(open(os.path.join(path, "config.yaml")))
        break
    except:
        pass
fab.env.user = conf["user"]
fab.env.key_filename = os.path.join(os.path.expanduser("~"),
                                    ".aws", "key.pem")

def create(name, itype="free", bootsize=None, drive=None, drivesize=10,
                           spot=False):
    """ create instance and mount drive
    
        name = name of instance
        itype = key for itypes dict parameter e.g. free, gpu
        bootsize = size of boot drive
        drive = name of attached, non-boot drive
        spot = spot versus on-demand
    """
    if aws.get(name, aws.ec2.instances):
        raise Exception("instance %s already exists"%name)
    spec = dict(ImageId=conf["amis"]["free"],
                    InstanceType=conf["itypes"]["free"], 
                    SecurityGroups=["simon"],
                    KeyName="key",
                    MinCount=1, MaxCount=1,
                    BlockDeviceMappings=[])

    # instance type
    spec.update(InstanceType=conf["itypes"][itype],
                ImageId=conf["amis"][itype])
    
    # boot drive
    if bootsize:
        bdm = dict(DeviceName="/dev/xvda",
                   Ebs=dict(VolumeType="gp2",
                           VolumeSize=bootsize))
        spec["BlockDeviceMappings"].append(bdm)
            
    # add drive to instance launch
    if drive:
        drive = Drive(drive)
        Ebs=dict(DeleteOnTermination=False,
                 VolumeType="gp2",
                 VolumeSize=drivesize)
        latest_snapshot = drive.latest_snapshot()
        if latest_snapshot:
            Ebs.update(SnapshotId=latest_snapshot.id)
        bdm = dict(DeviceName="/dev/xvdf",
                   Ebs=Ebs)
        spec["BlockDeviceMappings"].append(bdm)
        
    # create spot or on-demand instance
    if spot:
        instance = create_spot(spec)
    else:
        instance = aws.ec2.create_instances(**spec)[0]
    aws.set_name(instance, name)
    log.info("waiting for instance running")
    instance.wait_until_running()    
    
    # wait for ip address and ssh
    while True:
        if instance.public_ip_address:
            break
        log.info("awaiting IP address")
        sleep(1)
        instance.load()
    log.info("instance %s running at %s"%(name, instance.public_ip_address))
    fab.env.host_string = instance.public_ip_address
    wait_ssh()

    # prepare drive
    if drive:
        # set name
        for vol in instance.block_device_mappings:
            if vol["DeviceName"] == "/dev/xvdf":
                aws.set_name(aws.ec2.Volume(vol["Ebs"]["VolumeId"]), 
                                            drive.name)
                break
        # if new volume then format
        if not latest_snapshot:
            drive.formatdisk()
        drive.mount()
        
        # copy logconfig
        home = os.path.expanduser("~")
        fab.put(os.path.join(home, ".logconfig.yaml"), "/v1")

        # install docker
        apps.install_docker()
        apps.set_docker_folder("/v1")
        try:
            apps.install_nvidia_docker()
        except:
            log.warning("failed to install nvidia-docker")
        
    # put creds in home folder
    fab.put(_creds.__file__)
    
    log.info("instance %s ready at %s"%(name, instance.public_ip_address))
    return instance
 
def create_spot(spec, spotprice=".25"):
    """ returns a spot instance
    """
    del spec["MinCount"]
    del spec["MaxCount"]
    requestId = aws.client.request_spot_instances(
                     DryRun=False,
                     SpotPrice=spotprice,
                     LaunchSpecification=spec) \
                    ["SpotInstanceRequests"] \
                    [0]['SpotInstanceRequestId']
    log.info("spot request submitted")
    
    # wait for spot instance
    while True:
        # sometimes AWS gives a requestId but waiter says it does not exist
        try:
            aws.client.get_waiter("spot_instance_request_fulfilled") \
                                .wait(SpotInstanceRequestIds=[requestId])
            break
        except:
            log.warning("waiting for request id")
            sleep(1)
    instanceId = aws.client.describe_spot_instance_requests \
                    (SpotInstanceRequestIds=[requestId]) \
                    ['SpotInstanceRequests'][0] \
                    ['InstanceId']
    log.info("spot request fulfilled %s"%instanceId)
    return aws.ec2.Instance(instanceId)
    
def wait_ssh():
    """ wait for ssh server """
    log.info("waiting for ssh server")
    while True:
        with fab.quiet():
            try:
                fab.sudo("ls")
                break
            except:
                pass
        sleep(1)
    log.info("ssh connected %s"%fab.env.host_string)

def terminate(instance, save_drive=True):
    """ terminate instance and save drive as snapshot """
    if isinstance(instance, str):
        instance = aws.get(instance)
    
    apps.stop_docker()
        
    # get the drive
    for bdm in instance.block_device_mappings:
        if bdm["DeviceName"] == "/dev/xvdf":
            volume = aws.ec2.Volume(bdm["Ebs"]["VolumeId"])
            drive = Drive(aws.get_name(volume))
            break

    drive.unmount()
    
    # terminate instance before snapshot as instances are costly
    instance.terminate()
    aws.set_name(instance, "")
    log.info("instance terminated")
    
    if save_drive:
        drive.create_snapshot()
    # can still be attached even after instance terminated
    drive.detach()
    drive.delete_volume()
     
def get_tasks(target="python"):
    """ returns dataframe of tasks on server running inside docker containers
        where task contains target string
    """
    with fab.quiet():
        r = fab.run("docker inspect --format='{{.Name}}' "\
                         "$(docker ps -q)")
        if r.failed:
            return None
    containers = r.splitlines()
    containers = [container.lstrip("/") for container in containers]
    cout = []
    tout = []
    for container in containers:
        tasks = fab.run("docker exec %s ps -eo args | grep %s || true"\
                        %(container, target)).splitlines()
        for task in tasks:
            cout.append(container)
            tout.append(task)
    out = pd.DataFrame(dict(container=cout, task=tout))
    return out 