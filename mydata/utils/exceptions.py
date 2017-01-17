"""
Custom exceptions to raise within MyData.
"""


class DuplicateKey(Exception):
    """
    Duplicate key exception.
    """
    def __init__(self, message):
        super(DuplicateKey, self).__init__(message)


class HttpException(Exception):
    """
    Base class for deriving HTTP related exception classes from.
    """
    def __init__(self, message, response=None):
        super(HttpException, self).__init__(message)
        self.response = response

    def GetResponse(self):
        """
        Returns response
        """
        return self.response


class MultipleObjectsReturned(Exception):
    """
    Multiple objects returned exception.
    """
    def __init__(self, message, response=None):
        super(MultipleObjectsReturned, self).__init__(message)
        self.response = response

    def GetResponse(self):
        """
        Returns response
        """
        return self.response


class DoesNotExist(Exception):
    """
    Does not exist exception.
    """
    def __init__(self, message, response=None, modelClass=None):
        super(DoesNotExist, self).__init__(message)
        self.response = response
        self.modelClass = modelClass

    def GetResponse(self):
        """
        Returns response
        """
        return self.response

    def GetModelClass(self):
        """
        Returns model class.
        """
        return self.modelClass


class Unauthorized(HttpException):
    """
    Unauthorized exception.
    """
    def __init__(self, message, response=None):
        super(Unauthorized, self).__init__(message, response)


class InternalServerError(HttpException):
    """
    Internal server exception.
    """
    def __init__(self, message, response=None):
        super(InternalServerError, self).__init__(message, response)


class BadGateway(HttpException):
    """
    BadGateway exception (HTTP status: 502).
    """
    def __init__(self, message, response=None):
        super(BadGateway, self).__init__(message, response)


class ServiceUnavailable(HttpException):
    """
    Service unavailable exception (HTTP status: 503).
    """
    def __init__(self, message, response=None):
        super(ServiceUnavailable, self).__init__(message, response)


class GatewayTimeout(HttpException):
    """
    Gateway timeout exception (HTTP status: 504).
    """
    def __init__(self, message, response=None):
        super(GatewayTimeout, self).__init__(message, response)


class SshException(Exception):
    """
    SSH exception.
    """
    def __init__(self, message, returncode=None):
        super(SshException, self).__init__(message)
        self.returncode = returncode


class ScpException(SshException):
    """
    SCP exception.
    """
    def __init__(self, message, command=None, returncode=None):
        super(ScpException, self).__init__(message)
        self.command = command
        self.returncode = returncode


class NoActiveNetworkInterface(Exception):
    """
    No active network interface exception.
    """
    def __init__(self, message):
        super(NoActiveNetworkInterface, self).__init__(message)


class BrokenPipe(Exception):
    """
    Broken pipe exception.
    """
    def __init__(self, message):
        super(BrokenPipe, self).__init__(message)


class PrivateKeyDoesNotExist(Exception):
    """
    Private key does not exist exception.
    """
    def __init__(self, message):
        super(PrivateKeyDoesNotExist, self).__init__(message)


class InvalidFolderStructure(Exception):
    """
    Invalid folder structure exception.
    """
    def __init__(self, message):
        super(InvalidFolderStructure, self).__init__(message)


class MissingMyDataAppOnMyTardisServer(Exception):
    """
    Missing MyData app on MyTardis server exception.
    """
    def __init__(self, message):
        super(MissingMyDataAppOnMyTardisServer, self).__init__(message)


class MissingMyDataReplicaApiEndpoint(Exception):
    """
    Missing /api/v1/mydata_replica/ endpoint on MyTardis server exception.
    """
    def __init__(self, message):
        super(MissingMyDataReplicaApiEndpoint, self).__init__(message)


class StorageBoxAttributeNotFound(Exception):
    """
    Storage box attribute not found exception.
    """
    def __init__(self, storageBox, key):
        message = "Key '%s' not found in attributes for storage box '%s'" \
            % (key, storageBox.GetName())
        super(StorageBoxAttributeNotFound, self).__init__(message)


class StorageBoxOptionNotFound(Exception):
    """
    Storage box option not found exception.
    """
    def __init__(self, storageBox, key):
        message = "Key '%s' not found in options for storage box '%s'" \
            % (key, storageBox.GetName())
        super(StorageBoxOptionNotFound, self).__init__(message)


class FileNotFoundOnStaging(Exception):
    """
    While attempting to measure how many bytes of an unverified file have been
    uploaded to staging, MyData determined that the file does not yet exist on
    staging.
    """
    def __init__(self, remoteFilePath):
        message = "No such file or directory: %s" % remoteFilePath
        super(FileNotFoundOnStaging, self).__init__(message)
