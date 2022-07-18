# -*- coding: utf-8 -*-

"""
This file contains the Qudi hardware StepMotor class.

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

from core.module import Base
from core.configoption import ConfigOption
from interface.motor_interface import MotorInterface

import pyvisa as visa

class StepMotor(Base, MotorInterface):
    """ Designed for driving a servo motor through Arduino.

    See [arduino-python3 Command API] & [arduino-libraries/Servo] for details.

    Example config for copy-paste:

    StepMotor:
        module.Class: 'local.step_motor.StepMotor'
        port:
            - 'COM4'

    """

    # config options
    _resurce_name = ConfigOption('port', list(), missing='error')


    def on_activate(self):
        self.rm = visa.ResourceManager()
        self._my_instrument = self.rm.open_resource(resource_name = self._resurce_name[0], baud_rate=57600, write_termination='\n')

    def on_deactivate(self):
        self._my_instrument.close()
        self.rm.close()
        return 0

    
    def get_constraints(self):
        pass

    def move_rel(self, motor_channel=None, degree=None):
        if motor_channel is None:
            self.log.error('The motor channel is None.')
            return -1
        if degree is None:
            self.log.error('The degree is None.')
            return -1

        self._my_instrument.write('MOVEREL {} {} deg'.format(motor_channel, degree))

    
    def move_abs(self, motor_channel=None, degree=None):
        if motor_channel is None:
            self.log.error('The motor channel is None.')
            return -1
        if degree is None:
            self.log.error('The degree is None.')
            return -1

        self._my_instrument.write('MOVEABS {} {} deg'.format(motor_channel, degree))
        


    def abort(self):
        pass


    def get_pos(self):
        pass


    def get_status(self):
        pass
    def calibrate(self):
        pass
    def get_velocity(self):
        pass
    def set_velocity(self):
        pass

    def _attach(self):
        pass
 
