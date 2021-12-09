# -*- coding: utf-8 -*-

import numpy as np

from core.connector import Connector
from logic.generic_logic import GenericLogic
from core.util.mutex import Mutex
from qtpy import QtCore
import time


class LocalLaserScannerlogic(GenericLogic):
    """ Playground
    """
    confocalscanner1 = Connector(interface='NITTConfocalScanner')
    #savelogic = Connector(interface='SaveLogic')
    
    sigNextLine = QtCore.Signal()
    sigSwitchToCursorLoop = QtCore.Signal()
    sigSwitchToScanloop = QtCore.Signal()
    sigCursorLoopRepeat = QtCore.Signal()
    sigUpdatePlots = QtCore.Signal()
    sigScannerClockFrequencyChanged = QtCore.Signal()
    
    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self.threadlock = Mutex()

    def on_activate(self):
        """ Prepare logic module for work.
        """
        self._scanning_device = self.confocalscanner1()
        #self._save_logic = self.savelogic()

        

        self.smooth_V_unit = 0.002
        self.scan_time = 2
        self.return_speed = 5
        self.no_of_loops = 1000
        self.frequency_range = self._scanning_device.get_position_range()[0]
        self.voltage_range = self._scanning_device._scanner_voltage_ranges[0]
        self.no_of_bins = int((self.voltage_range[1] - self.voltage_range[0]) / self.smooth_V_unit)
        self.time_per_points = self.scan_time / self.no_of_bins
        self.V_MHz_ratio = (self.voltage_range[1] - self.voltage_range[0]) / (self.frequency_range[1] - self.frequency_range[0])
        self.MHz_unit = self.smooth_V_unit / self.V_MHz_ratio
        self.return_MHz_unit = self.return_speed * self.MHz_unit
        self._scanner_clock_frequency = int(1/self.time_per_points)
        self._scanning_device.scanner_set_position(self._scanning_device._current_position[0])
        self._main_cursor_position = self.frequency_range[0]
        self._start_f = int(self.frequency_range[0])
        self._stop_f = int(self.frequency_range[1])
        self.ref_binnum = int((self._stop_f - self._start_f) / self.MHz_unit)





        self.stopCursorLoopRequest = False
        self.stopScanLoopRequest = False
        self.sigNextLine.connect(self.scan_line, QtCore.Qt.QueuedConnection)
        self.sigCursorLoopRepeat.connect(self.cursorLoop, QtCore.Qt.QueuedConnection)

    def on_deactivate(self):
        """ Deactivate modeule.
        """
        self.stopMeasure()
        return 0


    def stopMeasure(self):
        """ Ask the measurement loop to stop. """
        with self.threadlock:
            if self.module_state() == 'locked':
                self.stopScanLoopRequest = True
        return 0

    
    def start_scan_loop(self):
        with self.threadlock:
            if self.module_state() == 'locked':
                self.log.error('Can not start scan. Logic is already locked.')
                return -1
            self.module_state.lock()
            self._scanning_device.close_scanner_clock_task()
            self._scanning_device.create_scanner_clock_task(clock_frequency = self._scanner_clock_frequency)
            self.sigNextLine.emit()
            return 0
    
    def scan_line(self):
        with self.threadlock:
            # If the measurement is not running do nothing
            if self.module_state() != 'locked':
                return

            # Stop measurement if stop has been requested
            if self.stopScanLoopRequest:
                self.stopScanLoopRequest = False
                self._scanning_device.close_scanner_clock_task()
                self._scanning_device.close_ai_task()
                self._scanning_device.close_counter_task()
                self.module_state.unlock()
                self.sigSwitchToCursorLoop.emit()
                return
            time.sleep(0.1)
            self.plot_y = self._scanning_device.scan_line(line_path=[self.plot_x],pixel_clock=True)[0]
            if np.any(self.plot_y == -1):
                self.stopScanLoopRequested = True
                self.sigNextLine.emit()
                return
                
            self._scanning_device.scan_line(line_path=[self.return_x], pixel_clock=False)
            self.plot_y_sum.append(self.plot_y)
            self.plot_y_average = np.mean(self.plot_y_sum, axis = 0)

            self._scan_loop_cnts = self._scan_loop_cnts + 1
            if self._scan_loop_cnts == self.no_of_loops:
                self.stopScanLoopRequest = True
            self.sigUpdatePlots.emit()
            self.sigNextLine.emit()
            return
    


    def set_sweep_parameters(self):
        pass

    def sweep_on(self):
        pass
        
    def moveToPosition(self, position):
        if self._scanning_device._current_position[0] == position:
            return
        if self._scanning_device._current_position[0] < position:
            _move_line = np.arange(self._scanning_device._current_position[0], position, self.MHz_unit*self.return_speed)

        else:
            _move_line = np.arange(self._scanning_device._current_position[0], position, -1* self.MHz_unit*self.return_speed)

        for step in _move_line:
            self._scanning_device.scanner_set_position(step)
        self._scanning_device.scanner_set_position(position)


    def cursorLoop(self):

        if self.stopCursorLoopRequest:
            self.stopCursorLoopRequest = False
            return
        self.moveToPosition(self._main_cursor_position)
        time.sleep(0.01)
        self.sigCursorLoopRepeat.emit()
    





