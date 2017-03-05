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
import config as c
import copy
    
def create(name, itype="free", bootsize=None, pdrive=None, pdrivesize=10,
                           spot=False):
    """ create instance and mount pdrive
    
        name = name of instance
        itype = key for itypes dict parameter e.g. free, gpu
        bootsize = size of boot drive
        pdrive = name of attached, non-boot drive
        spot = spot versus on-demand
    """
    if aws.get(name, aws.ec2.instances):
        raise Exception("instance %s already exists"%name)
    spec = copy.deepcopy(c.base_spec)

    # instance type
    spec.update(InstanceType=c.itypes[itype],
                ImageId=c.useramis[itype])
    
    # boot drive
    if bootsize:
        bdm = dict(DeviceName="/dev/xvda",
                   Ebs=dict(VolumeType="gp2",
                           VolumeSize=bootsize))
        spec["BlockDeviceMappings"].append(bdm)
            
    # add pdrive to instance launch
    if pdrive:
        pdrive = Pdrive(pdrive)
        Ebs=dict(DeleteOnTermination=False,
                 VolumeType="gp2",
                 VolumeSize=pdrivesize)
        latest_snapshot = pdrive.latest_snapshot()
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
    fab.env.user = c.user
    wait_ssh()

    # prepare pdrive
    if pdrive:
        # set name
        for vol in instance.block_device_mappings:
            if vol["DeviceName"] == "/dev/xvdf":
                aws.set_name(aws.ec2.Volume(vol["Ebs"]["VolumeId"]), 
                                            pdrive.name)
                break
        # if new volume then format
        if not latest_snapshot:
            pdrive.formatdisk()
        pdrive.mount()

        # install docker
        apps.install_docker()
        apps.set_docker_folder("/v1")
        if itype=="gpu":
            apps.install_nvidia_docker()
    
    log.info("instance %s ready at %s"%(name, instance.public_ip_address))
    return instance
 
def create_spot(spec):
    """ returns a spot instance
    """
    del spec["MinCount"]
    del spec["MaxCount"]
    requestId = aws.client.request_spot_instances(
                     DryRun=False,
                     SpotPrice=c.spotprice,
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
    
    # terminate instance before snapshot as instances are costly
    instance.terminate()
    aws.set_name(instance, "")
    log.info("instance terminated")
    
    if save_pdrive:
        pdrive.create_snapshot()
    # can still be attached even after instance terminated
    pdrive.detach()
    pdrive.delete_volume()
     
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