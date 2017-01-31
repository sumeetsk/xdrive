""" configuration file for notebook server
"""
# certificate does not work. don't know why!!!!
#c.NotebookApp.certfile = "/root/.ssh/authorized_keys"
c.NotebookApp.ip = '*'
c.NotebookApp.open_browser = False
c.NotebookApp.port = 8888