# -*- coding: utf-8 -*-
"""
AWS functions
    create AWS key, security group and server
    install applications on server
        source from github
        creds from laptop
    run docker containers
        wordpress/mysql
        jupyter notebook
        meetup

manual steps before running scripts
    create AWS account
    request gpu access
"""
import logging as log
import pandas as pd
from IPython.display import display as d
import os
import io
from _creds import notebook as nbpassword
from notebook.auth import passwd

import boto3
import fabric.api as fab
log.getLogger("paramiko").setLevel(log.ERROR)

### parameters ####################################################

# login parameters
user = 'ec2-user'
keyfile = os.path.join(os.path.expanduser("~"), ".aws", "key.pem")

# fabric parameters
fab.env.user = user
fab.env.key_filename = keyfile

here = os.path.dirname(os.path.abspath(__file__))
ec2 = boto3.resource('ec2')
getgit = "if cd {project}; then git pull; else git clone https://github.com/simonm3/{project}.git {project}; fi"

### create resource ####################################################
    
def create_key():
    """ creates keypair and saves private key to file """
    try:
        key = ec2.create_key_pair(KeyName="key")
        with open(keyfile, "w") as f:
            f.write(key.key_material)
    except Exception as e:
        log.warning(e)

def create_securityGroup():
    """ creates security group """
    sec = ec2.create_security_group(GroupName="simon", 
                                    Decription="wordpress, jupyter, ssh")
    sec.authorize_ingress(
          IpPermissions=[dict(IpProtocol='tcp', FromPort=80, ToPort=80),
                         dict(IpProtocol='tcp', FromPort=443, ToPort=443),
                         dict(IpProtocol='tcp', FromPort=8888, ToPort=8888),
                         dict(IpProtocol='tcp', FromPort=22, ToPort=22)])
    return sec

def create_server(servertype="free", disksize=15):
    """ create and start instance """
    servers = dict(free="t2.micro", gpu="p2.xlarge")
    instances = ec2.create_instances(
                        ImageId="ami-c51e3eb6",    # amazon linux
                        MinCount=1, MaxCount=1, 
                        InstanceType=servers[servertype], 
                        SecurityGroups=["simon"],
                        KeyName="key",
                        BlockDeviceMappings=[dict(DeviceName="/dev/xvda", 
                                             Ebs=dict(VolumeSize=disksize))])
    instances[0].wait_until_running()
    show()
    return instances[0]

### tools ##############################################################

def show():
    """ shows list of instances """
    a=[["name", "instance_id","image","type","state","ip"]]
    for i in list(ec2.instances.all()):
                    a.append([getName(i), i.instance_id, i.image.image_id,
                              i.instance_type, i.state["Name"],                                             i.public_ip_address])
    d(pd.DataFrame(a[1:], columns=a[0]))

def getName(resource):
    """ get name from resource """
    try:
        # security group
        return resource.group_name
    except:
        # instance
        try:
            tags = {tag["Key"]:tag["Value"] for tag in resource.tags}
            return tags["Name"]
        except:
            return "unknown"
            
def getRes(name, collection):
    """ get resource by name """
    for i in list(collection.all()):
        if name == getName(i):
            return i

### install ####################################################

def install_base():
    # docker and docker-compose
    fab.sudo("yum install docker")
    url = "https://github.com/docker/compose/releases/download/\
        1.9.0/docker-compose-$(uname -s)-$(uname -m)"
    fab.run("curl -L %s -o /usr/local/bin/docker-compose"%url)
    fab.sudo("chmod +x /usr/local/bin/docker-compose")

    # other
    fab.sudo("yum install git -y")
    fab.run("docker pull kaggle/python")
    
def install_wordpress():
    fab.run("mkdir wordpress || true")
    fab.put("wordpress/docker-compose.yml", "wordpress")
    fab.run("wordpress/docker-compose up -d")
        
def install_projects(projects=["basics", "analysis", "meetup"]):
    for project in projects:
        fab.run("mkdir -p %s"%project)
        fab.run(getgit.format(project=project))
    
    # meetup creds from laptop
    fab.put(os.path.join(os.path.expanduser("~"), 
                "documents/py/apps/meetup", "_creds.py"), "meetup")
    
    # notebook config
    os.chdir(here)
    with open("jupyter/jupyter_notebook_config.py") as f:
        config = f.read()
    config = config + "\nc.NotebookApp.password='%s'"%passwd(nbpassword)
    fab.run('mkdir -p .jupyter')
    fab.put(io.StringIO(config) , ".jupyter/jupyter_notebook_config.py")

### restart ###########################################################

def restart_notebook():
    fab.run("docker rm -f notebook || true")
    # -d=daemon. -i=keep running
    volumes = "-v $PWD/.ssh:/root/.ssh -v $PWD/.jupyter:/root/.jupyter "\
              "-v $PWD:/host"
    fab.run("docker run {volumes} -w=/host -p 8888:8888 -d -i "\
            "--name notebook kaggle/python".format(**locals()))
    fab.run("docker exec notebook python basics/pathconfig.py")
    fab.run("docker exec -d notebook jupyter notebook")

def restart_meetup():
    fab.run("docker rm -f meetup || true")
    fab.run("docker run -v $PWD:/host -w=/host -d -i "\
                "--name meetup kaggle/python")
    fab.run("docker exec meetup python basics/pathconfig.py")
    # need -d otherwise fabric waits for finish
    fab.run("docker exec -d meetup python meetup/meetup.py")
