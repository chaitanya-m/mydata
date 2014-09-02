import wx.dataview
import sqlite3
from UploadModel import UploadModel
from UploadModel import UploadStatus

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
# Our data is stored in a list of UploadModel objects.


class ColumnType:
    TEXT = 0
    BITMAP = 1
    PROGRESS = 2


class UploadsModel(wx.dataview.PyDataViewIndexListModel):
    def __init__(self, sqlitedb):

        self.sqlitedb = sqlitedb

        self.uploadsData = []

        wx.dataview.PyDataViewIndexListModel.__init__(self,
                                                      len(self.uploadsData))

        self.unfilteredUploadsData = self.uploadsData
        self.filteredUploadsData = list()
        self.filtered = False
        self.searchString = ""

        self.columnNames = ("Id", "Folder", "Subdirectory", "Filename",
                            "File Size", "Status", "Progress", "Message")
        self.columnKeys = ("id", "folder", "subdirectory", "filename",
                           "filesize", "status", "progress", "message")
        self.defaultColumnWidths = (40, 170, 170, 200, 75, 55, 100, 300)
        self.columnTypes = (ColumnType.TEXT, ColumnType.TEXT, ColumnType.TEXT,
                            ColumnType.TEXT, ColumnType.TEXT,
                            ColumnType.BITMAP, ColumnType.PROGRESS,
                            ColumnType.TEXT)

        # This is the largest ID value which has been used in this model.
        # It may no longer exist, i.e. if we delete the row with the
        # largest ID, we don't decrement the maximum ID.
        self.maxId = 0

        self.inProgressIcon = wx.Image('png-normal/icons16x16/Refresh.png',
                                       wx.BITMAP_TYPE_PNG).ConvertToBitmap()
        self.completedIcon = wx.Image('png-normal/icons16x16/Apply.png',
                                      wx.BITMAP_TYPE_PNG).ConvertToBitmap()
        self.failedIcon = wx.Image('png-normal/icons16x16/Delete.png',
                                   wx.BITMAP_TYPE_PNG).ConvertToBitmap()

    def Filter(self, searchString):
        self.searchString = searchString
        q = self.searchString.lower()
        if not self.filtered:
            # This only does a shallow copy:
            self.unfilteredUploadsData = list(self.uploadsData)

        for row in reversed(range(0, self.GetRowCount())):
            if q not in self.uploadsData[row].GetFilename().lower():
                self.filteredUploadsData.append(self.uploadsData[row])
                del self.uploadsData[row]
                # Notify the view(s) using this model that it has been removed
                self.RowDeleted(row)
                self.filtered = True

        for filteredRow in reversed(range(0, self.GetFilteredRowCount())):
            fud = self.filteredUploadsData[filteredRow]
            if q in fud.lower():
                # Model doesn't care about currently sorted column.
                # Always use ID.
                row = 0
                col = 0
                ascending = True
                while row < self.GetRowCount() and \
                        self.CompareUploadRecords(self.uploadsData[row],
                                                  fud, col, ascending) < 0:
                    row = row + 1

                if row == self.GetRowCount():
                    self.uploadsData.append(fud)
                    # Notify the view that it has been added
                    self.RowAppended()
                else:
                    self.uploadsData.insert(row, fud)
                    # Notify the view that it has been added
                    self.RowInserted(row)
                del self.filteredUploadsData[filteredRow]
                if self.GetFilteredRowCount() == 0:
                    self.filtered = False

    # All of our columns are strings.  If the model or the renderers
    # in the view are other types then that should be reflected here.
    def GetColumnType(self, col):
        if col == self.columnNames.index("Status"):
            return "wxBitmap"
        if col == self.columnNames.index("Progress"):
            return "long"
        return "string"

    # This method is called to provide the uploadsData object for a
    # particular row,col
    def GetValueByRow(self, row, col):
        if col == self.columnNames.index("Status"):
            icon = wx.NullBitmap
            if self.uploadsData[row].GetStatus() == UploadStatus.IN_PROGRESS:
                icon = self.inProgressIcon
            elif self.uploadsData[row].GetStatus() == UploadStatus.COMPLETED:
                icon = self.completedIcon
            elif self.uploadsData[row].GetStatus() == UploadStatus.FAILED:
                icon = self.failedIcon
            return icon
        columnKey = self.GetColumnKeyName(col)
        return self.uploadsData[row].GetValueForKey(columnKey)

    # This method is called to provide the uploadsData object for a
    # particular row,colname
    def GetValueForRowColname(self, row, colname):
        for col in range(0, self.GetColumnCount()):
            if self.GetColumnName(col) == colname:
                return self.GetValueByRow(row, col)
        return None

    def GetValuesForColname(self, colname):
        values = []
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

    def GetColumnType(self, col):
        return self.columnTypes[col]

    # Report how many rows this model provides data for.
    def GetRowCount(self):
        return len(self.uploadsData)

    # Report how many rows this model provides data for.
    def GetUnfilteredRowCount(self):
        return len(self.unfilteredUploadsData)

    # Report how many rows this model provides data for.
    def GetFilteredRowCount(self):
        return len(self.filteredUploadsData)

    # Report how many columns this model provides data for.
    def GetColumnCount(self):
        return len(self.columnNames)

    # Report the number of rows in the model
    def GetCount(self):
        return len(self.uploadsData)

    # Called to check if non-standard attributes should be used in the
    # cell at (row, col)
    def GetAttrByRow(self, row, col, attr):
        return False

    # This is called to assist with sorting the data in the view.  The
    # first two args are instances of the DataViewItem class, so we
    # need to convert them to row numbers with the GetRow method.
    # Then it's just a matter of fetching the right values from our
    # data set and comparing them.  The return value is -1, 0, or 1,
    # just like Python's cmp() function.
    def Compare(self, item1, item2, col, ascending):
        if not ascending:
            item2, item1 = item1, item2
        row1 = self.GetRow(item1)
        row2 = self.GetRow(item2)
        if col == 0:
            return cmp(int(self.GetValueByRow(row1, col)),
                       int(self.GetValueByRow(row2, col)))
        else:
            return cmp(self.GetValueByRow(row1, col),
                       self.GetValueByRow(row2, col))

    # Unlike the previous Compare method, in this case,
    # the upload records don't need
    # to be visible in the current (possibly filtered) data view.
    def CompareUploadRecords(self, uploadRecord1, uploadRecord2, col,
                             ascending):
        if not ascending:
            uploadRecord2, uploadRecord1 = uploadRecord1, uploadRecord2
        if col == 0 or col == 3:
            return cmp(int(uploadRecord1.GetId()), int(uploadRecord2.GetId()))
        else:
            return cmp(uploadRecord1.GetValueForKey(self.columnKeys[col]),
                       uploadRecord2.GetValueForKey(self.columnKeys[col]))

    def DeleteRows(self, rows):

        # Ensure that we save the largest ID used so far:
        self.GetMaxId()

        # make a copy since we'll be sorting(mutating) the list
        rows = list(rows)
        # use reverse order so the indexes don't change as we remove items
        rows.sort(reverse=True)

        for row in rows:
            del self.uploadsData[row]
            # Notify the view(s) using this model that it has been removed
            self.RowDeleted(row)

    def DeleteUpload(self, folderModel, dataFileIndex):

        # Ensure that we save the largest ID used so far:
        self.GetMaxId()

        for row in range(0, self.GetRowCount()):
            if self.uploadsData[row].GetFolderModel() == folderModel and \
                    self.uploadsData[row].GetDataFileIndex() == dataFileIndex:
                del self.uploadsData[row]
                # Notify the view(s) using this model that it has been removed
                self.RowDeleted(row)
                return

    def Contains(self, filename):
        for row in range(0, self.GetCount()):
            if self.uploadsData[row].GetFilename().strip() == name:
                return True
        return False

    def GetUploadById(self, id):
        for row in range(0, self.GetRowCount()):
            if self.unfilteredUploadsData[row].GetId() == id:
                return self.unfilteredUploadsData[row]
        return None

    def GetUploadByFilename(self, filename):
        for row in range(0, self.GetRowCount()):
            if self.unfilteredUploadsData[row].GetFilename() == filename:
                return self.unfilteredUploadsData[row]
        return None

    def GetMaxIdFromExistingRows(self):
        maxId = 0
        for row in range(0, self.GetCount()):
            if self.uploadsData[row].GetId() > maxId:
                maxId = self.uploadsData[row].GetId()
        return maxId

    def GetMaxId(self):
        if self.GetMaxIdFromExistingRows() > self.maxId:
            self.maxId = self.GetMaxIdFromExistingRows()
        return self.maxId

    def AddRow(self, value):
        self.uploadsData.append(value)
        # Notify views
        self.RowAppended()

    def UploadFileSizeUpdated(self, uploadModel):
        for row in range(0, self.GetCount()):
            if self.uploadsData[row] == uploadModel:
                col = self.columnNames.index("File Size")
                self.RowValueChanged(row, col)

    def UploadProgressUpdated(self, uploadModel):
        for row in range(0, self.GetCount()):
            if self.uploadsData[row] == uploadModel:
                col = self.columnNames.index("Progress")
                self.RowValueChanged(row, col)

    def UploadStatusUpdated(self, uploadModel):
        for row in range(0, self.GetCount()):
            if self.uploadsData[row] == uploadModel:
                col = self.columnNames.index("Status")
                self.RowValueChanged(row, col)

    def UploadMessageUpdated(self, uploadModel):
        for row in range(0, self.GetCount()):
            if self.uploadsData[row] == uploadModel:
                col = self.columnNames.index("Message")
                self.RowValueChanged(row, col)

    def CancelAll(self):
        for row in range(0, self.GetCount()):
            self.uploadsData[row].Cancel()