# -*- coding: utf-8 -*-
"""
create and manage server instances

NOTE: This is a set of functions not a class
"""
from pdrive import Pdrive
import logging as log
import aws
import apps
import fabric.api as fab
from time import sleep
import pandas as pd

# add others as needed
itypes = dict(gpu="p2.xlarge", free="t2.micro")

# what is best setting for this????
spotprice = ".5"

#### amazon linux 8GB boot volume
base_spec = dict(ImageId="ami-c51e3eb6",
                InstanceType=itypes["free"], 
                SecurityGroups=["simon"],
                KeyName="key",
                MinCount=1, MaxCount=1,
                BlockDeviceMappings=[])

#### alternative AMIs
# amazon deep learning = "ami-cb97d5b8"
# fastai = "ami-b43d1ec7"
# amazon linux = "ami-c51e3eb6"
    
def create(name, bootsize=None, itype="free", spot=False,
                            pdrive=None, pdrivesize=10):
    """ create main types of instance needed for deep learning
    
        name = name of instance
        bootsize = size of boot volume
            amazon linux AMI default is 8GB
            docker kaggle/python requires 11GB minimum
        itype = key for itypes dict parameter e.g. free, gpu
        pdrive = name of attached, non-boot drive
        spot = use spot. default is on-demand
    """
    if aws.get(name, aws.ec2.instances):
        raise("instance %s already exists"%name)
    if isinstance(pdrive, str):
        pdrive = Pdrive(pdrive)
    
    spec = base_spec.copy()
    
    # size of root volume
    if bootsize:
        bdm = dict(DeviceName="/dev/xvda",
                   Ebs=dict(VolumeType="gp2",
                           VolumeSize=bootsize))
        spec["BlockDeviceMappings"].append(bdm)
        
    # instance type
    spec.update(InstanceType=itypes[itype])
    
    # if persistent volume then add to instance launch
    if pdrive:
        latest_snapshot = pdrive.latest_snapshot()
        if latest_snapshot:
            latest_snapshot = latest_snapshot.id
        bdm = dict(DeviceName="/dev/xvdf",
                   Ebs=dict(SnapshotId=latest_snapshot,
                            DeleteOnTermination=False,
                            VolumeType="gp2",
                            VolumeSize=pdrivesize))
        spec["BlockDeviceMappings"].append(bdm)

    # spot or on-demand
    if spot:
        instance = create_spot(spec)
    else:
        instance = aws.ec2.create_instances(**spec)[0]
    
    log.info("instance pending")
    instance.wait_until_running()    
    aws.set_name(instance, name)
    
    # wait for ip address. is this necessary????
    while True:
        if instance.public_ip_address:
            break
        log.info("awaiting IP address")
        sleep(1)
        instance.load()
    log.info("instance %s running at %s"%(name, instance.public_ip_address))
    
    fab.env.host_string = instance.public_ip_address
    
    # prepare pdrive
    if pdrive:
        # set name
        for vol in instance.block_device_mappings:
            if vol["DeviceName"] == "/dev/xvdf":
                aws.set_name(aws.ec2.Volume(vol["Ebs"]["VolumeId"]), 
                                            pdrive.name)
                break
            
        # format and mount
        wait_ssh()
        if not latest_snapshot:
            pdrive.formatdisk()
        pdrive.mount()
    
    apps.install_docker()
    
    return instance
 
def create_spot(spec):
    """ returns a spot instance
    NOTE to autobid without spotprice then have to use AWS browser console
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
    
    # wait until fulfilled
    aws.client.get_waiter("spot_instance_request_fulfilled") \
                        .wait(SpotInstanceRequestIds=[requestId])
    instanceId = aws.client.describe_spot_instance_requests \
                    (SpotInstanceRequestIds=[requestId]) \
                    ['SpotInstanceRequests'][0] \
                    ['InstanceId']
    log.info("spot request fulfilled")
    return aws.ec2.Instance(instanceId)
    
def create_static_server():
    """ creates instance with static ip address """
    instance = create("sm1")
    fab.env.host_string = aws.get_ips()[0]
    aws.client.associate_address(InstanceId=instance.instance_id,
                                 PublicIp=fab.env.host_string)
    wait_ssh()
    apps.install_docker()
    apps.install_wordpress()
    apps.install_miniconda()
    apps.install_kaggle()

def wait_ssh():
    """ wait for successfull ssh connection """
    while True:
        with fab.quiet():
            try:
                r = fab.sudo("ls")
                if r.succeeded:
                    break
            except:
                log.warning("SHOULD THIS HAPPEN???")
            log.info("waiting for ssh")
        sleep(1)
    log.info("connected")

def terminate(instance):
    """ terminate instance and save pdrive as snapshot """
    if isinstance(instance, str):
        instance = aws.get(instance)
    
    apps.stop_docker()
        
    # get the pdrive
    for bdm in instance.block_device_mappings:
        if bdm["DeviceName"] == "/dev/xvdf":
            volume = aws.ec2.Volume(bdm["Ebs"]["VolumeId"])
            pdrive = Pdrive(aws.get_name(volume))
            break

    pdrive.unmount()
    
    # note terminate instance before snapshot as instances are costly
    # note no need for separate detach step
    instance.terminate()
    log.info("instance terminated")
    pdrive.create_snapshot()
     
def get_tasks(target="python"):
    """ returns dataframe of tasks running inside docker containers
        where task contains target string
    """
    with fab.quiet():
        r = fab.run("docker inspect --format='{{.Name}}' "\
                         "$(docker ps -q)")
        if r.failed:
            return None
        containers = r.splitlines()
    containers = [c.lstrip("/") for c in containers]
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