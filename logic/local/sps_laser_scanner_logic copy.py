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
from tkinter import N
from html5lib import serialize
import matplotlib.pyplot as plt
import numpy as np
import time

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
        self.number_of_repeats = 0

        # Default scan speed
        self.scan_speed = int((self.a_range[1] - self.a_range[0])/2)

        # Variable to check if a scan is continuable
        self.scan_counter = 0
        self.scan_continuable = False

        # Default values for custom scan
        self.custom_scan = False
        self.custom_scan_mode = CustomScanMode.FUNCTION
        self.custom_scan_sweeps_per_action = 1
        self.custom_scan_x_range = self.x_range
        self.custom_scan_y_range = self.y_range
        self.custom_scan_z_range = self.z_range
        self.custom_scan_x_order = 1
        self.custom_scan_y_order = 2
        self.custom_scan_z_order = 0
        self.custom_scan_order_1_resolution = 100
        self.custom_scan_order_2_resolution = 100
        self.custom_scan_order_3_resolution = 50
    
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
        laserscanner._custom_scan_mode = self.custom_scan_mode

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
        except AttributeError:
            self.trace_scan_matrix = np.copy(laserscanner.trace_scan_matrix)
            self.retrace_scan_matrix = np.copy(laserscanner.retrace_scan_matrix)
            self.trace_plot_y_sum = np.copy(laserscanner.trace_plot_y_sum)
            self.trace_plot_y = np.copy(laserscanner.trace_plot_y)
            self.retrace_plot_y = np.copy(laserscanner.retrace_plot_y)
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
        self.custom_scan_mode = laserscanner._custom_scan_mode

        self.trace_scan_matrix = np.copy(laserscanner.trace_scan_matrix)
        self.retrace_scan_matrix = np.copy(laserscanner.retrace_scan_matrix)
        self.trace_plot_y_sum = np.copy(laserscanner.trace_plot_y_sum)
        self.trace_plot_y = np.copy(laserscanner.trace_plot_y)
        self.retrace_plot_y = np.copy(laserscanner.retrace_plot_y)

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

        serialized['trace_scan_matrix'] = self.trace_scan_matrix
        serialized['retrace_scan_matrix'] = self.retrace_scan_matrix
        serialized['trace_plot_y_sum'] = self.trace_plot_y_sum
        serialized['trace_plot_y'] = self.trace_plot_y 
        serialized['retrace_plot_y'] = self.retrace_plot_y
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
        if 'custom_scan_mode' in serialized and isinstance(serialized[custom_scan_mode], CustomScanMode):
            self.custom_scan_mode = serialized['custom_scan_mode']
        
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



