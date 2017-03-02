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
from config import itypes, amis, spotprice, base_spec, user
import copy
    
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
        raise Exception("instance %s already exists"%name)
    if isinstance(pdrive, str):
        pdrive = Pdrive(pdrive)
    spec = copy.deepcopy(base_spec)
    
    # size of root volume
    if bootsize:
        bdm = dict(DeviceName="/dev/xvda",
                   Ebs=dict(VolumeType="gp2",
                           VolumeSize=bootsize))
        spec["BlockDeviceMappings"].append(bdm)
        
    # instance type
    spec.update(InstanceType=itypes[itype],
                ImageId=amis[itype])
    
    # if persistent volume then add to instance launch
    if pdrive:
        Ebs=dict(DeleteOnTermination=False,
                 VolumeType="gp2",
                 VolumeSize=pdrivesize)
        latest_snapshot = pdrive.latest_snapshot()
        if latest_snapshot:
            Ebs.update(SnapshotId=latest_snapshot.id)
        bdm = dict(DeviceName="/dev/xvdf",
                   Ebs=Ebs)
        spec["BlockDeviceMappings"].append(bdm)
        
    # spot or on-demand
    if spot:
        instance = create_spot(spec)
    else:
        instance = aws.ec2.create_instances(**spec)[0]
    
    log.info("waiting for instance running")
    instance.wait_until_running()    
    aws.set_name(instance, name)
    
    # wait for ip address
    while True:
        if instance.public_ip_address:
            break
        log.info("awaiting IP address")
        sleep(1)
        instance.load()
    log.info("instance %s running at %s"%(name, instance.public_ip_address))
    
    fab.env.host_string = instance.public_ip_address
    fab.env.user = user
    wait_ssh()

    # install docker
    apps.install_docker()
    if itype=="gpu":
        apps.install_nvidia_docker()
    
    # prepare pdrive
    if pdrive:
        # set name
        for vol in instance.block_device_mappings:
            if vol["DeviceName"] == "/dev/xvdf":
                aws.set_name(aws.ec2.Volume(vol["Ebs"]["VolumeId"]), 
                                            pdrive.name)
                break
            
        # if new volume then format and mount
        if not latest_snapshot:
            pdrive.formatdisk()
        pdrive.mount()
        apps.set_docker_folder("/v1")
    else:
        apps.set_docker_folder()
        
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
    
    # AWS bug. sometimes gives a requestId but the waiter says it does not exist
    while True:
        try:
            aws.client.get_waiter("spot_instance_request_fulfilled") \
                                .wait(SpotInstanceRequestIds=[requestId])
            break
        except:
            sleep(1)

    # wait until fulfilled
    instanceId = aws.client.describe_spot_instance_requests \
                    (SpotInstanceRequestIds=[requestId]) \
                    ['SpotInstanceRequests'][0] \
                    ['InstanceId']
    log.info("spot request fulfilled")
    return aws.ec2.Instance(instanceId)
    
def wait_ssh():
    """ wait for successfull ssh connection """
    log.info("waiting for ssh")
    while True:
        with fab.quiet():
            try:
                fab.sudo("ls")
                break
            except:
                pass
        sleep(1)
    log.info("ssh connected")

def terminate(instance, save_pdrive=True):
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

    # reset name so can be reused
    aws.set_name(instance, "")
    
    # terminate instance before snapshot as instances are costly
    # note automatically detached when terminates
    instance.terminate()
    log.info("instance terminated")

    if save_pdrive:
        pdrive.create_snapshot()
    
    pdrive.delete_volume()
     
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