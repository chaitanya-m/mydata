"""
Represents the Users tab of MyData's main window,
and the tabular data displayed on that tab view.
"""

# pylint: disable=missing-docstring

import os
import threading

import wx
if wx.version().startswith("3.0.3.dev"):
    from wx.dataview import DataViewIndexListModel  # pylint: disable=no-name-in-module
else:
    from wx.dataview import PyDataViewIndexListModel as DataViewIndexListModel


class UsersModel(DataViewIndexListModel):
    """
    Represents the Users tab of MyData's main window,
    and the tabular data displayed on that tab view.
    """
    # pylint: disable=too-many-public-methods
    # pylint: disable=too-many-instance-attributes
    def __init__(self, settingsModel):

        self.settingsModel = settingsModel
        self.foldersModel = None

        self.usersData = list()

        DataViewIndexListModel.__init__(self, len(self.usersData))

        self.unfilteredUsersData = self.usersData
        self.filteredUsersData = list()
        self.filtered = False
        self.searchString = ""

        self.columnNames = ("Id", "Username", "Name", "Email")
        self.columnKeys = ("dataViewId", "username", "name", "email")
        self.defaultColumnWidths = (40, 100, 200, 260)

        # This is the largest ID value which has been used in this model.
        # It may no longer exist, i.e. if we delete the row with the
        # largest ID, we don't decrement the maximum ID.
        self.maxDataViewId = 0

    def SetFoldersModel(self, foldersModel):
        self.foldersModel = foldersModel

    def Filter(self, searchString):
        # pylint: disable=too-many-branches
        self.searchString = searchString
        query = self.searchString.lower()
        if not self.filtered:
            # This only does a shallow copy:
            self.unfilteredUsersData = list(self.usersData)

        for row in reversed(range(0, self.GetRowCount())):
            if query not in self.usersData[row].GetUsername().lower() and \
                    query not in self.usersData[row].GetName().lower() and \
                    query not in self.usersData[row].GetEmail().lower():
                self.filteredUsersData.append(self.usersData[row])
                del self.usersData[row]
                # notify the view(s) using this model that it has been removed
                if threading.current_thread().name == "MainThread":
                    self.RowDeleted(row)
                else:
                    wx.CallAfter(self.RowDeleted, row)
                self.filtered = True

        for filteredRow in reversed(range(0, self.GetFilteredRowCount())):
            fud = self.filteredUsersData[filteredRow]
            if query in fud.GetName().lower() or \
                    query in fud.GetUsername().lower() or \
                    query in fud.GetEmail().lower():
                # Model doesn't care about currently sorted column.
                # Always use ID.
                row = 0
                col = 0
                # Need to get current sort direction
                ascending = True
                while row < self.GetRowCount() and \
                        self.Compare(self.usersData[row],
                                     fud, col, ascending) < 0:
                    row += 1

                if row == self.GetRowCount():
                    self.usersData.append(fud)
                    # Notify the view using this model that it has been added
                    if threading.current_thread().name == "MainThread":
                        self.RowAppended()
                    else:
                        wx.CallAfter(self.RowAppended)
                else:
                    self.usersData.insert(row, fud)
                    # Notify the view using this model that it has been added
                    if threading.current_thread().name == "MainThread":
                        self.RowInserted(row)
                    else:
                        wx.CallAfter(self.RowInserted, row)
                del self.filteredUsersData[filteredRow]
                if self.GetFilteredRowCount() == 0:
                    self.filtered = False

    def GetColumnType(self, col):
        """
        All of our columns are strings.  If the model or the renderers
        in the view are other types then that should be reflected here.
        """
        # pylint: disable=arguments-differ
        # pylint: disable=unused-argument
        # pylint: disable=no-self-use
        return "string"

    def GetValueByRow(self, row, col):
        """
        This method is called to provide the usersData object
        for a particular row, col
        """
        # pylint: disable=arguments-differ
        columnKey = self.GetColumnKeyName(col)
        return str(self.usersData[row].GetValueForKey(columnKey))

    def GetValuesForColname(self, colname):
        values = []
        col = -1
        for col in range(0, self.GetColumnCount()):
            if self.GetColumnName(col) == colname:
                break
        if col == self.GetColumnCount():
            return None

        for row in range(0, self.GetRowCount()):
            values.append(self.GetValueByRow(row, col))
        return values

    def GetColumnName(self, col):
        return self.columnNames[col]

    def GetColumnKeyName(self, col):
        return self.columnKeys[col]

    def GetDefaultColumnWidth(self, col):
        return self.defaultColumnWidths[col]

    def GetRowCount(self):
        """
        Report how many rows this model provides data for.
        """
        return len(self.usersData)

    def GetUnfilteredRowCount(self):
        return len(self.unfilteredUsersData)

    def GetFilteredRowCount(self):
        return len(self.filteredUsersData)

    def GetColumnCount(self):
        """
        Report how many columns this model provides data for.
        """
        # pylint: disable=arguments-differ
        return len(self.columnNames)

    def GetCount(self):
        """
        Report the number of rows in the model
        """
        # pylint: disable=arguments-differ
        return len(self.usersData)

    def GetAttrByRow(self, row, col, attr):
        """
        Called to check if non-standard attributes should be
        used in the cell at (row, col)
        """
        # pylint: disable=arguments-differ
        # pylint: disable=unused-argument
        # pylint: disable=no-self-use
        return False

    def Compare(self, userRecord1, userRecord2, col, ascending):
        """
        This is called to assist with sorting the data in the view.  The
        first two args are instances of the DataViewItem class, so we
        need to convert them to row numbers with the GetRow method.
        Then it's just a matter of fetching the right values from our
        data set and comparing them.  The return value is -1, 0, or 1,
        just like Python's cmp() function.
        """
        # pylint: disable=arguments-differ
        try:
            userRecord1 = self.usersData[self.GetRow(userRecord1)]
            userRecord2 = self.usersData[self.GetRow(userRecord2)]
        except TypeError:
            # Compare is also called by Filter in which case we
            # don't need to convert from DataViewItem to UserModel.
            pass
        if not ascending:
            userRecord2, userRecord1 = userRecord1, userRecord2
        if col == 0 or col == 3:
            return cmp(int(userRecord1.GetDataViewId()),
                       int(userRecord2.GetDataViewId()))
        else:
            return cmp(userRecord1.GetValueForKey(self.columnKeys[col]),
                       userRecord2.GetValueForKey(self.columnKeys[col]))

    def DeleteAllRows(self):
        """
        Delete all rows.
        """
        rowsDeleted = []
        for row in reversed(range(0, self.GetCount())):
            del self.usersData[row]
            rowsDeleted.append(row)

        # notify the view(s) using this model that it has been removed
        if threading.current_thread().name == "MainThread":
            self.RowsDeleted(rowsDeleted)
        else:
            wx.CallAfter(self.RowsDeleted, rowsDeleted)

        self.unfilteredUsersData = list()
        self.filteredUsersData = list()
        self.filtered = False
        self.searchString = ""
        self.maxDataViewId = 0

    def GetMaxDataViewIdFromExistingRows(self):
        maxDataViewId = 0
        for row in range(0, self.GetCount()):
            if self.usersData[row].GetDataViewId() > maxDataViewId:
                maxDataViewId = self.usersData[row].GetDataViewId()
        return maxDataViewId

    def GetMaxDataViewId(self):
        if self.GetMaxDataViewIdFromExistingRows() > self.maxDataViewId:
            self.maxDataViewId = self.GetMaxDataViewIdFromExistingRows()
        return self.maxDataViewId

    def AddRow(self, value):
        self.Filter("")
        self.usersData.append(value)
        # Notify views
        if threading.current_thread().name == "MainThread":
            self.RowAppended()
        else:
            wx.CallAfter(self.RowAppended)

        self.unfilteredUsersData = self.usersData
        self.filteredUsersData = list()
        self.Filter(self.searchString)

    def GetNumUserOrGroupFolders(self):
        dataDir = self.settingsModel.GetDataDirectory()
        userOrGroupFolderNames = os.walk(dataDir).next()[1]
        return len(userOrGroupFolderNames)
