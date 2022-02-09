# -*- coding: utf-8 -*-

"""

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

import os

from core.connector import Connector
from gui.guibase import GUIBase
from gui.colordefs import QudiPalettePale as palette
from qtpy import QtWidgets
from qtpy import QtCore
from qtpy import uic


class StepMotorMainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir,'ui_stepmotor.ui')

        super().__init__()
        uic.loadUi(ui_file, self)
        self.show



class StepMotorGui(GUIBase):
    stepmotorlogic = Connector(interface='StepMotorLogic')
    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
    def on_activate(self):
        
        self._step_motor_logic = self.stepmotorlogic()
    
        self._mw= StepMotorMainWindow()

        self._mw.setDockNestingEnabled(True)
        self._motor_channel = None


        self._mw.motorchanlineEdit.returnPressed.connect(self.update_motor_channel)
        self._mw.moveabslineEdit.returnPressed.connect(self.MOVEABS)
        self._mw.moverellineEdit.returnPressed.connect(self.MOVEREL)

        self.show()
    
    def show(self):
        """Make window visible and put it above all other windows. """
        self._mw.show()
        self._mw.activateWindow()
        self._mw.raise_()

    def on_deactivate(self):

        self._mw.motorchanlineEdit.returnPressed.disconnect()
        self._mw.moveabslineEdit.returnPressed.disconnect()
        self._mw.moverellineEdit.returnPressed.disconnect()
        return 0


    def update_motor_channel(self):
        self._motor_channel = int(self._mw.motorchanlineEdit.text())
    
    def MOVEABS(self):
        destination = round(float(self._mw.moveabslineEdit.text()),2)
        self._step_motor_logic.move_abs(self._motor_channel,destination)

    def MOVEREL(self):
        degree = round(float(self._mw.moverellineEdit.text()),2)
        self._step_motor_logic.move_rel(self._motor_channel,degree)



    


