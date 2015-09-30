"""
A logging handler which can be used with a wx.TextCtrl.
"""

import wx
import wx.lib.newevent

import logging

# create event type
# pylint: disable=invalid-name
wxLogEvent, EVT_WX_LOG_EVENT = wx.lib.newevent.NewEvent()


class WxLogHandler(logging.Handler):
    """
    A handler class which sends log strings to a wx object
    """
    def __init__(self, wxDest=None):
        """
        Initialize the handler
        @param wxDest: the destination object to post the event to
        @type wxDest: wx.Window
        """
        logging.Handler.__init__(self)
        self.wxDest = wxDest
        self.level = logging.DEBUG

    def flush(self):
        """
        does nothing for this handler
        """

    def emit(self, record):
        """
        Emit a record.

        """
        # pylint: disable=bare-except
        try:
            msg = self.format(record)
            evt = wxLogEvent(message=msg, levelname=record.levelname)
            wx.PostEvent(self.wxDest, evt)
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            self.handleError(record)
