# -*- coding: utf-8 -*-
import copy
import numpy as np
from enum import Enum 
import time

from core.module import Base
from core.connector import Connector
from TimeTagger import ChannelEdge
from core.util.helpers import natural_sort
from interface.data_instream_interface import DataInStreamInterface, DataInStreamConstraints
from interface.data_instream_interface import StreamingMode, StreamChannelType, StreamChannel


class TTMeasurementMode(Enum):
    COUNTER = 0
    COUNTBETWEENMARKERS = 1
    HISTOGRAM = 2
    CORRELATION = 3

class TTInstreamInterfuse(Base, DataInStreamInterface):
    """ Methods to use TimeTagger as data in-streaming device (continuously read values)
    """

    timetagger = Connector(interface = "TT")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.__data_type = np.float64
        self._is_running = False

        self.configure(*args, **kwargs)

        # Internal settings

        self.__stream_length = -1
        self.__buffer_size = -1
        self.__use_circular_buffer = False
        self.__streaming_mode = None
        self.__active_channels = tuple()

        # Data buffer
        self._data_buffer = np.empty(0, dtype=self.__data_type)
        self._has_overflown = False

        self._last_read = None
        self._start_time = None

        # Stored hardware constraints
        self._constraints = None
        return


    def on_activate(self):
        self._tt = self.timetagger()


    def on_deactivate(self):
        """ Deactivate the module and clean up.
        """
        pass

    def configure(self, **kwargs):
        """
        Method to configure all possible settings of the data input stream.

        @param float sample_rate: The sample rate in Hz at which data points are acquired
        @param StreamingMode streaming_mode: The streaming mode to use (finite or continuous)
        @param iterable active_channels: Iterable of channel names (str) to be read from.
        @param int stream_length: In case of a finite data stream, the total number of
                                            samples to read per channel
        @param int buffer_size: The size of the data buffer to pre-allocate in samples per channel
        @param bool use_circular_buffer: Use circular buffering (True) or stop upon buffer overflow
                                         (False)

        @return dict: All current settings in a dict. Keywords are the same as kwarg names.
        """

        if self._check_settings_change():
            if len(args) == 0:
                param_dict = kwargs
            elif len(args) == 1 and isinstance(args[0], dict):
                param_dict = args[0]
                param_dict.update(kwargs)
            else:
                raise TypeError('"TTInstreamInterfuse.configure" takes exactly 0 or 1 positional '
                                'argument of type dict.')

            if isinstance(param_dict['measurement_mode'], TTMeasurementMode):
                self.__measurement_mode = param_dict["measurement_mode"]
            else:
                self.log.error('"TTInstreamInterfuse.configure" Argurement must include measurement_mode'
                                'Example: measurement_mode = TTMeasurementMode.COUNTER')
                return

            if self.__measurement_mode == TTMeasurementMode.COUNTER:
                if 'channel' in param_dict.keys():
                    self.__active_channels = tuple(param_dict['channel'])
                else:
                
                if 'sample_rate' in param_dict.keys():
                    self.__sample_rate = param_dict['sample_rate']
                else:
                    self.__sample_rate = int(round(1e12/ self._tt._counter['bins_width']))
                
                


            # Handle sample rate change
            if sample_rate is not None:
                self.sample_rate = sample_rate

            # Handle streaming mode change
            if streaming_mode is not None:
                self.streaming_mode = streaming_mode

            # Handle active channels
            if active_channels is not None:
                self.active_channels = active_channels

            # Handle total number of samples
            if stream_length is not None:
                self.stream_length = stream_length

            # Handle buffer size
            if buffer_size is not None:
                self.buffer_size = buffer_size

            # Handle circular buffer flag
            if use_circular_buffer is not None:
                self.use_circular_buffer = use_circular_buffer
        return self.all_settings


    def is_running(self):
        """
        Read-only flag indicating if the data acquisition is running.

        @return bool: Data acquisition is running (True) or not (False)
        """
        return self._is_running


    # =============================================================================================
    def _init_buffer(self):
        if not self.is_running:
            self._data_buffer = np.zeros(
                self.number_of_channels * self.buffer_size,
                dtype=self.data_type)
            self._has_overflown = False
        return

    def _check_settings_change(self):
        """
        Helper method to check if streamer settings can be changed, i.e. if the streamer is idle.
        Throw a warning if the streamer is running.

        @return bool: Flag indicating if settings can be changed (True) or not (False)
        """
        if self.is_running:
            self.log.warning('Unable to change streamer settings while streamer is running. '
                             'New settings ignored.')
            return False
        return True