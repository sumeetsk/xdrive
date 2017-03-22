# -*- coding: utf-8 -*-
"""     
install and manage applications on Amazon Linux AMI using yum install 
    
NOTE: This is a set of functions not a class
"""
import logging as log
import os
import io
import json

import fabric.api as fab
from fabric.state import connections

################ needed for xdrive ######################

def install_docker():
    # docker. note closes connection to set new permissions.
    fab.sudo("yum install docker -y -q")
    fab.sudo("usermod -aG docker %s"%fab.env.user)
    connections[fab.env.host_string].get_transport().close() 
    
    # docker compose
    fab.sudo("pip install -q docker-compose")
    log.info("docker installed. if need to pull images then use ssh "\
             "as this shows progress whereas fabric does not")

def install_nvidia_docker():
    """ install nvidia_docker and plugin
    NOTE: uses instructions for "other" NOT "centos" as this fails
    """
    # only needed on GPU
    with fab.quiet():
        r = fab.run("nvidia-smi")
        if r.failed:
            log.warning("nvidia drivers not found")
            return    
    
    fab.sudo("wget -P /tmp https://github.com/NVIDIA/nvidia-docker/releases/"\
            "download/v1.0.0/nvidia-docker_1.0.0_amd64.tar.xz")
    fab.sudo("tar --strip-components=1 -C "\
            "/usr/bin -xvf /tmp/nvidia-docker*.tar.xz "\
            "&& rm /tmp/nvidia-docker*.tar.xz")
    
    # NOTE fab.run used as fab.sudo command does not accept -b option
    # -b for background. nohup for run forever.
    # -d is data volumes for drivers. was used to stop/start containers on GPUs
    # -d unnecessary now commit/run used rather than stop/start???????
    # commit/run enables reuse of containers across CPUs and GPUs
    fab.run("sudo -b nohup nvidia-docker-plugin -d /v1/nvidia-docker/volumes")
    log.info("nvidia-docker-plugin is running")
    
def set_docker_folder(folder="/var/lib"):
    """ set location of docker images and containers
    for xdrive volume = "/v1"
    """
    # create daemon.json settings
    config = '{"graph":"%s/docker"}'%folder
    fab.sudo("mkdir -p /etc/docker")
    fab.put(io.StringIO(config), "/etc/docker/daemon.json", use_sudo=True)
    
    # create target folder
    fab.sudo("mkdir -p %s/docker"%folder)
    
    # restart to activate new target folder
    with fab.quiet():
        fab.sudo("service docker restart")

def stop_docker():
    """ terminate all containers and stop docker """
    with fab.quiet():        
        fab.run("docker ps -aq | xargs docker stop")
        fab.sudo("service docker stop")
        log.info("docker stopped")

def commit():
    """ commit all containers to images; and remove containers
    nvidia-docker looks for drivers when "run"
    therefore use commit/run rather than stop/start
    """
    containers = fab.run("docker ps -aq").split()

    for container in containers:
        # get container metadata
        with fab.quiet():
            r = fab.run(f"docker inspect {container}")
        c = json.loads(r)[0]
        image = c["Config"]["Image"]

        # commit to image
        fab.run(f"docker commit {container} {image}")

        # remove
        fab.run(f"docker rm -f {container}")
        
def dangling():
    """ remove dangling docker images """
    fab.run("docker rmi $(docker images -f 'dangling=true; -q)")
     
##################### application scripts ###########################

def run_fastai():
    """ run fastai notebook
        note: -d=daemon so task returns
    """
    with fab.quiet():
        r = fab.sudo("nvidia-smi")
    docker = "nvidia-docker" if  r.succeeded else "docker"

    # /v1/nbs is home folder
    fab.run("mkdir -p /v1/nbs")
    
    fab.run("{docker} run "\
              "-v /v1:/v1 "\
             "-w /v1/nbs "\
             "-p 8888:8888 -d "\
             "--name fastai "\
             "simonm3/fastai".format(**locals()))
    
    log.info("fastai running on %s:%s"%(fab.env.host_string, "8888"))
    
def install_github(owner, projects):
    """ install github projects or project (if string passed) """
    
    if isinstance(projects, str):
        projects = [projects]
    
    getgit = "if cd {project}; then git pull; else git clone "\
            "https://github.com/{owner}/{project}.git {project}; fi"
    
    for project in projects:
        fab.run(getgit.format(owner=owner, project=project))

def install_python(projects, home="/v1"):
    """ installs and runs python project in docker container as root user
    """
    if isinstance(projects, str):
        projects = [projects]
    for project in projects:
        # copy ~/.project config settings
        with fab.cd(home):
            fab.put(os.path.join(os.path.expanduser("~"), "."+project))
        
        # remove existing container
        fab.run(f"docker rm -f {project}")
        
        # run container with home folder for config and creds
        fab.run(f"docker run -v {home}:/root --name {project} -di python")
        
        # install project from pypi
        fab.run(f"docker exec {project} pip install {project}")
        
        # run project
        fab.run(f"docker exec {project} {project}")
            
def install_wordpress():
    fab.run("mkdir wordpress || true")
    fab.put("../wordpress/docker-compose.yml", "wordpress")
    with fab.cd("wordpress"):
        fab.run("docker-compose up -d")

def install_miniconda():
    fab.run("wget https://repo.continuum.io/miniconda/"\
                "Miniconda3-latest-Linux-x86_64.sh")
    fab.run("bash Miniconda3-latest-Linux-x86_64.sh")
    
def install_kaggle(user, password):
    """ note bug means must install in home folder not /v1
    will only download data to home and subfolders
    """
    fab.sudo("sudo yum install -y libxml2-devel libxslt-devel")
    fab.sudo("pip install kaggle-cli")
    fab.run("kg config -u %s -p %s"%(user, password))