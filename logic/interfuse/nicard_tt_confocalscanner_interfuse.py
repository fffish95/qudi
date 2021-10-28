# -*- coding: utf-8 -*-
import numpy as np
from enum import Enum 
import time


from core.module import Base
from core.configoption import ConfigOption
from core.connector import Connector




class NITTConfocalScanner(Base):
    """ Designed for use a National Instruments device to control laser scanning and use TimeTagger to count photons.

    See [National Instruments X Series Documentation](@ref nidaq-x-series) for details.

    stable: Kay Jahnke, Alexander Stark

    Example config for copy-paste:


    nicard_tt_confocalscanner:
        module.Class: 'interfuse.nicard_tt_confocalscanner_interfuse.NITTConfocalScanner'
        connect:
            nicard: 'nicard'
            timetagger: 'tagger'

        read_write_timeout: 10

        scanner_ao_channels:
            - 'AO0'
        scanner_voltage_ranges:
            - [-5, 5]
        scanner_clock_channel:
            - 'ctr0'
        ai_channels:
            - 'ai0'
        ai_voltage_ranges:
            - [-5, 5]
        scanner_position_ranges:
            - [0e4, 3e4]
        pixel_clock_channel:
            - 'pfi0'
        marker_channel:
            - 'ch8'




    """

    nicard = Connector(interface = "NICard")
    timetagger = Connector(interface = "TT")
    # config options
    _RWTimeout = ConfigOption('read_write_timeout', default=10)
    _scanner_ao_channels = ConfigOption('scanner_ao_channels', missing='warn')
    _scanner_voltage_ranges = ConfigOption('scanner_voltage_ranges', missing='warn')
    _scanner_position_ranges = ConfigOption('scanner_position_ranges', missing='warn')
    _scanner_clock_channel = ConfigOption('scanner_clock_channel', missing='warn')
    _ai_channels = ConfigOption('ai_channels', missing='info')
    _ai_voltage_ranges = ConfigOption('ai_voltage_ranges', missing='info')
    _pixel_clock_channel = ConfigOption('pixel_clock_channel', None)
    _marker_channel = ConfigOption('marker_channel', None)



    def on_activate(self):
        self._nicard = self.nicard()
        self._tt = self.timetagger()
        self._scanner_clock_task = None
        self._scanner_task = None
        self._ai_task = None
        self._counter_task = None

        self._current_position = np.zeros(len(self._scanner_ao_channels))
        
        if len(self._scanner_ao_channels) != len(self._scanner_voltage_ranges):
            self.log.error(
                'Specify as many scanner_voltage_ranges as scanner_ao_channels!')

        if len(self._scanner_ao_channels) != len(self._scanner_position_ranges):
            self.log.error(
                'Specify as many scanner_position_ranges as scanner_ao_channels!')
        
        self.create_scanner_task()
        self._scanner_task.start()

    def on_deactivate(self):
        """ Deactivate the module and clean up.
        """
        self.close_scanner_task()
        self.close_scanner_clock_task()
        self.close_ai_task()
        self.close_counter_task()
        self.reset_hardware()

    def reset_hardware(self):
        return self._nicard.reset_hardware()


    def get_position_range(self):
        return self._scanner_position_ranges


    def set_position_range(self, myrange=None):
        n_ch = len(self.get_scanner_axes())
        if myrange is None:
            self.log.error('No range in set_position_range.')
            return -1

        if not isinstance(myrange, (frozenset, list, set, tuple, np.ndarray, )):
            self.log.error('Given range is no array type.')
            return -1

        if len(myrange) != n_ch:
            self.log.error(
                'Given range should have dimension {1:d}, but has {0:d} instead.'
                ''.format(len(myrange), n_ch))
            return -1

        for pos in myrange:
            if len(pos) != 2:
                self.log.error(
                    'Given range limit {1:d} should have dimension 2, but has {0:d} instead.'
                    ''.format(len(pos), pos))
                return -1
            if pos[0]>pos[1]:
                self.log.error(
                    'Given range limit {0:d} has the wrong order.'.format(pos))
                return -1

        self._scanner_position_ranges = myrange
        return 0


    def set_voltage_range(self, myrange=None):
        n_ch = len(self.get_scanner_axes())
        if myrange is None:
            self.log.error('No range in set_voltage_range.')
            return -1

        if not isinstance(myrange, (frozenset, list, set, tuple, np.ndarray)):
            self.log.error('Given range is no array type.')
            return -1

        if len(myrange) != n_ch:
            self.log.error(
                'Given range should have dimension {1:d}, but has {0:d} instead.'
                ''.format(len(myrange), n_ch))
            return -1

        for r in myrange:
            if len(r) != 2:
                self.log.error(
                    'Given range limit {1:d} should have dimension 2, but has {0:d} instead.'
                    ''.format(len(r), r))
                return -1
            if r[0] > r[1]:
                self.log.error('Given range limit {0:d} has the wrong order.'.format(r))
                return -1

        self._scanner_voltage_ranges = myrange
        return 0

    def get_scanner_axes(self):
        if len(self._nicard._ao_task_handles) == 0:
            self.log.error('Cannot get channel number, analog output task does not exist.')
            return []

        for i, task in enumerate(self._nicard._ao_task_handles):
            if task.name.lower() == 'scanner':
                n_channels = task.number_of_channels
                break
            else:
                if i == len(self._nicard._ao_task_handles)-1:
                    self.log.error("Cannot get channel number, task 'scanner' does not exist.")
                    return []

        possible_channels = ['x', 'y', 'z', 'a']

        return possible_channels[0:int(n_channels)]



    def create_scanner_clock_task(self, clock_frequency=None, clock_channel=None):
        if clock_frequency is None:
            self.log.error('No clock_frequency in set_up_scanner_clock.')
            return -1
        else:
            self._scanner_clock_frequency = float(clock_frequency)
        if clock_channel is not None:   
            self._scanner_clock_channel = clock_channel

        self._scanner_clock_task = self._nicard.create_co_task(taskname = 'scanner clock', channels = self._scanner_clock_channel, freq = self._scanner_clock_frequency, duty_cycle = 0.5)
        # Create buffer for generating signal
        self._nicard.samp_timing_type(self._scanner_clock_task, type = 'implicit')
        self._nicard.cfg_implicit_timing(self._scanner_clock_task, sample_mode='continuous', samps_per_chan=10000)
        return 0



    def create_scanner_task(self, scanner_ao_channels=None, scanner_voltage_ranges = None):
        if scanner_ao_channels is not None:
            self._scanner_ao_channels = scanner_ao_channels
        
        if scanner_voltage_ranges is not None:
            self._scanner_voltage_ranges = scanner_voltage_ranges
        self._scanner_task = self._nicard.create_ao_task(taskname = 'scanner', channels = self._scanner_ao_channels, voltage_ranges = self._scanner_voltage_ranges)
        return 0 

    
    def create_ai_task(self, ai_channels = None, ai_voltage_ranges = None):
        if ai_channels is not None:
            self._ai_channels = ai_channels
        
        if ai_voltage_ranges is not None:
            self._ai_voltage_ranges = ai_voltage_ranges
        self._ai_task = self._nicard.create_ai_task(taskname = 'ai', channels = self._ai_channels, voltage_ranges = self._ai_voltage_ranges)
        return 0


    def scanner_set_position(self, x=None, y=None, z=None, a=None):
        if self.module_state() == 'locked':
            self.log.error('Another scan_line is already running, close this one first.')
            return -1

        if x is not None:
            if not(self._scanner_position_ranges[0][0] <= x <= self._scanner_position_ranges[0][1]):
                self.log.error('You want to set x out of range: {0:f}.'.format(x))
                return -1
            self._current_position[0] = np.float(x)

        if y is not None:
            if not(self._scanner_position_ranges[1][0] <= y <= self._scanner_position_ranges[1][1]):
                self.log.error('You want to set y out of range: {0:f}.'.format(y))
                return -1
            self._current_position[1] = np.float(y)

        if z is not None:
            if not(self._scanner_position_ranges[2][0] <= z <= self._scanner_position_ranges[2][1]):
                self.log.error('You want to set z out of range: {0:f}.'.format(z))
                return -1
            self._current_position[2] = np.float(z)

        if a is not None:
            if not(self._scanner_position_ranges[3][0] <= a <= self._scanner_position_ranges[3][1]):
                self.log.error('You want to set a out of range: {0:f}.'.format(a))
                return -1
            self._current_position[3] = np.float(a)

        # the position has to be a vstack
        my_position = np.vstack(self._current_position)

        # then directly write the position to the hardware
        try:
            self._nicard.write_task(task = self._scanner_task, data = self._scanner_position_to_volt(my_position), auto_start = True )
        except:
            return -1
        return 0


    def get_scanner_position(self):
        return self._current_position.tolist()


    def scan_line(self, line_path=None, pixel_clock=False):
        if not isinstance(line_path, (frozenset, list, set, tuple, np.ndarray, ) ):
            self.log.error('Given line_path list is not array type.')
            return np.array([[-1.]])
        

        try:
            self._line_length = np.shape(line_path)[1]     
            # set up the configuration of co task for scanning with certain length
            self._scanner_clock_task.stop()
            self._nicard.cfg_implicit_timing(self._scanner_clock_task, sample_mode='finite', samps_per_chan = self._line_length+1)
            if pixel_clock and self._pixel_clock_channel is not None:
                self._nicard.connect_ctr_to_pfi(self._scanner_clock_channel[0], self._pixel_clock_channel[0])

            # set up the configuration of ao task for scanning with certain length
            self._scanner_task.stop()
            self._nicard.samp_timing_type(self._scanner_task, 'sample_clock')
            self._nicard.cfg_samp_clk_timing(self._scanner_task, rate = self._scanner_clock_frequency, source = self._scanner_clock_channel[0], samps_per_chan = self._line_length)
            line_volts = self._scanner_position_to_volt(line_path)
            self._nicard.write_task(task = self._scanner_task, data = line_volts, auto_start = False)

            # set up the configuration of ai task for scanning with certain length
            if self._ai_task is not None:
                self._ai_task.stop()
                self._nicard.samp_timing_type(self._ai_task, 'sample_clock')
                self._nicard.cfg_samp_clk_timing(self._ai_task, rate = self._scanner_clock_frequency, source = self._scanner_clock_channel[0], samps_per_chan = self._line_length)

            # create counter task
            if self._counter_task is not None:
                self.close_counter_task()
            self._counter_task = self._tt.count_between_markers(click_channel = self._tt._combined_detectorChans.getChannel(), begin_channel = self._tt.channel_codes[self._marker_channel[0]], n_values=self._line_length)
            self._counter_task.clear()

            # start scan
            self._scanner_task.start()
            if self._ai_task is not None:
                self._ai_task.start()
            self._counter_task.start()
            self._scanner_clock_task.start()
            self._scanner_clock_task.wait_until_done(timeout = self._RWTimeout * 2 * self._line_length)
            if self._ai_task is not None:
                self._analog_data = self._ai_task.read(self._line_length)
                self._ai_task.stop()
                self._nicard.samp_timing_type(self._ai_task, 'on_demand')
            self._scanner_clock_task.stop()
            self._scanner_task.stop()
            self._nicard.samp_timing_type(self._scanner_task, 'on_demand')
            if pixel_clock and self._pixel_clock_channel is not None:
                self._nicard.disconnect_ctr_to_pfi(self._scanner_clock_channel[0], self._pixel_clock_channel[0])

            timeout = time.time()
            while (time.time()-timeout)<(1/self._scanner_clock_frequency * 20):
                if self._counter_task.ready():
                    break
            counts = np.nan_to_num(self._counter_task.getData())
            data = np.reshape(counts,(1, self._line_length))
            all_data = data * self._scanner_clock_frequency
            # if self._ai_task is not None:
            #     all_data[1:] = self._analog_data
            # update the scanner position instance variable
            # self._current_position = np.array(line_path[:, -1])
        except:
            self.log.exception('Error while scanning line.')
            return np.array([[-1.]])
        # return values is a rate of counts/s
        return all_data


    def close_scanner_clock_task(self):
        if self._scanner_clock_task is not None:
            try:
                self._scanner_clock_task.stop()
                self._scanner_clock_task.close()
                self._scanner_clock_task = None
            except:
                self.log.exception('Could not close scanner clock task.')
        else:
            return 0





    def close_scanner_task(self):
        if self._scanner_task is not None:
            try:
                self._scanner_task.stop()
                self._scanner_task.close()
                self._scanner_task = None
            except:
                self.log.exception('Could not close scanner task.')
        else:
            return 0


    
    def close_ai_task(self):
        if self._ai_task is not None:
            try:
                self._ai_task.stop()
                self._ai_task.close()
                self._ai_task = None
            except:
                self.log.exception('Could not close ai task.')
        else:
            return 0

    def close_counter_task(self):
        if self._counter_task is not None:
            try:
                self._counter_task.clear()
                self._counter_task = None
            except:
                self.log.exception('Could not close counter task.')
        else:
            return 0

    def _scanner_position_to_volt(self, positions=None):
        """ Converts a set of position pixels to acutal voltages.

        @param float[][n] positions: array of n-part tuples defining the pixels

        @return float[][n]: array of n-part tuples of corresponing voltages


        The positions is typically a matrix like
            [[x_values], [y_values], [z_values], [a_values]]
            but x, xy, xyz and xyza are allowed formats.
        The position has to be a vstack
        """

        if not isinstance(positions, (frozenset, list, set, tuple, np.ndarray, )):
            self.log.error('Given position list is no array type.')
            return np.array([np.NaN])

        vlist = []
        for i, position in enumerate(positions):
            vlist.append(
                (self._scanner_voltage_ranges[i][1] - self._scanner_voltage_ranges[i][0])
                / (self._scanner_position_ranges[i][1] - self._scanner_position_ranges[i][0])
                * (position - self._scanner_position_ranges[i][0])
                + self._scanner_voltage_ranges[i][0]
            )
        volts = np.vstack(vlist)

        for i, v in enumerate(volts):
            if v.min() < self._scanner_voltage_ranges[i][0] or v.max() > self._scanner_voltage_ranges[i][1]:
                self.log.error(
                    'Voltages ({0}, {1}) exceed the limit, the positions have to '
                    'be adjusted to stay in the given range.'.format(v.min(), v.max()))
                return np.array([np.NaN])
        return volts
