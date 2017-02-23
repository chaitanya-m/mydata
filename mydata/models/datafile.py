"""
Model class for MyTardis API v1's DataFileResource.
See: https://github.com/mytardis/mytardis/blob/3.7/tardis/tardis_portal/api.py
"""

import io
import json
import urllib
import urllib2

import requests
import poster

from mydata.logs import logger
from mydata.utils.exceptions import DoesNotExist
from mydata.utils.exceptions import MultipleObjectsReturned
from mydata.utils import UnderscoreToCamelcase
from .replica import ReplicaModel
from . import HandleHttpError


# pylint: disable=too-many-instance-attributes
class DataFileModel(object):
    """
    Model class for MyTardis API v1's DataFileResource.
    See: https://github.com/mytardis/mytardis/blob/3.7/tardis/tardis_portal/api.py
    """
    def __init__(self, settingsModel, dataset, dataFileJson):
        self.settingsModel = settingsModel
        self.json = dataFileJson
        self.datafileId = None
        self.filename = None
        self.directory = None
        self.size = None
        self.createdTime = None
        self.modificationTime = None
        self.mimetype = None
        self.md5sum = None
        self.sha512sum = None
        self.deleted = None
        self.deletedTime = None
        self.version = None
        self.replicas = []
        self.parameterSets = []
        if dataFileJson is not None:
            for key in dataFileJson:
                attr = UnderscoreToCamelcase(key)
                if attr == "id":
                    attr = "datafileId"
                if hasattr(self, attr):
                    self.__dict__[attr] = dataFileJson[key]
            self.replicas = []
            for replicaJson in dataFileJson['replicas']:
                self.replicas.append(ReplicaModel(replicaJson=replicaJson))
        # This needs to go after self.__dict__[key] = dataFileJson[key]
        # so we get the full dataset model, not just the API resource string:
        self.dataset = dataset

    def GetId(self):
        """
        Returns datafile ID.
        """
        return self.datafileId

    def GetReplicas(self):
        """
        Get replicas.
        """
        return self.replicas

    def GetJson(self):
        """
        Return JSON representation.
        """
        return self.json

    def GetSize(self):
        """
        Returns size.
        """
        return self.size

    def GetMd5Sum(self):
        """
        Returns MD5 sum.
        """
        return self.md5sum

    @staticmethod
    def GetDataFile(settingsModel, dataset, filename, directory):
        """
        Lookup datafile by dataset, filename and directory.
        """
        myTardisUrl = settingsModel.general.myTardisUrl
        url = myTardisUrl + "/api/v1/mydata_dataset_file/?format=json" + \
            "&dataset__id=" + str(dataset.GetId()) + \
            "&filename=" + urllib.quote(filename.encode('utf-8')) + \
            "&directory=" + urllib.quote(directory.encode('utf-8'))
        response = requests.get(url=url, headers=settingsModel.defaultHeaders)
        if response.status_code < 200 or response.status_code >= 300:
            logger.debug("Failed to look up datafile \"%s\" "
                         "in dataset \"%s\"."
                         % (filename, dataset.GetDescription()))
            HandleHttpError(response)
        dataFilesJson = response.json()
        numDataFilesFound = dataFilesJson['meta']['total_count']
        if numDataFilesFound == 0:
            raise DoesNotExist(
                message="Datafile \"%s\" was not found in MyTardis" % filename,
                response=response)
        elif numDataFilesFound > 1:
            raise MultipleObjectsReturned(
                message="Multiple datafiles matching %s were found in MyTardis"
                % filename,
                response=response)
        else:
            return DataFileModel(
                settingsModel=settingsModel,
                dataset=dataset,
                dataFileJson=dataFilesJson['objects'][0])

    @staticmethod
    def GetDataFileFromId(settingsModel, dataFileId):
        """
        Lookup datafile by ID.
        """
        myTardisUrl = settingsModel.general.myTardisUrl
        url = "%s/api/v1/mydata_dataset_file/%s/?format=json" \
            % (myTardisUrl, dataFileId)
        response = requests.get(url=url, headers=settingsModel.defaultHeaders)
        if response.status_code == 404:
            raise DoesNotExist(
                message="Datafile ID \"%s\" was not found in MyTardis" % dataFileId,
                response=response)
        elif response.status_code < 200 or response.status_code >= 300:
            logger.debug("Failed to look up datafile ID \"%s\"." % dataFileId)
            HandleHttpError(response)
        dataFileJson = response.json()
        return DataFileModel(
            settingsModel=settingsModel,
            dataset=None,
            dataFileJson=dataFileJson)

    @staticmethod
    def Verify(settingsModel, datafileId):
        """
        Verify a datafile via the MyTardis API.
        """
        myTardisUrl = settingsModel.general.myTardisUrl
        url = myTardisUrl + "/api/v1/dataset_file/%s/verify/" % datafileId
        response = requests.get(url=url, headers=settingsModel.defaultHeaders)
        if response.status_code < 200 or response.status_code >= 300:
            logger.warning("Failed to verify datafile id \"%s\" " % datafileId)
            logger.warning(response.text)
        # Returning True doesn't mean that the file has been verified.
        # It just means that the MyTardis API has accepted our verification
        # request without raising an error.  The verification is asynchronous
        # so it might not happen immediately if there is congestion in the
        # Celery queue.
        return True

    @staticmethod
    def CreateDataFileForStagingUpload(settingsModel, dataFileDict):
        """
        Create a DataFile record and return a temporary URL to upload
        to (e.g. by SCP).
        """
        myTardisUrl = settingsModel.general.myTardisUrl
        url = myTardisUrl + "/api/v1/mydata_dataset_file/"
        dataFileJson = json.dumps(dataFileDict)
        response = requests.post(headers=settingsModel.defaultHeaders,
                                 url=url, data=dataFileJson)
        return response

    @staticmethod
    def UploadDataFileWithPost(settingsModel, dataFilePath, dataFileDict,
                               uploadsModel, uploadModel, posterCallback):
        """
        Upload a file to the MyTardis API via POST, creating a new
        DataFile record.
        """
        # pylint: disable=too-many-locals
        myTardisUsername = settingsModel.general.username
        myTardisApiKey = settingsModel.general.apiKey
        myTardisUrl = settingsModel.general.myTardisUrl
        url = myTardisUrl + "/api/v1/dataset_file/"
        message = "Initializing buffered reader..."
        uploadsModel.SetMessage(uploadModel, message)
        datafileBufferedReader = io.open(dataFilePath, 'rb')
        uploadModel.SetBufferedReader(datafileBufferedReader)

        datagen, headers = poster.encode.multipart_encode(
            {"json_data": json.dumps(dataFileDict),
             "attached_file": datafileBufferedReader},
            cb=posterCallback)
        opener = poster.streaminghttp.register_openers()
        opener.addheaders = [("Authorization", "ApiKey " +
                              myTardisUsername +
                              ":" + myTardisApiKey),
                             ("Content-Type", "application/json"),
                             ("Accept", "application/json")]
        request = urllib2.Request(url, datagen, headers)
        response = urllib2.urlopen(request)
        return response
