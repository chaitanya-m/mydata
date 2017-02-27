"""
MyData classes can import DataViewIndexListModel from here, and automatically
get the right the module, which depends on the wxPython version.
"""
import threading
import traceback

import wx
if wx.version().startswith("3.0.3.dev"):
    from wx.dataview import DataViewIndexListModel  # pylint: disable=no-name-in-module
else:
    from wx.dataview import PyDataViewIndexListModel as DataViewIndexListModel

from ..logs import logger  # pylint: disable=wrong-import-position


class MyDataDataViewModel(DataViewIndexListModel):
    """
    Generic base class to inherit from
    """
    # pylint: disable=arguments-differ
    # pylint: disable=unused-argument
    # pylint: disable=no-self-use
    def __init__(self):
        super(MyDataDataViewModel, self).__init__()

        self.rowsData = list()

        self.columnNames = list()
        self.columnKeys = list()
        self.defaultColumnWidths = list()

        self.unfilteredData = list()
        self.filteredData = list()
        self.filtered = False
        self.searchString = ""

        # This is the largest ID value which has been used in this model.
        # It may no longer exist, i.e. if we delete the row with the
        # largest ID, we don't decrement the maximum ID.
        self.maxDataViewId = 0
        self.maxDataViewIdLock = threading.Lock()

    def GetColumnType(self, col):
        """
        All of our columns are strings.  If the model or the renderers
        in the view are other types then that should be reflected here.
        """
        return "string"

    def GetAttrByRow(self, row, col, attr):
        """
        Called to check if non-standard attributes should be
        used in the cell at (row, col)
        """
        return False

    def GetCount(self):
        """
        Report the number of rows in the model
        """
        return len(self.rowsData)

    def GetValueByRow(self, row, col):
        """
        This method is called to provide the rowsData object
        for a particular row, col
        """
        columnKey = self.GetColumnKeyName(col)
        return str(self.rowsData[row].GetValueForKey(columnKey))

    def GetValueForRowColumnKeyName(self, row, columnKeyName):
        """
        This method is called to provide the rowsData object for a
        particular row,columnKeyName
        """
        for col in range(0, self.GetColumnCount()):
            if self.GetColumnKeyName(col) == columnKeyName:
                return self.GetValueByRow(row, col)
        return None

    def GetValuesForColname(self, colname):
        """
        Get values for column name
        """
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
        """
        Get column name
        """
        return self.columnNames[col]

    def GetColumnKeyName(self, col):
        """
        Get column key name
        """
        return self.columnKeys[col]

    def GetDefaultColumnWidth(self, col):
        """
        Get default column width
        """
        return self.defaultColumnWidths[col]

    def GetRowCount(self):
        """
        Report how many rows this model provides data for.
        """
        return len(self.rowsData)

    def GetUnfilteredRowCount(self):
        """
        Report how many rows this model provides data for.
        """
        return len(self.unfilteredData)

    def GetFilteredRowCount(self):
        """
        Report how many rows this model provides data for,
        taking into account the filter query string.
        """
        return len(self.filteredData)

    def GetColumnCount(self):
        """
        Report how many columns this model provides data for.
        """
        return len(self.columnNames)

    def Filter(self, searchString):
        """
        Only show rows matching the query string, typed in the search box
        in the upper-right corner of the main window.
        """
        pass

    def AddRow(self, value):
        """
        Add a new row
        """
        self.Filter("")
        self.rowsData.append(value)
        # Notify views
        if threading.current_thread().name == "MainThread":
            self.RowAppended()
        else:
            wx.CallAfter(self.RowAppended)

        self.unfilteredData = self.rowsData
        self.filteredData = list()
        self.Filter(self.searchString)

        self.maxDataViewIdLock.acquire()
        self.maxDataViewId = value.dataViewId
        self.maxDataViewIdLock.release()

    def DeleteAllRows(self):
        """
        Delete all rows.
        """
        rowsDeleted = []
        for row in reversed(range(0, self.GetCount())):
            del self.rowsData[row]
            rowsDeleted.append(row)

        if threading.current_thread().name == "MainThread":
            self.RowsDeleted(rowsDeleted)
        else:
            wx.CallAfter(self.RowsDeleted, rowsDeleted)

        self.unfilteredData = list()
        self.filteredData = list()
        self.filtered = False
        self.searchString = ""
        self.maxDataViewId = 0

    def GetMaxDataViewId(self):
        """
        Get maximum dataview ID
        """
        return self.maxDataViewId

    def TryRowValueChanged(self, row, col):
        """
        Notify views of a change in value

        Use try/except when calling RowValueChanged, because
        sometimes there are timing issues which raise wx
        assertions suggesting that the row index we are trying
        to report a change on is greater than or equal to the
        total number of rows in the model.
        """
        try:
            if row < self.GetCount():
                self.RowValueChanged(row, col)
            else:
                logger.warning("TryRowValueChanged called with "
                               "row=%d, self.GetRowCount()=%d" %
                               (row, self.GetRowCount()))
                self.RowValueChanged(row, col)
        except wx.PyAssertionError:
            logger.warning(traceback.format_exc())
