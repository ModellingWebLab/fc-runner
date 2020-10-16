# Task queue for Functional Curation web service

import glob
import os
import logging
import shutil
import subprocess
import tempfile
import time
import traceback
import zipfile

import celery
from celery.exceptions import SoftTimeLimitExceeded
import requests

from cellmlmanip import load_model
from fc import Protocol
from fc.file_handling import combine_manifest
from fc.parsing.rdf import get_used_annotations

from . import config
from . import celeryconfig
from . import utils
from . import GetQueue

app = celery.Celery('fcws.tasks')
app.config_from_object(celeryconfig)


def Callback(callbackUrl, signature, data, json=False, isRetriedError=False, **kwargs):
    """Make a callback to the front-end server.

    @param callbackUrl: URL to send callback to
    @param signature: unique identifier for this web service call
    @param data: the data to POST
    @param json: whether to send data as JSON
    @param isRetriedError: whether this callback is simply to report
        that a previous callback timed out
    @param kwargs: extra parameters for requests.post
    """
    data['signature'] = signature
    if json:
        kwargs['json'] = data
    else:
        kwargs['data'] = data
    r = requests.Response()  # In case we never get through
    r.status_code = 500
    for attempt in range(celeryconfig.weblab_max_callback_attempts):
        r = requests.post(callbackUrl, verify=False, timeout=celeryconfig.weblab_timeout, **kwargs)
        if 400 <= r.status_code < 600:
            print("Error attempting callback at attempt %d: %s" % (attempt + 1, str(e)))
            time.sleep(60 * 2.0**attempt)  # Exponential backoff, in seconds
            # Rewind any file handles so we read from the beginning again
            for fp in kwargs.get('files', {}).values():
                fp.seek(0)
        else:
            break  # Callback successful so don't try again
    else:
        print("Giving up on callback after %d attempts." %
              celeryconfig.weblab_max_callback_attempts)
        if not isRetriedError:
            # This is the first time we're giving up, so define an error message for later delivery
            data = {'returntype': 'failed', 'returnmsg': 'No response received from server'}
            NotifyOfError.apply_async(
                (callbackUrl, signature, data), queue=GetQueue('', True), countdown=60 * 5)
    return r


def ReportError(callbackUrl, signature, prefix="failed due to unexpected error: ", json=False):
    """Report an unexpected error, with details, to the front-end, then re-raise."""
    import sys
    import traceback
    message = (prefix + sys.exc_info()[0].__name__ + ": " + str(sys.exc_info()[1]) +
               "<br/>Full internal details follow:<br/>")
    message += traceback.format_exc().replace('\n', '<br/>')
    Callback(callbackUrl, signature, {'returntype': 'failed', 'returnmsg': message}, json=json)
    raise


def MakeTempDir():
    """Make a temporary folder within the configured location."""
    try:
        os.makedirs(config['temp_dir'], 0o775)
    except os.error:
        pass
    return tempfile.mkdtemp(dir=config['temp_dir'])


@app.task(name="fcws.tasks.GetModelInterface")
def GetModelInterface(callbackUrl, signature, modelUrl):
    """Get the ontology terms used to annotate this model's variables.

    @param callbackUrl: URL to post status updates to
    @param signature: unique identifier for this web service call
    @param protocolUrl: where to download the model archive from
    """
    temp_dir = None
    error_prefix = "Unable to determine interface for model due to errors parsing file:\n"
    try:
        # Download the model archive to a temporary folder & unpack
        temp_dir = MakeTempDir()
        model_path = os.path.join(temp_dir, 'model.zip')
        utils.Wget(modelUrl, model_path, signature)
        main_model_path = utils.UnpackArchive(model_path, temp_dir, 'model')
        # Parse the model and find annotations
        model = load_model(main_model_path)
        model_terms = get_used_annotations(model)
        # Report back
        Callback(callbackUrl, signature,
                 {
                     'returntype': 'success',
                     'model_terms': list(model_terms),
                 },
                 json=True)
    except Exception:
        ReportError(callbackUrl, signature, prefix=error_prefix, json=True)
    finally:
        # Remove the temporary folder, if created
        if temp_dir and os.path.isdir(temp_dir):
            shutil.rmtree(temp_dir)

