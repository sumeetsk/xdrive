# -*- coding: utf-8 -*-
"""     
install and manage applications on server
    wordpress/mysql
    jupyter notebook
    github apps
    
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

### install ####################################################

def install_docker():
    fab.sudo("yum install docker -y")
    fab.sudo("usermod -aG docker %s"%fab.env.user)
    
    # restart docker
    fab.sudo("service docker start")
    connections.connect(fab.env.host_string)
    
    # docker compose
    url = "https://github.com/docker/compose/releases/download/"\
            "1.9.0/docker-compose-$(uname -s)-$(uname -m)"
    fab.sudo("curl -L %s -o /usr/local/bin/docker-compose"%url)
    fab.sudo("chmod +x /usr/local/bin/docker-compose")
    log.info("docker installed. if need to pull images then use ssh "\
             "as this shows progress whereas fabric does not")

def install_nvidia():
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
    for pdata volume is /v1
    """
    with fab.quiet():
        fab.sudo("service docker stop")
    
    # create daemon.json settings
    with open("docker/daemon.json", "w") as f:
        f.write('{"graph":"%s/docker"}'%folder)
    fab.sudo("mkdir -p /etc/docker")
    fab.put("docker/daemon.json", "/etc/docker", use_sudo=True)
    fab.sudo("mkdir -p %s/docker"%folder)
    
    fab.sudo("service docker start")

def stop_docker():
    """ terminate all containers and stop docker """
    with fab.quiet():        
        fab.run("docker ps -aq | xargs docker stop")
        fab.sudo("service docker stop")
        log.info("docker stopped")
    
def install_git():
    fab.sudo("yum install git -y")
    
def install_py3():
    fab.sudo("yum install python35 -y")
    fab.run("echo 'alias python=python35' > .bashrc")

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
        
def install_github(user, projects):
    """ install github projects """
    
    getgit = "if cd {project}; then git pull; else git clone "\
            "https://github.com/{user}/{project}.git {project}; fi"
    
    for project in projects:
        fab.run(getgit.format(user=user, project=project))

        # creds (not git controlled)
        try:
            fab.put(os.path.join(here, os.pardir, project,
                             "_creds.py"), project)
        except:
            pass

### running ###########################################################

def restart_python(project):
    """ runs python project from host folder in container """
    fab.run("docker rm -f {project} || true".format(**locals()))
    fab.run("docker run -v $HOME:/host -w=/host -d -i "\
                    "--name {project} python".format(**locals()))
    fab.run("docker exec {project} python " \
                "basics/pathconfig.py".format(**locals()))
    fab.run("docker exec {project} pip install requests".format(**locals()))
    fab.run("docker exec -d {project} python "\
                "{project}/{project}.py".format(**locals()))

def restart_notebook():
    """ terminates and restarts
        note: -d=daemon so task returns. -i=keep alive.
    """
    fab.run("docker rm -f notebook || true")
    docker = "nvidia-docker" if fab.sudo("nvidia-smi").succeeded \
                    else "docker"
    
    volumes = "-v /v1:/root "\
              "-v /v1:/host"
    fab.sudo("{docker} run {volumes} -w=/host -p 8888:8888 -d -i "\
             "-u root "\
             "--name notebook simoneva/fastai7".format(**locals()))
    with fab.quiet():
        fab.run("docker exec notebook python basics/pathconfig.py")
