# -*- coding: utf-8 -*-
import aws
import logging as log
import sys
import fabric.api as fab
from time import sleep
import json
import apps

class Pdrive():
    """ persistent storage for use with spot instances
    
    FUNCTION::
        
        enables persistent data
            training data can be reused on future instance
            model state can be saved to Pdrive periodically e.g. each epoch
            
        enables persistent program settings
            docker runs on boot volume; images/containers are stored on Pdrive
            on instance termination Pdrive saves to snapshot
            [MANUAL CURRENTLY. DOES NOT DETECT AWS INITIATED SHUTDOWN]
            
        can be used in parallel with AWS menus. only retained state is name.
            
    USAGE::
        
        initialise fabric before calling instance functions
            fab.env.user = "ec2-user"
            fab.env.host_string = "<ipaddress>"
        
        new instance
            create instance with pdrive:
                itools.create(name, bootsize=None, itype="free", spot=False,
                              pdrivename=None, pdrivesize=10)
                start containers as required
                
            terminate instance with pdrive:
                itools.terminate(instance/name)

        existing instance
            connect pdrive
                pdrive.connect(instance/name)
                start docker and containers as required
                
            shutdown pdrive cleanly
                pdrive.disconnect()
                
        set docker location
            to pdrive volume (default when instance/pdrive created together)
                apps.set_docker_folder("/v1")
               
            to boot volume (default when instance created without pdrive)
                apps.set_docker_folder()
            
    NOTES::
            
        reasons for use of snapshots
            cheaper storage
            can be mounted when instance created (volume cannot)
            can be attached in any availability_zone (volume is single zone)
            
        assumptions
            only one external volume which will be mounted as /v1
            volume name is unique (snapshot name is reused)
            snapshots must be deleted manually
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
        
    def disconnect(self):
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
        self.create_snapshot()
        
######## lower level functions ############################
        
    def attach(self, instance):
        """ attach volume or snapshot """
        if isinstance(instance, str):
            instance = aws.get(instance, collections=aws.ec2.instances)
        fab.env.host_string = instance.public_ip_address
        
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
        while True:
            with fab.quiet():
                if fab.sudo("ls -l /dev/xvdf").succeeded:
                    break
                log.info("waiting to attach volume")
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
        aws.client.get_waiter('volume_available').wait(VolumeIds=[volume.id])
        log.info("volume available")

    def create_snapshot(self):
        """ create snapshot; delete volume """
        # create snapshot
        volume = aws.get(self.name, collections=aws.ec2.volumes)
        snap = aws.ec2.create_snapshot(VolumeId=volume.id)
        aws.set_name(snap, self.name)
        snap.wait_until_completed()
        log.info("snapshot completed")
        
        # wait until available
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
        
########### no longer needed ???? #############################        
        
    def create(self, instance, **params):
        """ creates empty volume, attaches, mounts and formats
        NOT NEEDED. instance_create is simpler
        """
        # check does not exist
        if aws.get(self.name, collections=aws.ec2.volumes):
            log.warning("Volume %s already exists"%self.name)
            sys.exit()
        if aws.get(self.name, collections=aws.ec2.snapshots, unique=False):
            log.exception("Snapshot %s already exists"%self.name)
            sys.exit()
            
        if isinstance(instance, str):
            instance = aws.get(instance, aws.ec2.instances)
        
        # create volume
        params2 = self.default.copy()
        params2.update(AvailabilityZone=instance.placement["AvailabilityZone"])
        params2.update(params)
        volume = aws.ec2.create_volume(**params2)
        aws.set_name(volume, self.name)
        waiter = aws.client.get_waiter('volume_available')
        waiter.wait(VolumeIds=[volume.id])
        log.info("volume available")
        
        # attach and mount
        self.attach(instance, formatdisk=True)