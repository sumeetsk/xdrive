# -*- coding: utf-8 -*-
"""     
install and manage applications on Amazon Linux AMI using yum install 
    
NOTE: This is a set of functions not a class
"""
import logging as log
import os
import io
import json
import requests
from time import sleep
import pyperclip

import fabric.api as fab
from fabric.state import connections
from fabric.contrib.files import exists

################ xdrive functions ######################

def install_docker():
    # docker. note closes connection to set new permissions.
    fab.sudo("yum install docker -y -q")
    fab.sudo(f"usermod -aG docker {fab.env.user}")
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
    
    # if drivers exist then -d=/v1/driver/folder.
    # better to keep on /v1 as copying to boot drive takes several seconds
    volumepath = "/v1/var/lib/nvidia-docker/volumes"
    if exists(volumepath):
        volumepath = f"-d {volumepath}"
    else:
        # if not then -d must be left blank until created by nvidia-docker run
        volumepath = ""

    # NOTE fab.run used as fab.sudo command does not accept -b option
    # -b for background. nohup for run forever.
    # -s must be left blank for /run/docker/plugins NOT moved to /v1
    fab.run(f"sudo -b nohup nvidia-docker-plugin {volumepath}")
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
    fab.sudo(f"mkdir -p {folder}/docker")
    
    # restart to activate new target folder
    with fab.quiet():
        fab.sudo("service docker restart")

def stop_docker():
    """ terminate all containers and stop docker """
    with fab.quiet():        
        fab.run("docker ps -aq | xargs docker stop")
        fab.sudo("service docker stop")
        log.info("docker stopped")

def commit(container):
    """ commits to image and deletes container """
    # get container metadata
    with fab.quiet():
        r = fab.run(f"docker inspect {container}")
    c = json.loads(r)[0]
    image = c["Config"]["Image"]

    # commit to image and remove
    fab.run(f"docker commit {container} {image}")
    fab.run(f"docker rm -f {container}")
        
def dangling():
    """ remove dangling docker images """
    return fab.run("docker rmi $(docker images -f dangling=true -q)")
    
def get_names():
    """ gets list of container names """
    return fab.run("docker inspect --format='{{.Name}}' $(docker ps -aq --no-trunc)")

def run(params):
    """ run container """
    with fab.quiet():
        r = fab.sudo("nvidia-smi")

    # gpu
    if r.succeeded:
        # nvidia-docker run and save drivers
        fab.run(f"nvidia-docker run {params}")
        volumepath = "/v1/var/lib/nvidia-docker/volumes"
        if exists(volumepath):
            fab.sudo("cp -r --parents /var/lib/nvidia-docker/volumes /v1")
    else:
        # cpu
        fab.run(f"docker run {params}")

def wait_notebook():
    """ wait for notebook server """
    log.info("waiting for jupyter notebook server")
    while True:
        try:
            r=requests.get(f"http://{fab.env.host_string}:8888")
            if r.status_code==200:
                break
        except:
            pass
        sleep(5)
    ip = f"{fab.env.host_string}:8888"
    try:
        pyperclip.copy(ip)
    except:
        log.warning("pyperclip cannot find copy/paste mechanism")
        pass
    log.info(f"notebook running on {ip} (clipboard)")

############ fastai specific #################################

def start_fastai():
    fab.run(f"docker start fastai")
    wait_notebook()
    
def run_fastai():
    """ run fastai in container 
    version root user and nbs in container """
    log.warning("Working folder is now in container /fastai/deeplearning1/nbs")
    params = "-v /v1:/v1 "\
             "-w /fastai/deeplearning1/nbs "\
             "-p 8888:8888 -d "\
             "--name fastai "\
             "simonm3/fastai"
    run(params)
    wait_notebook()

########## fastai8 UNDER TEST ###################################

def start_fastai8():
    fab.run(f"docker start fastai8")
    wait_notebook()
    
def run_fastai8():
    """ run fastai in container 
    version root user and nbs in container """
    params = "-v /v1:/v1 "\
             "-w /fastai/deeplearning1/nbs "\
             "-p 8888:8888 -d "\
             "--name fastai8 "\
             "simonm3/fastai8"
    run(params)
    wait_notebook()

################## other applications ###############
    
def install_github(owner, projects):
    """ install github projects or project (if string passed) """
    
    if isinstance(projects, str):
        projects = [projects]
    
    getgit = "if cd {project}; then git pull; else git clone "\
            "https://github.com/{owner}/{project}.git {project}; fi"
    
    for project in projects:
        fab.run(getgit.format(owner=owner, project=project))

def install_python(project, configs=None):
    """ installs and runs python project in docker container
    """
    # cleanup params
    if not configs:
        configs = []
    if isinstance(configs, str):
        configs = [configs]
    
    # remove container and create fresh one
    with fab.quiet():
        fab.run(f"docker rm -f {project}")
    fab.run(f"docker run --name {project} -di python")

    # copy ~/config settings
    for config in configs:
        fab.put(os.path.join(os.path.expanduser("~"), config))
        fab.run(f"docker cp {config} {project}:/root/{config}")
        fab.run(f"rm -rf {config}")
    
    # install and run
    fab.run(f"docker exec {project} pip install {project}")
    fab.run(f"docker exec -d {project} {project}")
            
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
    fab.run(f"kg config -u {user} -p {password}")