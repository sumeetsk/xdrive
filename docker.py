# -*- coding: utf-8 -*-
"""     
install and manage applications in docker containers
    wordpress/mysql
    jupyter notebook
    meetup
"""
import logging as log
from aws import keyfile
import os
import io
import pandas as pd

from _creds import notebook as nbpassword
from notebook.auth import passwd
import fabric.api as fab
from fabric.state import connections
log.getLogger("paramiko").setLevel(log.ERROR)

# fabric parameters
fab.env.key_filename = keyfile

here = os.path.dirname(os.path.abspath(__file__))
getgit = "if cd {project}; then git pull; else git clone "\
            "https://github.com/simonm3/{project}.git {project}; fi"

### install ####################################################

def mount():
    """ mounts pdata volume """
    fab.sudo("mkdir /v1")
    fab.sudo("mount /dev/xvdf /v1")
    fab.sudo("chown -Rf %s /v1"%fab.env.user)

def chdir_docker():
    fab.sudo("mkdir -p /etc/docker")
    fab.put("docker/daemon.json", "/etc/docker", use_sudo=True)
    fab.sudo("mkdir -p /v1/docker")

def install_docker():
    fab.sudo("yum install docker -y")
    fab.sudo("usermod -aG docker %s"%fab.env.user)
    
    # restart docker
    fab.sudo("service docker start")
    connections.connect(fab.env.host_string)

    log.info("ready to ssh pull kaggle/python or other")
  
def install_other():
    # docker compose
    url = "https://github.com/docker/compose/releases/download/"\
            "1.9.0/docker-compose-$(uname -s)-$(uname -m)"
    fab.sudo("curl -L %s -o /usr/local/bin/docker-compose"%url)
    fab.sudo("chmod +x /usr/local/bin/docker-compose")

    # git 
    fab.sudo("yum install git -y")
    
    # python3
    fab.sudo("yum install python35 -y")
    fab.run("echo 'alias python=python35' > .bashrc")

def install_wordpress():
    fab.run("mkdir wordpress || true")
    fab.put("wordpress/docker-compose.yml", "wordpress")
    with fab.cd("wordpress"):
        fab.run("docker-compose up -d")
        
def install_projects(projects=["basics", "analysis", "meetup"]):
    """ installs python projects from github """
        
    # get git controlled files from laptop
    for project in projects:
        #fab.run("mkdir %s || true"%project)
        fab.run(getgit.format(project=project))
            
    # meetup creds (not git controlled)
    if "meetup" in projects:
        fab.put(os.path.join(here, os.pardir, project, 
                             "_creds.py"), project)
        
    # notebook config
    with open("jupyter/jupyter_notebook_config.py") as f:
        config = f.read()
    config = config + "\nc.NotebookApp.password='%s'"%passwd(nbpassword)
    fab.run('mkdir .jupyter || true')
    fab.put(io.StringIO(config) , ".jupyter/jupyter_notebook_config.py")

### running ###########################################################

def gettasks(target="python"):
    """ returns dataframe of running tasks inside containers
        where task contains target string
    """
    containers = fab.run("docker inspect --format='{{.Name}}' "\
                         "$(docker ps -q)").splitlines()
    containers = [c.lstrip("/") for c in containers]
    cout = []
    tout = []
    for container in containers:
        tasks = fab.run("docker exec %s ps -eo args | grep %s || true"\
                        %(container, target)).splitlines()
        for task in tasks:
            cout.append(container)
            tout.append(task)
    out = pd.DataFrame(dict(container=cout, task=tout))
    return out 

def restart_notebook():
    """ stops if running; runs notebook server
        note: -d=daemon so task returns. -i=keep alive.
    """
    fab.run("docker rm -f notebook || true")
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
    fab.run("docker exec -d meetup python meetup/meetup.py")
