# FC experiment runner for the Web Lab

This repository implements a backend job runner for the WebLab’s [Functional Curation (FC)](https://github.com/ModellingWebLab/weblab-fc) experiments. It functions as an asynchronous execution service that bridges the WebLab frontend with long-running FC model/protocol runs, then reports status and artifacts back to the frontend.

At a high level, it:

1. Accepts experiment-related requests from a web-facing CGI endpoint.
1. Queues work in [Celery](https://docs.celeryq.dev/).
1. Downloads model/protocol archives (and optional fitting data/specs).
1. Checks protocol-model compatibility.
1. Runs the simulation/fitting executable.
1. Zips results and posts them back to a callback URL.

## Installation

### Install dependencies

Install [Functional Curation (FC)](https://github.com/ModellingWebLab/weblab-fc).

Install additional dependencies
```bash
python3 -m pip install -r requirements/base.txt
```

Update configuration settings in `fcws/config.json`

### Install service

Install a Celery service. For example, save this to `/etc/systemd/system/celery.service`:

```txt
[Unit]
Description=Celery Service
After=network.target

[Service]
Type=forking
User=celery
Group=celery
EnvironmentFile=-/etc/default/celery

WorkingDirectory=/path/to/fc-runner
RuntimeDirectory=celery

ExecStart=/bin/sh -c '${CELERY_BIN} multi start ${CELERYD_NODES} -A ${CELERY_APP} \
  --pidfile=${CELERYD_PID_FILE} \
  --logfile=${CELERYD_LOG_FILE} \
  --loglevel=${CELERYD_LOG_LEVEL} ${CELERYD_OPTS}'

ExecStop=/bin/sh -c '${CELERY_BIN} multi stopwait ${CELERYD_NODES} --pidfile=${CELERYD_PID_FILE}'

ExecReload=/bin/sh -c '${CELERY_BIN} multi restart ${CELERYD_NODES} -A ${CELERY_APP} \
  --pidfile=${CELERYD_PID_FILE} \
  --logfile=${CELERYD_LOG_FILE} \
  --loglevel=${CELERYD_LOG_LEVEL} ${CELERYD_OPTS}'

Restart=on-failure

[Install]
WantedBy=multi-user.target
```

and save this to `/etc/default/celery`

```txt
# Configuration for Functional Curation celery daemon.

# Number of worker nodes
CELERYD_NODES=2

# Path to celery executable
CELERY_BIN=/path/to/bin/celery"

# Celery application
CELERY_APP="fcws.tasks:app"

# Extra command-line arguments to the workers
CELERYD_OPTS="--concurrency=2 -l info -Ofair --statedb=/var/lib/celery/%n.state -Q:1 admin -Q default,admin"

CELERYD_LOG_FILE="/var/log/celery/%n%I.log"
CELERYD_PID_FILE="/run/%n.pid"
CELERYD_LOG_LEVEL="INFO"

# Notes:
# - The default queue is set to 'default' in celeryconfig.py, and admin users 
#   use 'admin' (see fcws/__init__.py).
# - %n will be replaced with the first part of the nodename.
# - %I will be replaced with the current child process index
#   and is important when using the prefork pool to avoid race conditions.
```

```sh
sudo systemctl daemon-reload
sudo systemctl start celery.service
```
