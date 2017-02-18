# -*- coding: utf-8 -*-
import aws
import logging as log
import sys
import fabric.api as fab
from time import sleep
import json
import apps
from config import user

class Pdrive():
    """ persistent storage for use with spot instances
    """
    default = dict(Size=10, VolumeType="gp2")        
    
    def __init__(self, name):
        """ note minimal state (just name) to allow changes via AWS menus """
        self.name = name
    
    def connect(self, instance):
        """ connect drive to existing instance """
        self.attach(instance)
        self.diskformat()
        self.mount()
        
    def disconnect(self, save=True):
        """ disconnect cleanly and save to snapshot """
        # stop docker on pdrive
        with fab.quiet():
            r = fab.get("/etc/docker/daemon.json", "temp", use_sudo=True)
        if r.succeeded:
            daemon = json.load(open("temp"))
            folder = daemon["graph"]
            if folder.startswith("/v1"):
                apps.stop_docker()
        self.unmount()
        self.detach()
        if save:
            self.create_snapshot()
        self.delete_volume()
        
######## lower level functions ############################
        
    def attach(self, instance):
        """ attach volume or snapshot """
        if isinstance(instance, str):
            instance = aws.get(instance, collections=aws.ec2.instances)

        fab.env.host_string = instance.public_ip_address
        fab.env.user = user
        
        volume = aws.get(self.name, collections=aws.ec2.volumes)

        if volume:
            # validate volume
            if volume.availability_zone != \
                       instance.placement["AvailabilityZone"]:
                raise Exception("volume and instance must be in same "
                                "availability zone")
        else:
            # create volume from snapshot
            snapshot = self.latest_snapshot()
            if snapshot is None:
                log.exception("No volume or snapshot found for %s"%self.name)
                sys.exit()
            r = aws.client.create_volume(
                    SnapshotId=snapshot.id,
                    AvailabilityZone=instance.placement["AvailabilityZone"],
                    VolumeType="gp2")
            volume = aws.ec2.Volume(r["VolumeId"])
            aws.set_name(volume, self.name)
        
        # remove existing attachment
        if volume.attachments:
            self.detach()
            
        # attach volume
        aws.client.get_waiter('volume_available').wait(VolumeIds=[volume.id])
        log.info("volume available")
        instance.attach_volume(VolumeId=volume.id, Device='/dev/xvdf')
        
        # wait until device usable.
        log.info("waiting to attach volume")
        while True:
            with fab.quiet():
                if fab.sudo("ls -l /dev/xvdf").succeeded:
                    break
            sleep(1)
        log.info("volume attached")
            
    def diskformat(self):
        """ format volume if no file system """
        if not fab.sudo("blkid /dev/xvdf"):
            fab.sudo("mkfs -t ext4 /dev/xvdf")
            log.info("volume formatted")
        
    def mount(self):
        """ mount volume to v1 """
        fab.sudo("mkdir -p /v1")
        fab.sudo("mount /dev/xvdf /v1")
        log.info("volume mounted")
    
    def unmount(self):
        """ unmount """
        with fab.quiet():        
            r = fab.sudo("umount /dev/xvdf")
            if r.succeeded:
                log.info("volume dismounted")
           
    def detach(self):
        """ detach """
        volume = aws.get(self.name, collections=aws.ec2.volumes)
        if not volume:
            raise Exception("volume %s does not exist"%self.name)
        try:
            volume.detach_from_instance(volume.attachments[0]["InstanceId"])
            log.info("volume detached")
        except:
            log.warning("failed to detach volume")
            return

    def create_snapshot(self):
        volume = aws.get(self.name, collections=aws.ec2.volumes)
        snap = aws.ec2.create_snapshot(VolumeId=volume.id)
        aws.set_name(snap, self.name)
        log.info("waiting for snapshot. this can take 15 minutes."\
                     "you can break and then delete volume manually")
        snap.wait_until_completed()
        log.info("snapshot completed")
    
    def delete_volume(self):
        volume = aws.get(self.name, collections=aws.ec2.volumes)
    
        # wait until available
        log.info("waiting until volume available")
        aws.client.get_waiter('volume_available').wait(VolumeIds=[volume.id])
        log.info("volume available")
        
        # delete volume
        volume.delete()
        aws.client.get_waiter('volume_deleted').wait(VolumeIds=[volume.id])
        log.info("volume deleted")
        
    def latest_snapshot(self):
        """ returns most recent snapshot """  
        volume = aws.get(self.name, collections=aws.ec2.volumes)
        if volume:
            log.warning("cannot get snapshot as volume exists")
            sys.exit()
        snapshots = aws.get(self.name, collections=aws.ec2.snapshots, 
                            unique=False)
        if snapshots:
            snapshots = sorted(snapshots, 
                               key=lambda s:s.start_time, reverse=True)
            return snapshots[0]
        log.warning("no snapshots found")
        
    def create_kaggle(project):
        """ configure new kaggle project """
        # manually on website accept T&Cs for competition
        fab.run("mkdir /v1/%s"%project)
        with fab.cd("cd /v1/%s"%project):
            fab.run("cp ~/.kaggle-cli")
            fab.run("kg config -c %s"%project)
            fab.run("kg download")