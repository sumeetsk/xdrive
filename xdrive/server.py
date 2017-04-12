# -*- coding: utf-8 -*-
"""
create and manage server instances

NOTE: This is a set of functions not a class
"""
from .drive import Drive
from . import apps, aws
import logging as log
import os
import time
from threading import Thread

import fabric.api as fab
from time import sleep
import pandas as pd
import yaml
import sys
import configparser
import pyperclip

conf = dict()

def configure():
    """ runs on import and loads config """
    global conf

    # get xdrive config.yaml
    for path in [os.path.join(os.path.expanduser("~"), ".xdrive"),
                 os.getcwd(),
                 # dev install
                 os.path.join(__file__, os.pardir, os.pardir),
                 # remote install
                 os.path.join(sys.prefix, "etc", "xdrive")]:
        try:
            conf = yaml.load(open(os.path.join(path, "config.yaml")))
            break
        except:
            pass

    # get user and key
    try:
        # if not already set then use first ip address on account
        if not fab.env.host_string:
            fab.env.host_string = aws.get_ips()[0]
            try:
                pyperclip.copy(fab.env.host_string)
            except:
                log.warning("pyperclip cannot find copy/paste mechanism")
            log.info("%s put on clipboard and for fabric"%fab.env.host_string)
    except:
        pass
    fab.env.user = conf["user"]
    awsfolder = os.path.join(os.path.expanduser("~"), ".aws")
    fab.env.key_filename = os.path.join(awsfolder, "key.pem")

    # get aws region
    config = configparser.ConfigParser()
    try:
        config.read(os.path.join(awsfolder, "config"))
        awsregion = config["default"]["region"]
    except Exception as e:
        log.exception(e)
        awsregion = "eu-west-1"
    log.info(f"setting region to {awsregion}")

    # get amis from region
    if awsregion not in conf["regions"]:
        raise Exception(f"{awsregion} region not found")
    amis = conf["regions"][awsregion]
    if not amis["free"]:
        raise Exception(f"{awsregion} region has no amazon linux AMI available")
    if not amis["gpu"]:
        raise Exception(f"{awsregion} region has no amazon/nvidia linux AMI available")

    conf = dict(amis=amis, itypes=conf["itypes"])

def create(name, itype="free", bootsize=None, drive=None, drivesize=15,
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
    fab.env.host_string = instance.public_ip_address
    try:
        pyperclip.copy(fab.env.host_string)
    except:
        log.warning("pyperclip cannot find copy/paste mechanism")

    log.info("instance %s running at %s (clipboard)"
                         %(name, instance.public_ip_address))
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

        # install docker
        apps.install_docker()
        apps.set_docker_folder("/v1")
        try:
            apps.install_nvidia_docker()
        except:
            log.warning("failed to install nvidia-docker")

    log.info("instance %s ready at %s (clipboard)"
                                     %(name, instance.public_ip_address))
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
    
    # wait for spot instance
    log.info("waiting for spot instance")
    while True:
        # sometimes AWS gives a requestId but waiter says it does not exist
        try:
            instanceId = aws.client.describe_spot_instance_requests \
                (SpotInstanceRequestIds=[requestId]) \
                ['SpotInstanceRequests'][0] \
                ['InstanceId']
            if instanceId:
                break
        except:
            pass
        sleep(15)
    log.info("spot request fulfilled %s"%instanceId)

    # start thread to poll for AWS termination notice
    t = Thread(target=spotcheck, name=requestId, args=[requestId,])
    t.start()

    return aws.ec2.Instance(instanceId)

def spotcheck(requestId):
    """ poll for spot instance termination notice """
    while True:
        requests = aws.client.describe_spot_instance_requests \
                        (SpotInstanceRequestIds=[requestId])

        # request already deleted
        try:
            request = requests['SpotInstanceRequests'][0]
        except:
            return

        # instance already terminated
        instance = aws.ec2.Instance(request["InstanceId"])
        if instance.state["Name"] != "running":
            return

        # instance marked for termination
        if request["Status"]["Code"] == "marked-for-termination":
            name = aws.get_name(instance)
            log.warning(f"{name} has been marked for termination by AWS.\n"\
                        "Attempting to terminate cleanly and save data.")
            terminate(instance)
            return

        # amazon recommend poll every 5 seconds
        time.sleep(5)

def optimise_gpu():
    """ disable autoboost 
    https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/accelerated-computing-instances.html#optimize_gpu
    """
    fab.sudo("nvidia-smi --auto-boost-default=0")
    fab.sudo("sudo nvidia-smi -ac 2505,875")

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

def terminate(instance, save=True):
    """ terminate instance and save drive as snapshot """

    # wait for fab connection. fab disconnects if idle for too long.
    for x in range(2):
        try:
            with fab.quiet():
                fab.run("ls")
            break
        except ConnectionResetError:
            pass

    if isinstance(instance, str):
        instance = aws.get(instance)

    # get the drive
    drive = None
    for bdm in instance.block_device_mappings:
        if bdm["DeviceName"] == "/dev/xvdf":
            volume = aws.ec2.Volume(bdm["Ebs"]["VolumeId"])
            drive = Drive(aws.get_name(volume))
            break

    if not drive:
        instance.terminate()
        aws.set_name(instance, "")
        log.info("instance terminated")
        return
    
    apps.stop_docker()
    drive.unmount()

    # terminate instance before snapshot as instances are costly
    instance.terminate()
    aws.set_name(instance, "")
    log.info("instance terminated")

    if save:
        drive.create_snapshot()
    
    # note can still be attached even after instance terminated
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

configure()