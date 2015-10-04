"""
MyData.py

Main module for MyData.

To run MyData from the command-line, use "python run.py", where run.py is
in the parent directory of the directory containing MyData.py.
"""

# Don't worry about exceeding .pylintrc's max-module-lines for now:
# pylint: disable=too-many-lines

import sys
import wx
import webbrowser
import os
import appdirs  # pylint: disable=import-error
import traceback
import threading
import argparse
from datetime import datetime
import logging

from mydata import __version__ as VERSION
from mydata import LATEST_COMMIT
from mydata.views.folders import FoldersView
from mydata.dataviewmodels.folders import FoldersModel
from mydata.controllers.folders import FoldersController
from mydata.views.users import UsersView
from mydata.dataviewmodels.users import UsersModel
from mydata.views.groups import GroupsView
from mydata.dataviewmodels.groups import GroupsModel
from mydata.views.verifications import VerificationsView
from mydata.dataviewmodels.verifications import VerificationsModel
from mydata.views.uploads import UploadsView
from mydata.dataviewmodels.uploads import UploadsModel
from mydata.views.tasks import TasksView
from mydata.dataviewmodels.tasks import TasksModel
from mydata.models.uploader import UploaderModel
from mydata.views.log import LogView
from mydata.models.settings import SettingsModel
from mydata.views.settings import SettingsDialog
from mydata.utils.exceptions import InvalidFolderStructure
from mydata.views.statusbar import EnhancedStatusBar
from mydata.logs import logger
from mydata.views.taskbaricon import MyDataTaskBarIcon
import mydata.events as mde
from mydata.media import MYDATA_ICONS
from mydata.media import IconStyle
from mydata.utils.notification import Notification
from mydata.models.settings import LastSettingsUpdateTrigger
from mydata.controllers.schedule import ScheduleController

if wx.version().startswith("3.0.3.dev"):
    from wx import Icon as EmptyIcon
    from wx.lib.agw.aui import AuiNotebook
    from wx.lib.agw.aui import AUI_NB_TOP
    from wx.lib.agw.aui import EVT_AUINOTEBOOK_PAGE_CHANGING
    # pylint: disable=import-error
    from wx.adv import EVT_TASKBAR_LEFT_UP
else:
    from wx import EmptyIcon
    # pylint: disable=import-error
    from wx.aui import AuiNotebook
    from wx.aui import AUI_NB_TOP
    from wx.aui import EVT_AUINOTEBOOK_PAGE_CHANGING
    from wx import EVT_TASKBAR_LEFT_UP


class NotebookTabs(object):
    """
    Enumerated data type for referencing the different tab views in
    MyData's main window.
    """
    # pylint: disable=too-few-public-methods
    FOLDERS = 0
    USERS = 1
    GROUPS = 2
    VERIFICATIONS = 3
    UPLOADS = 4
    LOG = 5


def EndBusyCursorIfRequired():
    """
    The built in wx.EndBusyCursor raises an ugly exception if the
    busy cursor has already been stopped.
    """
    # pylint: disable=no-member
    # Otherwise pylint complains about PyAssertionError.
    # pylint: disable=protected-access
    try:
        wx.EndBusyCursor()
    except wx._core.PyAssertionError, err:
        if "no matching wxBeginBusyCursor()" \
                not in str(err):
            logger.error(str(err))
            raise


class MyDataFrame(wx.Frame):
    """
    MyData's main window.
    """
    def __init__(self, title, style, settingsModel):
        wx.Frame.__init__(self, None, wx.ID_ANY, title, style=style)
        self.settingsModel = settingsModel
        self.SetSize(wx.Size(1000, 600))
        self.statusbar = EnhancedStatusBar(self)
        if sys.platform.startswith("win"):
            self.statusbar.SetSize(wx.Size(-1, 28))
        else:
            self.statusbar.SetSize(wx.Size(-1, 18))
        self.statusbar.SetFieldsCount(2)
        self.SetStatusBar(self.statusbar)
        self.statusbar.SetStatusWidths([-1, 60])
        self.connectedBitmap = MYDATA_ICONS.GetIcon("Connect")
        self.disconnectedBitmap = MYDATA_ICONS.GetIcon("Disconnect")
        self.connected = False
        self.SetConnected(settingsModel.GetMyTardisUrl(), False)

    def SetStatusMessage(self, msg):
        """
        Update status bar's message.
        """
        self.statusbar.SetStatusMessage(msg)

    def SetConnected(self, myTardisUrl, connected):
        """
        Update status bar's connected/disconnected icon.
        """
        if self.connected == connected:
            return

        self.myTardisUrl = myTardisUrl
        self.connected = connected

        if self.myTardisUrl != self.settingsModel.GetMyTardisUrl():
            # This probably came from an old thread which took a while to
            # return a connection error.  While it was attempting to connect,
            # the user may have corrected the MyTardis URL in the Settings
            # dialog.
            return

        if connected:
            if sys.platform.startswith("win"):
                self.statusbar.SetStatusConnectionIcon(self.connectedBitmap)
        else:
            if sys.platform.startswith("win"):
                self.statusbar.SetStatusConnectionIcon(self.disconnectedBitmap)


