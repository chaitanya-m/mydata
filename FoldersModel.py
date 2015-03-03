import wx
import wx.dataview
from FolderModel import FolderModel
from UserModel import UserModel
from GroupModel import GroupModel
from ExperimentModel import ExperimentModel
import threading
import os
import sys
import traceback
from datetime import datetime

from logger.Logger import logger
from Exceptions import InvalidFolderStructure
from Exceptions import DoesNotExist


# This model class provides the data to the view when it is asked for.
# Since it is a list-only model (no hierachical data) then it is able
# to be referenced by row rather than by item object, so in this way
# it is easier to comprehend and use than other model types.  In this
# example we also provide a Compare function to assist with sorting of
# items in our model.  Notice that the data items in the data model
# object don't ever change position due to a sort or column
# reordering.  The view manages all of that and maps view rows and
# columns to the model's rows and columns as needed.
#
# Our data is stored in a list of FolderModel objects.


class FoldersModel(wx.dataview.PyDataViewIndexListModel):
    def __init__(self, usersModel, groupsModel, settingsModel):

        self.foldersData = []

        # Earlier prototypes loaded the last used folder view from an Sqlite
        # database on disk, recording the folders which the user had
        # previously dragged and dropped into the application.  Whereas now
        # it scans the root data directory and constructs the folder list from
        # scratch every time.

        wx.dataview.PyDataViewIndexListModel.__init__(self,
                                                      len(self.foldersData))

        self.usersModel = usersModel
        self.groupsModel = groupsModel
        self.settingsModel = settingsModel

        # Unfiltered folders data:
        self.ufd = self.foldersData
        # Filtered folders data:
        self.ffd = list()
        self.filtered = False
        self.searchString = ""

        self.columnNames = ("Id", "Folder (dataset)", "Location", "Created",
                            "Experiment", "Status", "Owner", "Group")
        self.columnKeys = ("dataViewId", "folder", "location", "created",
                           "experimentTitle", "status",
                           "owner.username", "group.shortName")

        if sys.platform.startswith("win"):
            self.defaultColumnWidths = (40, 185, 200, 80, 150, 160, 90, 150)
        else:
            self.defaultColumnWidths = (40, 185, 200, 80, 160, 160, 90, 150)

        # This is the largest ID value which has been used in this model.
        # It may no longer exist, i.e. if we delete the row with the
        # largest ID, we don't decrement the maximum ID.
        self.maxDataViewId = 0

    def DeleteAllRows(self):
        rowsDeleted = []
        for row in reversed(range(0, self.GetCount())):
            del self.foldersData[row]
            rowsDeleted.append(row)

        if threading.current_thread().name == "MainThread":
            self.RowsDeleted(rowsDeleted)
        else:
            wx.CallAfter(self.RowsDeleted, rowsDeleted)

        self.ufd = list()
        self.ffd = list()
        self.filtered = False
        self.searchString = ""
        self.maxDataViewId = 0

    def GetFolderRecord(self, row):
        return self.foldersData[row]

    def CleanUp(self):
        logger.debug("Joining FoldersModel's UploadDataThread...")
        self.uploadDataThread.join()
        logger.debug("Joined FoldersModel's UploadDataThread.")

        logger.debug("Cleaning up each FolderModel record's threads...")
        for row in range(0, self.GetRowCount()):
            self.foldersData[row].CleanUp()
        logger.debug("Cleaned up each FolderModel record's threads...")

    def GetSettingsModel(self):
        return self.settingsModel

    def Filter(self, searchString):
        self.searchString = searchString
        q = self.searchString.lower()
        if not self.filtered:
            # This only does a shallow copy:
            self.ufd = list(self.foldersData)

        for row in reversed(range(0, self.GetRowCount())):
            fd = self.foldersData[row]
            if q not in fd.GetFolder().lower() and \
                    q not in fd.GetLocation().lower() and \
                    q not in fd.GetOwner().GetUsername().lower() and \
                    q not in fd.GetExperimentTitle():
                self.ffd.append(fd)
                del self.foldersData[row]
                # Notify the view(s) using this model that it has been removed
                if threading.current_thread().name == "MainThread":
                    self.RowDeleted(row)
                else:
                    wx.CallAfter(self.RowDeleted, row)
                self.filtered = True

        for filteredRow in reversed(range(0, self.GetFilteredRowCount())):
            ffd = self.ffd[filteredRow]
            if q in ffd.GetFolder().lower() or \
                    q in ffd.GetLocation().lower() or \
                    q in ffd.GetOwner().GetUsername().lower() or \
                    q in ffd.GetExperimentTitle():
                # Model doesn't care about currently sorted column.
                # Always use ID.
                row = 0
                col = 0
                ascending = True  # Need to get current sort direction
                while row < self.GetRowCount() and \
                        self.CompareFolderRecords(
                            self.foldersData[row],
                            self.ffd[filteredRow],
                            col, ascending) < 0:
                    row = row + 1

                if row == self.GetRowCount():
                    self.foldersData\
                        .append(self.ffd[filteredRow])
                    # Notify the view(s) using this model
                    # that it has been added
                    if threading.current_thread().name == "MainThread":
                        self.RowAppended()
                    else:
                        wx.CallAfter(self.RowAppended)
                else:
                    self.foldersData.insert(
                        row, self.ffd[filteredRow])
                    # Notify the view(s) using this model
                    # that it has been added
                    if threading.current_thread().name == "MainThread":
                        self.RowInserted(row)
                    else:
                        wx.CallAfter(self.RowInserted)
                del self.ffd[filteredRow]
                if self.GetFilteredRowCount() == 0:
                    self.filtered = False

    # All of our columns are strings.  If the model or the renderers
    # in the view are other types then that should be reflected here.
    def GetColumnType(self, col):
        return "string"

    # This method is called to provide the foldersData object for a
    # particular row,col
    def GetValueByRow(self, row, col):
        columnKey = self.GetColumnKeyName(col)
        if columnKey.startswith("owner."):
            ownerKey = columnKey.split("owner.")[1]
            owner = self.foldersData[row].GetOwner()
            if owner is not None:
                return owner.GetValueForKey(ownerKey)
            else:
                return ""
        elif columnKey.startswith("group."):
            groupKey = columnKey.split("group.")[1]
            group = self.foldersData[row].GetGroup()
            if group is not None:
                return group.GetValueForKey(groupKey)
            else:
                return ""
        return str(self.foldersData[row].GetValueForKey(columnKey))

    # This method is called to provide the foldersData object for a
    # particular row,colname
    def GetValueForRowColname(self, row, colname):
        for col in range(0, self.GetColumnCount()):
            if self.GetColumnName(col) == colname:
                return self.GetValueByRow(row, col)
        return None

    def GetColumnName(self, col):
        return self.columnNames[col]

    def GetColumnKeyName(self, col):
        return self.columnKeys[col]

    def GetDefaultColumnWidth(self, col):
        return self.defaultColumnWidths[col]

    def GetFolderPath(self, row):
        import os
        return os.path.join(self.foldersData[row].GetLocation(),
                            self.foldersData[row].GetFolder())

    # Report how many rows this model provides data for.
    def GetRowCount(self):
        return len(self.foldersData)

    # Report how many rows this model provides data for.
    def GetUnfilteredRowCount(self):
        return len(self.ufd)

    # Report how many rows this model provides data for.
    def GetFilteredRowCount(self):
        return len(self.ffd)

    # Report how many columns this model provides data for.
    def GetColumnCount(self):
        return len(self.columnNames)

    # Report the number of rows in the model
    def GetCount(self):
        return len(self.foldersData)

    # Called to check if non-standard attributes should be used in the
    # cell at (row, col)
    def GetAttrByRow(self, row, col, attr):
        if col == 4:
            attr.SetColour('blue')
            attr.SetBold(True)
            return True
        return False

    # This is called to assist with sorting the data in the view.  The
    # first two args are instances of the DataViewItem class, so we
    # need to convert them to row numbers with the GetRow method.
    # Then it's just a matter of fetching the right values from our
    # data set and comparing them.  The return value is -1, 0, or 1,
    # just like Python's cmp() function.
    def Compare(self, item1, item2, col, ascending):
        if not ascending:  # swap sort order?
            item2, item1 = item1, item2
        row1 = self.GetRow(item1)
        row2 = self.GetRow(item2)
        if col == 0:
            return cmp(int(self.GetValueByRow(row1, col)),
                       int(self.GetValueByRow(row2, col)))
        else:
            return cmp(self.GetValueByRow(row1, col),
                       self.GetValueByRow(row2, col))

    # Unlike the previous Compare method, in this case, the folder records
    # don't need to be visible in the current (possibly filtered) data view.
    def CompareFolderRecords(self, folderRecord1, folderRecord2,
                             col, ascending):
        if not ascending:  # swap sort order?
            folderRecord2, folderRecord1 = folderRecord1, folderRecord2
        if col == 0 or col == 3:
            return cmp(int(folderRecord1.GetDataViewId()),
                       int(folderRecord2.GetDataViewId()))
        else:
            return cmp(folderRecord1.GetValueForKey(self.columnKeys[col]),
                       folderRecord2.GetValueForKey(self.columnKeys[col]))

    def DeleteRows(self, rows):
        # Ensure that we save the largest ID used so far:
        self.GetMaxDataViewId()

        # make a copy since we'll be sorting(mutating) the list
        rows = list(rows)
        # use reverse order so the indexes don't change as we remove items
        rows.sort(reverse=True)

        for row in rows:
            del self.foldersData[row]
            del self.ufd[row]
            # Notify the view(s) using this model that it has been removed
            if threading.current_thread().name == "MainThread":
                self.RowDeleted(row)
            else:
                wx.CallAfter(self.RowDeleted, row)

    def DeleteFolderById(self, id):
        # Ensure that we save the largest ID used so far:
        self.GetMaxDataViewId()

        for row in range(0, self.GetRowCount()):
            if self.foldersData[row].GetId() == id:
                del self.foldersData[row]
                # notify the view(s) using this model that it has been removed
                if threading.current_thread().name == "MainThread":
                    self.RowDeleted(row)
                else:
                    wx.CallAfter(self.RowDeleted, row)
                return

    def Contains(self, path):
        import os
        from Win32SamePath import Win32SamePath
        win32SamePath = Win32SamePath()
        dir1 = path
        for row in range(0, self.GetCount()):

            dir2 = self.GetFolderPath(row)
            if win32SamePath.paths_are_equal(dir1, dir2):
                return True
        return False

    def GetMaxDataViewIdFromExistingRows(self):
        maxDataViewId = 0
        for row in range(0, self.GetCount()):
            if self.foldersData[row].GetDataViewId() > maxDataViewId:
                maxDataViewId = self.foldersData[row].GetDataViewId()
        return maxDataViewId

    def GetMaxDataViewId(self):
        if self.GetMaxDataViewIdFromExistingRows() > self.maxDataViewId:
            self.maxDataViewId = self.GetMaxDataViewIdFromExistingRows()
        return self.maxDataViewId

    def AddRow(self, value):
        self.Filter("")
        self.foldersData.append(value)
        # Notify views
        if threading.current_thread().name == "MainThread":
            self.RowAppended()
        else:
            wx.CallAfter(self.RowAppended)

        self.ufd = self.foldersData
        self.ffd = list()
        self.Filter(self.searchString)

    def FolderStatusUpdated(self, folderModel):
        for row in range(0, self.GetCount()):
            if self.foldersData[row] == folderModel:
                col = self.columnNames.index("Status")
                if threading.current_thread().name == "MainThread":
                    self.RowValueChanged(row, col)
                else:
                    wx.CallAfter(self.RowValueChanged, row, col)

    def Refresh(self, incrementProgressDialog, shouldAbort):
        if self.GetCount() > 0:
            self.DeleteAllRows()
        if self.usersModel.GetCount() > 0:
            self.usersModel.DeleteAllRows()
        if self.groupsModel.GetCount() > 0:
            self.groupsModel.DeleteAllRows()
        dataDir = self.settingsModel.GetDataDirectory()
        folderStructure = self.settingsModel.GetFolderStructure()
        self.ignoreOldDatasets = self.settingsModel.IgnoreOldDatasets()
        if self.ignoreOldDatasets:
            seconds = {}
            seconds['day'] = 24 * 60 * 60
            seconds['week'] = 7 * seconds['day']
            seconds['year'] = int(365.25 * seconds['day'])
            seconds['month'] = seconds['year'] / 12
            singularIgnoreIntervalUnit = \
                self.settingsModel.GetIgnoreOldDatasetIntervalUnit().rstrip('s')
            ignoreIntervalUnitSeconds = seconds[singularIgnoreIntervalUnit]

            self.ignoreIntervalNumber = \
                self.settingsModel.GetIgnoreOldDatasetIntervalNumber()
            self.ignoreIntervalUnit = \
                self.settingsModel.GetIgnoreOldDatasetIntervalUnit()
            self.ignoreIntervalSeconds = \
                self.ignoreIntervalNumber * ignoreIntervalUnitSeconds
        logger.debug("FoldersModel.Refresh(): Scanning " + dataDir + "...")
        if folderStructure.startswith("Username") or \
                folderStructure.startswith("Email"):
            self.ScanForUserFolders(incrementProgressDialog, shouldAbort)
        elif folderStructure.startswith("User Group"):
            self.ScanForGroupFolders(incrementProgressDialog, shouldAbort)
        else:
            raise InvalidFolderStructure("Unknown folder structure.")

    def ScanForUserFolders(self, incrementProgressDialog, shouldAbort):
        dataDir = self.settingsModel.GetDataDirectory()
        folderStructure = self.settingsModel.GetFolderStructure()
        userFolderNames = os.walk(dataDir).next()[1]
        for userFolderName in userFolderNames:
            if shouldAbort():
                wx.CallAfter(wx.GetApp().GetMainFrame().SetStatusMessage,
                             "Data uploads canceled")
                return
            if folderStructure.startswith("Username"):
                logger.debug("Found folder assumed to be username: " +
                             userFolderName)
            elif folderStructure.startswith("Email"):
                logger.debug("Found folder assumed to be email: " +
                             userFolderName)
            usersDataViewId = self.usersModel.GetMaxDataViewId() + 1
            try:
                if folderStructure.startswith("Username"):
                    userRecord = \
                        UserModel.GetUserByUsername(self.settingsModel,
                                                    userFolderName)
                elif folderStructure.startswith("Email"):
                    userRecord = \
                        UserModel.GetUserByEmail(self.settingsModel,
                                                 userFolderName)

            except DoesNotExist:
                userRecord = None
            if shouldAbort():
                wx.CallAfter(wx.GetApp().GetMainFrame().SetStatusMessage,
                             "Data uploads canceled")
                return
            if userRecord is not None:
                userRecord.SetDataViewId(usersDataViewId)
                self.usersModel.AddRow(userRecord)
                self.ImportUserFolders(os.path.join(dataDir,
                                                    userFolderName),
                                       userRecord)
                if shouldAbort():
                    wx.CallAfter(wx.GetApp().GetMainFrame()
                                 .SetStatusMessage,
                                 "Data uploads canceled")
                    return
            else:
                message = "Didn't find a MyTardis user record for folder " \
                    "\"%s\" in %s" % (userFolderName, dataDir)
                logger.warning(message)
                if shouldAbort():
                    wx.CallAfter(wx.GetApp().GetMainFrame().SetStatusMessage,
                                 "Data uploads canceled")
                    return
                userRecord = UserModel(settingsModel=self.settingsModel,
                                       username=userFolderName,
                                       name="USER NOT FOUND IN MYTARDIS",
                                       email="USER NOT FOUND IN MYTARDIS")
                userRecord.SetDataViewId(usersDataViewId)
                self.usersModel.AddRow(userRecord)
                if shouldAbort():
                    wx.CallAfter(wx.GetApp().GetMainFrame().SetStatusMessage,
                                 "Data uploads canceled")
                    return
                self.ImportUserFolders(os.path.join(dataDir,
                                                    userFolderName),
                                       userRecord)
            if threading.current_thread().name == "MainThread":
                incrementProgressDialog()
            else:
                wx.CallAfter(incrementProgressDialog)

    def ScanForGroupFolders(self, incrementProgressDialog, shouldAbort):
        dataDir = self.settingsModel.GetDataDirectory()
        groupFolderNames = os.walk(dataDir).next()[1]
        for groupFolderName in groupFolderNames:
            if shouldAbort():
                wx.CallAfter(wx.GetApp().GetMainFrame().SetStatusMessage,
                             "Data uploads canceled")
                return
            logger.debug("Found folder assumed to be user group name: " +
                         groupFolderName)
            groupsDataViewId = self.groupsModel.GetMaxDataViewId() + 1
            try:
                groupName = self.settingsModel.GetGroupPrefix() + \
                    groupFolderName
                groupRecord = \
                    GroupModel.GetGroupByName(self.settingsModel,
                                              groupName)
            except DoesNotExist:
                groupRecord = None
            if shouldAbort():
                wx.CallAfter(wx.GetApp().GetMainFrame().SetStatusMessage,
                             "Data uploads canceled")
                return
            if groupRecord is not None:
                groupRecord.SetDataViewId(groupsDataViewId)
                self.groupsModel.AddRow(groupRecord)
                self.ImportGroupFolders(os.path.join(dataDir,
                                                     groupFolderName),
                                        groupRecord)
                if shouldAbort():
                    wx.CallAfter(wx.GetApp().GetMainFrame().SetStatusMessage,
                                 "Data uploads canceled")
                    return
            else:
                message = "Didn't find a MyTardis user group record for " \
                    "folder \"%s\" in %s" % (groupFolderName,
                                             dataDir)
                logger.warning(message)
                if not self.settingsModel.RunningInBackgroundMode():
                    raise InvalidFolderStructure(message)
            if threading.current_thread().name == "MainThread":
                incrementProgressDialog()
            else:
                wx.CallAfter(incrementProgressDialog)

    def ImportUserFolders(self, userFolderPath, owner):
        try:
            folderStructure = self.settingsModel.GetFolderStructure()
            if folderStructure == 'Username / Dataset' or \
                    folderStructure == 'Email / Dataset':
                logger.debug("Scanning " + userFolderPath +
                             " for dataset folders...")
                datasetFolders = os.walk(userFolderPath).next()[1]
                for datasetFolderName in datasetFolders:
                    if datasetFolderName.lower() == 'mytardis':
                        mytardisFolderName = datasetFolderName
                        logger.debug("Found '%s' folder in %s folder."
                                     % (mytardisFolderName, userFolderPath))
                        mytardisFolderPath = os.path.join(userFolderPath,
                                                          mytardisFolderName)
                        self.ImportFoldersUsingSpecialSchema(mytardisFolderPath,
                                                             owner)
                    else:
                        if self.ignoreOldDatasets:
                            datasetFolderPath = os.path.join(userFolderPath,
                                                             datasetFolderName)
                            ctimestamp = os.path.getctime(datasetFolderPath)
                            ctime = datetime.fromtimestamp(ctimestamp)
                            age = datetime.now() - ctime
                            if age.total_seconds() > \
                                    self.ignoreIntervalSeconds:
                                message = "Ignoring \"%s\", because it is " \
                                    "older than %d %s" \
                                    % (datasetFolderPath,
                                       self.ignoreIntervalNumber,
                                       self.ignoreIntervalUnit)
                                logger.warning(message)
                                continue
                        dataViewId = self.GetMaxDataViewId() + 1
                        folderModel = \
                            FolderModel(dataViewId=dataViewId,
                                        folder=datasetFolderName,
                                        location=userFolderPath,
                                        folder_type='Dataset',
                                        owner=owner,
                                        foldersModel=self,
                                        usersModel=self.usersModel,
                                        settingsModel=self.settingsModel)
                        folderModel.SetCreatedDate()
                        experimentTitle = "%s - %s" \
                            % (self.settingsModel.GetInstrumentName(),
                               owner.GetName())
                        folderModel.SetExperimentTitle(experimentTitle)
                        self.AddRow(folderModel)
            elif folderStructure == \
                    'Username / "MyTardis" / Experiment / Dataset':
                logger.debug("Scanning " + userFolderPath +
                             " for a MyTardis folder...")
                folders = os.walk(userFolderPath).next()[1]
                foundMyTardisFolder = False
                for folderName in folders:
                    if folderName.lower() == 'mytardis':
                        foundMyTardisFolder = True
                        mytardisFolderName = folderName
                        logger.debug("Found '%s' folder in %s folder."
                                     % (mytardisFolderName, userFolderPath))
                        mytardisFolderPath = os.path.join(userFolderPath,
                                                          mytardisFolderName)
                        self.ImportFoldersUsingSpecialSchema(mytardisFolderPath,
                                                             owner)
                if not foundMyTardisFolder:
                    raise InvalidFolderStructure("MyTardis folder not found "
                                                 "in %s" % userFolderPath)
        except:
            print traceback.format_exc()

    def ImportFoldersUsingSpecialSchema(self, mytardisFolderPath, owner):
        """
        Instead of looking for dataset folders as direct children of
        the username folder, this method looks for dataset folders
        structured in the following format:
        <username>\mytardis\<experiment_title>\<dataset_name>

        """
        expFolders = os.walk(mytardisFolderPath).next()[1]
        for expFolderName in expFolders:
            expFolderPath = os.path.join(mytardisFolderPath, expFolderName)
            datasetFolders = os.walk(expFolderPath).next()[1]
            for datasetFolderName in datasetFolders:
                if self.ignoreOldDatasets:
                    datasetFolderPath = os.path.join(expFolderPath,
                                                     datasetFolderName)
                    ctimestamp = os.path.getctime(datasetFolderPath)
                    ctime = datetime.fromtimestamp(ctimestamp)
                    age = datetime.now() - ctime
                    if age.total_seconds() > self.ignoreIntervalSeconds:
                        message = "Ignoring \"%s\", because it is " \
                            "older than %d %s" \
                            % (datasetFolderPath, self.ignoreIntervalNumber,
                               self.ignoreIntervalUnit)
                        logger.warning(message)
                        continue
                dataViewId = self.GetMaxDataViewId() + 1
                folderModel = FolderModel(dataViewId=dataViewId,
                                          folder=datasetFolderName,
                                          location=expFolderPath,
                                          folder_type='Dataset',
                                          owner=owner,
                                          foldersModel=self,
                                          usersModel=self.usersModel,
                                          settingsModel=self.settingsModel)
                folderModel.SetCreatedDate()
                folderModel.SetExperimentTitle(expFolderName)
                self.AddRow(folderModel)

    def ImportGroupFolders(self, groupFolderPath, groupModel):
        try:
            logger.debug("Scanning " + groupFolderPath +
                         " for instrument folders...")
            instrumentFolders = os.walk(groupFolderPath).next()[1]

            if len(instrumentFolders) > 1:
                message = "Multiple instrument folders found in %s" \
                    % groupFolderPath
                logger.error(message)
                raise InvalidFolderStructure(message=message)
            elif len(instrumentFolders) == 0:
                message = "No instrument folder was found in %s" \
                    % groupFolderPath
                logger.error(message)
                raise InvalidFolderStructure(message=message)
            elif instrumentFolders[0] != \
                    self.settingsModel.GetInstrumentName():
                message = "Instrument folder name \"%s\" doesn't match " \
                    "instrument name \"%s\" in MyData Settings in \"%s\"." \
                    % (instrumentFolders[0],
                       self.settingsModel.GetInstrumentName(),
                       groupFolderPath)
                logger.warning(message)
                # raise InvalidFolderStructure(message=message)

            instrumentFolderPath = os.path.join(groupFolderPath,
                                                instrumentFolders[0])

            defaultOwner = self.settingsModel.GetDefaultOwner()

            logger.debug("Scanning " + instrumentFolderPath +
                         " for user folders...")
            userFolders = os.walk(instrumentFolderPath).next()[1]
            for userFolderName in userFolders:
                userFolderPath = os.path.join(instrumentFolderPath,
                                              userFolderName)
                owner = defaultOwner
                try:
                    owner = UserModel.GetUserByUsername(self.settingsModel,
                                                        userFolderName)
                except DoesNotExist:
                    owner = defaultOwner
                logger.debug("Scanning " + userFolderPath +
                             " for dataset folders...")
                datasetFolders = os.walk(userFolderPath).next()[1]
                for datasetFolderName in datasetFolders:
                    if self.ignoreOldDatasets:
                        datasetFolderPath = os.path.join(userFolderPath,
                                                         datasetFolderName)
                        ctimestamp = os.path.getctime(datasetFolderPath)
                        ctime = datetime.fromtimestamp(ctimestamp)
                        age = datetime.now() - ctime
                        if age.total_seconds() > self.ignoreIntervalSeconds:
                            message = "Ignoring \"%s\", because it is " \
                                "older than %d %s" \
                                % (datasetFolderPath,
                                   self.ignoreIntervalNumber,
                                   self.ignoreIntervalUnit)
                            logger.warning(message)
                            continue
                    dataViewId = self.GetMaxDataViewId() + 1
                    folderModel = FolderModel(dataViewId=dataViewId,
                                              folder=datasetFolderName,
                                              location=userFolderPath,
                                              folder_type='Dataset',
                                              owner=owner,
                                              foldersModel=self,
                                              usersModel=self.usersModel,
                                              settingsModel=self.settingsModel)
                    folderModel.SetGroup(groupModel)
                    folderModel.SetCreatedDate()
                    folderModel.SetExperimentTitle("%s - %s" %
                                                   (instrumentFolders[0],
                                                    userFolderName))
                    self.AddRow(folderModel)
        except InvalidFolderStructure:
            raise
        except:
            logger.error(traceback.format_exc())