class LaserScannernernerLogic(GenericLogic):

    """This is the logic class for laser scanner.
    """

    # declare connectors
    laserscannerscanner1 = Connector(interface='NITTlaserscannerScanner')
    confocallogic1 = Connector(interface='ConfocalLogic')
    savelogic = Connector(interface='SaveLogic')

    # status vars
    _smoothing_steps = StatusVar(default=10)
    max_history_length = StatusVar(default=10)

    # signals
    signal_start_scanning = QtCore.Signal()
    signal_continue_scanning = QtCore.Signal()
    signal_scan_lines_next = QtCore.Signal()
    signal_plots_updated = QtCore.Signal()
    signal_change_position = QtCore.Signal(str)
    signal_save_started = QtCore.Signal()
    signal_saved = QtCore.Signal()
    signal_draw_figure_completed = QtCore.Signal()
    signal_position_changed = QtCore.Signal()
    signal_clock_frequency_updated = QtCore.Signal()

    _signal_save_plots = QtCore.Signal(object, object)

    sigPlotsInitialized = QtCore.Signal()
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
        self.signal_continue_scanning.connect(self.contine_scanner, QtCore.Qt.QueuedConnection)
        
        self._signal_save_plots.connect(self._save_plots, QtCore.Qt.QueuedConnection)

    def on_deactivate(self):
        """ Deinitialisation performed during deactivation of the module.
        """
        self.stopRequested = True
        self.save_history_config()
    
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
        self.signal_plots_updated.emit()
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
        if self.module_state() == 'locked':
            return -1
        else:
            return 0

    def start_scanning(self, custom_scan = False):
        self._scan_counter = 0
        self._custom_scan = custom_scan
        if not self._custom_scan:
            self._scan_continuable = True
        else:
            self._scan_continuable = False
        self._move_to_start = True
        self.signal_start_scanning.emit()
        return 0

    def continue_scanning(self):
        self._move_to_start = True
        self.signal_continue_scanning.emit()
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
        self._confocal_logic.signal_scan_range_updated.emit()

    def initialise_data_matrix(self): 
        self.trace_scan_matrix = np.zeros((self._number_of_repeats, self._resolution))
        self.retrace_scan_matrix = np.zeros((self._number_of_repeats, self._resolution))
        self.trace_plot_y_sum = np.zeros(self._resolution)
        self.trace_plot_y = np.zeros(self._resolution)
        self.retrace_plot_y = np.zeros(self._resolution)


        if self._custom_scan and self._custom_scan_mode == CustomScanMode.XYPLOT:
            self._confocal_logic._zscan = False
            self._confocal_logic._xyscan_continuable = False
            self._confocal_logic._scan_counter = 0
            self.update_confocal_scan_range()
            # x1: x-start-value, x2: x-end-value
            x1, x2 = self._custom_scan_x_range[0], self._custom_scan_x_range[1]
            # y1: y-start-value, y2: y-end-value
            y1, y2 = self._custom_scan_y_range[0], self._custom_scan_y_range[1]
            # z1: z-start-value, z2: x-end-value
            #z1, z2 = self._custom_scan_z_range[0], self._custom_scan_z_range[1]

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
            # TO DO when z order = 0, z2 = z1
            #if self._custom_scan_z_order in [0,3]:
               # if z2 < z1:
               #     self.log.error(
                  #      'z1 must be smaller than z2, but they are '
                  #      '({0:.3f},{1:.3f}).'.format(z1, z2))
                  #  return -1
            #else:
                #self.log.error('z order must be 0 or 3 in xyplot mode.')
            self._X = np.linspace( x1, x2, self._custom_scan_order_1_resolution)
            self._Y = np.linspace( y1, y2, self._custom_scan_order_2_resolution)
            self._confocal_logic.xy_image = np.zeros((
                    len(self._Y),
                    len(self._X),
                    3 + len(self.get_scanner_count_channels())
                ))
            self._confocal_logic.xy_image[:, :, 0] = np.full(
                (len(self._Y), len(self._X), self._X)
            )
            y_value_matrix = np.full((len(self._X), len(self._Y)), self._Y)
            self.xy_image[:, :, 1] = y_value_matrix.transpose()
            self.xy_image[:, :, 2] = self._current_z * np.ones(
                (len(self._Y, len(self._X)))
            )
        #if custom_scan and self._custom_scan_mode == CustomScanMode.AO:
    
    def start_scanner(self):
        """Setting up the scanner device and starts the scanning procedure

        @return int: error code (0:OK, -1:error)
        """
        self.module_state.lock()
        self._scanning_device.module_state.lock()
        if self._custom_scan:
            self._number_of_repeats = self._custom_scan_order_1_resolution * self._custom_scan_order_2_resolution
            if self._custom_scan_mode == CustomScanMode.XYPLOT:
                self._confocal_logic.module_state.lock()
        
        clock_status = self._scanning_device.set_up_scanner_clock(
            clock_frequency=self._clock_frequency)

        if clock_status < 0:
            self._scanning_device.module_state.unlock()
            self.module_state.unlock()
            if self._custom_scan and self._custom_scan_mode == CustomScanMode.XYPLOT:
                self._confocal_logic.module_state.unlock()
            self._change_position()
            self._confocal_logic.set_position(tag='laserscanner', x = self._current_x, y = self._current_y, z = self._current_z)
            return -1
        
        scanner_status = self._scanning_device.set_up_scanner()

        if scanner_status < 0:
            self._scanning_device.close_scanner_clock()
            self._scanning_device.module_state.unlock()
            self.module_state.unlock()
            if self._custom_scan and self._custom_scan_mode == CustomScanMode.XYPLOT:
                self._confocal_logic.module_state.unlock()
            self._change_position()
            self._confocal_logic.set_position(tag='laserscanner', x = self._current_x, y = self._current_y, z = self._current_z)
            return -1
                
        self.initialise_data_matrix()
        self.signal_scan_lines_next.emit()
        return 0
    
    def start_oneline_scanner(self):
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
                position_min_linear = position_start + position_range_of_accel
                position_max_linear = position_end - position_range_of_accel
            else:
                position_min_linear = position_end + position_range_of_accel
                position_max_linear = position_start - position_range_of_accel

            if (position_max_linear - position_min_linear) / linear_position_step < self._smoothing_steps:
                ramp = np.linspace(position_start,position_end, self._resolution)
            else:
                num_of_linear_steps = np.rint(self._resolution - 2*self._smoothing_steps)

                smooth_curve = np.array(
                    [sum(
                        n * linear_position_step / smoothing_range for n in range(1, N)
                    ) for N in range(1, smoothing_range)
                    ])
                accel_part = position_min_linear + smooth_curve
                decel_part = position_max_linear - smooth_curve[::-1]

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
        move_line = self._generate_ramp(self._scanning_device.get_scanner_position()[3], self._current_a)
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

    
    def _scan_line(self, pixel_clock = False):

        # stops scanning
        if self.stopRequested:
            with self.threadlock:
                self.kill_scanner()
                self.stopRequested = False
                self.module_state.unlock()
                self.siganl_plots_updated.exmit()
                self._change_position()
                
        if line_to_scan is None:
            self.log.error('Voltage scanning logic needs a line to scan!')
            return -1
        try:
            # scan of a single line
            if pixel_clock:
                counts_on_scan_line = self._scanning_device.scan_line(line_to_scan, pixel_clock = True)
            else:
                counts_on_scan_line = self._scanning_device.scan_line(line_to_scan)
            return counts_on_scan_line.transpose()[0]

        except Exception as e:
            self.log.error('The scan went wrong, killing the scanner.')
            self.stop_scanning()
            self.sigScanNextLine.emit()
            raise e


    def _do_next_line(self):
        """ If stopRequested then finish the scan, otherwise perform next repeat of the scan line
        """
        # stops scanning
        if self.stopRequested or self._scan_counter_down >= self.number_of_repeats:
            print(self.current_position)
            self._goto_during_scan(self._static_v)
            self._close_scanner()
            self.sigScanFinished.emit()
            return

        if self._scan_counter_up == 0:
            # move from current voltage to start of scan range.
            self._goto_during_scan(self.scan_range[0])

        if self.upwards_scan:
            counts = self._scan_line(self._upwards_ramp, pixel_clock=True)
            self.scan_matrix[self._scan_counter_up] = counts
            self.plot_y += counts
            self._scan_counter_up += 1
            self.upwards_scan = False
            self.plot_y_2 = counts
        else:
            counts = self._scan_line(self._downwards_ramp)
            self.scan_matrix2[self._scan_counter_down] = counts
            self.plot_y2 += counts
            self._scan_counter_down += 1
            self.upwards_scan = True
        
        self.sigUpdatePlots.emit()
        self.sigScanNextLine.emit()

    def _goto_during_scan(self, voltage=None):

        if voltage is None:
            return -1

        goto_ramp = self._generate_ramp(self.get_current_voltage(), voltage, self._goto_speed)
        ignored_counts = self._scan_line(goto_ramp)

        return 0



    def set_scan_range(self, scan_range):
        """ Set the scan rnage """
        self._scan_range = scan_range



    def set_scan_speed(self, scan_speed):
        """ Set scan speed in volt per second """
        self._scan_speed = np.clip(scan_speed, 1e-9, 2e6)
        self._goto_speed = self._scan_speed

    def set_scan_lines(self, scan_lines):
        self.number_of_repeats = int(np.clip(scan_lines, 1, 1e6))

    def _initialise_data_matrix(self, scan_length):

        self.scan_matrix = np.zeros((self.number_of_repeats, scan_length))
        self.scan_matrix2 = np.zeros((self.number_of_repeats, scan_length))
        self.plot_x = np.linspace(self.scan_range[0], self.scan_range[1], scan_length)
        self.plot_y = np.zeros(scan_length)
        self.plot_y_2 = np.zeros(scan_length)
        self.plot_y2 = np.zeros(scan_length)
        self.fit_x = np.linspace(self.scan_range[0], self.scan_range[1], scan_length)
        self.fit_y = np.zeros(scan_length)

    def get_current_voltage(self):
        """returns current voltage of hardware device(atm NIDAQ 4th output)"""
        return self._scanning_device.get_scanner_position()[3]

    def _initialise_scanner(self):
        """Initialise the clock and locks for a scan"""
        self.module_state.lock()
        self._scanning_device.module_state.lock()

        returnvalue = self._scanning_device.set_up_scanner_clock(
            clock_frequency=self._clock_frequency)
        if returnvalue < 0:
            self._scanning_device.module_state.unlock()
            self.module_state.unlock()
            self.set_position('scanner')
            return -1

        returnvalue = self._scanning_device.set_up_scanner()
        if returnvalue < 0:
            self._scanning_device.module_state.unlock()
            self.module_state.unlock()
            self.set_position('scanner')
            return -1

        return 0

    def start_scanning(self, v_min=None, v_max=None):
        """Setting up the scanner device and starts the scanning procedure

        @return int: error code (0:OK, -1:error)
        """

        self.current_position = self._scanning_device.get_scanner_position()
        print(self.current_position)

        if v_min is not None:
            self.scan_range[0] = v_min
        else:
            v_min = self.scan_range[0]
        if v_max is not None:
            self.scan_range[1] = v_max
        else:
            v_max = self.scan_range[1]

        self._scan_counter_up = 0
        self._scan_counter_down = 0
        self.upwards_scan = True

        # TODO: Generate Ramps
        self._upwards_ramp = self._generate_ramp(v_min, v_max, self._scan_speed)
        self._downwards_ramp = self._generate_ramp(v_max, v_min, self._scan_speed)

        self._initialise_data_matrix(len(self._upwards_ramp[3]))

        # Lock and set up scanner
        returnvalue = self._initialise_scanner()
        if returnvalue < 0:
            # TODO: error message
            return -1

        self.sigScanNextLine.emit()
        self.sigScanStarted.emit()
        return 0

    def stop_scanning(self):
        """Stops the scan

        @return int: error code (0:OK, -1:error)
        """
        with self.threadlock:
            if self.module_state() == 'locked':
                self.stopRequested = True
        return 0

    def _close_scanner(self):
        """Close the scanner and unlock"""
        with self.threadlock:
            self.kill_scanner()
            self.stopRequested = False
            if self.module_state.can('unlock'):
                self.module_state.unlock()

    def _do_next_line(self):
        """ If stopRequested then finish the scan, otherwise perform next repeat of the scan line
        """
        # stops scanning
        if self.stopRequested or self._scan_counter_down >= self.number_of_repeats:
            print(self.current_position)
            self._goto_during_scan(self._static_v)
            self._close_scanner()
            self.sigScanFinished.emit()
            return

        if self._scan_counter_up == 0:
            # move from current voltage to start of scan range.
            self._goto_during_scan(self.scan_range[0])

        if self.upwards_scan:
            counts = self._scan_line(self._upwards_ramp, pixel_clock=True)
            self.scan_matrix[self._scan_counter_up] = counts
            self.plot_y += counts
            self._scan_counter_up += 1
            self.upwards_scan = False
            self.plot_y_2 = counts
        else:
            counts = self._scan_line(self._downwards_ramp)
            self.scan_matrix2[self._scan_counter_down] = counts
            self.plot_y2 += counts
            self._scan_counter_down += 1
            self.upwards_scan = True
        
        self.sigUpdatePlots.emit()
        self.sigScanNextLine.emit()

    def _generate_ramp(self, voltage1, voltage2, speed):
        """Generate a ramp vrom voltage1 to voltage2 that
        satisfies the speed, step, smoothing_steps parameters.  Smoothing_steps=0 means that the
        ramp is just linear.

        @param float voltage1: voltage at start of ramp.

        @param float voltage2: voltage at end of ramp.
        """

        # It is much easier to calculate the smoothed ramp for just one direction (upwards),
        # and then to reverse it if a downwards ramp is required.

        v_min = min(voltage1, voltage2)
        v_max = max(voltage1, voltage2)

        if v_min == v_max:
            ramp = np.array([v_min, v_max])
        else:
            # These values help simplify some of the mathematical expressions
            linear_v_step = speed / self._clock_frequency
            smoothing_range = self._smoothing_steps + 1

            # Sanity check in case the range is too short

            # The voltage range covered while accelerating in the smoothing steps
            v_range_of_accel = sum(
                n * linear_v_step / smoothing_range for n in range(0, smoothing_range)
                )

            # Obtain voltage bounds for the linear part of the ramp
            v_min_linear = v_min + v_range_of_accel
            v_max_linear = v_max - v_range_of_accel

            if v_min_linear > v_max_linear:
                # self.log.warning(
                #     'Voltage ramp too short to apply the '
                #     'configured smoothing_steps. A simple linear ramp '
                #     'was created instead.')
                num_of_linear_steps = np.rint((v_max - v_min) / linear_v_step)
                ramp = np.linspace(v_min, v_max, num_of_linear_steps)

            else:

                num_of_linear_steps = np.rint((v_max_linear - v_min_linear) / linear_v_step)

                # Calculate voltage step values for smooth acceleration part of ramp
                smooth_curve = np.array(
                    [sum(
                        n * linear_v_step / smoothing_range for n in range(1, N)
                        ) for N in range(1, smoothing_range)
                    ])

                accel_part = v_min + smooth_curve
                decel_part = v_max - smooth_curve[::-1]

                linear_part = np.linspace(v_min_linear, v_max_linear, num_of_linear_steps)

                ramp = np.hstack((accel_part, linear_part, decel_part))

        # Reverse if downwards ramp is required
        if voltage2 < voltage1:
            ramp = ramp[::-1]

        # Put the voltage ramp into a scan line for the hardware (4-dimension)
        spatial_pos = self._scanning_device.get_scanner_position()

        scan_line = np.vstack((
            np.ones((len(ramp), )) * spatial_pos[0],
            np.ones((len(ramp), )) * spatial_pos[1],
            np.ones((len(ramp), )) * spatial_pos[2],
            ramp
            ))

        return scan_line



    def kill_scanner(self):
        """Closing the scanner device.

        @return int: error code (0:OK, -1:error)
        """
        try:
            self._scanning_device.close_scanner()
            self._scanning_device.close_scanner_clock()
        except Exception as e:
            self.log.exception('Could not even close the scanner, giving up.')
            raise e
        try:
            if self._scanning_device.module_state.can('unlock'):
                self._scanning_device.module_state.unlock()
        except:
            self.log.exception('Could not unlock scanning device.')
        return 0

    def save_data(self, tag=None, colorscale_range=None, percentile_range=None):
        """ Save the counter trace data and writes it to a file.

        @return int: error code (0:OK, -1:error)
        """
        if tag is None:
            tag = ''

        self._saving_stop_time = time.time()

        filepath = self._save_logic.get_path_for_module(module_name='laserscannerning')
        filepath2 = self._save_logic.get_path_for_module(module_name='laserscannerning')
        filepath3 = self._save_logic.get_path_for_module(module_name='laserscannerning')
        timestamp = datetime.datetime.now()

        if len(tag) > 0:
            filelabel = tag + '_volt_data'
            filelabel2 = tag + '_volt_data_raw_trace'
            filelabel3 = tag + '_volt_data_raw_retrace'
        else:
            filelabel = 'volt_data'
            filelabel2 = 'volt_data_raw_trace'
            filelabel3 = 'volt_data_raw_retrace'

        # prepare the data in a dict or in an OrderedDict:
        data = OrderedDict()
        data['frequency (Hz)'] = self.plot_x
        data['trace count data (counts/s)'] = self.plot_y
        # data['trace count data (counts/s)'] = self.plot_y_2
        data['retrace count data (counts/s)'] = self.plot_y2

        data2 = OrderedDict()
        data2['count data (counts/s)'] = self.scan_matrix[:self._scan_counter_up, :]

        data3 = OrderedDict()
        data3['count data (counts/s)'] = self.scan_matrix2[:self._scan_counter_down, :]

        parameters = OrderedDict()
        parameters['Number of frequency sweeps (#)'] = self._scan_counter_up
        parameters['Start Voltage (V)'] = self.scan_range[0]
        parameters['Stop Voltage (V)'] = self.scan_range[1]
        parameters['Scan speed [V/s]'] = self._scan_speed
        parameters['Clock Frequency (Hz)'] = self._clock_frequency

        fig = self.draw_figure(
            self.scan_matrix,
            self.plot_x,
            self.plot_y,
            self.fit_x,
            self.fit_y,
            cbar_range=colorscale_range,
            percentile_range=percentile_range)

        fig2 = self.draw_figure(
            self.scan_matrix2,
            self.plot_x,
            self.plot_y2,
            self.fit_x,
            self.fit_y,
            cbar_range=colorscale_range,
            percentile_range=percentile_range)

        self._save_logic.save_data(
            data,
            filepath=filepath,
            parameters=parameters,
            filelabel=filelabel,
            fmt='%.6e',
            delimiter='\t',
            timestamp=timestamp
        )

        self._save_logic.save_data(
            data2,
            filepath=filepath2,
            parameters=parameters,
            filelabel=filelabel2,
            fmt='%.6e',
            delimiter='\t',
            timestamp=timestamp,
            plotfig=fig
        )

        self._save_logic.save_data(
            data3,
            filepath=filepath3,
            parameters=parameters,
            filelabel=filelabel3,
            fmt='%.6e',
            delimiter='\t',
            timestamp=timestamp,
            plotfig=fig2
        )

        self.log.info('Laser Scan saved to:\n{0}'.format(filepath))
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
                self.number_of_repeats
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
