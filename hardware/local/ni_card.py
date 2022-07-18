# -*- coding: utf-8 -*-

"""
This file contains the Qudi Hardware module NICard class.

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

import numpy as np
import re

import PyDAQmx as daq

from core.module import Base
from core.configoption import ConfigOption
import nidaqmx as ni
from nidaqmx._lib import lib_importer  # Due to NIDAQmx C-API bug needed to bypass property getter
from nidaqmx.constants import  SampleTimingType, ChannelType, UsageTypeCO
import six
from nidaqmx._task_modules.write_functions import (
    _write_analog_f_64, _write_digital_lines, _write_digital_u_32,
    _write_ctr_freq, _write_ctr_time, _write_ctr_ticks)
from nidaqmx.errors import DaqError
from nidaqmx.error_codes import DAQmxErrors
from nidaqmx.constants import AcquisitionType


class UnsetNumSamplesSentinel(object):
    pass


class UnsetAutoStartSentinel(object):
    pass


NUM_SAMPLES_UNSET = UnsetNumSamplesSentinel()
AUTO_START_UNSET = UnsetAutoStartSentinel()

del UnsetNumSamplesSentinel
del UnsetAutoStartSentinel

class NICardConstraints:
    """
    Collection of constraints for NICard.
    """
    def __init__(self, ao_channels=None, ai_channels=None, digital_channels=None,
                 ci_channels=None, co_channels=None, ao_rate=None,
                 ai_rate=None, digital_max_rate=None, counter_max_timebase=None):

        if ao_channels is None:
            self.ao_channels = dict()
        else:
            self.ao_channels = tuple(ch.copy() for ch in ao_channels)
        
        if ai_channels is None:
            self.ai_channels = dict()
        else:
            self.ai_channels = tuple(ch.copy() for ch in ai_channels)

        if digital_channels is None:
            self.digital_channels = dict()
        else:
            self.digital_channels = tuple(ch.copy() for ch in digital_channels)

        if ci_channels is None:
            self.ci_channels = dict()
        else:
            self.ci_channels = tuple(ch.copy() for ch in ci_channels)

        if co_channels is None:
            self.co_channels = dict()
        else:
            self.co_channels = tuple(ch.copy() for ch in co_channels)

        if ao_rate is None:
            self.ao_rate=[]
        else:
            self.ao_rate = ao_rate
        
        if ai_rate is None:
            self.ao_rate=[]
        else:
            self.ai_rate = ai_rate
        
        if digital_max_rate is None:
            self.digital_max_rate = None
        else:
            self.digital_max_rate = digital_max_rate
        
        if counter_max_timebase is None:
            self.counter_max_timebase = None
        else:
            self.counter_max_timebase = counter_max_timebase

        return


class NICard(Base):
    """ Designed for use a National Instruments device to count photons and control laser scanning.

    See [National Instruments X Series Documentation](@ref nidaq-x-series) for details.

    stable: Kay Jahnke, Alexander Stark

    Example config for copy-paste:

    nicard:
        module.Class: 'local.ni_card.NICard'
        device_name: 'Dev3'  
    """

    # config options
    _device_name = ConfigOption(name='device_name', default='Dev1', missing='error')


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._ao_task_handles = list()
        self._ai_task_handles = list()
        self._do_task_handles = list()
        self._di_task_handles = list()
        self._co_task_handles = list()
        self._ci_task_handles = list()

    def on_activate(self):
        """
        Starts up the NI-card and performs sanity checks.
        """
        # Check if device is connected and set device to use
        dev_names = ni.system.System().devices.device_names
        if self._device_name.lower() not in set(dev.lower() for dev in dev_names):
            raise Exception('Device name "{0}" not found in list of connected devices: {1}\n'
                            'Activation of NIXSeriesInStreamer failed!'
                            ''.format(self._device_name, dev_names))
        for dev in dev_names:
            if dev.lower() == self._device_name.lower():
                self._device_name = dev
                break
        self._device_handle = ni.system.Device(self._device_name)
        self._device_handle.self_test_device()
        
        # Create constraints
        self._constraints = NICardConstraints()
        self._constraints.ao_channels = tuple(
            term.rsplit('/', 1)[-1].lower() for term in self._device_handle.ao_physical_chans.channel_names)
        self._constraints.ai_channels = tuple(
            term.rsplit('/', 1)[-1].lower() for term in self._device_handle.ai_physical_chans.channel_names)        
        self._constraints.digital_channels = tuple(
            term.rsplit('/', 1)[-1].lower() for term in self._device_handle.terminals if 'PFI' in term)
        self._constraints.ci_channels = tuple(
            term.rsplit('/', 1)[-1].lower() for term in self._device_handle.ci_physical_chans.channel_names)        
        self._constraints.co_channels = tuple(
            term.rsplit('/', 1)[-1].lower() for term in self._device_handle.co_physical_chans.channel_names)
        self._constraints.ao_rate = [self._device_handle.ao_min_rate, self._device_handle.ao_max_rate]  
        self._constraints.ai_rate = [self._device_handle.ai_min_rate, self._device_handle.ai_max_multi_chan_rate] 
        self._constraints.digital_max_rate = self._device_handle.di_max_rate
        self._constraints.counter_max_timebase = self._device_handle.ci_max_timebase

        self.terminate_all_tasks()


    def on_deactivate(self):
        self.reset_hardware()




    def create_ao_task(self, taskname = None, channels = None, voltage_ranges = None):
        if taskname is None:
            self.log.error('Need taskname to create the ao task.')
            return -1
        else:
        # Check if task by that name already exists
            try:
                task = ni.Task(taskname)
            except ni.DaqError:
                self.log.error('ao task with name "{0}" already exists'.format(taskname))
                return -1
        if channels is None:
            self.log.error('Need channels to create the ao task.')
            return -1
        
        if voltage_ranges is None:
            self.log.error(
                'ao task voltage_ranges is None')
            return -1


        if len(channels) != len(voltage_ranges):
            self.log.error(
                'Specify as many voltage_ranges as channels in create_ao_task')
            return -1
        
        # Set up ao tasks
        try:       
            for i, chn in enumerate(channels):
                chn = chn.lower()
                if chn not in self._constraints.ao_channels:
                    self.log.error(
                        'Channel {0} not exists'.format(chn))
                    return -1
                chn_name = '/{0}/{1}'.format(self._device_name, chn)
                task.ao_channels.add_ao_voltage_chan(physical_channel=chn_name, min_val=voltage_ranges[i][0],
                max_val=voltage_ranges[i][1])
        except:
            self.terminate_all_tasks()
            self.log.exception('Error adding analog output task.')
            return -1
        self._ao_task_handles.append(task)
        return task

    def close_ao_task(self, taskname = None):
        if taskname is None:
            self.log.error('Need taskname to close the ao task.')
            return -1        
        else:
            for i, task in enumerate(self._ao_task_handles):
                if task.name == taskname:
                    try:
                        if not task.is_task_done():
                            task.stop()
                        task.close()
                    except ni.DaqError:
                        self.log.exception('Error while trying to terminate ao task {0}'.format(taskname))
                        return -1
                    finally:
                        self._ao_task_handles.remove(task)
                        return 0
                elif i == len(self._ao_task_handles)-1:
                    self.log.info('cant close ao task {0}, because it does not exist'.format(taskname))
                    return 0

    def create_ai_task(self, taskname = None, channels = None, voltage_ranges = None):
        if taskname is None:
            self.log.error('Need taskname to create the ai task.')
            return -1
        else:
        # Check if task by that name already exists
            try:
                task = ni.Task(taskname)
            except ni.DaqError:
                self.log.error('ai task with name "{0}" already exists.'.format(taskname))
                return -1
        if channels is None:
            self.log.error('Need channels to create the ai task.')
            return -1
        
        if voltage_ranges is None:
            self.log.error(
                'ai task voltage_ranges is None')
            return -1

        if len(channels) != len(voltage_ranges):
            self.log.error(
                'Specify as many voltage_ranges as channels in create_ai_task')
            return -1
        
        # Set up ai tasks
        try:       
            for i, chn in enumerate(channels):
                chn = chn.lower()
                if chn not in self._constraints.ai_channels:
                    self.log.error(
                        'Channel {0} not exists'.format(chn))
                    return -1
                chn_name = '/{0}/{1}'.format(self._device_name, chn)
                task.ai_channels.add_ai_voltage_chan(physical_channel=chn_name, min_val=voltage_ranges[i][0],
                max_val=voltage_ranges[i][1])
        except:
            self.terminate_all_tasks()
            self.log.exception('Error adding analog input task.')
            return -1
        self._ai_task_handles.append(task)
        return task

    def close_ai_task(self, taskname = None):
        if taskname is None:
            self.log.error('Need taskname to close the ai task.')
            return -1        
        else:
            for i, task in enumerate(self._ai_task_handles):
                if task.name == taskname:
                    try:
                        if not task.is_task_done():
                            task.stop()
                        task.close()
                    except ni.DaqError:
                        self.log.exception('Error while trying to terminate ai task {0}'.format(taskname))
                        return -1
                    finally:
                        self._ai_task_handles.remove(task)
                        return 0
                elif i == len(self._ai_task_handles)-1:
                    self.log.info('cant close ai task {0}, because it does not exist'.format(taskname))
                    return 0


    def create_do_task(self, taskname = None, channels = None):
        if taskname is None:
            self.log.error('Need taskname to create the do task.')
            return -1
        else:
        # Check if task by that name already exists
            try:
                task = ni.Task(taskname)
            except ni.DaqError:
                self.log.error('do task with name "{0}" already exists'.format(taskname))
                return -1
        if channels is None:
            self.log.error('Need channels to create the do task.')
            return -1
        
        # Set up do tasks
        try:       
            for i, chn in enumerate(channels):
                chn = chn.lower()
                chn_name = '/{0}/{1}'.format(self._device_name, chn)
                task.do_channels.add_do_chan(lines=chn_name)
        except:
            self.terminate_all_tasks()
            self.log.exception('Error adding digital output task.')
            return -1
        self._do_task_handles.append(task)
        return task


    def create_di_task(self, taskname = None, channels = None):
        if taskname is None:
            self.log.error('Need taskname to create the di task.')
            return -1
        else:
        # Check if task by that name already exists
            try:
                task = ni.Task(taskname)
            except ni.DaqError:
                self.log.error('di task with name "{0}" already exists'.format(taskname))
                return -1
        if channels is None:
            self.log.error('Need channels to create the di task.')
            return -1
        
        # Set up di tasks
        try:       
            for i, chn in enumerate(channels):
                chn = chn.lower()
                chn_name = '/{0}/{1}'.format(self._device_name, chn)
                task.di_channels.add_di_chan(lines=chn_name)
        except:
            self.terminate_all_tasks()
            self.log.exception('Error adding digital input task.')
            return -1
        self._di_task_handles.append(task)
        return task


    def create_co_task(self, taskname = None, channels = None, freq = None, duty_cycle = None):
        if taskname is None:
            self.log.error('Need taskname to create the co task.')
            return -1
        else:
        # Check if task by that name already exists
            try:
                task = ni.Task(taskname)
            except ni.DaqError:
                self.log.error('co task with name "{0}" already exists'.format(taskname))
                return -1
        if channels is None:
            self.log.error('Need channels to create the co task.')
            return -1
        
        if freq is None:
            self.log.error(
                'co task freq is None')
            return -1

        if duty_cycle is None:
            self.log.error(
                'co task duty_cycle is None')
            return -1
        if len(channels) == 1:
            freq = [freq]
            duty_cycle = [duty_cycle]
        if len(channels) != len(freq):
            self.log.error(
                'Specify as many freq as channels in create_co_task')
            return -1

        if len(channels) != len(duty_cycle):
            self.log.error(
                'Specify as many duty_cycle as channels in create_co_task')
            return -1
        
        # Set up co tasks
        try:       
            for i, chn in enumerate(channels):
                chn = chn.lower()
                if chn not in self._constraints.co_channels:
                    self.log.error(
                        'Channel {0} not exists'.format(chn))
                    return -1
                chn_name = '/{0}/{1}'.format(self._device_name, chn)
                task.co_channels.add_co_pulse_chan_freq(counter=chn_name, freq=freq[i],
                duty_cycle=duty_cycle[i])
        except:
            self.terminate_all_tasks()
            self.log.exception('Error adding counter output task.')
            return -1
        self._co_task_handles.append(task)
        return task

    def close_co_task(self, taskname = None):
        if taskname is None:
            self.log.error('Need taskname to close the co task.')
            return -1        
        else:
            for i, task in enumerate(self._co_task_handles):
                if task.name == taskname:
                    try:
                        if not task.is_task_done():
                            task.stop()
                        task.close()
                    except ni.DaqError:
                        self.log.exception('Error while trying to terminate co task {0}'.format(taskname))
                        return -1
                    finally:
                        self._co_task_handles.remove(task)
                        return 0
                elif i == len(self._co_task_handles)-1:
                    self.log.info('cant close co task {0}, because it does not exist'.format(taskname))
                    return 0


    def create_ci_task(self, taskname = None, channels = None, count_ranges = None):
        """
        Create a task for channels to measure the time between state transitions of a digital signal
        """
        if taskname is None:
            self.log.error('Need taskname to create the ci task.')
            return -1
        else:
        # Check if task by that name already exists
            try:
                task = ni.Task(taskname)
            except ni.DaqError:
                self.log.error('ci task with name "{0}" already exists'.format(taskname))
                return -1
        if channels is None:
            self.log.error('Need channels to create the ci task.')
            return -1
        
        if count_ranges is None:
            self.log.error(
                'ci task count_ranges is None')
            return -1
        if len(channels) == 1:
            count_ranges = [count_ranges]

        if len(channels) != len(count_ranges):
            self.log.error(
                'Specify as many count_ranges as channels in create_ci_task')
            return -1
        
        # Set up co tasks
        try:       
            for i, chn in enumerate(channels):
                chn = chn.lower()
                if chn not in self._constraints.ci_channels:
                    self.log.error(
                        'Channel {0} not exists'.format(chn))
                    return -1
                chn_name = '/{0}/{1}'.format(self._device_name, chn)
                task.ci_channels.add_ci_semi_period_chan(counter=chn_name, min_val=count_ranges[i][0],
                max_val=count_ranges[i][1])
        except:
            self.terminate_all_tasks()
            self.log.exception('Error adding counter input task.')
            return -1
        self._ci_task_handles.append(task)
        return task



    def write_task(self, task, data, auto_start=AUTO_START_UNSET, timeout=10.0):
        """
        copied from task.py in nidaqmx, but fixed a stupid bug from:
                    frequencies.append(sample.duty_cycle)
                    duty_cycles.append(sample.freq)
        to:
                    frequencies.append(sample.freq)
                    duty_cycles.append(sample.duty_cycle)
        """
        channels_to_write = task.channels
        number_of_channels = len(channels_to_write.channel_names)
        write_chan_type = channels_to_write.chan_type

        element = None
        if number_of_channels == 1:
            if isinstance(data, list):
                if isinstance(data[0], list):
                    task._raise_invalid_write_num_chans_error(
                        number_of_channels, len(data))

                number_of_samples_per_channel = len(data)
                element = data[0]

            elif isinstance(data, np.ndarray):
                if len(data.shape) == 2:
                    number_of_samples_per_channel = data.shape[1]
                    element = data[0][0]
                else:
                    number_of_samples_per_channel = len(data)
                    element = data[0]

            else:
                number_of_samples_per_channel = 1
                element = data

        else:
            if isinstance(data, list):
                if len(data) != number_of_channels:
                    task._raise_invalid_write_num_chans_error(
                        number_of_channels, len(data))

                if isinstance(data[0], list):
                    number_of_samples_per_channel = len(data[0])
                    element = data[0][0]
                else:
                    number_of_samples_per_channel = 1
                    element = data[0]

            elif isinstance(data, np.ndarray):
                if data.shape[0] != number_of_channels:
                    task._raise_invalid_write_num_chans_error(
                        number_of_channels, data.shape[0])

                if len(data.shape) == 2:
                    number_of_samples_per_channel = data.shape[1]
                    element = data[0][0]
                else:
                    number_of_samples_per_channel = 1
                    element = data[0]

            else:
                task._raise_invalid_write_num_chans_error(
                    number_of_channels, 1)

        if auto_start is AUTO_START_UNSET:
            if number_of_samples_per_channel > 1:
                auto_start = False
            else:
                auto_start = True

        # Analog Input
        if write_chan_type == ChannelType.ANALOG_OUTPUT:
            data = np.asarray(data, dtype=np.float64)
            return _write_analog_f_64(
                task._handle, data, number_of_samples_per_channel, auto_start,
                timeout)

        # Digital Input
        elif write_chan_type == ChannelType.DIGITAL_OUTPUT:
            if task.out_stream.do_num_booleans_per_chan == 1:
                if (not isinstance(element, bool) and
                        not isinstance(element, np.bool_)):
                    raise DaqError(
                        'Write failed, because this write method only accepts '
                        'boolean samples when there is one digital line per '
                        'channel in a task.\n\n'
                        'Requested sample type: {0}'.format(type(element)),
                        DAQmxErrors.UNKNOWN.value, task_name=task.name)

                data = np.asarray(data, dtype=np.bool)
                return _write_digital_lines(
                    task._handle, data, number_of_samples_per_channel,
                    auto_start, timeout)
            else:
                if (not isinstance(element, six.integer_types) and
                        not isinstance(element, np.uint32)):
                    raise DaqError(
                        'Write failed, because this write method only accepts '
                        'unsigned 32-bit integer samples when there are '
                        'multiple digital lines per channel in a task.\n\n'
                        'Requested sample type: {0}'.format(type(element)),
                        DAQmxErrors.UNKNOWN.value, task_name=task.name)

                data = np.asarray(data, dtype=np.uint32)
                return _write_digital_u_32(
                    task._handle, data, number_of_samples_per_channel,
                    auto_start, timeout)

        # Counter Input
        elif write_chan_type == ChannelType.COUNTER_OUTPUT:
            output_type = channels_to_write.co_output_type

            if number_of_samples_per_channel == 1:
                data = [data]

            if output_type == UsageTypeCO.PULSE_FREQUENCY:
                frequencies = []
                duty_cycles = []
                for sample in data:
                    frequencies.append(sample.freq)
                    duty_cycles.append(sample.duty_cycle)

                frequencies = np.asarray(frequencies, dtype=np.float64)
                duty_cycles = np.asarray(duty_cycles, dtype=np.float64)

                return _write_ctr_freq(
                    task._handle, frequencies, duty_cycles,
                    number_of_samples_per_channel, auto_start, timeout)

            elif output_type == UsageTypeCO.PULSE_TIME:
                high_times = []
                low_times = []
                for sample in data:
                    high_times.append(sample.high_time)
                    low_times.append(sample.low_time)

                high_times = np.asarray(high_times, dtype=np.float64)
                low_times = np.asarray(low_times, dtype=np.float64)

                return _write_ctr_time(
                    task._handle, high_times, low_times,
                    number_of_samples_per_channel, auto_start, timeout)

            elif output_type == UsageTypeCO.PULSE_TICKS:
                high_ticks = []
                low_ticks = []
                for sample in data:
                    high_ticks.append(sample.high_tick)
                    low_ticks.append(sample.low_tick)

                high_ticks = np.asarray(high_ticks, dtype=np.uint32)
                low_ticks = np.asarray(low_ticks, dtype=np.uint32)

                return _write_ctr_ticks(
                    task._handle, high_ticks, low_ticks,
                    number_of_samples_per_channel, auto_start, timeout)
        else:
            raise DaqError(
                'Write failed, because there are no output channels in this '
                'task to which data can be written.',
                DAQmxErrors.WRITE_NO_OUTPUT_CHANS_IN_TASK.value,
                task_name=task.name)





    def samp_timing_type(self, task, type):
        """
        'burst_handshake'
            Determine sample timing using burst handshaking between the device and a peripheral device. 
        'change_detection'
            Acquire samples when a change occurs in the state of one or more digital input lines. The lines must be contained within a digital input channel.
        'handshake'
            Determine sample timing by using digital handshaking between the device and a peripheral device.
        'implicit'
            Configure only the duration of the task.
        'on_demand'
            Acquire or generate a sample on each read or write operation. This timing type is also referred to as static or software-timed.
        'pipelined_sample_clock'
            Device acquires or generates samples on each sample clock edge, but does not respond to certain triggers until a few sample clock edges later. Pipelining allows higher data transfer rates at the cost of increased trigger response latency. Refer to the device documentation for information about which triggers pipelining affects. This timing type allows handshaking with some devices using the Pause trigger, the Ready for Transfer event, or the Data Active event. Refer to the device documentation for more information.
        'sample_clock'
            Acquire or generate samples on the specified edge of the sample clock.
        """
        if isinstance(SampleTimingType[type.upper()], SampleTimingType):
            task.timing.samp_timing_type = SampleTimingType[type.upper()]
        else:
            self.log.error(
                'timing type not in nidaqmx.constants.SampleTimingType')
            return -1
    

    def cfg_implicit_timing(self, task, sample_mode, samps_per_chan=1000):
        """
        Sets only the number of samples to acquire or generate without
        specifying timing. Typically, you should use this instance when
        the task does not require sample timing, such as tasks that use
        counters for buffered frequency measurement, buffered period
        measurement, or pulse train generation. For finite counter
        output tasks, **samps_per_chan** is the number of pulses to
        generate.

        Args:
            sample_mode (Optional[nidaqmx.constants.AcquisitionType]): 
                Specifies if the task acquires or generates samples
                continuously or if it acquires or generates a finite
                number of samples.
            samps_per_chan (Optional[long]): Specifies the number of
                samples to acquire or generate for each channel in the
                task if **sample_mode** is **FINITE_SAMPLES**. If
                **sample_mode** is **CONTINUOUS_SAMPLES**, NI-DAQmx uses
                this value to determine the buffer size. This function
                returns an error if the specified value is negative.
        """  
        if isinstance(AcquisitionType[sample_mode.upper()], AcquisitionType):
            task.timing.cfg_implicit_timing(sample_mode = AcquisitionType[sample_mode.upper()], samps_per_chan = samps_per_chan)
        else:
            self.log.error(
                'sample_mode not in nidaqmx.constants.AcquisitionType')
            return -1

    def cfg_samp_clk_timing(
            self, task, rate, source="", samps_per_chan=1000):
        """
        Sets the source of the Sample Clock, the rate of the Sample
        Clock, and the number of samples to acquire or generate.

        Args:
            rate (float): Specifies the sampling rate in samples per
                channel per second. If you use an external source for
                the Sample Clock, set this input to the maximum expected
                rate of that clock.
            source (Optional[str]): Specifies the source terminal of the
                Sample Clock. Leave this input unspecified to use the
                default onboard clock of the device.
            samps_per_chan (Optional[long]): Specifies the number of
                samples to acquire or generate for each channel in the
                task if **sample_mode** is **FINITE_SAMPLES**. If
                **sample_mode** is **CONTINUOUS_SAMPLES**, NI-DAQmx uses
                this value to determine the buffer size. This function
                returns an error if the specified value is negative.
        """
        source = source.lower()
        source = source[0].upper()+source[1:]
        clk_terminal = '/{0}/{1}InternalOutput'.format(self._device_name,source)
        if clk_terminal in self._device_handle.terminals:
            return task.timing.cfg_samp_clk_timing(rate = rate, source = clk_terminal, samps_per_chan = samps_per_chan)
        else:
            self.log.error(
                '{0} not in _device_handle.terminals'.format(clk_terminal))
            return -1



    def connect_ctr_to_pfi(self, ctr_source, pfi_destination):
        """
        Creates a route between a source and destination terminal. The
        route can carry a variety of digital signals, such as triggers,
        clocks, and hardware events.

        Args:
            source_terminal (str): Specifies the originating terminal of
                the route. A DAQmx terminal constant lists all terminals
                available on devices installed in the system. You also
                can specify a source terminal by specifying a string
                that contains a terminal name.
            destination_terminal (str): Specifies the receiving terminal
                of the route. A DAQmx terminal constant provides a list
                of all terminals available on devices installed in the
                system. You also can specify a destination terminal by
                specifying a string that contains a terminal name.
            signal_modifiers (Optional[nidaqmx.constants.SignalModifiers]): 
                Specifies whether to invert the signal this function
                routes from the source terminal to the destination
                terminal.
        """
        ctr_source = ctr_source.lower()
        ctr_source = ctr_source[0].upper()+ctr_source[1:]
        ctr_source_terminal = '/{0}/{1}InternalOutput'.format(self._device_name, ctr_source)

        pfi_destination = pfi_destination.lower()
        pfi_destination = pfi_destination[:3].upper() + pfi_destination[3:]
        pfi_destination_terminal = '/{0}/{1}'.format(self._device_name, pfi_destination)
        if ctr_source_terminal in self._device_handle.terminals and pfi_destination_terminal in self._device_handle.terminals:
            _system = ni.system.system.System()
            return _system.connect_terms(source_terminal=ctr_source_terminal, destination_terminal=pfi_destination_terminal)
        else:
            self.log.error(
                '{0} or {1} not in _device_handle.terminals'.format(ctr_source_terminal, pfi_destination_terminal))
            return -1


    def disconnect_ctr_to_pfi(self,  ctr_source, pfi_destination):
        """
        Removes signal routes you created by using the DAQmx Connect
        Terminals function. The DAQmx Disconnect Terminals function
        cannot remove task-based routes, such as those you create
        through timing and triggering configuration.

        Args:
            source_terminal (str): Specifies the originating terminal of
                the route. A DAQmx terminal constant lists all terminals
                available on devices installed in the system. You also
                can specify a source terminal by specifying a string
                that contains a terminal name.
            destination_terminal (str): Specifies the receiving terminal
                of the route. A DAQmx terminal constant provides a list
                of all terminals available on devices installed in the
                system. You also can specify a destination terminal by
                specifying a string that contains a terminal name.
        """
        ctr_source = ctr_source.lower()
        ctr_source = ctr_source[0].upper()+ctr_source[1:]
        ctr_source_terminal = '/{0}/{1}InternalOutput'.format(self._device_name, ctr_source)

        pfi_destination = pfi_destination.lower()
        pfi_destination = pfi_destination[:3].upper() + pfi_destination[3:]
        pfi_destination_terminal = '/{0}/{1}'.format(self._device_name, pfi_destination)
        if ctr_source_terminal in self._device_handle.terminals and pfi_destination_terminal in self._device_handle.terminals:
            _system = ni.system.system.System()
            return _system.disconnect_terms(source_terminal=ctr_source_terminal, destination_terminal=pfi_destination_terminal)
        else:
            self.log.error(
                '{0} or {1} not in _device_handle.terminals'.format(ctr_source_terminal, pfi_destination_terminal))
            return -1










    def terminate_all_tasks(self):
        err = 0

        while len(self._ao_task_handles) > 0:
            try:
                if not self._ao_task_handles[-1].is_task_done():
                    self._ao_task_handles[-1].stop()
                self._ao_task_handles[-1].close()
            except ni.DaqError:
                self.log.exception('Error while trying to terminate ao task.')
                err = -1
            finally:
                del self._ao_task_handles[-1]
        self._ao_task_handles = list()

        while len(self._ai_task_handles) > 0:
            try:
                if not self._ai_task_handles[-1].is_task_done():
                    self._ai_task_handles[-1].stop()
                self._ai_task_handles[-1].close()
            except ni.DaqError:
                self.log.exception('Error while trying to terminate ai task.')
                err = -1
            finally:
                del self._ai_task_handles[-1]
        self._ai_task_handles = list()

        while len(self._do_task_handles) > 0:
            try:
                if not self._do_task_handles[-1].is_task_done():
                    self._do_task_handles[-1].stop()
                self._do_task_handles[-1].close()
            except ni.DaqError:
                self.log.exception('Error while trying to terminate do task.')
                err = -1
            finally:
                del self._do_task_handles[-1]
        self._do_task_handles = list()


        while len(self._di_task_handles) > 0:
            try:
                if not self._di_task_handles[-1].is_task_done():
                    self._di_task_handles[-1].stop()
                self._di_task_handles[-1].close()
            except ni.DaqError:
                self.log.exception('Error while trying to terminate di task.')
                err = -1
            finally:
                del self._di_task_handles[-1]
        self._di_task_handles = list()


        while len(self._co_task_handles) > 0:
            try:
                if not self._co_task_handles[-1].is_task_done():
                    self._co_task_handles[-1].stop()
                self._co_task_handles[-1].close()
            except ni.DaqError:
                self.log.exception('Error while trying to terminate co task.')
                err = -1
            finally:
                del self._co_task_handles[-1]
        self._co_task_handles = list()

        while len(self._ci_task_handles) > 0:
            try:
                if not self._ci_task_handles[-1].is_task_done():
                    self._ci_task_handles[-1].stop()
                self._ci_task_handles[-1].close()
            except ni.DaqError:
                self.log.exception('Error while trying to terminate ci task.')
                err = -1
            finally:
                del self._ci_task_handles[-1]
        self._ci_task_handles = list()

        return err


    def reset_hardware(self):
        """
        Resets the NI hardware, so the connection is lost and other programs can access it.

        @return int: error code (0:OK, -1:error)
        """
        self.terminate_all_tasks()
        try:
            self._device_handle.reset_device()
            self.log.info('Reset device {0}.'.format(self._device_name))
        except ni.DaqError:
            self.log.exception('Could not reset NI device {0}'.format(self._device_name))
            return -1
        return 0

