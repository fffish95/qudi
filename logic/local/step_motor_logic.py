# -*- coding: utf-8 -*-

"""
This file contains the general logic for step motor.

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


class StepMotorLogic(GenericLogic):
    stepmotor1 = Connector(interface='MotorInterface')
    def __init__(self, config, **kwargs):
        super().__init__(config= config, **kwargs)
        self.threadlock = Mutex()

    def on_activate(self):
        self._motor = self.stepmotor1()


    def on_deactivate(self):
        return 0


    def move_rel(self, motor_channel=None, degree=None):
        return self._motor.move_rel(motor_channel, degree)

    
    def move_abs(self, motor_channel=None, degree=None):
        return self._motor.move_abs(motor_channel, degree)

