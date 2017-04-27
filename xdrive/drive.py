# -*- coding: utf-8 -*-
from . import aws, apps
import logging as log
import fabric.api as fab
from time import sleep
import json
from io import BytesIO

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
        apps.setdebug()

        if not save:
            self.unmount()
            self.detach()
            self.delete_volume()
            return
        
        # if docker on xdrive then stop
        f = BytesIO()
        r = fab.get("/etc/docker/daemon.json", f, use_sudo=True)
        if r.succeeded:
            folder = json.loads(f.getvalue()).get("graph", "")
            if folder.startswith("/v1"):
                apps.stop_docker()

        self.unmount()
        self.detach()
        self.create_snapshot()
        self.delete_volume()
        
        snapcount = len(aws.get(self.name, aws.ec2.snapshots, unique=False))
        log.info(f"You now have {snapcount} {self.name} snapshots")
        
######## lower level functions ############################
        
    def attach(self, instance, user="ec2-user"):
        """ attach volume or snapshot """
        apps.setdebug()

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
            
        # wait until available
        while True:
            item = aws.client.describe_volumes(
                        VolumeIds=[volume.id])["Volumes"][0]
            if item["State"] == "available":
                break
            log.info("waiting until volume available")
            sleep(15)
        log.info("volume available")
        
        # attach
        instance.attach_volume(VolumeId=volume.id, Device='/dev/xvdf')
        
        # wait until usable.
        while True:
            if fab.sudo("ls -l /dev/xvdf").succeeded:
                break
            log.info("waiting until volume visible")
            sleep(1)
        log.info("volume attached")
            
    def formatdisk(self):
        """ format volume if no file system """
        apps.setdebug()
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
        apps.setdebug()
        fab.sudo("mkdir -p /v1")
        fab.sudo("mount /dev/xvdf /v1")
        fab.sudo("chown -R %s:%s /v1"%(fab.env.user, fab.env.user))
        log.info("volume mounted")
    
    def unmount(self):
        """ unmount """
        apps.setdebug()

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
            
            # wait until available
            while True:
                item = aws.client.describe_volumes(
                            VolumeIds=[volume.id])["Volumes"][0]
                if item["State"] == "available":
                    break
                log.info("waiting until volume available")
                sleep(15)
            log.info("volume available")

    def create_snapshot(self):
        volume = aws.get(self.name, collections=aws.ec2.volumes)
        snap = aws.ec2.create_snapshot(VolumeId=volume.id)
        aws.set_name(snap, self.name)
        
        log.info("waiting for snapshot. this can take 15 minutes."\
                                              "Have a cup of tea.")
        while True:
            try:
                item = aws.client.describe_snapshots(
                            SnapshotIds=[snap.id])["Snapshots"][0]
            except:
                # may delete snapshot via menus
                break
            if item["State"] == "completed":
                break
            log.info("%s snapshot completed"%item["Progress"])
            sleep(60)
        log.info(f"snapshot completed")
    
    def delete_volume(self):
        volume = aws.get(self.name, collections=aws.ec2.volumes)
        volume.delete()

        while True:
            try:
                item = aws.client.describe_volumes(
                            VolumeIds=[volume.id])["Volumes"][0]
            except:
                # volume can be deleted before state set to deleted
                break
            if item["State"] == "deleted":
                break
            log.info("waiting for volume to be deleted")
            sleep(15)
        log.info("volume deleted")
        
    def latest_snapshot(self):
        """ returns most recent snapshot """  
        volume = aws.get(self.name, collections=aws.ec2.volumes)
        if volume:
            raise Exception("%s volume already exists from a "\
                "previous session. If you want to keep it then save it as a "\
                "snapshot; name the snapshot %s; and delete volume. If you "\
                "don't want to keep it then delete it"%(self.name, self.name))
        snapshots = aws.get(self.name, collections=aws.ec2.snapshots, 
                            unique=False)
        if snapshots:
            snapshots = sorted(snapshots, 
                               key=lambda s:s.start_time, reverse=True)
            return snapshots[0]
        
    def resize(self, size):
        """ make volume larger """
        apps.setdebug()
        
        volume = aws.get(self.name, collections=aws.ec2.volumes)
        aws.client.modify_volume(VolumeId=volume.id, size=size)
        fab.sudo("resize2fs /dev/xvdf")