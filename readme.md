**Currently testing some changes. Will remove this notice when complete**:

* simplified configuration
* xdriveclient in a container. this is cleaner as it eliminates any conflict 
with local settings
* Terminates server when amazon issues termination notice. Not tested but not
critical as volume is retained anyway and can be saved manually.
* End to end test and fix a number of bugs

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

Run xdrive in a container (using ~/.aws and ~/.xdrive/config.yaml)
* download https://raw.githubusercontent.com/simonm3/xdrive/master/xdriveclient.py
* python xdriveclient.py
* open browser at localhost:8888
* open examples.ipynb

Install locally (if you don't want to run in a container)
* pip install xdrive
* download https://raw.githubusercontent.com/simonm3/xdrive/master/examples.ipynb
* open browser at localhost:8888
* open examples.ipynb

View the source
* https://github.com/simonm3/xdrive

## Issues

* If notebook says "Connection reset by peer" then just rerun the cell. If you
know how I can stop this then please let me know.
* If you run xdrive in a container this means you have four machines running.
If you get problems then first check which machine you are using!
    - Your laptop
    - xdrive container on your laptop running notebook server
    - Amazon instance
    - fastai (or other) container on the amazon instance running notebook server

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
    
#### How does this package provide persistent storage?

* xdrive volume is created based on most recent snapshot (or empty volume)
* xdrive is mounted as /v1
* on termination by user xdrive volume is saved to a snapshot
* on termination of spot instance by amazon volume is saved to a snapshot. Note
this needs testing. If it fails then data volume remains and can be saved 
manually to a snapshot.
* all snapshots are retained until manually deleted
* xdrive volume and snapshots are linked via a "name" tag

#### How are program settings retained?

* programs run in a docker container
* xdrive holds the database of docker containers
* boot volume runs a simple AMI such as the amazon linux AMI
* nvidia-docker runs the docker container on the xdrive volume

#### Why snapshots?

* cheaper storage
* can be mounted when instance created (volume cannot)
* can be attached in any availability_zone (volume is in one zone and instance 
                                            would need to be in same zone)

#### Differences to fastai AMI
* Uses python3
* Uses nvidia version 7.5
* Notebooks are on /v1 outside the container