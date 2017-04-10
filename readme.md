## Portable drive that can be moved between AWS instances

This package puts programs and data on an external drive rather than an the  
the boot drive. This can then be moved between different types of server 
and creates persistence for spot instances.

Note that xdrive holds minimal state so you can continue to use AWS menus in
parallel.

## Installation:

Pre-requisites
* open AWS account 
* add AWS config and AWS credentials to ~/.aws
* It will automatically select AMIs based on AWS config default region

Install locally
* pip install xdrive
* download https://raw.githubusercontent.com/simonm3/xdrive/master/examples.ipynb
* open browser in jupyter at localhost:8888
* open examples.ipynb

View the source
* https://github.com/simonm3/xdrive

## Potential issues and responses

* If notebook says "Connection reset by peer":
   - just rerun the cell
   - not sure how this can be prevented. tried setting
fab.env["connection_attempts"] = 2 but no difference.
* When a termination notice is received from AWS this gives 2 minutes warning.
This should be enough but if shutdown takes longer then:
   - manually save the volume as a snapshot
   - give the snapshot the name of the volume
   - delete the volume.
* The GPU drivers are fixed when you run the container the first time. So you  
can move a container between instances using the same GPU drivers. You cannot 
directly move a container from a CPU to GPU; or between GPUs with different 
drivers. This has to be done indirectly and takes some time. These are the steps:
   - docker commit the container to fastai_image
   - nvidia-docker run --name fastai fastai_image
* Terminating server/drive at the same time works well. However disconnecting 
from a running instance can fail silently:
   - Double check AWS console to make sure no orphaned volumes
   - If necessary force detach/delete or save snapshot manually
* "Error response from daemon: get nvidia_driver_352.99: no such volume: nvidia_driver_352.99"
   - You originally ran the container using an older version so need to
recreate the volume driver and copy to /v1
   - run any container e.g. nvidia-docker run nvidia/cuda:7.5 nvidia-smi
   - cp -r --parents /var/lib/nvidia-docker/volumes /v1
   
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
  - Costs £700-1000 and need to update the hardware frequently
  - What If you want to run multiple GPUs?
  - You may sometimes need a different spec e.g. multiple cores or big memory 
* Run AWS spot instances directly at market price so they don't get terminated
  - You need to manually add any program settings that are not in the AMI
  - You need to manually mount data volumes in the correct availability zone
  - You need to manually dismount volumes and save to snapshots if required
* There is a recent package that implements a portable boot drive
  - Not tried this yet

## Notes

#### What is wrong with spot instances?

They have no persistent storage:

* AWS can terminate the instance at any time and all data and programs are lost
* When the user terminates the instance then all data and programs are lost
* It is not possible to stop and start the instance only to terminate it

The lack of persistent storage makes spot instances impractical for long 
running processes; where setup requires significant time installing packages 
and downloading data.
    
#### How does this provide persistent storage?

* xdrive volume is created based on most recent snapshot (or empty volume)
* xdrive is mounted as /v1
* on termination by user or amazon, containers are committed as images;
volume is saved to a snapshot; and volume is then deleted.
* all snapshots are retained until manually deleted
* xdrive volume and snapshots are linked via a "name" tag

#### How are program settings retained?

* programs run in a docker container
* on the GPU this uses nvidia-docker which detects the drivers on run
* on termination all containers are committed as images. This allows them to
be run on GPUs and CPUs
* xdrive holds the database of docker images

#### Why use Amazon linux AMI?

* All the hard work happens in docker containers
* The CPU version should be as simple as possible but available in all regions
* The GPU version should be similar but with GPU drivers installed
* Note it is centos based using yum instead of apt-get

#### Why snapshots?

* cheaper storage
* can be mounted when instance created (volume cannot)
* can be attached in any availability_zone (volume is in one zone and instance 
                                            would need to be in same zone)

#### Differences to fastai AMI

* Uses python3
* Uses nvidia version 7.5

### How could you use python2

* Build fastai docker image with parameter py=2
* Write a script based on apps.run_fastai()
* I think that is it but would need testing!