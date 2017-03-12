# -*- coding: utf-8 -*-
from . import aws, apps
import logging as log
import fabric.api as fab
from time import sleep
import json

class Drive():
    """ persistent storage for use with spot instances
    """
    def __init__(self, name):
        """ note minimal state (just name) to allow changes via AWS menus """
        self.name = name
    
    def connect(self, instance):
        """ connect drive to existing instance """
        self.attach(instance)
        self.formatdisk()
        self.mount()
        
    def disconnect(self, save=True):
        """ disconnect cleanly and save to snapshot
        """
        # if docker on xdrive then stop
        fab.get("/etc/docker/daemon.json", "_temp", use_sudo=True)
        daemon = json.load(open("_temp"))
        folder = daemon["graph"]
        if folder.startswith("/v1"):
            apps.stop_docker()
            
        self.unmount()
        self.detach()
        if save:
            self.create_snapshot()
        self.delete_volume()
        
######## lower level functions ############################
        
    def attach(self, instance, user="ec2-user"):
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
                raise Exception("No volume or snapshot found "
                                            "for %s"%self.name)
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
        log.info("waiting until volume available")
        aws.client.get_waiter('volume_available').wait(VolumeIds=[volume.id])
        log.info("volume available")
        instance.attach_volume(VolumeId=volume.id, Device='/dev/xvdf')
        
        # wait until device usable.
        log.info("waiting for device to be visible")
        while True:
            with fab.quiet():
                if fab.sudo("ls -l /dev/xvdf").succeeded:
                    break
            sleep(1)
        log.info("volume attached")
            
    def formatdisk(self):
        """ format volume if no file system """
        with fab.quiet():
            r = fab.sudo("blkid /dev/xvdf")
        if r.succeeded:
            log.warning("volume is already formatted")
            return
        r = fab.sudo("mkfs -t ext4 /dev/xvdf")
        if r.failed:
            raise Exception("format failed as no volume attached")
        log.info("volume formatted")
        
    def mount(self):
        """ mount volume to v1 """
        fab.sudo("mkdir -p /v1")
        fab.sudo("mount /dev/xvdf /v1")
        fab.sudo("chown -R %s:%s /v1"%(fab.env.user, fab.env.user))
        log.info("volume mounted")
    
    def unmount(self):
        """ unmount """
        with fab.quiet():        
            r = fab.sudo("umount /v1")
            if r.succeeded:
                log.info("volume dismounted")
            else:
                log.warning("dismount failed. trying to force.")
                r = fab.sudo("fuser -km /v1")
                if r.succeeded:
                    log.info("volume dismounted")
                else:
                    log.warning("failed to force dismount")
           
    def detach(self):
        """ detach """
        volume = aws.get(self.name, collections=aws.ec2.volumes)
        if not volume:
            raise Exception("volume %s does not exist"%self.name)
        if volume.attachments:
            volume.detach_from_instance(volume.attachments[0]["InstanceId"],
                                        Force=True)
            log.info("detach request sent")
        log.info("waiting until volume available")
        aws.client.get_waiter('volume_available').wait(VolumeIds=[volume.id])
        log.info("volume available")

    def create_snapshot(self):
        volume = aws.get(self.name, collections=aws.ec2.volumes)
        snap = aws.ec2.create_snapshot(VolumeId=volume.id)
        aws.set_name(snap, self.name)
        log.info("waiting for snapshot. this can take 15 minutes."\
                                              "Have a cup of tea.")
        snap.wait_until_completed()
        log.info("snapshot completed")
    
    def delete_volume(self):
        volume = aws.get(self.name, collections=aws.ec2.volumes)
    
        # delete volume
        volume.delete()
        aws.client.get_waiter('volume_deleted').wait(VolumeIds=[volume.id])
        log.info("volume deleted")
        
    def latest_snapshot(self):
        """ returns most recent snapshot """  
        volume = aws.get(self.name, collections=aws.ec2.volumes)
        if volume:
            raise Exception("cannot get snapshot as volume exists")
        snapshots = aws.get(self.name, collections=aws.ec2.snapshots, 
                            unique=False)
        if snapshots:
            snapshots = sorted(snapshots, 
                               key=lambda s:s.start_time, reverse=True)
            return snapshots[0]
        log.warning("no snapshots found. creating new volume %s"%self.name)