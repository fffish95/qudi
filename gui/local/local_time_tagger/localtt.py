# -*- coding: utf-8 -*-
"""
This file contains the Qudi GUI module for timetagger control.

Qudi is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Qudi is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Qudi. If not, see <http://www.gnu.org/licenses/>.

Copyright (c) the Qudi Developers. See the COPYRIGHT.txt file at the
top-level directory of this distribution and at <https://github.com/Ulm-IQO/qudi/>
"""

import numpy as np
import os
import pyqtgraph as pg

from core.connector import Connector
from gui.guibase import GUIBase
from qtpy import QtCore
from qtpy import QtCore, QtWidgets, uic


class LocalTTMainWindow(QtWidgets.QMainWindow):
    """ The main window for the local timetagger GUI.
    """

    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_localtt.ui')

        # Load it
        super(LocalTTMainWindow, self).__init__()
        uic.loadUi(ui_file, self)
        self.show()


class LocalTTChooseChannelsDialog(QtWidgets.QDialog):
    """ The settings dialog for choosing the timetagger channels.
    """

    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_localtt_choosechannels.ui')

        # Load it
        super(LocalTTChooseChannelsDialog, self).__init__()
        uic.loadUi(ui_file, self)


class LocalTTGui(GUIBase):
    """
    This is the GUI Class for local timetagger.
    """

    # declare connectors
    localtimetaggerlogic = Connector(interface='LocalTimeTaggerLogic')

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)

    def on_activate(self):
        """ Definition, configuration and initialisation of the Timetagger.

        This init connects all the graphic modules, which were created in the
        *.ui file and configures the event handling between the modules.
        """

        self._timetagger_logic = self.localtimetaggerlogic()
        
        self._mw = LocalTTMainWindow()
        self._ccd = LocalTTChooseChannelsDialog()
        self._mw.triggedchannels_PushButton.clicked.connect(self._choose_channels)
        self._mw.filtedchannels_PushButton.clicked.connect(self._choose_channels)
    

    def on_deactivate(self):
        """ Reverse steps of activation """
        
        self._mw.triggedchannels_PushButton.clicked.disconnect()
        self._mw.filtedchannels_PushButton.clicked.disconnect()
        self._mw.close()
        return 0
    
    def show(self):
        """ Make window visible and put it above all other windows. """
        self._mw.show()
        self._mw.activateWindow()
        self._mw.raise_()



    def _choose_channels(self):
        """ Open the choose channels dialog"""
        self.log.info(self.sender().objectName())
        self._ccd.exec_()

        