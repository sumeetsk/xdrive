# -*- coding: utf-8 -*-
"""     
install and manage applications on Amazon Linux AMI using yum install 
    
NOTE: This is a set of functions not a class
"""
import logging as log
import os
import io

from config import keyfile, here
from notebook.auth import passwd
from _creds import notebook, kaggle
import fabric.api as fab
from fabric.state import connections
log.getLogger("paramiko").setLevel(log.ERROR)
fab.env.key_filename = keyfile

### essentials to setup boot drive and pdrive ######################

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
    fab.run("sudo -b nohup nvidia-docker-plugin")
    log.info("nvidia-docker-plugin is running")
    
def set_docker_folder(folder="/var/lib"):
    """ set location of docker images and containers
    for pdrive volume = "/v1"
    """
    # create daemon.json settings
    with open("docker/daemon.json", "w") as f:
        f.write('{"graph":"%s/docker"}'%folder)
    fab.sudo("mkdir -p /etc/docker")
    fab.put("docker/daemon.json", "/etc/docker", use_sudo=True)
    
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
        
def run_fastai():
    """ runs fastai notebook for the first time (after that it restarts)
        note: -d=daemon so task returns
    """
    with fab.quiet():
        r = fab.sudo("nvidia-smi")
    docker = "nvidia-docker" if  r.succeeded else "docker"

    # config on host
    fab.sudo("{docker} run "\
              "-v /v1:/host "\
             "-w=/host/nbs "\
             "-p 8888:8888 -d "\
             "--restart=always "\
             "--name fastai "\
             "simonm3/fastai".format(**locals()))
    log.info("fastai running on %s:%s"%(fab.env.host_string, "8888"))

#### utilities ##############################################
                
def install_github(user, projects):
    """ install github projects or project (if string passed) """
    
    if isinstance(projects, str):
        projects = [projects]
    
    getgit = "if cd {project}; then git pull; else git clone "\
            "https://github.com/{user}/{project}.git {project}; fi"
    
    for project in projects:
        fab.sudo(getgit.format(user=user, project=project))

        # creds (not git controlled)
        try:
            fab.put(os.path.join(here, os.pardir, project,
                             "_creds.py"), project)
        except:
            pass
        
def install_wordpress():
    fab.run("mkdir wordpress || true")
    fab.put("wordpress/docker-compose.yml", "wordpress")
    with fab.cd("wordpress"):
        fab.run("docker-compose up -d")

def install_miniconda():
    fab.run("wget https://repo.continuum.io/miniconda/"\
                "Miniconda3-latest-Linux-x86_64.sh")
    fab.run("bash Miniconda3-latest-Linux-x86_64.sh")
    
def install_kaggle():
    with fab.cd("/v1"):
        fab.run("pip install kaggle-cli")
        fab.run("kg config -u %s -p %s"% \
                    (kaggle["user"], kaggle["password"]))
        
def install_notebook():
    with open("jupyter/jupyter_notebook_config.py") as f:
        config = f.read()
    config = config + "\nc.NotebookApp.password='%s'"\
                                %passwd(notebook["password"])
    fab.run('mkdir .jupyter || true')
    fab.put(io.StringIO(config) , ".jupyter/jupyter_notebook_config.py")

def run_python(project):
    """ runs python project from host folder in container """
    
    fab.run("docker run -v $HOME:/host "\
                    "-w=/host -d -i "\
                    "--restart=always "\
                    "--name {project} python".format(**locals()))
    fab.run("docker exec {project} python " \
                "/host/basics/pathconfig.py".format(**locals()))
    fab.run("docker exec {project} pip install requests".format(**locals()))
    fab.run("docker exec -d {project} python "\
                "{project}/{project}.py".format(**locals()))

