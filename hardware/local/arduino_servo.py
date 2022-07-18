# -*- coding: utf-8 -*-

"""
This file contains the Qudi hardware ArduinoServo class.

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

from Arduino import Arduino
import time

class ArduinoServo(Base, MotorInterface):
    """ Designed for driving a servo motor through Arduino.

    See [arduino-python3 Command API] & [arduino-libraries/Servo] for details.

    Example config for copy-paste:

    ServoMotor:
        module.Class: 'local.arduino_servo.ArduinoServo'
        # Arduino Params
        baud: 9600
        tmeout: 2
        port:
            - 'COM3'
        # Servo Motor Params
        pin: 5
        0 degree position: 750          #test with code ServoMotor._board.Servos.writeMicroseconds(5,750)
        90 degree position: 1650        #test with code ServoMotor._board.Servos.writeMicroseconds(5,1650)
        slow down time: 0               #s
        step size: 0.3                  #degree
        angle_range:
            - [0,90]
    """

    # config options
    _arduino_port = ConfigOption('port', list(), missing='error')
    _baud = ConfigOption('baud', default=9600)
    _timeout = ConfigOption('timeout',default=2)

    _pin= ConfigOption('pin', missing='error')
    _deg0= ConfigOption('0 degree position', missing='error')
    _deg90= ConfigOption('90 degree position', missing='error')
    _slow_down_time= ConfigOption('slow down time', missing='error')
    _step_size = ConfigOption('step size', missing='error')
    _angle_range = ConfigOption('angle_range', missing= 'error')


    def on_activate(self):
        self._min= int(self._deg0)
        self._max= self._min + (int(self._deg90)-self._min)*2


        self._board=Arduino(baud = self._baud, port= self._arduino_port[0], timeout= self._timeout)
        self._attach()

    def on_deactivate(self):
        self._board.Servos.detach(self._pin)

    
    def get_constraints(self):
        return self._angle_range

    def move_rel(self, step_val=1):
        new_angle = self.current_angle + step_val
        if (new_angle < self._angle_range[0][0]) or (new_angle > self._angle_range[0][1]):
            self.log.error('New angle out of angle range.')
            return -1
        self.move_abs(new_angle)

    
    def move_abs(self, new_angle):
        if (new_angle < self._angle_range[0][0]) or (new_angle > self._angle_range[0][1]):
            self.log.error('New angle out of angle range.')
            return -1
        self._board.Servos.write(self._pin,new_angle)
        self.current_angle = new_angle

        


    def abort(self):
        self._board.Servos.detach(self._pin)


    def get_pos(self):
        return self.current_angle


    def get_status(self):
        pass
    def calibrate(self):
        pass
    def get_velocity(self):
        pass
    def set_velocity(self):
        pass

    def _attach(self):
        self._board.Servos.attach(self._pin, min=self._min, max=self._max)
        self._board.Servos.write(self._pin,45)
        self.current_angle = 45
 
