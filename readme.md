## Overview of pdrive package

This package puts programs and data on a portable "pdrive" rather than an on 
the AWS server. The "pdrive" can then be moved between different types of 
server including spot instances.

## Installation:
    git clone https://github.com/simonm3/pdrive pdrive
    git clone https://github.com/simonm3/basics basics
    add pdrive and basics to python path
    open pdrive/examples.ipynb in jupyter notebook

## Benefits

* Saves 100% of the cost of setting up data and programs. Free tier instances
can be used to set up data and programs before switching to a GPU or other 
more expensive instance for the heavy lifting
* Saves 80% of the cost of running GPU deep learning by enabling the use of 
spot instances at 18c/hour rather than on-demand at 90c/hour.
* Makes it easy to try different types of server on the exact same data and 
program setup
* Makes it easy to migrate to faster or better servers when AWS makes them
available

## Alternatives

* Buy your own GPU
  - Costs £600+ and need to update the hardware frequently
  - If you want to run multiple GPUs then it will be expensive
  - You may sometimes need a different spec e.g. multiple cores or big memory 
* Run AWS spot instances directly at market price so they don't get terminated
  - You need to manually add any program settings that are not in the AMI
  - You need to manually mount data volumes in the correct availability zone
  - You need to manually dismount volumes and save to snapshots if required

## Notes

#### What is wrong with spot instances?

They have no persistent storage:

* AWS can terminate the instance at any time and all data and programs are lost
* When the user terminates the instance then all data and programs are lost
* It is not possible to stop and start the instance only to terminate it

The lack of persistent storage makes spot instances impractical for long 
running processes; where setup requires significant time installing packages 
and downloading data.
    
#### How does this package provide persistent storage?

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