@app.task(name="fcws.tasks.GetProtocolInterface")
def GetProtocolInterface(callbackUrl, signature, protocolUrl):
    """Get the ontology terms forming the interface to a protocol.

    Returns both required and optional terms via a callback to the website.

    @param callbackUrl: URL to post status updates to
    @param signature: unique identifier for this web service call
    @param protocolUrl: where to download the protocol archive from
    """
    temp_dir = None
    error_prefix = "Unable to determine interface for protocol due to errors parsing file:\n"
    try:
        # Download the protocol archive to a temporary folder & unpack
        temp_dir = MakeTempDir()
        proto_path = os.path.join(temp_dir, 'protocol.zip')
        utils.Wget(protocolUrl, proto_path, signature)
        main_proto_path = utils.UnpackArchive(proto_path, temp_dir, 'proto')
        # Check a full parse of the protocol succeeds; only continue if it does
        try:
            proto = Protocol(main_proto_path)
        except Exception:
            ReportError(callbackUrl, signature, prefix=error_prefix, json=True)
        else:
            # Determine the interface, getting sets of ontology terms
            required_terms, optional_terms = proto.get_required_model_annotations()
            ioputs = proto.get_protocol_interface()
            # Report back
            Callback(callbackUrl, signature,
                     {
                         'returntype': 'success',
                         'required': list(required_terms),
                         'optional': list(optional_terms),
                         'ioputs': list(ioputs),
                     },
                     json=True)
    except:
        ReportError(callbackUrl, signature, prefix=error_prefix, json=True)
    finally:
        # Remove the temporary folder, if created
        if temp_dir and os.path.isdir(temp_dir):
            shutil.rmtree(temp_dir)


@app.task(name="fcws.tasks.CheckExperiment")
def CheckExperiment(callbackUrl, signature, modelUrl, protocolUrl, datasetUrl=None, fittingSpecUrl=None):
    """Check a model/protocol combination for compatibility.

    If the interfaces match up, then the experiment can be run.
    Otherwise, we alert the front-end to update the experiment status.
    As a side effect this downloads & unpacks the model & protocol definitions,
    ready for the RunExperiment task.

    @param callbackUrl: URL to post status updates to
    @param signature: unique identifier for this experiment run
    @param modelUrl: where to download the model archive from
    @param protocolUrl: where to download the protocol archive from
    @param datasetUrl: if doing a fit, where to download the reference dataset from
    @param fittingSpecUrl: if doing a fit, the fitting specification
    """
    log = logging.getLogger(__name__)

    try:
        # Download the submitted COMBINE archives to disk in temporary folder
        temp_dir = MakeTempDir()
        model_path = os.path.join(temp_dir, 'model.zip')
        proto_path = os.path.join(temp_dir, 'protocol.zip')
        utils.Wget(modelUrl, model_path, signature)
        utils.Wget(protocolUrl, proto_path, signature)

        # Unpack the model & protocol
        main_model_path = utils.UnpackArchive(model_path, temp_dir, 'model')
        main_proto_path = utils.UnpackArchive(proto_path, temp_dir, 'proto')

        if datasetUrl and fittingSpecUrl:
            # We're doing a fit
            dataset_zip = os.path.join(temp_dir, 'dataset.zip')
            utils.Wget(datasetUrl, dataset_zip, signature)
            fitting_data_path = utils.UnpackArchive(dataset_zip, temp_dir, 'dataset', ignoreManifest=True)
            if fittingSpecUrl == protocolUrl:
                # Temporary hack: fitting spec is part of the protocol archive
                proto_dir, proto_name = os.path.split(main_proto_path)
                for filename in os.listdir(proto_dir):
                    if (filename != proto_name and
                            os.path.splitext(filename)[1] in utils.EXPECTED_EXTENSIONS['fittingSpec']):
                        fitting_spec_path = os.path.join(proto_dir, filename)
                        break
                else:
                    raise ValueError("Failed to find fitting specification within protocol")
            else:
                # This is what we're moving towards
                fitting_spec_zip = os.path.join(temp_dir, 'fittingSpec.zip')
                utils.Wget(fittingSpecUrl, fitting_spec_zip, signature)
                fitting_spec_path = utils.UnpackArchive(fitting_spec_zip, temp_dir, 'fittingSpec')
        else:
            # Not a fitting experiment
            fitting_spec_path = fitting_data_path = None

        # Check whether their interfaces are compatible
        missing_terms, missing_optional_terms = utils.DetermineCompatibility(
            main_proto_path, main_model_path)
        # TODO: CHECK FOR MISSING FSPEC/FDATA TERMS
        if missing_terms:
            message = ("inapplicable - required ontology terms are not present in the model."
                       " Missing terms are:<br/>")
            for term in missing_terms:
                message += "&nbsp;" * 4 + term + "<br/>"
            if missing_optional_terms:
                message += "Missing optional terms are:<br/>"
                for term in missing_optional_terms:
                    message += "&nbsp;" * 4 + term + "<br/>"
            # Report & clean up temporary files
            Callback(callbackUrl, signature, {'returntype': 'inapplicable', 'returnmsg': message})
            shutil.rmtree(temp_dir)
        else:
            # Run the experiment directly in this task,
            # to ensure it has access to the unpacked model & protocol
            RunExperiment(
                callbackUrl,
                signature,
                main_model_path,
                main_proto_path,
                fitting_spec_path,
                fitting_data_path,
                temp_dir,
            )
    except:
        ReportError(callbackUrl, signature)


