# -*- coding: utf-8 -*-

"""
This file contains the general logic for flip mirror.

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


from core.connector import Connector
from logic.generic_logic import GenericLogic
from core.util.mutex import Mutex
from qtpy import QtCore
import time


class LocalFlipMirrorLogic(GenericLogic):
    servomotor1 = Connector(interface='MotorInterface')

    def __init__(self, config, **kwargs):
        super().__init__(config= config, **kwargs)
        self.threadlock = Mutex()

    def on_activate(self):
        self._motor = self.servomotor1()

        self._current_angle = self._motor.get_pos()

    def on_deactivate(self):
        self._motor.abort()
        return 0

    def move_rel(self, step_val):
        self._motor.move_rel(step_val)
        self._current_angle = self._motor.get_pos()

    def move_abs(self, new_angle):
        self._motor.move_abs(new_angle)
        self._current_angle = self._motor.get_pos()

    def detach(self):
        self._motor.abort()

    def attach(self):
        self._motor._attach()
        self._current_angle = self._motor.get_pos()


