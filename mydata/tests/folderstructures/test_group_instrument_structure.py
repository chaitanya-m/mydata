"""
Test ability to scan the User Group / Instrument / Full Name / Dataset folder structure.
"""
import os
import unittest

import wx

from mydata.events import MYDATA_EVENTS
from mydata.models.settings import SettingsModel
from mydata.models.settings.validation import ValidateSettings
from mydata.models.settings.validation import CheckStructureAndCountDatasets
from mydata.dataviewmodels.folders import FoldersModel
from mydata.dataviewmodels.users import UsersModel
from mydata.dataviewmodels.groups import GroupsModel
from mydata.tests.utils import StartFakeMyTardisServer
from mydata.tests.utils import WaitForFakeMyTardisServerToStart


class ScanUserGroupInstrumentTester(unittest.TestCase):
    """
    Test ability to scan the User Group / Instrument / Full Name / Dataset folder structure.
    """
    def __init__(self, *args, **kwargs):
        super(ScanUserGroupInstrumentTester, self).__init__(*args, **kwargs)
        self.app = None
        self.frame = None
        self.httpd = None
        self.fakeMyTardisHost = "127.0.0.1"
        self.fakeMyTardisPort = None
        self.fakeMyTardisServerThread = None

    def setUp(self):
        self.app = wx.App()
        self.frame = wx.Frame(parent=None, id=wx.ID_ANY,
                              title='ScanUserGroupInstrumentTester')
        MYDATA_EVENTS.InitializeWithNotifyWindow(self.frame)
        self.fakeMyTardisHost, self.fakeMyTardisPort, self.httpd, \
            self.fakeMyTardisServerThread = StartFakeMyTardisServer()

    def tearDown(self):
        self.frame.Destroy()
        self.httpd.shutdown()
        self.fakeMyTardisServerThread.join()

    def test_scan_folders(self):
        """
        Test ability to scan the User Group / Instrument / Full Name / Dataset folder structure.
        """
        # pylint: disable=too-many-statements
        # pylint: disable=too-many-locals
        # pylint: disable=too-many-branches

        pathToTestConfig = os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "../testdata/testdataGroupInstrument.cfg")
        self.assertTrue(os.path.exists(pathToTestConfig))
        settingsModel = SettingsModel(pathToTestConfig)
        dataDirectory = os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "../testdata", "testdataGroupInstrument")
        self.assertTrue(os.path.exists(dataDirectory))
        settingsModel.general.dataDirectory = dataDirectory
        settingsModel.general.myTardisUrl = \
            "http://%s:%s" % (self.fakeMyTardisHost, self.fakeMyTardisPort)
        datasetCount = CheckStructureAndCountDatasets(settingsModel)
        self.assertEqual(datasetCount, 8)
        WaitForFakeMyTardisServerToStart(settingsModel.general.myTardisUrl)
        ValidateSettings(settingsModel)
        usersModel = UsersModel(settingsModel)
        groupsModel = GroupsModel(settingsModel)
        foldersModel = FoldersModel(usersModel, groupsModel, settingsModel)

        def IncrementProgressDialog():
            """
            Callback for ScanFolders.
            """
            pass

        def ShouldAbort():
            """
            Callback for ScanFolders.
            """
            return False

        foldersModel.ScanFolders(IncrementProgressDialog, ShouldAbort)
        self.assertEqual(sorted(groupsModel.GetValuesForColname("Full Name")),
                         ["TestFacility-Group1", "TestFacility-Group2"])

        folders = []
        for row in range(foldersModel.GetRowCount()):
            folders.append(foldersModel.GetFolderRecord(row).GetFolder())
        self.assertEqual(sorted(folders), [
            'Dataset 001', 'Dataset 002', 'Dataset 003', 'Dataset 004',
            'Dataset 005', 'Dataset 006', 'Dataset 007', 'Dataset 008'])

        numFiles = 0
        for row in range(foldersModel.GetRowCount()):
            numFiles += foldersModel.GetFolderRecord(row).GetNumFiles()
        self.assertEqual(numFiles, 8)