# pylint: disable=too-many-public-methods
class MyData(wx.App):
    """
    Encapsulates the MyData application.
    """

    # pylint: disable=too-many-instance-attributes

    def __init__(self, name):
        self.name = name

        self.configPath = None

        self.frame = None
        self.panel = None
        self.foldersUsersNotebook = None

        self.menuBar = None
        self.editMenu = None
        self.helpMenu = None

        self.toolbar = None
        self.settingsTool = None
        self.stopTool = None
        self.refreshTool = None
        self.myTardisTool = None
        self.aboutTool = None
        self.helpTool = None

        self.taskBarIcon = None

        self.searchCtrl = None

        self.myDataEvents = None

        self.scanningFolders = False
        self.scanningFoldersThreadingLock = threading.Lock()
        self.performingLookupsAndUploads = False
        self.numUserFoldersScanned = 0
        self.shouldAbort = False

        self.activeNetworkInterface = None
        self.lastConnectivityCheckSuccess = False
        self.lastConnectivityCheckTime = datetime.fromtimestamp(0)

        self.settingsModel = None
        self.settingsValidation = None
        self.foldersModel = None
        self.foldersView = None
        self.foldersController = None
        self.scheduleController = None
        self.usersModel = None
        self.usersView = None
        self.groupsModel = None
        self.groupsView = None
        self.verificationsModel = None
        self.verificationsView = None
        self.uploadsModel = None
        self.uploadsView = None
        self.tasksModel = None
        self.tasksView = None
        self.logView = None

        wx.App.__init__(self, redirect=False)

    # This method is too long.  Needs refactoring.
    # pylint: disable=too-many-branches
    # pylint: disable=too-many-statements
    def OnInit(self):
        """
        Called automatically when application instance is created.
        """
        self.SetAppName("MyData")  # pylint: disable=no-member
        logger.debug("MyData version:   " + VERSION)
        logger.debug("MyData commit:  " + LATEST_COMMIT)
        appname = "MyData"
        appdirPath = appdirs.user_data_dir(appname, "Monash University")
        logger.debug("appdirPath: " + appdirPath)
        if not os.path.exists(appdirPath):
            os.makedirs(appdirPath)

        if hasattr(sys, "frozen"):
            if sys.platform.startswith("darwin"):
                # When frozen with Py2App, the default working directory
                # will be /Applications/MyData.app/Contents/Resources/
                # and setup.py will copy requests's cacert.pem into that
                # directory.
                certPath = os.path.realpath('.')
            else:
                # On Windows, setup.py will install requests's cacert.pem
                # in the same directory as MyData.exe.
                certPath = os.path.dirname(sys.executable)
            os.environ['REQUESTS_CA_BUNDLE'] = \
                os.path.join(certPath, 'cacert.pem')

        # MyData.cfg stores settings in INI format, readable by ConfigParser
        self.SetConfigPath(os.path.join(appdirPath, appname + '.cfg'))
        logger.debug("self.GetConfigPath(): " + self.GetConfigPath())

        self.settingsModel = SettingsModel(self.GetConfigPath())
        self.frame = MyDataFrame(self.name,
                                 style=wx.DEFAULT_FRAME_STYLE,
                                 settingsModel=self.settingsModel)

        self.frame.Bind(wx.EVT_ACTIVATE_APP, self.OnActivateApp)

        parser = argparse.ArgumentParser()
        parser.add_argument("-v", "--version", action="store_true",
                            help="Display MyData version and exit")
        parser.add_argument("-l", "--loglevel", help="set logging verbosity")
        args, _ = parser.parse_known_args()
        if args.version:
            print "MyData %s (%s)" % (VERSION, LATEST_COMMIT)
            sys.exit(0)
        if args.loglevel:
            if args.loglevel == "DEBUG":
                logger.SetLevel(logging.DEBUG)
            elif args.loglevel == "INFO":
                logger.SetLevel(logging.INFO)
            elif args.loglevel == "WARN":
                logger.SetLevel(logging.WARN)
            elif args.loglevel == "ERROR":
                logger.SetLevel(logging.ERROR)

        self.CheckIfAlreadyRunning(appdirPath)

        if sys.platform.startswith("darwin"):
            self.CreateMacMenu()

        self.usersModel = UsersModel(self.settingsModel)
        self.groupsModel = GroupsModel(self.settingsModel)
        self.foldersModel = FoldersModel(self.usersModel, self.groupsModel,
                                         self.settingsModel)
        self.usersModel.SetFoldersModel(self.foldersModel)
        self.verificationsModel = VerificationsModel()
        self.uploadsModel = UploadsModel()
        self.tasksModel = TasksModel(self.settingsModel)

        self.frame.Bind(wx.EVT_ACTIVATE, self.OnActivateFrame)
        self.myDataEvents = mde.MyDataEvents(notifyWindow=self.frame)

        self.taskBarIcon = MyDataTaskBarIcon(self.frame, self.settingsModel)
        self.taskBarIcon.Bind(EVT_TASKBAR_LEFT_UP, self.OnTaskBarLeftClick)

        self.frame.Bind(wx.EVT_MENU, self.taskBarIcon.OnExit, id=wx.ID_EXIT)

        self.frame.Bind(wx.EVT_CLOSE, self.OnCloseFrame)
        self.frame.Bind(wx.EVT_ICONIZE, self.OnMinimizeFrame)

        bmp = MYDATA_ICONS.GetIcon("favicon", vendor="MyTardis")
        icon = EmptyIcon()
        icon.CopyFromBitmap(bmp)
        self.frame.SetIcon(icon)

        self.panel = wx.Panel(self.frame)

        if wx.version().startswith("3.0.3.dev"):
            self.foldersUsersNotebook = \
                AuiNotebook(self.panel, agwStyle=AUI_NB_TOP)
        else:
            self.foldersUsersNotebook = \
                AuiNotebook(self.panel, style=AUI_NB_TOP)
        # Without the following line, the tab font looks
        # too small on Mac OS X:
        self.foldersUsersNotebook.SetFont(self.panel.GetFont())
        self.frame.Bind(EVT_AUINOTEBOOK_PAGE_CHANGING,
                        self.OnNotebookPageChanging, self.foldersUsersNotebook)

        self.foldersView = FoldersView(self.foldersUsersNotebook,
                                       foldersModel=self.foldersModel)

        self.foldersUsersNotebook.AddPage(self.foldersView, "Folders")
        self.foldersController = \
            FoldersController(self.frame,
                              self.foldersModel,
                              self.foldersView,
                              self.usersModel,
                              self.verificationsModel,
                              self.uploadsModel,
                              self.settingsModel)

        self.scheduleController = \
            ScheduleController(self.settingsModel, self.tasksModel)

        self.usersView = UsersView(self.foldersUsersNotebook,
                                   usersModel=self.usersModel)
        self.foldersUsersNotebook.AddPage(self.usersView, "Users")

        self.groupsView = GroupsView(self.foldersUsersNotebook,
                                     groupsModel=self.groupsModel)
        self.foldersUsersNotebook.AddPage(self.groupsView, "Groups")

        self.verificationsView = \
            VerificationsView(self.foldersUsersNotebook,
                              verificationsModel=self.verificationsModel,
                              foldersController=self.foldersController)
        self.foldersUsersNotebook.AddPage(self.verificationsView,
                                          "Verifications")

        self.uploadsView = \
            UploadsView(self.foldersUsersNotebook,
                        uploadsModel=self.uploadsModel,
                        foldersController=self.foldersController)
        self.foldersUsersNotebook.AddPage(self.uploadsView, "Uploads")

        self.tasksView = TasksView(self.foldersUsersNotebook,
                                   tasksModel=self.tasksModel)
        self.foldersUsersNotebook.AddPage(self.tasksView, "Tasks")

        self.logView = LogView(self.foldersUsersNotebook, self.settingsModel)
        self.foldersUsersNotebook.AddPage(self.logView, "Log")

        self.CreateToolbar()

        sizer = wx.BoxSizer()
        sizer.Add(self.foldersUsersNotebook, 1, flag=wx.EXPAND)
        self.panel.SetSizer(sizer)

        sizer = wx.BoxSizer()
        sizer.Add(self.panel, 1, flag=wx.EXPAND)
        self.frame.SetSizer(sizer)

        self.foldersUsersNotebook.SendSizeEvent()

        self.panel.SetFocus()

        self.SetTopWindow(self.frame)

        self.scanningFolders = threading.Event()
        self.performingLookupsAndUploads = threading.Event()

        event = None
        if self.settingsModel.RequiredFieldIsBlank():
            self.frame.Show(True)
            self.OnSettings(event)
        else:
            self.frame.SetTitle("MyData - " +
                                self.settingsModel.GetInstrumentName())
            self.frame.Hide()
            title = "MyData"
            if sys.platform.startswith("darwin"):
                message = \
                    "Click the MyData menubar icon to access its menu."
            else:
                message = \
                    "Click the MyData system tray icon to access its menu."
            Notification.Notify(message, title=title)
            self.scheduleController.ApplySchedule(event)

        return True

    def CheckIfAlreadyRunning(self, appdirPath):
        """
        Using wx.SingleInstanceChecker to check whether MyData is already
        running.
        Running MyData --version is allowed when MyData is already running.
        A workaround for the 'Deleted stale lock file' issue with
        SingleInstanceChecker on Mac OS X is to lower the wx logging level.
        MyData doesn't use wx.Log
        """
        wx.Log.SetLogLevel(wx.LOG_Error)
        instance = wx.SingleInstanceChecker(self.name, path=appdirPath)
        if instance.IsAnotherRunning():
            logger.warning("Another MyData instance is already running.")
            if sys.platform.startswith("darwin"):
                applescript = (
                    'tell application "System Events"\n'
                    '        set theprocs to every process whose name is '
                    '"MyData"\n'
                    '        repeat with proc in theprocs\n'
                    '                set the frontmost of proc to true\n'
                    '        end repeat\n'
                    'end tell')
                os.system("osascript -e '%s'" % applescript)
                sys.exit(0)
            else:
                wx.MessageBox("MyData is already running!", "MyData",
                              wx.ICON_ERROR)
                sys.exit(1)

    def CreateMacMenu(self):
        """
        On Mac OS X, adding an Edit menu seems to help with
        enabling command-c (copy) and command-v (paste)
        """
        self.menuBar = wx.MenuBar()
        self.editMenu = wx.Menu()
        self.editMenu.Append(wx.ID_UNDO, "Undo\tCTRL+Z", "Undo")
        self.frame.Bind(wx.EVT_MENU, self.OnUndo, id=wx.ID_UNDO)
        self.editMenu.Append(wx.ID_REDO, "Redo\tCTRL+SHIFT+Z", "Redo")
        self.frame.Bind(wx.EVT_MENU, self.OnRedo, id=wx.ID_REDO)
        self.editMenu.AppendSeparator()
        self.editMenu.Append(wx.ID_CUT, "Cut\tCTRL+X",
                             "Cut the selected text")
        self.frame.Bind(wx.EVT_MENU, self.OnCut, id=wx.ID_CUT)
        self.editMenu.Append(wx.ID_COPY, "Copy\tCTRL+C",
                             "Copy the selected text")
        self.frame.Bind(wx.EVT_MENU, self.OnCopy, id=wx.ID_COPY)
        self.editMenu.Append(wx.ID_PASTE, "Paste\tCTRL+V",
                             "Paste text from the clipboard")
        self.frame.Bind(wx.EVT_MENU, self.OnPaste, id=wx.ID_PASTE)
        self.editMenu.Append(wx.ID_SELECTALL, "Select All\tCTRL+A",
                             "Select All")
        self.frame.Bind(wx.EVT_MENU, self.OnSelectAll, id=wx.ID_SELECTALL)
        self.menuBar.Append(self.editMenu, "Edit")

        self.helpMenu = wx.Menu()

        helpMenuItemID = wx.NewId()
        self.helpMenu.Append(helpMenuItemID, "&MyData Help")
        self.frame.Bind(wx.EVT_MENU, self.OnHelp, id=helpMenuItemID)

        walkthroughMenuItemID = wx.NewId()
        self.helpMenu.Append(
            walkthroughMenuItemID, "Mac OS X &Walkthrough")
        self.frame.Bind(wx.EVT_MENU, self.OnWalkthrough,
                        id=walkthroughMenuItemID)

        self.helpMenu.Append(wx.ID_ABOUT, "&About MyData")
        self.frame.Bind(wx.EVT_MENU, self.OnAbout, id=wx.ID_ABOUT)
        self.menuBar.Append(self.helpMenu, "&Help")
        self.frame.SetMenuBar(self.menuBar)

    def OnActivateApp(self, event):
        """
        Called when MyData is activated.
        """
        if event.GetActive():
            if sys.platform.startswith("darwin"):
                self.frame.Show(True)
                self.frame.Raise()
        event.Skip()

    def OnActivateFrame(self, event):
        """
        Called when MyData's main window is activated.
        """
        if event.GetActive():
            self.frame.Show(True)
            self.frame.Raise()

    # pylint: disable=no-self-use
    def OnUndo(self, event):
        """
        Called when Edit menu's Undo menu item is clicked.
        """
        textCtrl = wx.Window.FindFocus()
        if textCtrl is not None:
            textCtrl.Undo()
        event.Skip()

    # pylint: disable=no-self-use
    def OnRedo(self, event):
        """
        Called when Edit menu's Redo menu item is clicked.
        """
        textCtrl = wx.Window.FindFocus()
        if textCtrl is not None:
            textCtrl.Redo()
        event.Skip()

    # pylint: disable=no-self-use
    def OnCut(self, event):
        """
        Called when Edit menu's Cut menu item is clicked.
        """
        textCtrl = wx.Window.FindFocus()
        if textCtrl is not None:
            textCtrl.Cut()
        event.Skip()

    # pylint: disable=no-self-use
    def OnCopy(self, event):
        """
        Called when Edit menu's Copy menu item is clicked.
        """
        textCtrl = wx.Window.FindFocus()
        if textCtrl is not None:
            textCtrl.Copy()
        event.Skip()

    # pylint: disable=no-self-use
    def OnPaste(self, event):
        """
        Called when Edit menu's Paste menu item is clicked.
        """
        textCtrl = wx.Window.FindFocus()
        if textCtrl is not None:
            textCtrl.Paste()
        event.Skip()

    # pylint: disable=no-self-use
    def OnSelectAll(self, event):
        """
        Called when Edit menu's Select All menu item is clicked.
        """
        textCtrl = wx.Window.FindFocus()
        if textCtrl is not None:
            textCtrl.SelectAll()
        event.Skip()

    def OnTaskBarLeftClick(self, event):
        """
        Called when task bar icon is clicked with the left mouse button.
        """
        self.taskBarIcon.PopupMenu(self.taskBarIcon.CreatePopupMenu())
        event.Skip()

    # pylint: disable=unused-argument
    def OnCloseFrame(self, event):
        """
        Don't actually close it, just hide it.
        """
        if sys.platform.startswith("win"):
            self.frame.Show()  # See: http://trac.wxwidgets.org/ticket/10426
        self.frame.Hide()

    # pylint: disable=unused-argument
    def ShutDownCleanlyAndExit(self, event):
        """
        Shut down MyData cleanly and quit.
        """
        started = self.foldersController.Started()
        completed = self.foldersController.Completed()
        canceled = self.foldersController.Canceled()
        failed = self.foldersController.Failed()

        message = "Are you sure you want to shut down MyData's " \
            "data scans and uploads?"
        if started and not completed and not canceled and not failed:
            message += "\n\n" \
                "MyData will attempt to shut down any uploads currently " \
                "in progress."
        confirmationDialog = \
            wx.MessageDialog(None, message, "MyData",
                             wx.YES | wx.NO | wx.ICON_QUESTION)
        okToExit = confirmationDialog.ShowModal()
        if okToExit == wx.ID_YES:
            def ShutDownDataScansAndUploads():
                """
                Shut down data folder scanning, datafile lookups
                (verifications) and uploads.
                """
                logger.debug("Starting ShutDownDataScansAndUploads...")
                # pylint: disable=bare-except
                try:
                    wx.CallAfter(wx.BeginBusyCursor)
                    self.foldersController.ShutDownUploadThreads()
                    wx.CallAfter(EndBusyCursorIfRequired)
                    self.tasksModel.ShutDown()
                    sys.exit(0)
                except:
                    try:
                        logger.debug(traceback.format_exc())
                        self.tasksModel.ShutDown()
                        # pylint: disable=protected-access
                        os._exit(1)
                    # pylint: disable=bare-except
                    except:
                        logger.debug(traceback.format_exc())
                        # pylint: disable=protected-access
                        os._exit(1)
                logger.debug("Finishing run() method for thread %s"
                             % threading.current_thread().name)

            thread = threading.Thread(target=ShutDownDataScansAndUploads)
            logger.debug("Starting thread %s" % thread.name)
            thread.start()
            logger.debug("Started thread %s" % thread.name)

    def OnMinimizeFrame(self, event):
        """
        When minimizing, hide the frame so it "minimizes to tray"
        """
        if event.Iconized():
            self.frame.Show()  # See: http://trac.wxwidgets.org/ticket/10426
            self.frame.Hide()
        else:
            self.frame.Show(True)
            self.frame.Raise()
        # event.Skip()

    def CreateToolbar(self):
        """
        Create a toolbar.
        """
        self.toolbar = self.frame.CreateToolBar()
        self.toolbar.SetToolBitmapSize(wx.Size(24, 24))  # sets icon size

        openIcon = MYDATA_ICONS.GetIcon("Open folder", size="24x24")
        if wx.version().startswith("3.0.3.dev"):
            addToolMethod = self.toolbar.AddTool
        else:
            addToolMethod = self.toolbar.AddLabelTool
        openTool = addToolMethod(wx.ID_ANY, "Open folder",
                                 openIcon, shortHelp="Open folder")
        self.frame.Bind(wx.EVT_MENU, self.OnOpen, openTool)

        self.toolbar.AddSeparator()

        refreshIcon = MYDATA_ICONS.GetIcon("Refresh", size="24x24")
        self.refreshTool = addToolMethod(wx.ID_REFRESH, "Refresh",
                                         refreshIcon, shortHelp="Refresh")
        self.toolbar.EnableTool(wx.ID_REFRESH, True)
        self.frame.Bind(wx.EVT_TOOL, self.OnRefreshFromToolbar, self.refreshTool,
                        self.refreshTool.GetId())

        self.toolbar.AddSeparator()

        stopIcon = MYDATA_ICONS.GetIcon("Stop sign", size="24x24",
                                        style=IconStyle.NORMAL)
        self.stopTool = addToolMethod(wx.ID_STOP, "Stop",
                                      stopIcon, shortHelp="Stop")
        disabledStopIcon = MYDATA_ICONS.GetIcon("Stop sign", size="24x24",
                                                style=IconStyle.DISABLED)
        self.toolbar.SetToolDisabledBitmap(self.stopTool.GetId(),
                                           disabledStopIcon)
        self.toolbar.EnableTool(self.stopTool.GetId(), False)

        self.frame.Bind(wx.EVT_TOOL, self.OnStop, self.stopTool,
                        self.stopTool.GetId())

        self.toolbar.AddSeparator()

        settingsIcon = MYDATA_ICONS.GetIcon("Settings", size="24x24")
        self.settingsTool = addToolMethod(wx.ID_ANY, "Settings",
                                          settingsIcon, shortHelp="Settings")
        self.frame.Bind(wx.EVT_TOOL, self.OnSettings, self.settingsTool)

        self.toolbar.AddSeparator()

        internetIcon = MYDATA_ICONS.GetIcon("Internet explorer", size="24x24")
        self.myTardisTool = addToolMethod(wx.ID_ANY, "MyTardis",
                                          internetIcon, shortHelp="MyTardis")
        self.frame.Bind(wx.EVT_TOOL, self.OnMyTardis, self.myTardisTool)

        self.toolbar.AddSeparator()

        aboutIcon = MYDATA_ICONS.GetIcon("About", size="24x24",
                                         style=IconStyle.HOT)
        self.aboutTool = addToolMethod(wx.ID_ANY, "About MyData",
                                       aboutIcon, shortHelp="About MyData")
        self.frame.Bind(wx.EVT_TOOL, self.OnAbout, self.aboutTool)

        self.toolbar.AddSeparator()

        helpIcon = MYDATA_ICONS.GetIcon("Help", size="24x24",
                                        style=IconStyle.HOT)
        self.helpTool = addToolMethod(wx.ID_ANY, "Help", helpIcon,
                                      shortHelp="MyData User Guide")
        self.frame.Bind(wx.EVT_TOOL, self.OnHelp, self.helpTool)

        self.toolbar.AddStretchableSpace()
        self.searchCtrl = wx.SearchCtrl(self.toolbar, size=wx.Size(200, -1),
                                        style=wx.TE_PROCESS_ENTER)
        self.searchCtrl.ShowSearchButton(True)
        self.searchCtrl.ShowCancelButton(True)

        self.frame.Bind(wx.EVT_TEXT_ENTER, self.OnDoSearch, self.searchCtrl)
        self.frame.Bind(wx.EVT_TEXT, self.OnDoSearch, self.searchCtrl)

        self.toolbar.AddControl(self.searchCtrl)

        # This basically shows the toolbar
        self.toolbar.Realize()

        # self.SetCallFilterEvent(True)

    # def OnSearchButton(self,event):
        # pass

    # def OnSearchCancel(self,event):
        # pass

    def OnDoSearch(self, event):
        """
        Triggered by user typing into search field in upper-right corner
        or main window.
        """
        if self.foldersUsersNotebook.GetSelection() == NotebookTabs.FOLDERS:
            self.foldersModel.Filter(event.GetString())
        elif self.foldersUsersNotebook.GetSelection() == NotebookTabs.USERS:
            self.usersModel.Filter(event.GetString())
        elif self.foldersUsersNotebook.GetSelection() == NotebookTabs.GROUPS:
            self.groupsModel.Filter(event.GetString())
        elif self.foldersUsersNotebook.GetSelection() == \
                NotebookTabs.VERIFICATIONS:
            self.verificationsModel.Filter(event.GetString())
        elif self.foldersUsersNotebook.GetSelection() == NotebookTabs.UPLOADS:
            self.uploadsModel.Filter(event.GetString())

    def OnRefreshFromToolbar(self, event):
        """
        The user pressed the Refresh icon on the main windows' toolbar.
        """
        logger.debug("OnRefreshFromToolbar")
        self.tasksModel.DeleteAllRows()
        self.settingsModel.SetScheduleType("Manually")
        self.settingsModel.SetLastSettingsUpdateTrigger(
            LastSettingsUpdateTrigger.UI_RESPONSE)
        self.scheduleController.ApplySchedule(event, runManually=True)

    def OnRefresh(self, event, needToValidateSettings=True, jobId=None):
        """
        Shut down any existing data folder scan and upload threads,
        validate settings, and begin scanning data folders, checking
        for existing datafiles on MyTardis and uploading any datafiles
        not yet available on MyTardis.
        """
        self.LogOnRefreshCaller(event, jobId)
        shutdownForRefreshComplete = \
            event.GetId() in (mde.EVT_SHUTDOWN_FOR_REFRESH_COMPLETE,
                              mde.EVT_SETTINGS_VALIDATION_FOR_REFRESH_COMPLETE)

        if hasattr(event, "needToValidateSettings") and \
                event.needToValidateSettings is False:
            needToValidateSettings = False
        if hasattr(event, "shutdownSuccessful") and event.shutdownSuccessful:
            shutdownForRefreshComplete = True

        # Shutting down existing data scan and upload processes:

        if (self.ScanningFolders() or self.PerformingLookupsAndUploads()) \
                and not shutdownForRefreshComplete:
            message = \
                "Shutting down existing data scan and upload processes..."
            logger.debug(message)
            self.frame.SetStatusMessage(message)

            shutdownForRefreshEvent = \
                mde.MyDataEvent(mde.EVT_SHUTDOWN_FOR_REFRESH,
                                foldersController=self.foldersController)
            logger.debug("Posting shutdownForRefreshEvent")
            wx.PostEvent(wx.GetApp().GetMainFrame(), shutdownForRefreshEvent)
            return

        # Reset the status message to the connection status:
        self.frame.SetConnected(self.settingsModel.GetMyTardisUrl(),
                                False)
        self.foldersController.SetShuttingDown(False)

        self.searchCtrl.SetValue("")

        # Network connectivity check:

        validateSettingsForRefreshEvent = \
            mde.MyDataEvent(mde.EVT_VALIDATE_SETTINGS_FOR_REFRESH)
        if self.CheckConnectivityForRefresh(
                nextEvent=validateSettingsForRefreshEvent):
            # Wait for the event to be handled, which will result
            # in OnRefresh being called again.
            return

        # Settings validation:

        if needToValidateSettings:
            logger.debug("OnRefresh: needToValidateSettings is True.")
            self.frame.SetStatusMessage("Validating settings...")
            self.settingsValidation = None

            def ValidateSettings():
                """
                Validate settings.
                """
                logger.debug("Starting run() method for thread %s"
                             % threading.current_thread().name)
                # pylint: disable=bare-except
                try:
                    wx.CallAfter(wx.BeginBusyCursor)
                    # pylint: disable=broad-except
                    try:
                        activeNetworkInterfaces = \
                            UploaderModel.GetActiveNetworkInterfaces()
                    except Exception, err:
                        logger.error(traceback.format_exc())
                        if type(err).__name__ == "WindowsError" and \
                                "The handle is invalid" in str(err):
                            message = "An error occurred, suggesting " \
                                "that you have launched MyData.exe from a " \
                                "Command Prompt window.  Please launch it " \
                                "from a shortcut or from a Windows Explorer " \
                                "window instead.\n" \
                                "\n" \
                                "See: https://bugs.python.org/issue3905"

                            def ShowErrorDialog(message):
                                """
                                Needs to run in the main thread.
                                """
                                dlg = wx.MessageDialog(None, message, "MyData",
                                                       wx.OK | wx.ICON_ERROR)
                                dlg.ShowModal()
                            wx.CallAfter(ShowErrorDialog, message)
                    if len(activeNetworkInterfaces) == 0:
                        message = "No active network interfaces." \
                            "\n\n" \
                            "Please ensure that you have an active " \
                            "network interface (e.g. Ethernet or WiFi)."

                        def ShowDialog():
                            """
                            Needs to run in the main thread.
                            """
                            dlg = wx.MessageDialog(None, message, "MyData",
                                                   wx.OK | wx.ICON_ERROR)
                            dlg.ShowModal()
                            wx.CallAfter(EndBusyCursorIfRequired)
                            self.frame.SetStatusMessage("")
                            self.frame.SetConnected(
                                self.settingsModel.GetMyTardisUrl(), False)
                        wx.CallAfter(ShowDialog)
                        return

                    self.settingsValidation = self.settingsModel.Validate()
                    event = mde.MyDataEvent(
                        mde.EVT_SETTINGS_VALIDATION_FOR_REFRESH_COMPLETE,
                        needToValidateSettings=False)
                    wx.PostEvent(self.frame, event)
                    wx.CallAfter(EndBusyCursorIfRequired)
                except:
                    logger.debug(traceback.format_exc())
                    return
                logger.debug("Finishing run() method for thread %s"
                             % threading.current_thread().name)

            thread = threading.Thread(target=ValidateSettings,
                                      name="OnRefreshValidateSettings")
            logger.debug("Starting thread %s" % thread.name)
            thread.start()
            logger.debug("Started thread %s" % thread.name)
            return

        if needToValidateSettings and not self.settingsValidation.valid:
            logger.debug("Displaying result from settings validation.")
            message = self.settingsValidation.message
            logger.error(message)
            dlg = wx.MessageDialog(None, message, "MyData",
                                   wx.OK | wx.ICON_ERROR)
            dlg.ShowModal()
            self.OnSettings(event)
            return

        if "Group" in self.settingsModel.GetFolderStructure():
            userOrGroup = "user group"
        else:
            userOrGroup = "user"

        self.numUserFoldersScanned = 0
        self.shouldAbort = False

        def WriteProgressUpdateToStatusBar():
            """
            Write progress update to status bar.
            """
            self.numUserFoldersScanned = self.numUserFoldersScanned + 1
            message = "Scanned %d of %d %s folders" % (
                self.numUserFoldersScanned,
                self.usersModel.GetNumUserOrGroupFolders(),
                userOrGroup)
            self.frame.SetStatusMessage(message)

        # SECTION 4: Start FoldersModel.ScanFolders(),
        # followed by FoldersController.StartDataUploads().

        def ScanDataDirs():
            """
            Scan data folders, looking for datafiles to look up on MyTardis
            and upload if necessary.
            """
            logger.debug("Starting run() method for thread %s"
                         % threading.current_thread().name)
            wx.CallAfter(self.frame.SetStatusMessage,
                         "Scanning data folders...")
            try:
                self.scanningFoldersThreadingLock.acquire()
                self.SetScanningFolders(True)
                logger.info("Just set ScanningFolders to True")
                self.toolbar.EnableTool(self.stopTool.GetId(), True)
                self.foldersModel.ScanFolders(WriteProgressUpdateToStatusBar,
                                              self.ShouldAbort)
                self.SetScanningFolders(False)
                self.scanningFoldersThreadingLock.release()
                logger.info("Just set ScanningFolders to False")
            except InvalidFolderStructure, ifs:
                def ShowMessageDialog():
                    """
                    Needs to run in the main thread.
                    """
                    dlg = wx.MessageDialog(None, str(ifs), "MyData",
                                           wx.OK | wx.ICON_ERROR)
                    dlg.ShowModal()
                wx.CallAfter(ShowMessageDialog)
                self.frame.SetStatusMessage(str(ifs))
                return

            if self.ShouldAbort():
                wx.CallAfter(EndBusyCursorIfRequired)
                return

            if self.usersModel.GetNumUserOrGroupFolders() > 0:
                startDataUploadsEvent = \
                    mde.MyDataEvent(mde.EVT_START_DATA_UPLOADS,
                                    foldersController=self.foldersController)
                logger.debug("Posting startDataUploadsEvent")
                wx.PostEvent(wx.GetApp().GetMainFrame(),
                             startDataUploadsEvent)
            else:
                message = "No user/group folders to upload from."
                logger.debug(message)
                self.frame.SetStatusMessage(message)

            wx.CallAfter(EndBusyCursorIfRequired)
            logger.debug("Finishing run() method for thread %s"
                         % threading.current_thread().name)

        thread = threading.Thread(target=ScanDataDirs,
                                  name="ScanDataDirectoriesThread")
        logger.debug("OnRefresh: Starting ScanDataDirs thread.")
        thread.start()
        logger.debug("OnRefresh: Started ScanDataDirs thread.")

    def LogOnRefreshCaller(self, event, jobId):
        """
        Called by OnRefresh (the main method for starting the
        data folder scans and uploads) to log what triggered the
        call to OnRefresh (e.g. the toolbar button, the task bar
        icon menu item, or a scheduled task).
        """
        if jobId:
            logger.debug("OnRefresh called from job ID %d" % jobId)
        elif event is None:
            logger.debug("OnRefresh called automatically "
                         "from MyData's OnInit().")
        elif event.GetId() == self.settingsTool.GetId():
            logger.debug("OnRefresh called automatically from "
                         "OnSettings(), after displaying SettingsDialog, "
                         "which was launched from MyData's toolbar.")
        elif event.GetId() == self.refreshTool.GetId():
            logger.debug("OnRefresh triggered by Refresh toolbar icon.")
        elif self.taskBarIcon.GetMyTardisSyncMenuItem() is not None and \
                event.GetId() == \
                self.taskBarIcon.GetMyTardisSyncMenuItem().GetId():
            logger.debug("OnRefresh triggered by 'MyTardis Sync' "
                         "task bar menu item.")
        elif event.GetId() == mde.EVT_VALIDATE_SETTINGS_FOR_REFRESH:
            logger.debug("OnRefresh called from "
                         "EVT_VALIDATE_SETTINGS_FOR_REFRESH event.")
        elif event.GetId() == mde.EVT_SHUTDOWN_FOR_REFRESH_COMPLETE:
            logger.debug("OnRefresh called from "
                         "EVT_SHUTDOWN_FOR_REFRESH_COMPLETE event.")
        elif event.GetId() == mde.EVT_SETTINGS_VALIDATION_FOR_REFRESH_COMPLETE:
            logger.debug("OnRefresh called from "
                         "EVT_SETTINGS_VALIDATION_FOR_REFRESH_COMPLETE event.")
        else:
            logger.debug("OnRefresh: event.GetId() = %d" % event.GetId())

    def CheckConnectivityForRefresh(self, nextEvent=None):
        """
        Called from OnRefresh (the main method for scanning data folders
        and uploading data).
        This method determines if a network connectivity check is due,
        and if so, posts a check connectivity event, and returns True
        to indicate that the event has been posted.
        """
        intervalSinceLastCheck = \
            datetime.now() - self.lastConnectivityCheckTime
        checkInterval = self.settingsModel.GetConnectivityCheckInterval()
        if intervalSinceLastCheck.total_seconds() >= checkInterval or \
                not self.lastConnectivityCheckSuccess:
            logger.debug("Checking network connectivity...")
            checkConnectivityEvent = \
                mde.MyDataEvent(mde.EVT_CHECK_CONNECTIVITY,
                                settingsModel=self.settingsModel,
                                nextEvent=nextEvent)
            wx.PostEvent(wx.GetApp().GetMainFrame(), checkConnectivityEvent)
            return True
        return False

    def OnStop(self, event):
        """
        The user pressed the stop button on the main toolbar.
        """
        self.shouldAbort = True
        self.uploadsView.OnCancelRemainingUploads(event)

    def ShouldAbort(self):
        """
        The user has requested aborting the data folder scans and/or
        datafile lookups (verifications) and/or uploads.
        """
        return self.shouldAbort

    def OnOpen(self, event):
        """
        Open the selected data folder in Windows Explorer (Windows) or
        in Finder (Mac OS X).
        """
        if self.foldersUsersNotebook.GetSelection() == NotebookTabs.FOLDERS:
            self.foldersController.OnOpenFolder(event)

    def OnNotebookPageChanging(self, event):
        """
        Clear the search field after switching views
        (e.g. from Folders to Users).
        """
        if self.searchCtrl:
            self.searchCtrl.SetValue("")

    def OnSettings(self, event):
        """
        Open the Settings dialog, which could be in response to the main
        toolbar's Refresh icon, or in response to in response to the task bar
        icon's "MyData Settings" menu item, or in response to MyData being
        launched without any previously saved settings.
        """
        settingsDialog = SettingsDialog(self.frame, "Settings",
                                        self.settingsModel,
                                        size=wx.Size(400, 400),
                                        style=wx.DEFAULT_DIALOG_STYLE)
        if settingsDialog.ShowModal() == wx.ID_OK:
            logger.debug("settingsDialog.ShowModal() returned wx.ID_OK")
            myTardisUrlChanged = (self.settingsModel.GetMyTardisUrl() !=
                                  settingsDialog.GetMyTardisUrl())
            if myTardisUrlChanged:
                self.frame.SetConnected(settingsDialog.GetMyTardisUrl(), False)
            self.frame.SetTitle("MyData - " +
                                self.settingsModel.GetInstrumentName())
            self.tasksModel.DeleteAllRows()
            self.scheduleController.ApplySchedule(event)

    def OnMyTardis(self, event):
        """
        Called when user clicks the Internet Browser icon on the
        main toolbar.
        """
        # pylint: disable=bare-except
        try:
            items = self.foldersView.GetDataViewControl().GetSelections()
            rows = [self.foldersModel.GetRow(item) for item in items]
            if len(rows) == 1:
                folderRecord = self.foldersModel.GetFolderRecord(rows[0])
                if folderRecord.GetDatasetModel() is not None:
                    webbrowser\
                        .open(self.settingsModel.GetMyTardisUrl() + "/" +
                              folderRecord.GetDatasetModel().GetViewUri())
                else:
                    webbrowser.open(self.settingsModel.GetMyTardisUrl())
            else:
                webbrowser.open(self.settingsModel.GetMyTardisUrl())
        except:
            logger.error(traceback.format_exc())

    def OnHelp(self, event):
        """
        Called when the user clicks the Help icon on the
        main toolbar.
        """
        new = 2  # Open in a new tab, if possible
        url = "http://mydata.readthedocs.org/en/latest/"
        webbrowser.open(url, new=new)

    def OnWalkthrough(self, event):
        """
        Mac OS X Only.
        Called when the user clicks the Mac OS X Walkthrough
        menu item in the Help menu.
        """
        new = 2  # Open in a new tab, if possible
        url = "http://mydata.readthedocs.org/en/latest/macosx-walkthrough.html"
        webbrowser.open(url, new=new)

    def OnAbout(self, event):
        """
        Called when the user clicks the Info icon on the
        main toolbar.
        """
        msg = "MyData is a desktop application" \
              " for uploading data to MyTardis " \
              "(https://github.com/mytardis/mytardis).\n\n" \
              "MyData is being developed at the Monash e-Research Centre " \
              "(Monash University, Australia)\n\n" \
              "MyData is open source (GPL3) software available from " \
              "https://github.com/monash-merc/mydata\n\n" \
              "Version:   " + VERSION + "\n" \
              "Commit:  " + LATEST_COMMIT + "\n"
        dlg = wx.MessageDialog(None, msg, "About MyData",
                               wx.OK | wx.ICON_INFORMATION)
        dlg.ShowModal()

    def GetMainFrame(self):
        """
        Returns the application's main frame, which is
        an instance of MyDataFrame.
        """
        return self.frame

    def GetMyDataEvents(self):
        """
        Returns the MyData events object, which is
        an instance of mydata.events.MyDataEvents
        """
        return self.myDataEvents

    def GetScheduleController(self):
        """
        Returns MyData's schedule controller.
        """
        return self.scheduleController

    def GetLastConnectivityCheckTime(self):
        """
        Returns the last time when MyData checked
        for network connectivity.
        """
        return self.lastConnectivityCheckTime

    def SetLastConnectivityCheckTime(self, lastConnectivityCheckTime):
        """
        Sets the last time when MyData checked
        for network connectivity.
        """
        self.lastConnectivityCheckTime = lastConnectivityCheckTime

    def GetLastConnectivityCheckSuccess(self):
        """
        Returns the success or failure from the MyData's
        most recent check for network connectivity.
        """
        return self.lastConnectivityCheckSuccess

    def SetLastConnectivityCheckSuccess(self, success):
        """
        Sets the success or failure for the MyData's
        most recent check for network connectivity.
        """
        self.lastConnectivityCheckSuccess = success

    def GetActiveNetworkInterface(self):
        """
        Returns the active network interface found
        during the most recent check for network
        connectivity.
        """
        return self.activeNetworkInterface

    def SetActiveNetworkInterface(self, activeNetworkInterface):
        """
        Sets the active network interface found
        during the most recent check for network
        connectivity.
        """
        self.activeNetworkInterface = activeNetworkInterface

    def GetConfigPath(self):
        """
        Returns the location on disk of MyData.cfg
        e.g. "C:\\Users\\jsmith\\AppData\\Local\\Monash University\\MyData\\MyData.cfg" or
        "/Users/jsmith/Library/Application Support/MyData/MyData.cfg".
        """
        return self.configPath

    def SetConfigPath(self, configPath):
        """
        Sets the location on disk of MyData.cfg
        e.g. "C:\\Users\\jsmith\\AppData\\Local\\Monash University\\MyData\\MyData.cfg" or
        "/Users/jsmith/Library/Application Support/MyData/MyData.cfg".
        """
        self.configPath = configPath

    def ScanningFolders(self):
        """
        Returns True if MyData is currently scanning data folders.
        """
        return self.scanningFolders.isSet()

    def SetScanningFolders(self, value):
        """
        Records whether MyData is currently scanning data folders.
        """
        if value:
            self.scanningFolders.set()
        else:
            self.scanningFolders.clear()

    def PerformingLookupsAndUploads(self):
        """
        Returns True if MyData is currently performing
        datafile lookups (verifications) and uploading
        datafiles.
        """
        return self.performingLookupsAndUploads.isSet()

    def SetPerformingLookupsAndUploads(self, value):
        """
        Records whether MyData is currently performing
        datafile lookups (verifications) and uploading
        datafiles.
        """
        if value:
            self.performingLookupsAndUploads.set()
        else:
            self.performingLookupsAndUploads.clear()


def Run():
    """
    Main function for launching MyData.
    """
    app = MyData("MyData")
    app.MainLoop()

if __name__ == "__main__":
    print "Please use run.py in MyData.py's parent directory instead."
