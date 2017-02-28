## Overview of AWS package

The main purpose of this package is to add persistent data and program 
environment to AWS spot instances.

AWS spot instances offer an 80% cost saving versus on-demand GPU instances. 
However they have no persistent storage:

* AWS can terminate the instance at any time and all data and programs are lost
* When the user terminates the instance then all data and programs are lost
* It is not possible to stop and start the instance only to terminate it

The lack of persistent storage makes spot instances impractical for long 
running processes; where setup requires significant time installing packages 
and downloading data.

This package puts data and program environment onto a separate volume which 
persists when the instance is terminated. This makes spot instances practical 
for deep learning and other applications. It also enables setup to be carried 
out using a cheaper or free tier instance before firing up a GPU to do the 
actual training.

## Notes
    
#### How is data retained?

* pdrive volume is created based on most recent snapshot (or empty volume)
* pdrive is mounted as /v1
* on termination pdrive volume is saved to a snapshot
* if AWS initiates termination then volume remains and can be saved to a 
snapshot manually
* all snapshots are retained until manually deleted
* pdrive volume and snapshots are linked via a "name" tag

#### How are program settings retained?

* programs run in a docker container
* pdrive holds the database of docker containers
* boot volume runs a simple AMI such as the amazon linux AMI
* nvidia-docker runs the docker container on the pdrive volume

#### Why snapshots?

* cheaper storage
* can be mounted when instance created (volume cannot)
* can be attached in any availability_zone (volume is in one zone and instance 
                                            would need to be in same zone)