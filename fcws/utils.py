"""
Utility module for Functional Curation web services.

It handles unpacking COMBINE archives containing CellML models or Functional Curation protocols,
and determining which file within is the primary model/protocol.

It also contains a method for determining whether a model and protocol are compatible.
"""

import os
import sys
import requests
import xml.etree.ElementTree as ET
import zipfile

from fc import Protocol
import fc.parsing.CompactSyntaxParser as CSP

from . import config

EXPECTED_EXTENSIONS = {'model': ['.cellml'],
                       'proto': ['.txt', '.xml'],
                       'dataset': ['.csv'],
                       'fittingSpec': ['.txt']}

MANIFEST = 'manifest.xml'


def Wget(url, localPath, signature):
    """Retrieve a binary file from the given URL and save it to disk."""
    source = requests.get(url, stream=True, verify=False, headers={
        'Authorization': 'Token ' + signature
    })
    source.raise_for_status()
    with open(localPath, 'wb') as local_file:
        for chunk in source.iter_content(chunk_size=10240):
            if chunk:  # filter out keep-alive new chunks
                local_file.write(chunk)


def UnpackArchive(archivePath, tempPath, contentType, ignoreManifest=False):
    """Unpack a COMBINE archive, and return the path to the primary unpacked file.

    :param archivePath:  path to the archive
    :param tempPath:  path to a temporary folder under which to unpack
    :param contentType:  whether the archive contains a model ('model') or protocol ('proto')
    :param ignoreManifest:  if set, ignore the master file specified in the manifest

    Files will be unpacked into the path tempPath/contentType.
    """
    assert contentType in EXPECTED_EXTENSIONS
    archive = zipfile.ZipFile(archivePath)
    output_path = os.path.join(tempPath, contentType)
    archive.extractall(output_path)
    # Check if the archive manifest specifies the primary file
    primary_file = None
    manifest_path = os.path.join(output_path, MANIFEST)
    if not ignoreManifest and os.path.exists(manifest_path):
        manifest = ET.parse(manifest_path)
        for item in manifest.iter(
                '{http://identifiers.org/combine.specifications/omex-manifest}content'):
            if item.get('master', 'false') == 'true':
                primary_file = item.get('location')
                if primary_file[0] == '/':
                    # There's some debate over the preferred form of location URIs...
                    primary_file = primary_file[1:]
                break
    if not primary_file:
        # No manifest or no master listed, so try to figure it out ourselves:
        # find the first item with expected extension
        for item in archive.infolist():
            if (item.filename != MANIFEST and
                    os.path.splitext(item.filename)[1] in EXPECTED_EXTENSIONS[contentType]):
                primary_file = item.filename
                break
    if not primary_file:
        raise ValueError('No suitable primary file detected in COMBINE archive')
    primary_path = os.path.join(output_path, primary_file)
    if not os.path.exists(primary_path):
        raise ValueError('Declared primary file not present in archive')
    return primary_path


def GetProtoInterface(protocol):
    """Get the set of ontology terms used by the given protocol, recursively processing imports.

    :param protocol: a parsed :class:`fc.Protocol` instance
    :return: a pair (required terms, optional terms) of sets of ontology terms, as full URI strings
    """
    return protocol.get_required_model_annotations()


def DetermineCompatibility(protoPath, modelPath):
    """Determine whether the given protocol and model are compatible.

    This checks whether the ontology terms accessed by the protocol are present in the model.
    It returns a list of terms required but not present, so the pair are compatible if this
    list is empty.

    NB: Only works with textual syntax protocols at present; assumes OK otherwise.
    """
    protocol = Protocol(protoPath)
    return protocol.check_model_compatibility(modelPath)
