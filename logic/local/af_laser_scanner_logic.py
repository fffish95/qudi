# -*- coding: utf-8 -*-
"""
This file contains a Qudi logic module for controlling scans of the
fourth analog output channel.  It was originally written for
scanning laser frequency, but it can be used to control any parameter
in the experiment that is voltage controlled.  The hardware
range is typically -10 to +10 V.

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

from collections import OrderedDict
import datetime
import matplotlib.pyplot as plt
import numpy as np
import time
from enum import Enum 

from core.connector import Connector
from core.statusvariable import StatusVar
from core.util.mutex import Mutex
from logic.generic_logic import GenericLogic
from qtpy import QtCore


class CustomScanMode(Enum):
    XYPLOT = 0
    AO = 1
    FUNCTION = 2

class CustomScanXYPlotValues(Enum):
    MINIMUM = 0
    MEAN = 1
    MAXIMUM = 2


class LaserScannerHistoryEntry(QtCore.QObject):
    """ This class contains all relevant parameters of a laser scan.
        It provides methods to extract, restore and serialize this data.
    """

    def __init__(self, laserscanner):
        """ Make a laser scan data setting with default values. """
        super().__init__()

        # Reads in the maximal scanning range.
        self.x_range = laserscanner._scanning_device.get_position_range()[0]
        self.y_range = laserscanner._scanning_device.get_position_range()[1]
        self.z_range = laserscanner._scanning_device.get_position_range()[2]
        self.a_range = laserscanner._scanning_device.get_position_range()[3]

        # Sets the current position to the center of the maximal scanning range
        self.current_x = laserscanner._scanning_device.get_scanner_position()[0]
        self.current_y = laserscanner._scanning_device.get_scanner_position()[1]
        self.current_z = laserscanner._scanning_device.get_scanner_position()[2]
        self.current_a = self.a_range[0]

        # Sets the scan range of the image to the maximal scanning range
        self.scan_range = self.a_range

        # Default values for the resolution of the scan
        self.resolution = 5000

        # Default values for number of repeats
        self.number_of_repeats = 1000

        # Default scan speed
        self.scan_speed = int((self.a_range[1] - self.a_range[0])/2)

        # Variable to check if a scan is continuable
        self.scan_counter = 0
        self.scan_continuable = False

        # init plot_x
        self.plot_x = np.linspace(self.a_range[0], self.a_range[1], self.resolution)

        # Default values for custom scan
        self.custom_scan = False
        self.custom_scan_mode = CustomScanMode.FUNCTION.value
        self.custom_scan_values = CustomScanXYPlotValues.MINIMUM.value
        self.custom_scan_sweeps_per_action = 1
        self.custom_scan_x_range = self.x_range
        self.custom_scan_y_range = self.y_range
        self.custom_scan_z_range = self.z_range
        self.xyz_orders = [1,2,0]
        self.order_resolutions = [100,100,50]
    def restore(self, laserscanner):
        """ Write data back into laser scan logic and pull all the necessary strings"""
        laserscanner._current_x = self.current_x
        laserscanner._current_y = self.current_y
        laserscanner._current_z = self.current_z
        laserscanner._current_a = self.current_a
        laserscanner._scan_range = np.copy(self.scan_range)
        laserscanner._resolution = self.resolution
        laserscanner._number_of_repeats = self.number_of_repeats
        laserscanner._scan_speed = self.scan_speed
        laserscanner._scan_counter = self.scan_counter
        laserscanner._scan_continuable = self.scan_continuable
        laserscanner._custom_scan = False # To not init the plots in confocal logic
        if self.custom_scan_mode == 0:           
            laserscanner._custom_scan_mode = CustomScanMode.XYPLOT
        if self.custom_scan_mode == 1:           
            laserscanner._custom_scan_mode = CustomScanMode.AO
        if self.custom_scan_mode == 2:           
            laserscanner._custom_scan_mode = CustomScanMode.FUNCTION
        if self.custom_scan_values == 0:
            laserscanner._custom_scan_values = CustomScanXYPlotValues.MINIMUM
        if self.custom_scan_values == 1:
            laserscanner._custom_scan_values = CustomScanXYPlotValues.MEAN
        if self.custom_scan_values == 2:
            laserscanner._custom_scan_values = CustomScanXYPlotValues.MAXIMUM
        laserscanner._custom_scan_sweeps_per_action = self.custom_scan_sweeps_per_action
        laserscanner._custom_scan_x_range = np.copy(self.custom_scan_x_range)
        laserscanner._custom_scan_y_range = np.copy(self.custom_scan_y_range)
        laserscanner._custom_scan_z_range = np.copy(self.custom_scan_z_range)
        laserscanner._xyz_orders = np.copy(self.xyz_orders)
        laserscanner._order_resolutions = np.copy(self.order_resolutions)
        laserscanner.initialise_data_matrix()
        try:
            if laserscanner.trace_scan_matrix.shape == self.trace_scan_matrix.shape:
                laserscanner.trace_scan_matrix = np.copy(self.trace_scan_matrix)
            if laserscanner.retrace_scan_matrix.shape == self.retrace_scan_matrix.shape:
                laserscanner.retrace_scan_matrix = np.copy(self.retrace_scan_matrix)
            if laserscanner.trace_plot_y_sum.shape == self.trace_plot_y_sum.shape:
                laserscanner.trace_plot_y_sum = np.copy(self.trace_plot_y_sum)
            if laserscanner.trace_plot_y.shape == self.trace_plot_y.shape:
                laserscanner.trace_plot_y = np.copy(self.trace_plot_y)
            if laserscanner.retrace_plot_y.shape == self.retrace_plot_y.shape:
                laserscanner.retrace_plot_y = np.copy(self.retrace_plot_y)
            if laserscanner.plot_x.shape == self.plot_x.shape:
                laserscanner.plot_x = np.copy(self.plot_x)
        except AttributeError:
            self.trace_scan_matrix = np.copy(laserscanner.trace_scan_matrix)
            self.retrace_scan_matrix = np.copy(laserscanner.retrace_scan_matrix)
            self.trace_plot_y_sum = np.copy(laserscanner.trace_plot_y_sum)
            self.trace_plot_y = np.copy(laserscanner.trace_plot_y)
            self.retrace_plot_y = np.copy(laserscanner.retrace_plot_y)
            self.plot_x = np.copy(laserscanner.plot_x)
        laserscanner._custom_scan = self.custom_scan

    def snapshot(self, laserscanner):
        """ Extract all necessary data from a laserscanner logic and keep it for later use """
        self.current_x = laserscanner._current_x
        self.current_y = laserscanner._current_y
        self.current_z = laserscanner._current_z
        self.current_a = laserscanner._current_a 
        self.scan_range = np.copy(laserscanner._scan_range)
        self.resolution = laserscanner._resolution
        self.number_of_repeats = laserscanner._number_of_repeats
        self.scan_speed = laserscanner._scan_speed
        self.scan_counter = laserscanner._scan_counter
        self.scan_continuable = laserscanner._scan_continuable
        self.custom_scan = laserscanner._custom_scan
        self.custom_scan_mode = laserscanner._custom_scan_mode.value
        self.custom_scan_values = laserscanner._custom_scan_values.value 
        self.custom_scan_sweeps_per_action = laserscanner._custom_scan_sweeps_per_action
        self.custom_scan_x_range = np.copy(laserscanner._custom_scan_x_range)
        self.custom_scan_y_range = np.copy(laserscanner._custom_scan_y_range)
        self.custom_scan_z_range = np.copy(laserscanner._custom_scan_z_range)
        self.xyz_orders = np.copy(laserscanner._xyz_orders)
        self.order_resolutions = np.copy(laserscanner._order_resolutions)

        self.trace_scan_matrix = np.copy(laserscanner.trace_scan_matrix)
        self.retrace_scan_matrix = np.copy(laserscanner.retrace_scan_matrix)
        self.trace_plot_y_sum = np.copy(laserscanner.trace_plot_y_sum)
        self.trace_plot_y = np.copy(laserscanner.trace_plot_y)
        self.retrace_plot_y = np.copy(laserscanner.retrace_plot_y)
        self.plot_x = np.copy(laserscanner.plot_x)

    def serialize(self):
        """ Give out a dictionary that can be saved via the usua means """
        serialized = dict()
        serialized['focus_position'] = [self.current_x, self.current_y, self.current_z, self.current_a]
        serialized['scan_range'] = list(self.scan_range)
        serialized['resolution'] = self.resolution
        serialized['number_of_repeats'] = self.number_of_repeats
        serialized['scan_speed'] = self.scan_speed
        serialized['scan_counter'] = self.scan_counter
        serialized['scan_continuable'] = self.scan_continuable
        serialized['custom_scan'] = self.custom_scan
        serialized['custom_scan_mode'] = self.custom_scan_mode
        serialized['custom_scan_values'] = self.custom_scan_values
        serialized['custom_scan_sweeps_per_action'] = self.custom_scan_sweeps_per_action
        serialized['custom_scan_x_range'] = list(self.custom_scan_x_range)
        serialized['custom_scan_y_range'] = list(self.custom_scan_y_range)
        serialized['custom_scan_z_range'] = list(self.custom_scan_z_range)
        serialized['xyz_orders'] = list(self.xyz_orders)
        serialized['order_resolutions'] = list(self.order_resolutions)

        serialized['trace_scan_matrix'] = self.trace_scan_matrix
        serialized['retrace_scan_matrix'] = self.retrace_scan_matrix
        serialized['trace_plot_y_sum'] = self.trace_plot_y_sum
        serialized['trace_plot_y'] = self.trace_plot_y 
        serialized['retrace_plot_y'] = self.retrace_plot_y
        serialized['plot_x'] = self.plot_x
        return serialized

    def deserialize(self, serialized):
        """ Restore laser scanner history object from a dict """
        if 'focus_position' in serialized and len(serialized['focus_position']) == 4:
            self.current_x = serialized['focus_position'][0]
            self.current_y = serialized['focus_position'][1]
            self.current_z = serialized['focus_position'][2]
            self.current_a = serialized['focus_position'][3]
        if 'scan_range' in serialized and len(serialized['scan_range']) ==2:
            self.scan_range = serialized['scan_range']
        if 'resolution' in serialized:
            self.resolution = serialized['resolution']
        if 'number_of_repeats' in serialized:
            self.number_of_repeats = serialized['number_of_repeats']
        if 'scan_speed' in serialized:
            self.scan_speed = serialized['scan_speed']
        if 'scan_counter' in serialized:
            self.scan_counter = serialized['scan_counter']
        if 'scan_continuable' in serialized:
            self.scan_continuable = serialized['scan_continuable']
        if 'custom_scan' in serialized:
            self.custom_scan = serialized['custom_scan']
        if 'custom_scan_mode' in serialized:
            self.custom_scan_mode = serialized['custom_scan_mode']
        if 'custom_scan_values' in serialized:
            self.custom_scan_values = serialized['custom_scan_values']
        if 'custom_scan_sweeps_per_action' in serialized:
            self.custom_scan_sweeps_per_action = serialized['custom_scan_sweeps_per_action']
        if 'custom_scan_x_range' in serialized and len(serialized['custom_scan_x_range']) == 2:
            self.custom_scan_x_rangen = serialized['custom_scan_x_range']
        if 'custom_scan_y_range' in serialized and len(serialized['custom_scan_y_range']) == 2:
            self.custom_scan_y_rangen = serialized['custom_scan_y_range']
        if 'custom_scan_z_range' in serialized and len(serialized['custom_scan_z_range']) == 2:
            self.custom_scan_z_rangen = serialized['custom_scan_z_range']
        if 'xyz_orders' in serialized and len(serialized['xyz_orders']) == 3:
            self.xyz_orders = serialized['xyz_orders']
        if 'order_resolutions' in serialized and len(serialized['order_resolutions']) == 3:
            self.order_resolutions = serialized['order_resolutions']            
        
        if 'trace_scan_matrix' in serialized:
            self.trace_scan_matrix = serialized['trace_scan_matrix']
        if 'retrace_scan_matrix' in serialized:
            self.retrace_scan_matrix = serialized['retrace_scan_matrix']
        if 'trace_plot_y_sum' in serialized:
            self.trace_plot_y_sum = serialized['trace_plot_y_sum']
        if 'trace_plot_y' in serialized:
            self.trace_plot_y = serialized['trace_plot_y']
        if 'retrace_plot_y' in serialized:
            self.retrace_plot_y = serialized['retrace_plot_y']
        if 'plot_x' in serialized:
            self.plot_x = serialized['plot_x']



class LaserScannerLogic(GenericLogic):

    """This is the logic class for laser scanner.
    """

    # declare connectors
    laserscannerscanner1 = Connector(interface='NITTConfocalScanner')
    confocallogic1 = Connector(interface='ConfocalLogic')
    savelogic = Connector(interface='SaveLogic')

    # status vars
    _smoothing_steps = StatusVar(default=10)
    _order_3_counter = StatusVar(default=0)
    _oneline_scanner_frequency = StatusVar(default=20000)
    _goto_speed = StatusVar(default=100)

    max_history_length = StatusVar(default=10)

    # signals
    signal_start_scanning = QtCore.Signal(str)
    signal_continue_scanning = QtCore.Signal(str)
    signal_scan_lines_next = QtCore.Signal()
    signal_trace_plots_updated = QtCore.Signal()
    signal_retrace_plots_updated = QtCore.Signal()
    signal_change_position = QtCore.Signal(str)
    signal_save_started = QtCore.Signal()
    signal_data_saved = QtCore.Signal()
    signal_clock_frequency_updated = QtCore.Signal()
    signal_custom_scan_range_updated = QtCore.Signal()
    signal_initialise_matrix = QtCore.Signal()

    _signal_save_data = QtCore.Signal(object, object)

    signal_history_event = QtCore.Signal()


    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # locking for thread safety
        self.threadlock = Mutex()

        self._scan_counter = 0
        self.stopRequested = False
        self._custom_scan = False
        self._move_to_start = True


    def on_activate(self):
        """ Initialisation performed during activation of the module.
        """
        self._scanning_device = self.laserscannerscanner1()
        self._confocal_logic = self.confocallogic1()
        self._save_logic = self.savelogic()

        # Reads in the maximal scanning range. 
        self.a_range = self._scanning_device.get_position_range()[3]

        # restore history in StatusVariables
        self.load_history_config()

        # Sets connections between signals and functions
        self.signal_scan_lines_next.connect(self._scan_line, QtCore.Qt.QueuedConnection)
        self.signal_start_scanning.connect(self.start_scanner, QtCore.Qt.QueuedConnection)
        self.signal_continue_scanning.connect(self.continue_scanner, QtCore.Qt.QueuedConnection)

        self._signal_save_data.connect(self._save_data, QtCore.Qt.QueuedConnection)
        



    def on_deactivate(self):
        """ Deinitialisation performed during deactivation of the module.
        """
        self.stopRequested = True
        closing_state = LaserScannerHistoryEntry(self)
        closing_state.snapshot(self)
        self._statusVariables['history_0'] = closing_state.serialize()
        return 0
    
    def save_history_config(self):
        state_config = LaserScannerHistoryEntry(self)
        state_config.snapshot(self)
        self.history.append(state_config)
        histindex = 0
        for state in reversed(self.history):
            self._statusVariables['history_{0}'.format(histindex)] = state.serialize()
            histindex += 1

    def load_history_config(self):
        # restore here ...
        self.history = []
        for i in reversed(range(1, self.max_history_length)):
            try:
                new_history_item = LaserScannerHistoryEntry(self)
                new_history_item.deserialize(
                    self._statusVariables['history_{0}'.format(i)])
                self.history.append(new_history_item)
            except KeyError:
                pass
            except:
                self.log.warning(
                        'Restoring history {0} failed.'.format(i))
        try:
            new_state = LaserScannerHistoryEntry(self)
            new_state.deserialize(self._statusVariables['history_0'])
            new_state.restore(self)
        except:
            new_state = LaserScannerHistoryEntry(self)
            new_state.restore(self)
        finally:
            self.history.append(new_state)

        self.history_index = len(self.history) - 1
        self.history[self.history_index].restore(self)
        self.signal_trace_plots_updated.emit()
        self.signal_retrace_plots_updated.emit()
        # clock frequency is not in status variables, set clock frequency
        self.set_clock_frequency()
        self._change_position()
        self._confocal_logic.set_position(tag='laserscanner', x = self._current_x, y = self._current_y, z = self._current_z)
        self.signal_change_position.emit('history')
        self.signal_history_event.emit()

    def history_forward(self):
        """ Move forward in history.
        """
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            self.history[self.history_index].restore(self)
            self.signal_trace_plots_updated.emit()
            self.signal_retrace_plots_updated.emit()
            # clock frequency is not in status variables, set clock frequency
            self.set_clock_frequency()
            self._change_position()
            self._confocal_logic.set_position(tag='laserscanner', x = self._current_x, y = self._current_y, z = self._current_z)
            self.signal_change_position.emit('history')
            self.signal_history_event.emit()

    def history_back(self):
        """ Move backwards in history.
        """
        if self.history_index > 0:
            self.history_index -= 1
            self.history[self.history_index].restore(self)
            self.signal_trace_plots_updated.emit()
            self.signal_retrace_plots_updated.emit()
            # clock frequency is not in status variables, set clock frequency
            self.set_clock_frequency()
            self._change_position()
            self._confocal_logic.set_position(tag='laserscanner', x = self._current_x, y = self._current_y, z = self._current_z)
            self.signal_change_position.emit('history')
            self.signal_history_event.emit()


    def set_clock_frequency(self):
        scan_range = abs(self._scan_range[1] - self._scan_range[0])
        duration = scan_range / self._scan_speed
        clock_frequency = self._resolution / duration
        self._clock_frequency = float(clock_frequency)
        self.signal_clock_frequency_updated.emit()
        # checks if scanner is still running:
        if self._clock_frequency > 250000:
            self.log.error('Clock frequency too high, please reduce resolution or slow down speed.')
            return -1
        if self.module_state() == 'locked':
            return -1
        else:
            return 0

    def start_scanning(self, custom_scan = False, tag = 'logic'):
        self._scan_counter = 0
        self._custom_scan = custom_scan
        if not self._custom_scan:
            self._scan_continuable = True
        else:
            self._scan_continuable = False
        self._move_to_start = True
        self.signal_start_scanning.emit(tag)
        return 0

    def continue_scanning(self, tag = 'logic'):
        self._move_to_start = True
        self.signal_continue_scanning.emit(tag)
        return 0
    
    def stop_scanning(self):
        with self.threadlock:
            if self.module_state() == 'locked':
                self.stopRequested = True
        return 0

    def update_confocal_scan_range(self):
        self._confocal_logic.image_x_range[0] = self._custom_scan_x_range[0]
        self._confocal_logic.image_x_range[1] = self._custom_scan_x_range[1]
        self._confocal_logic.image_y_range[0] = self._custom_scan_y_range[0]
        self._confocal_logic.image_y_range[1] = self._custom_scan_y_range[1]
        self._confocal_logic.image_z_range[0] = self._custom_scan_z_range[0]
        self._confocal_logic.image_z_range[1] = self._custom_scan_z_range[1]

        if self._custom_scan_mode.value == 0:
            self._confocal_logic.xy_resolution = self._order_resolutions[0]
            self._confocal_logic.z_resolution = self._order_resolutions[2]
        self._confocal_logic.signal_scan_range_updated.emit()

    def get_confocal_scan_range(self):
        self._custom_scan_x_range[0] = self._confocal_logic.image_x_range[0]
        self._custom_scan_x_range[1] = self._confocal_logic.image_x_range[1]
        self._custom_scan_y_range[0] = self._confocal_logic.image_y_range[0]
        self._custom_scan_y_range[1] = self._confocal_logic.image_y_range[1]
        self._custom_scan_z_range[0] = self._confocal_logic.image_z_range[0]
        self._custom_scan_z_range[1] = self._confocal_logic.image_z_range[1]
        self.signal_custom_scan_range_updated.emit()

    def initialise_data_matrix(self): 
        self.trace_scan_matrix = np.zeros((self._number_of_repeats, self._resolution, 4 + len(self.get_scanner_count_channels())))
        self.retrace_scan_matrix = np.zeros((self._number_of_repeats, self._resolution, 4 + len(self.get_scanner_count_channels())))
        self.trace_plot_y_sum = np.zeros((len(self.get_scanner_count_channels()), self._resolution))
        self.trace_plot_y = np.zeros((len(self.get_scanner_count_channels()), self._resolution))
        self.retrace_plot_y = np.zeros((len(self.get_scanner_count_channels()), self._resolution))
        self.plot_x = np.linspace(self._scan_range[0], self._scan_range[1], self._resolution)
        self.signal_initialise_matrix.emit()


        if self._custom_scan and self._custom_scan_mode.value <2:

            self._confocal_logic._zscan = False
            self._confocal_logic._xyscan_continuable = False
            self._confocal_logic._scan_counter = 0
            self.update_confocal_scan_range()
            # x1: x-start-value, x2: x-end-value
            x1, x2 = self._custom_scan_x_range[0], self._custom_scan_x_range[1]
            # y1: y-start-value, y2: y-end-value
            y1, y2 = self._custom_scan_y_range[0], self._custom_scan_y_range[1]
            # z1: z-start-value, z2: x-end-value
            z1, z2 = self._custom_scan_z_range[0], self._custom_scan_z_range[1]

            if x2 < x1:
                self.log.error(
                    'x1 must be smaller than x2, but they are '
                    '({0:.3f},{1:.3f}).'.format(x1, x2))
                return -1 
            if y2 < y1:
                self.log.error(
                    'y1 must be smaller than y2, but they are '
                    '({0:.3f},{1:.3f}).'.format(y1, y2))
                return -1
            if z2 < z1:
                self.log.error(
                    'z1 must be smaller than z2, but they are '
                    '({0:.3f},{1:.3f}).'.format(z1, z2))
                return -1

            xyz1 = [x1,y1,z1]
            xyz2 = [x2,y2,y2]
            self._XYZ = []
            for i in range(0,3):
                if self._xyz_orders[i] > 0:
                    self._XYZ.append(np.linspace( xyz1[i], xyz2[i], self._order_resolutions[self._xyz_orders[i]-1]))
                else:
                    self._XYZ.append(np.linspace( xyz1[i], xyz2[i], 1))
            if self._custom_scan_mode.value == 0:
                self._confocal_logic.xy_image = np.zeros((
                        len(self._XYZ[1]),
                        len(self._XYZ[0]),
                        3 + len(self.get_scanner_count_channels())
                    ))
                self._confocal_logic.xy_image[:, :, 0] = np.full(
                    (len(self._XYZ[1]), len(self._XYZ[0])), self._XYZ[0])
                y_value_matrix = np.full((len(self._XYZ[0]), len(self._XYZ[1])), self._XYZ[1])
                self._confocal_logic.xy_image[:, :, 1] = y_value_matrix.transpose()
                self._confocal_logic.xy_image[:, :, 2] = self._XYZ[2][self._order_3_counter] * np.ones(
                    (len(self._XYZ[1]), len(self._XYZ[0])))
                self._confocal_logic.sigImageXYInitialized.emit()
    
    def start_scanner(self, tag):
        """Setting up the scanner device and starts the scanning procedure

        @return int: error code (0:OK, -1:error)
        """
        if tag != 'custom_scan':
            self.module_state.lock()
        self._scanning_device.module_state.lock()
        if self._custom_scan and self._custom_scan_mode.value < 2:
            self._confocal_logic.module_state.lock()
            self._confocal_logic.signal_custom_scan_started.emit()
        
        clock_status = self._scanning_device.set_up_scanner_clock(
            clock_frequency=self._clock_frequency)

        if clock_status < 0:
            self._scanning_device.module_state.unlock()
            self.module_state.unlock()
            if self._custom_scan and self._custom_scan_mode.value < 2:
                self._confocal_logic.module_state.unlock()
            self._change_position()
            self._confocal_logic.set_position(tag='laserscanner', x = self._current_x, y = self._current_y, z = self._current_z)
            return -1
        
        scanner_status = self._scanning_device.set_up_scanner()

        if scanner_status < 0:
            self._scanning_device.close_scanner_clock()
            self._scanning_device.module_state.unlock()
            self.module_state.unlock()
            if self._custom_scan and self._custom_scan_mode.value < 2:
                self._confocal_logic.module_state.unlock()
            self._change_position()
            self._confocal_logic.set_position(tag='laserscanner', x = self._current_x, y = self._current_y, z = self._current_z)
            return -1
                

        if tag != 'custom_scan':
            self.initialise_data_matrix()
            self.signal_scan_lines_next.emit()
        
        self.current_x = self._scanning_device.get_scanner_position()[0]
        self.current_y = self._scanning_device.get_scanner_position()[1]
        self.current_z = self._scanning_device.get_scanner_position()[2]
        self.current_a = self._scanning_device.get_scanner_position()[3]
        return 0
    
    def start_oneline_scanner(self):
        self._scanning_device.module_state.lock()

        clock_status = self._scanning_device.set_up_scanner_clock(
            clock_frequency=self._oneline_scanner_frequency)

        if clock_status < 0:
            self._scanning_device.module_state.unlock()
            self.module_state.unlock()
            self._change_position()
            self._confocal_logic.set_position(tag='laserscanner', x = self._current_x, y = self._current_y, z = self._current_z)
            return -1

        scanner_status = self._scanning_device.set_up_scanner()

        if scanner_status < 0:
            self._scanning_device.close_scanner_clock()
            self._scanning_device.module_state.unlock()
            self.module_state.unlock()
            self._change_position()
            self._confocal_logic.set_position(tag='laserscanner', x = self._current_x, y = self._current_y, z = self._current_z)
            return -1
        return 0
    
    def continue_scanner(self):
        """Continue the scanning procedure
        @return int: error code (0:OK, -1:error)
        """
        self.module_state.lock()
        self._scanning_device.module_state.lock()

        clock_status = self._scanning_device.set_up_scanner_clock(
            clock_frequency=self._clock_frequency)

        if clock_status < 0:
            self._scanning_device.module_state.unlock()
            self.module_state.unlock()
            self._change_position()
            self._confocal_logic.set_position(tag='laserscanner', x = self._current_x, y = self._current_y, z = self._current_z)
            return -1

        scanner_status = self._scanning_device.set_up_scanner()

        if scanner_status < 0:
            self._scanning_device.close_scanner_clock()
            self._scanning_device.module_state.unlock()
            self.module_state.unlock()
            self._change_position()
            self._confocal_logic.set_position(tag='laserscanner', x = self._current_x, y = self._current_y, z = self._current_z)
            return -1

        self.signal_scan_lines_next.emit()
        return 0

    def kill_scanner(self):
        """Closing the scanner device.

        @return int: error code (0:OK, -1:error)
        """
        try:
            self._scanning_device.close_scanner()
        except Exception as e:
            self.log.exception('Could not close the scanner.')
        try:
            self._scanning_device.close_scanner_clock()
        except Exception as e:
            self.log.exception('Could not close the scanner clock.')
        try:
            self._scanning_device.module_state.unlock()
        except Exception as e:
            self.log.exception('Could not unlock scanning device.')
        if self._custom_scan and self._custom_scan_mode.value < 2:
            try:
                self._confocal_logic.module_state.unlock()
            except Exception as e:
                self.log.exception('Could not unlock the confocal logic.')

        return 0

    def _generate_ramp(self, position_start, position_end, x = None, y = None, z = None):
        if x is None:
            x = self._scanning_device.get_scanner_position()[0]
        if y is None:
            y = self._scanning_device.get_scanner_position()[1]
        if z is None:
            z = self._scanning_device.get_scanner_position()[2]
        
        if position_start == position_end:
            ramp = np.array([position_start, position_end])
        else:
            linear_position_step = self._scan_speed / self._clock_frequency
            smoothing_range = self._smoothing_steps + 1

            position_range_of_accel = sum(n * linear_position_step / smoothing_range for n in range(0, smoothing_range)
            )
            if position_start < position_end:
                position_min = position_start
                position_max = position_end
            else:
                position_min = position_end
                position_max = position_start
            position_min_linear = position_min + position_range_of_accel
            position_max_linear = position_max - position_range_of_accel

            if (position_max_linear - position_min_linear) / linear_position_step < self._smoothing_steps:
                ramp = np.linspace(position_start,position_end, self._resolution)
            else:
                num_of_linear_steps = np.round(self._resolution - 2*self._smoothing_steps)

                smooth_curve = np.array(
                    [sum(
                        n * linear_position_step / smoothing_range for n in range(1, N)
                    ) for N in range(1, smoothing_range)
                    ])
                accel_part = position_min + smooth_curve
                decel_part = position_max - smooth_curve[::-1]

                linear_part = np.linspace(position_min_linear, position_max_linear, num_of_linear_steps)
                ramp = np.hstack((accel_part, linear_part, decel_part))
                if position_start > position_end:
                    ramp = ramp[::-1]
        move_line = np.vstack((
            np.ones((len(ramp), )) * x,
            np.ones((len(ramp), )) * y,
            np.ones((len(ramp), )) * z,
            ramp
            ))
        return move_line

    def set_position(self, x=None, y=None, z=None, a=None):
        """Update the current position to the destination position
        """
        # Changes the respective value
        if x is not None:
            self._current_x = x
        else: 
            self._current_x = self._scanning_device.get_scanner_position()[0]
        if y is not None:
            self._current_y = y
        else: 
            self._current_y = self._scanning_device.get_scanner_position()[1]
        if z is not None:
            self._current_z = z
        else: 
            self._current_z = self._scanning_device.get_scanner_position()[2]

        if a is not None:
            self._current_a = a
        else: 
            self._current_a = self._scanning_device.get_scanner_position()[3]

    def _change_position(self):
        """ Let hardware move to current a"""
        ramp = np.linspace(self._scanning_device.get_scanner_position()[3], self._current_a, self._goto_speed)
        move_line = np.vstack((
            np.ones((len(ramp), )) * self._scanning_device.get_scanner_position()[0],
            np.ones((len(ramp), )) * self._scanning_device.get_scanner_position()[1],
            np.ones((len(ramp), )) * self._scanning_device.get_scanner_position()[2],
            ramp
            ))
        self.module_state.lock()
        self.start_oneline_scanner()
        move_line_counts = self._scanning_device.scan_line(move_line)
        self.kill_scanner()
        self.module_state.unlock()
        return 0
    
    def get_scanner_count_channels(self):
        """ Get lis of counting channels from scanning device.
          @return list(str): names of counter channels
        """
        return self._scanning_device.get_scanner_count_channels()

    
    def _scan_line(self):

        # stops scanning
        if self.stopRequested:
            with self.threadlock:
                self.kill_scanner()
                self.stopRequested = False
                self.module_state.unlock()
                self.signal_trace_plots_updated.emit()
                self.signal_retrace_plots_updated.emit()
                if self._custom_scan and self._custom_scan_mode.value < 2:
                    self.custom_scan_xyz_stop()
                # add new history entry
                new_history = LaserScannerHistoryEntry(self)
                new_history.snapshot(self)
                self.history.append(new_history)
                if len(self.history) > self.max_history_length:
                    self.history.pop(0)
                self.history_index = len(self.history) - 1
                self._confocal_logic.set_position(tag='laserscanner', x = self._current_x, y = self._current_y, z = self._current_z)
                return



        try:
            if self._custom_scan and self._custom_scan_mode.value < 2 :
                self.custom_scan_xyz_prepare()
            if self._move_to_start:
                move_line = self._generate_ramp(self._scanning_device.get_scanner_position()[3], self._scan_range[0])
                move_line_counts = self._scanning_device.scan_line(move_line)
                if np.any(move_line_counts == -1):
                    self.stop_scanning()
                    self.signal_scan_lines_next.emit()
                    return
            trace_line = self._generate_ramp(self._scan_range[0], self._scan_range[1])
            counts_on_trace_line = self._scanning_device.scan_line(trace_line, pixel_clock = True)
            if np.any(counts_on_trace_line == -1):
                self.stop_scanning()
                self.signal_scan_lines_next.emit()
                return
            scan_counter = self._scan_counter
            # add scan counter here to make sure the display in gui displays the corresponding number for the nth line
            self._scan_counter += 1
            self.trace_scan_matrix[scan_counter, :, :4] = trace_line.transpose()
            self.trace_scan_matrix[scan_counter, :, 4:] = counts_on_trace_line
            self.trace_plot_y_sum +=  counts_on_trace_line.transpose()
            self.trace_plot_y = counts_on_trace_line.transpose()
            self.signal_trace_plots_updated.emit()


            retrace_line = self._generate_ramp(self._scan_range[1], self._scan_range[0])
            counts_on_retrace_line = self._scanning_device.scan_line(retrace_line, pixel_clock = True)
            if np.any(counts_on_retrace_line == -1):
                self.stop_scanning()
                self.signal_scan_lines_next.emit()
                return
            
            self.retrace_scan_matrix[scan_counter, :, :4] = retrace_line.transpose()           
            self.retrace_scan_matrix[scan_counter, :, 4:] = counts_on_retrace_line
            self.retrace_plot_y = counts_on_retrace_line.transpose()
            self.signal_retrace_plots_updated.emit()



            if self._custom_scan and self._custom_scan_mode.value < 2:
                self.custom_scan_xyz_process()
            
            elif self._scan_counter >= self._number_of_repeats:
                self.stop_scanning()
                self._scan_continuable = False
            
            self.signal_scan_lines_next.emit()
        except:
            self.log.exception('The scan went wrong, killing the scanner.')
            self.stop_scanning()
            self.signal_scan_lines_next.emit()

    def custom_scan_xyz_prepare(self):
        self._xyz_counter = np.zeros(3)
        for i in range(0,3):
            if self._xyz_orders[i] == 1:
                self._xyz_counter[i] = (self._scan_counter // self._custom_scan_sweeps_per_action) % self._order_resolutions[0]
            if self._xyz_orders[i] == 2:
                self._xyz_counter[i] = (self._scan_counter // self._custom_scan_sweeps_per_action) // self._order_resolutions[0]
            if self._xyz_orders[i] == 3:
                self._xyz_counter[i] = self._order_3_counter
            
        # when it is needed to change the point...
        if self._scan_counter % self._custom_scan_sweeps_per_action == 0:
            self.kill_scanner()
            self.set_position(x = self._XYZ[0][int(self._xyz_counter[0])], y = self._XYZ[1][int(self._xyz_counter[1])], z = self._XYZ[2][int(self._xyz_counter[2])])                
            self._confocal_logic.set_position(tag='laserscanner', x = self._current_x, y = self._current_y, z = self._current_z)
            self.start_scanner(tag = 'custom_scan')
    
    def custom_scan_xyz_process(self):
        # when it is needed to record the value...
        if self._scan_counter % self._custom_scan_sweeps_per_action == 0 and self._custom_scan_mode.value == 0:
            data_array = []
            for i in range(0, self._custom_scan_sweeps_per_action):
                data_array.append(self.trace_scan_matrix[self._scan_counter-1-i,:, 4:])
            data_array = np.array(data_array)
            for s_ch in range(0,len(self.get_scanner_count_channels())):
                data_ch_array=[]
                for i in range(0, np.shape(data_array)[1]):
                    data_ch_array.append(np.mean(data_array.T[s_ch][i]))
                if self._custom_scan_values.value == 0:
                    point_value = np.max(data_ch_array) - np.min(data_ch_array)
                if self._custom_scan_values.value == 1:
                    point_value = np.mean(data_ch_array)  
                if self._custom_scan_values.value == 2:
                    point_value = np.max(data_ch_array)
                self._confocal_logic.xy_image[:, :, 3 + s_ch][int(self._xyz_counter[1]), int(self._xyz_counter[0])] = point_value
            
            self._confocal_logic.signal_xy_image_updated.emit()

        # when it is needed to change z value or stop the scan
        if self._scan_counter >= self._number_of_repeats:
            self._order_3_counter += 1
            self.save_data()
            if self._custom_scan_mode.value == 0:
                self._confocal_logic.save_xy_data()

            if 3 not in self._xyz_orders or self._order_3_counter >= self._order_resolutions[2]:
                self.stop_scanning()
            else:
                self._scan_counter = 0
                self.initialise_data_matrix()
    
    def custom_scan_xyz_stop(self):
        self._confocal_logic.set_position(tag='laserscanner', x = self._current_x, y = self._current_y, z = self._current_z)
        self._custom_scan = False
        self._order_3_counter = 0
        self._confocal_logic.signal_custom_scan_stopped.emit()
        if self._custom_scan_mode.value == 0:
            self._confocal_logic.signal_xy_image_updated.emit()
            self._confocal_logic.add_new_history_entry()

    def set_scan_range(self, scan_range):
        """ Set the scan rnage """
        self._scan_range = scan_range
        self.set_clock_frequency()

    def set_scan_speed(self, scan_speed):
        """ Set scan speed in volt per second """
        self._scan_speed = np.clip(scan_speed, 1e-9, 2e6)
        self.set_clock_frequency()
    
    def set_resolution(self, resolution):
        self._resolution = int(np.clip(resolution, 1, 1e6))
        self.set_clock_frequency()
    

    def set_number_of_repeats(self, number_of_repeats):
        self._number_of_repeats = int(np.clip(number_of_repeats, 1, 1e6))

    def save_data(self, colorscale_range=None, percentile_range=None, block=True):

        if block:
            self._save_data(colorscale_range, percentile_range)
        else:
            self._signal_save_data.emit(colorscale_range, percentile_range)

    @QtCore.Slot(object, object)    
    def _save_data(self, colorscale_range=None, percentile_range=None):
        """ Save the counter trace data and writes it to a file.

        @return int: error code (0:OK, -1:error)
        """

        self._saving_stop_time = time.time()

        self.signal_save_started.emit()
        filepath = self._save_logic.get_path_for_module('af_laserscanner')
        timestamp = datetime.datetime.now()

        parameters = OrderedDict()
        
        parameters['Number_of_frequency_sweeps'] = self._scan_counter
        parameters['Start_Position_(MHz)'] = self._scan_range[0]
        parameters['Stop_Position_(MHz)'] = self._scan_range[1]
        parameters['Scan_speed'] = self._scan_speed
        parameters['Resolution'] = self._resolution
        parameters['Clock_Frequency_(Hz)'] = self._clock_frequency

        if self._custom_scan and self._custom_scan_mode.value < 2:
            parameters['custom_scan_mode'] = self._custom_scan_mode.name
            parameters['custom_scan_values'] = self._custom_scan_values.name
            parameters['custom_scan_sweeps_per_action'] = self._custom_scan_sweeps_per_action
            parameters['X_min'] = self._custom_scan_x_range[0]
            parameters['X_max'] = self._custom_scan_x_range[1]
            parameters['X_order'] = self._xyz_orders[0]
            parameters['current_x'] = self._current_x
            parameters['Y_min'] = self._custom_scan_y_range[0]
            parameters['Y_max'] = self._custom_scan_y_range[1]
            parameters['Y_order'] = self._xyz_orders[1]
            parameters['current_y'] = self._current_y
            parameters['Z_min'] = self._custom_scan_z_range[0]
            parameters['Z_max'] = self._custom_scan_z_range[1]
            parameters['Z_order'] = self._xyz_orders[2]
            parameters['current_z'] = self._current_z
            parameters['order_1_resolution'] = self._order_resolutions[0]
            parameters['order_2_resolution'] = self._order_resolutions[1]
            parameters['order_3_resolution'] = self._order_resolutions[2]

        fit_y = np.zeros(len(self.plot_x))
        figs = {ch: self.draw_figure(matrix_data=self.trace_scan_matrix[:self._scan_counter, :, 4 + n],
                                     freq_data = self.plot_x,
                                     count_data = self.trace_plot_y[n,:],
                                     fit_freq_vals = self.plot_x,
                                     fit_count_vals = fit_y,
                                     cbar_range=colorscale_range,
                                     percentile_range=percentile_range,)
                for n, ch in enumerate(self.get_scanner_count_channels())}
        # Save the image data and figure
        for n, ch in enumerate(self.get_scanner_count_channels()):
            # data for the text-array "image":
            image_data = OrderedDict()
            image_data['Trace matrix data.\n'] = self.trace_scan_matrix[:self._scan_counter, :, 4 + n]

            filelabel = 'Laserscanner_trace_image_{0}'.format(ch.replace('/', ''))
            self._save_logic.save_data(image_data,
                                       filepath=filepath,
                                       timestamp=timestamp,
                                       parameters=parameters,
                                       filelabel=filelabel,
                                       fmt='%.6e',
                                       delimiter='\t',
                                       plotfig=figs[ch])


        

        fit_y = np.zeros(len(self.plot_x))
        figs = {ch: self.draw_figure(matrix_data=self.retrace_scan_matrix[:self._scan_counter, :, 4 + n],
                                     freq_data = self.plot_x,
                                     count_data = self.retrace_plot_y[n,:],
                                     fit_freq_vals = self.plot_x,
                                     fit_count_vals = fit_y,
                                     cbar_range=colorscale_range,
                                     percentile_range=percentile_range,)
                for n, ch in enumerate(self.get_scanner_count_channels())}
        # Save the image data and figure
        for n, ch in enumerate(self.get_scanner_count_channels()):
            # data for the text-array "image":
            image_data = OrderedDict()
            image_data['Rerace matrix data.\n'] = self.retrace_scan_matrix[:self._scan_counter, :, 4 + n]

            filelabel = 'Laserscanner_retrace_image_{0}'.format(ch.replace('/', ''))
            self._save_logic.save_data(image_data,
                                       filepath=filepath,
                                       timestamp=timestamp,
                                       parameters=parameters,
                                       filelabel=filelabel,
                                       fmt='%.6e',
                                       delimiter='\t',
                                       plotfig=figs[ch])

            # prepare the full raw data in an OrderedDict:
        data = OrderedDict()

        data['x_position'] = self.trace_scan_matrix[:, :, 0].flatten()
        data['y_position'] = self.trace_scan_matrix[:, :, 1].flatten()
        data['z_position'] = self.trace_scan_matrix[:, :, 2].flatten()
        data['Frequency_(MHz)'] = self.trace_scan_matrix[:, :, 3].flatten()

        for n, ch in enumerate(self.get_scanner_count_channels()):
            if ch.lower().startswith('ch') or ch.lower().startswith('all'):
                data['count_rate_{0}_(Hz)'.format(ch)] = self.trace_scan_matrix[:self._scan_counter, :, 4 + n].flatten()
            elif ch.lower().startswith('ai'):
                data['signal_{0}_(V)'.format(ch)] = self.trace_scan_matrix[:self._scan_counter, :, 4 + n].flatten()
            else:
                data['signal_{0}_(a.u.)'.format(ch)] = self.trace_scan_matrix[:self._scan_counter, :, 4 + n].flatten()

        # Save the raw data to file
        filelabel = 'laser_scanner_trace_raw_data'
        self._save_logic.save_data(data,
                                   filepath=filepath,
                                   timestamp=timestamp,
                                   parameters=parameters,
                                   filelabel=filelabel,
                                   fmt='%.6e',
                                   delimiter='\t')

        self.log.debug('Laserscanner data saved.')
        self.signal_data_saved.emit()

        return 0

    def draw_figure(self, matrix_data, freq_data, count_data, fit_freq_vals, fit_count_vals, cbar_range=None, percentile_range=None):
        """ Draw the summary figure to save with the data.

        @param: list cbar_range: (optional) [color_scale_min, color_scale_max].
                                 If not supplied then a default of data_min to data_max
                                 will be used.

        @param: list percentile_range: (optional) Percentile range of the chosen cbar_range.

        @return: fig fig: a matplotlib figure object to be saved to file.
        """

        # If no colorbar range was given, take full range of data
        if cbar_range is None:
            cbar_range = np.array([np.min(matrix_data), np.max(matrix_data)])
        else:
            cbar_range = np.array(cbar_range)

        prefix = ['', 'k', 'M', 'G', 'T']
        prefix_index = 0

        # Rescale counts data with SI prefix
        while np.max(count_data) > 1000:
            count_data = count_data / 1000
            fit_count_vals = fit_count_vals / 1000
            prefix_index = prefix_index + 1

        counts_prefix = prefix[prefix_index]

        # Rescale frequency data with SI prefix
        prefix_index = 0

        while np.max(freq_data) > 1000:
            freq_data = freq_data / 1000
            fit_freq_vals = fit_freq_vals / 1000
            prefix_index = prefix_index + 1

        mw_prefix = prefix[prefix_index]

        # Rescale matrix counts data with SI prefix
        prefix_index = 0

        while np.max(matrix_data) > 1000:
            matrix_data = matrix_data / 1000
            cbar_range = cbar_range / 1000
            prefix_index = prefix_index + 1

        cbar_prefix = prefix[prefix_index]

        # Use qudi style
        plt.style.use(self._save_logic.mpl_qd_style)

        # Create figure
        fig, (ax_mean, ax_matrix) = plt.subplots(nrows=2, ncols=1)

        ax_mean.plot(freq_data, count_data, linestyle=':', linewidth=0.5)

        # Do not include fit curve if there is no fit calculated.
        if max(fit_count_vals) > 0:
            ax_mean.plot(fit_freq_vals, fit_count_vals, marker='None')

        ax_mean.set_ylabel('Fluorescence (' + counts_prefix + 'c/s)')
        ax_mean.set_xlim(np.min(freq_data), np.max(freq_data))

        matrixplot = ax_matrix.imshow(
            matrix_data,
            cmap=plt.get_cmap('inferno'),  # reference the right place in qd
            origin='lower',
            vmin=cbar_range[0],
            vmax=cbar_range[1],
            extent=[
                np.min(freq_data),
                np.max(freq_data),
                0,
                self._scan_counter
                ],
            aspect='auto',
            interpolation='nearest')

        ax_matrix.set_xlabel('Frequency (' + mw_prefix + 'Hz)')
        ax_matrix.set_ylabel('Scan #')

        # Adjust subplots to make room for colorbar
        fig.subplots_adjust(right=0.8)

        # Add colorbar axis to figure
        cbar_ax = fig.add_axes([0.85, 0.15, 0.02, 0.7])

        # Draw colorbar
        cbar = fig.colorbar(matrixplot, cax=cbar_ax)
        cbar.set_label('Fluorescence (' + cbar_prefix + 'c/s)')

        # remove ticks from colorbar for cleaner image
        cbar.ax.tick_params(which='both', length=0)

        # If we have percentile information, draw that to the figure
        if percentile_range is not None:
            cbar.ax.annotate(str(percentile_range[0]),
                             xy=(-0.3, 0.0),
                             xycoords='axes fraction',
                             horizontalalignment='right',
                             verticalalignment='center',
                             rotation=90
                             )
            cbar.ax.annotate(str(percentile_range[1]),
                             xy=(-0.3, 1.0),
                             xycoords='axes fraction',
                             horizontalalignment='right',
                             verticalalignment='center',
                             rotation=90
                             )
            cbar.ax.annotate('(percentile)',
                             xy=(-0.3, 0.5),
                             xycoords='axes fraction',
                             horizontalalignment='right',
                             verticalalignment='center',
                             rotation=90
                             )

        return fig