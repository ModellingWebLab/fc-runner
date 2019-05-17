#!/usr/bin/env python

from __future__ import print_function

import cgi
import cgitb
import os
import sys

import fcws

temporaryDir = fcws.config['temp_dir']
debugPrefix = fcws.config['debug_log_file_prefix']
cgitb.enable(format='text', context=1, logdir=os.path.join(temporaryDir, debugPrefix + 'cgitb'))


def SendError(msg):
    print("Content-Type: text/html\n\n")
    print("<html><head><title>ChastePermissionError</title></head><body>%s</body></html>" % msg)
    sys.exit(0)


# Parse sent objects
form = cgi.FieldStorage()

if 'password' not in form or form['password'].value != fcws.config['password']:
    SendError("Missing or incorrect password supplied.")

if 'cancelTask' in form:
    # Special action: cancel or revoke an experiment
    print("Content-Type: text/plain\n\n")
    fcws.CancelExperiment(form['cancelTask'].value)
elif 'getProtoInterface' in form:
    # Special action: get the ontology interface for a protocol
    for field in ['callBack', 'signature']:
        if field not in form:
            SendError("Missing required field.")
    print("Content-Type: text/plain\n\n")
    fcws.GetProtocolInterface(
        form['callBack'].value, form['signature'].value, form['getProtoInterface'].value)
else:
    # Standard action: schedule experiment
    for field in ['callBack', 'signature', 'model', 'protocol', 'user', 'isAdmin']:
        if field not in form:
            SendError("Missing required field.")

    print("Content-Type: text/plain\n\n")
    signature = form["signature"].value
    # Wrap the rest in a try so we alert the caller properly if an exception occurs
    try:
        callBack = form["callBack"].value
        modelUrl = form["model"].value
        protocolUrl = form["protocol"].value
        fcws.ScheduleExperiment(
            callBack,
            signature,
            modelUrl,
            protocolUrl,
            user=form['user'].value,
            isAdmin=(form['isAdmin'].value == 'true'),
        )
    except Exception as e:
        print(signature.value, "failed due to unexpected error:", e, "<br/>")
        print("Full internal details follow:<br/>")
        raise

