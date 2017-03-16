# -*- coding: utf-8 -*-
"""     
install and manage applications on Amazon Linux AMI using yum install 
    
NOTE: This is a set of functions not a class
"""
import logging as log
import os
import io

from notebook.auth import passwd
import fabric.api as fab
from fabric.state import connections
from _creds import nbpassword, kaggle

################ needed for xdrive ######################

def install_docker():
    # docker
    fab.sudo("yum install docker -y -q")
    fab.sudo("usermod -aG docker %s"%fab.env.user)
    connections.connect(fab.env.host_string)    
    
    # docker compose
    fab.sudo("pip install -q docker-compose")
    log.info("docker installed. if need to pull images then use ssh "\
             "as this shows progress whereas fabric does not")

def install_nvidia_docker():
    # nvidia docker (NOTE: use instructions for "other" NOT "centos")
    fab.sudo("wget -P /tmp https://github.com/NVIDIA/nvidia-docker/releases/"\
            "download/v1.0.0/nvidia-docker_1.0.0_amd64.tar.xz")
    fab.sudo("tar --strip-components=1 -C "\
            "/usr/bin -xvf /tmp/nvidia-docker*.tar.xz "\
            "&& rm /tmp/nvidia-docker*.tar.xz")
    
    # NOTE fab.run used as fab.sudo command does not accept -b option
    # -b for background. nohup for run forever.
    # -d is data location
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
        
##################### needed for fastai ###########################
        
def run_fastai():
    """ runs fastai notebook for the first time (after that it restarts)
        note: -d=daemon so task returns
    """
    # if already exists then start
    with fab.quiet():
        r = fab.run("docker ps -a | grep fastai")
    if r.succeeded:
        fab.run("docker start fastai")
        return
    
    with fab.quiet():
        r = fab.sudo("nvidia-smi")
    docker = "nvidia-docker" if  r.succeeded else "docker"

    # password on /v1 allows it to be changed
    with fab.cd("/v1"):
        install_notebook()
        
    # /host/nbs is working copy and home folder
    fab.run("mkdir -p /v1/nbs")
        
    fab.run("{docker} run "\
              "-v /v1:/host "\
             "-v /v1/.jupyter:/home/docker/.jupyter "\
             "-w /host/nbs "\
             "-p 8888:8888 -d "\
             "--restart=always "\
             "--name fastai "\
             "simonm3/fastai".format(**locals()))
    
    # copy driver files. these are not created until nvidia-docker run
    fab.sudo("cp -r /var/lib/nvidia-docker /v1")
    
    # /host/nbs is working copy and home folder
    fab.run("docker exec -it -u docker fastai cp -R "\
                     "/fastai-courses/deeplearning1/nbs /host")
    
    log.info("fastai running on %s:%s"%(fab.env.host_string, "8888"))
 
def install_notebook():
    """ create config on /v1 """
    config = ["c.NotebookApp.ip = '*'",
              "c.NotebookApp.open_browser = False",
              "c.NotebookApp.port = 8888",
              "c.NotebookApp.password='%s'"%nbpassword]
    fab.run('mkdir -p /v1/.jupyter')
    f = io.StringIO("\n".join(config))
    fab.put(f, "/v1/.jupyter/jupyter_notebook_config.py")
    
###### install other projects in docker containers #########
    
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
        
#### install on host ################################################  
    
def install_wordpress():
    fab.run("mkdir wordpress || true")
    fab.put("../wordpress/docker-compose.yml", "wordpress")
    with fab.cd("wordpress"):
        fab.run("docker-compose up -d")

def install_miniconda():
    fab.run("wget https://repo.continuum.io/miniconda/"\
                "Miniconda3-latest-Linux-x86_64.sh")
    fab.run("bash Miniconda3-latest-Linux-x86_64.sh")
    
def install_kaggle():
    """ note bug means must install in home folder not /v1
    will only download data to home and subfolders
    """
    fab.sudo("sudo yum install -y libxml2-devel libxslt-devel")
    fab.sudo("pip install kaggle-cli")
    fab.run("kg config -u %s -p %s"% \
                (kaggle["user"], kaggle["password"]))