# @app.task(name="fcws.tasks.RunExperiment")
def RunExperiment(
        callbackUrl, signature, modelPath, protoPath, fspecPath, fdataPath,
        tempDir):
    """Run a functional curation experiment.

    @param callbackUrl: URL to post status updates and results to
    @param signature: unique identifier for this experiment run
    @param modelPath: path to the main model file
    @param protoPath: path to the main protocol file
    @param fspecPath: path to the main fitting specification file (or None)
    @param fdataPath: path to the main fitting data file (or None)
    @param tempDir: folder in which to store any temporary files
    """
    log = logging.getLogger(__name__)
    log.info('RunExperiment called with ' + str(fspecPath) + ' and ' + str(fdataPath))

    try:
        # Tell the website we've started running
        Callback(callbackUrl, signature, {'returntype': 'running'})

        # Call FunctionalCuration exe, writing output to the temporary folder containing inputs
        # (or rather, a subfolder thereof).
        # Also redirect stdout and stderr so we can debug any issues.
        for key, value in config['environment'].items():
            os.environ[key] = value

        if fspecPath and fdataPath:
            log.info('Running fitting experiment')

            for key, value in config['environment'].items():
                log.info('Setting environment variable ' + key + ': ' + value)
                os.environ[key] = value

            log.info('Using virtual environment ' + config['fitting_virtualenv'])

            args = [
                config['fitting_path'],
                config['fitting_virtualenv'],
                modelPath,
                protoPath,
                fspecPath,
                fdataPath,
                os.path.join(tempDir, 'output'),
            ]

        else:
            log.info('Running functional curation experiment')

            args = [
                config['exe_path'],
                modelPath,
                protoPath,
                os.path.join(tempDir, 'output'),
            ]

        child_stdout_name = os.path.join(tempDir, 'stdout.txt')
        output_file = open(child_stdout_name, 'w')
        timeout = False
        retcode = 0
        try:
            child = None
            child = subprocess.Popen(
                args,
                stdout=output_file,
                stderr=subprocess.STDOUT,
                bufsize=1,
            )
            retcode = child.wait()
        except SoftTimeLimitExceeded:
            # If we're timed out, kill off the child process, but send back any partial output
            # - don't re-raise
            child.terminate()
            time.sleep(5)
            child.kill()
            timeout = True
        except:
            # If any other error happens, just make sure the child is dead then report it
            if child is not None:
                child.terminate()
                time.sleep(5)
                child.kill()
            raise
        output_file.close()

        #TODO
        #if retcode:
        #    Callback(callbackUrl, signature,
        #        {'returntype': 'failed', 'returnmsg': output},
        #        json=True
        #    )

        # Zip up the outputs and post them to the callback
        output_path = os.path.join(tempDir, 'output.zip')
        output_files = glob.glob(os.path.join(tempDir, 'output', '*', '*', '*'))  # Yuck!
        output_zip = zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED)
        output_zip.write(child_stdout_name, 'stdout.txt')
        # Remove any manifest file since we'll need to create a new one with stdout.txt in (and possibly errors.txt)
        for ofile in output_files:
            if os.path.basename(ofile) == 'manifest.xml':
                output_files.remove(ofile)
                break
        if timeout:
            # Add a message about the timeout to the errors.txt file
            # (which is created if not present)
            for ofile in output_files:
                if os.path.isfile(ofile) and os.path.basename(ofile) == "errors.txt":
                    error_file_path = ofile
                    break
            else:
                error_file_path = os.path.join(tempDir, 'errors.txt')
                output_files.append(error_file_path)
            error_file = open(error_file_path, 'a+')
            error_file.write("\nExperiment terminated due to exceeding time limit\n")
            error_file.close()
        for ofile in output_files:
            if os.path.isfile(ofile):
                output_zip.write(ofile, os.path.basename(ofile))
        if 'success' in output_zip.namelist():
            outcome = 'success'
        else:
            for filename in output_zip.namelist():
                if filename.endswith('plot_data.csv'):
                    outcome = 'partial'  # Some output plots created => might be useful
                    break
            else:
                outcome = 'failed'  # No outputs created => total failure
        # Add a manifest with the final contents list
        manifest = combine_manifest(output_zip.namelist())
        output_zip.writestr('manifest.xml', manifest)
        output_zip.close()

        files = {'experiment': open(output_path, 'rb')}
        r = Callback(callbackUrl, signature, {'returntype': outcome}, files=files)

        return r.status_code
    except:
        ReportError(callbackUrl, signature)
    finally:
        # Remove the temporary folder
        shutil.rmtree(tempDir)


@app.task(name="fcws.tasks.NotifyOfError")
def NotifyOfError(callbackUrl, signature, data):
    """Keep trying to contact the front-end with a short error message.

    @param callbackUrl: URL to post error to
    @param signature: unique identifier for this web service call
    @param data: POST data containing the error message string (see Callback for construction)
    """
    Callback(callbackUrl, signature, data, isRetriedError=True)
