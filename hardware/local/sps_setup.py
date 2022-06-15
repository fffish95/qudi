# -*- coding: utf-8 -*-
from xml.sax.handler import all_features
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
    sps_setup:
        module.Class: 'local.sps_setup.NITTConfocalScanner'
        connect:
            nicard: 'nicard'
            timetagger: 'tagger'

        scanner_ao_channels:
            - 'AO0'
            - 'AO1'
            - 'AO2'
            - 'AO3'
        scanner_voltage_ranges:
            - [0, 5]
            - [0, 5]
            - [0, 3.2]
            - [-5, 5]
        scanner_position_ranges:
            - [0, 300e-6]
            - [0, 300e-6]
            - [0, 20e-6]
            - [0, 30e3]
        scanner_clock_channel:
            - 'ctr0'
        pixel_clock_channel:
            - 'pfi0'
        timetagger_cbm_begin_channel:
            - 'ch8'
        scanner_ai_channels:
            - 'AI0'
            - 'AI1'
        ai_voltage_ranges:
            - [-10,10]
            - [-10,10]

    """

    nicard = Connector(interface = "NICard")
    timetagger = Connector(interface = "TT")

    # config options
    _scanner_ao_channels = ConfigOption('scanner_ao_channels', missing='error')
    _scanner_voltage_ranges = ConfigOption('scanner_voltage_ranges', missing='error')
    _scanner_position_ranges = ConfigOption('scanner_position_ranges', missing='error')
    _scanner_clock_channel = ConfigOption('scanner_clock_channel', missing='error') 
    _pixel_clock_channel = ConfigOption('pixel_clock_channel', None, missing='nothing')
    _timetagger_cbm_begin_channel = ConfigOption('timetagger_cbm_begin_channel', missing='error')
    _scanner_ai_channels = ConfigOption('scanner_ai_channels', list(), missing='nothing')
    _ai_voltage_ranges = ConfigOption('ai_voltage_ranges', None, missing='nothing')


    def on_activate(self):
        self._nicard = self.nicard()
        self._tt = self.timetagger()
        self._scanner_task = None
        self._scanner_clock_task = None
        self._timetagger_cbm_tasks = list()
        if self._scanner_ai_channels:
            self._scanner_ai_task = None
        self._line_length = None
        self._current_position = np.zeros(len(self._scanner_ao_channels))
        
        if len(self._scanner_ao_channels) != len(self._scanner_voltage_ranges):
            self.log.error(
                'Specify as many scanner_voltage_ranges as scanner_ao_channels!')

        if len(self._scanner_ao_channels) != len(self._scanner_position_ranges):
            self.log.error(
                'Specify as many scanner_position_ranges as scanner_ao_channels!')

        # channels to show in the image channel combobox
        self._timetagger_scanner_counter_channels = self._tt._detector_channels.copy()
        self._timetagger_scanner_counter_channels.insert(0,'all')

        self._scanner_task = self._nicard.create_ao_task(taskname = 'sps_setup_ao', channels = self._scanner_ao_channels, voltage_ranges = self._scanner_voltage_ranges)


    def on_deactivate(self):
        """ Deactivate the module and clean up.
        """
        self._nicard.close_ao_task(taskname = 'sps_setup_ao')
        self._scanner_task = None
        self._nicard.close_co_task(taskname = 'sps_setup_scanner_clock')
        self._scanner_clock_task = None
        if self._scanner_ai_channels and self._scanner_ai_task is not None:
            self._nicard.close_ai_task(taskname = 'sps_setup_ai')
            self._scanner_ai_task = None

    def reset_hardware(self):
        """ Resets the NI hardware, so the connection is lost and other
            programs can access it.

        @return int: error code (0:OK, -1:error)
        """
        return self._nicard.reset_hardware()

    def get_scanner_axes(self):
        """ Scanner axes depends on how many channels tha analog output task has.
        """
        if self._scanner_task is None:
            self.log.error('Cannot get channel number, analog output task does not exist.')
            return []

        n_channels = self._scanner_task.number_of_channels
        possible_channels = ['x', 'y', 'z', 'a']

        return possible_channels[0:int(n_channels)]

    def get_scanner_count_channels(self):
        """ Return list of counter channels """
        ch = self._timetagger_scanner_counter_channels.copy()
        ch.extend(self._scanner_ai_channels)
        return ch

    def get_position_range(self):
        """ Returns the physical range of the scanner.

        @return float [4][2]: array of 4 ranges with an array containing lower
                              and upper limit. The unit of the scan range is
                              meters.
        """
        return self._scanner_position_ranges


    def set_up_scanner_clock(self, clock_frequency=None, clock_channel=None):
        """ Configures the hardware clock of the NiDAQ card to give the timing.

        @param float clock_frequency: if defined, this sets the frequency of
                                      the clock
        @param string clock_channel: if defined, this is the physical channel
                                     of the clock

        @return int: error code (0:OK, -1:error)
        """
        if clock_frequency is None:
            self.log.error('No clock_frequency in set_up_scanner_clock.')
            return -1
        else:
            self._scanner_clock_frequency = float(clock_frequency)
        if clock_channel is not None:   
            self._scanner_clock_channel = clock_channel

        self._scanner_clock_task = self._nicard.create_co_task(taskname = 'sps_setup_scanner_clock', channels = self._scanner_clock_channel, freq = self._scanner_clock_frequency, duty_cycle = 0.5)
        # Create buffer for generating signal
        self._nicard.samp_timing_type(self._scanner_clock_task, type = 'implicit')
        self._nicard.cfg_implicit_timing(self._scanner_clock_task, sample_mode='continuous', samps_per_chan=10000)
        return 0


    def set_up_scanner(self):
        """ Check if everything right before scanning.

        @return int: error code (0:OK, -1:error)
        """
        if self._scanner_task is None:
            self._scanner_task = self._nicard.create_ao_task(taskname = 'sps_setup_ao', channels = self._scanner_ao_channels, voltage_ranges = self._scanner_voltage_ranges)
        else:
            for i, task in enumerate(self._nicard._ao_task_handles):
                if task.name == 'sps_setup_ao':
                    break
                elif i == len(self._nicard._ao_task_handles)-1:
                    self._scanner_task = self._nicard.create_ao_task(taskname = 'sps_setup_ao', channels = self._scanner_ao_channels, voltage_ranges = self._scanner_voltage_ranges)

        if self._scanner_clock_task is None:
            self.log.error('No clock running, call set_up_scanner_clock before starting the counter.')
            return -1
        else:
            for i, task in enumerate(self._nicard._co_task_handles):
                if task.name == 'sps_setup_scanner_clock':
                    break
                elif i == len(self._nicard._co_task_handles)-1:
                    self.log.error('task sps_setup_scanner_clock is closed by other program')
                    return -1
        if self._scanner_ai_channels:
            if self._scanner_ai_task is None:
                self._scanner_ai_task = self._nicard.create_ai_task(taskname = 'sps_setup_ai', channels = self._scanner_ai_channels, voltage_ranges = self._ai_voltage_ranges)
            else:
                for i, task in enumerate(self._nicard._ai_task_handles):
                    if task.name == 'sps_setup_ai':
                        break
                    elif i == len(self._nicard._ai_task_handles)-1:
                        self._scanner_ai_task = self._nicard.create_ai_task(taskname = 'sps_setup_ai', channels = self._scanner_ai_channels, voltage_ranges = self._ai_voltage_ranges)

        return 0

    def scanner_set_position(self, x=None, y=None, z=None, a=None):
        """Move stage to x, y, z, a (where a is the fourth voltage channel).

        @param float x: postion in x-direction (volts)
        @param float y: postion in y-direction (volts)
        @param float z: postion in z-direction (volts)
        @param float a: postion in a-direction (volts)

        @return int: error code (0:OK, -1:error)
        """
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


    def _scanner_position_to_volt(self, positions=None):
        """ Converts a set of position pixels to acutal voltages.

        @param float[][n] positions: array of n-part tuples defining the pixels

        @return float[][n]: array of n-part tuples of corresponing voltages


        The positions is typically a matrix like
            np.vstack([[x_values], [y_values], [z_values], [a_values]])
            but x, xy, xyz and xyza are allowed formats as long as they are consistent with your pre-define.
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
        

    def get_scanner_position(self):
        """ Get the current position of the scanner hardware.

        @return float[]: current position in (x, y, z, a).
        """
        return self._current_position.tolist()


    def _set_up_line(self, length = 100):
        """the configuration needed to do before every scan line, assign buffer according to length to tasks

        start cbm task in TimeTagger

        Set up the configuration of ao task for scanning with certain length

        Connect the timing of the ao task with the timing of the
        co task.

        @param int length: length of the line in pixel

        @return int: error code (0:OK, -1:error)
        """
        self._line_length = length

        try:
            # Just a formal check whether length is not a too huge number
            if length < np.inf:

                # Configure the Sample Clock Timing.
                # Set up the timing of the scanner counting while the voltages are
                # being scanned (i.e. that you go through each voltage, which
                # corresponds to a position. How fast the voltages are being
                # changed is combined with obtaining the counts per voltage peak).
                self._nicard.cfg_samp_clk_timing(self._scanner_task, rate = self._scanner_clock_frequency, source = self._scanner_clock_channel[0], samps_per_chan = self._line_length)

            # Start instance of TimeTagger.CountBetweenMarkers with the correct channels. Does this every time a line is scanned
            self._timetagger_cbm_tasks = list()
            for i,ch in enumerate(self._timetagger_scanner_counter_channels):
                if ch == 'all':
                    self._timetagger_cbm_tasks.append(self._tt.count_between_markers(click_channel = self._tt._combined_detectorChans.getChannel(), begin_channel = self._tt.channel_codes[self._timetagger_cbm_begin_channel[0]], n_values=self._line_length))
                else:
                    self._timetagger_cbm_tasks.append(self._tt.count_between_markers(click_channel = self._tt.channel_codes[ch], begin_channel = self._tt.channel_codes[self._timetagger_cbm_begin_channel[0]], n_values=self._line_length))
            # Set up the configuration of ai task for scanning with certain length
            # dont't put ai task into self._timetagger_cbm_tasks
            if self._scanner_ai_channels:
                self._nicard.cfg_samp_clk_timing(self._scanner_ai_task, rate = self._scanner_clock_frequency, source= self._scanner_clock_channel[0], samps_per_chan = self._line_length+1)


            # Configure Implicit Timing for the clock.
            # Set timing for scanner clock task to the number of pixel.
            self._nicard.cfg_implicit_timing(self._scanner_clock_task, sample_mode='finite', samps_per_chan = self._line_length+1)
        except:
            self.log.exception('Error while setting up scanner to scan a line.')
            return -1
        return 0

    def scan_line(self, line_path=None, pixel_clock=False):
        """ Scans a line and return the counts on that line.

        @param float[c][m] line_path: array of c-tuples defining the voltage points
            (m = samples per line)
        @param bool pixel_clock: whether we need to output a pixel clock for this line

        @return float[m][n]: m (samples per line) n-channel photon counts per second

        The input array looks for a xy scan of 5x5 points at the position z=-2
        like the following:
            [ [1, 2, 3, 4, 5], [1, 1, 1, 1, 1], [-2, -2, -2, -2] ]
        n is the number of scanner axes, which can vary. Typical values are 2 for galvo scanners,
        3 for xyz scanners and 4 for xyz scanners with a special function on the a axis.
        """

        if not isinstance(line_path, (frozenset, list, set, tuple, np.ndarray, ) ):
            self.log.error('Given line_path list is not array type.')
            return np.array([[-1.]])
        

        try:
            # set task timing to use a sampling clock:
            # specify how the Data of the selected task is collected, i.e. set it
            # now to be sampled by a hardware (clock) signal.
            self._nicard.samp_timing_type(self._scanner_task, 'sample_clock')
            self._set_up_line(np.shape(line_path)[1])
            line_volts = self._scanner_position_to_volt(line_path)
            # write the positions to the analog output
            self._nicard.write_task(task = self._scanner_task, data = line_volts, auto_start = False)

            # set up the configuration of co task for scanning with certain length
            self._scanner_clock_task.stop()
            if pixel_clock and self._pixel_clock_channel is not None:
                self._nicard.connect_ctr_to_pfi(self._scanner_clock_channel[0], self._pixel_clock_channel[0])
            # start the timed analog output task
            self._scanner_task.start()
            if self._scanner_ai_channels:
                self._scanner_ai_task.start()
            self._scanner_clock_task.start()

            # # wait for the scanner counter to finish
            # for i, ch in enumerate(self._timetagger_cbm_tasks):
            #     self._timetagger_cbm_tasks[i].waitUntilFinished(timeout = 10 * 2 * self._line_length)
            
            # wait for the scanner clock to finish
            self._scanner_clock_task.wait_until_done(timeout = 10 * 2 * self._line_length)

            # data readout from ai channels
            if self._scanner_ai_channels:
                self._analog_data = self._scanner_ai_task.read(self._line_length + 1)
                self._scanner_ai_task.stop()

            # stop the clock task
            self._scanner_clock_task.stop()
            # stop the ao task
            self._scanner_task.stop()
            self._nicard.samp_timing_type(self._scanner_task, 'on_demand')

            if pixel_clock and self._pixel_clock_channel is not None:
                self._nicard.disconnect_ctr_to_pfi(self._scanner_clock_channel[0], self._pixel_clock_channel[0])

            all_data = np.full(
                (len(self.get_scanner_count_channels()), self._line_length), 2, dtype=np.float64)
            for i, task in enumerate(self._timetagger_cbm_tasks):
                counts = np.nan_to_num(task.getData())
                data = np.reshape(counts,(1, self._line_length))
                all_data[i] = data * self._scanner_clock_frequency
            if self._scanner_ai_channels:
                analog_data = np.reshape(self._analog_data,(len(self._scanner_ai_channels),self._line_length +1))
                all_data[len(self._timetagger_cbm_tasks):] = analog_data[:, :-1]

            # update the scanner position instance variable
            self._current_position = np.array(line_path[:, -1])

        except:
            self.log.exception('Error while scanning line.')
            return np.array([[-1.]])
        # return values is a rate of counts/s
        return all_data.transpose()

    def close_scanner(self):
        """ Closes the scanner and cleans up afterwards.

        @return int: error code (0:OK, -1:error)
        """
        try:
            self._scanner_task.stop()
            self._nicard.samp_timing_type(self._scanner_task, 'on_demand')
            for i, task in enumerate(self._timetagger_cbm_tasks):
                if task.isRunning():
                    task.stop()
                task.clear()
            if self._scanner_ai_channels and self._scanner_ai_task is not None:
                if not self._scanner_ai_task.is_task_done():
                    self._scanner_ai_task.stop()
        except:
            self.log.exception('Error while closing scanner')
            return -1
        finally:
            return 0
        
        
        

    def close_scanner_clock(self):
        """ Closes the clock and cleans up afterwards.

        @return int: error code (0:OK, -1:error)
        """
        
        self._scanner_clock_task = None
        return self._nicard.close_co_task(taskname = 'sps_setup_scanner_clock')



