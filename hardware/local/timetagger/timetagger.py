
from os.path import join, getsize, isfile
import numpy as np
from TimeTagger import createTimeTagger, Dump, Correlation, Histogram, Counter, CountBetweenMarkers, FileWriter, Countrate, Combiner, TimeDifferences
from core.configoption import ConfigOption
from core.module import Base


class TT(Base):
    """ Designed for driving TimeTagger from swabian instruments.

    See Time Tagger User Manual.

    Example config for copy-paste:

    tagger:
        module.Class: 'local.timetagger.TT'
        hist:
            channel: 1
            trigger_channel: 5
            bins_width: 1000    #ps
            number_of_bins: 500
        
        corr:
            channel_start: 1
            channel_stop: 2
            bins_width: 1000
            number_of_bins: 1000

        counter:
            channels: [1, 2]
            bins_width: 1e12
            n_values: 100
        


    """
    _hist = ConfigOption('hist', False, missing='warn')
    _corr = ConfigOption('corr', False, missing='warn')
    _counter = ConfigOption('counter', False, missing='warn')
    _channels_params = ConfigOption('channels_params', False, missing='warn')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.sample_rate = 50
        chan_alphabet = ['one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight']
        self.channel_codes = dict(zip(chan_alphabet, list(range(1,9,1))))

    def on_activate(self):
        self.setup_TT()

    def on_deactivate(self):
        pass

    def setup_TT(self):
        try:
            self.tagger = createTimeTagger()
            # self.tagger.reset()
            print(f"Tagger initialization successful: {self.tagger.getSerial()}")
        except:
            self.log.error(f"\nCheck if the TimeTagger device is being used by another instance.")
            Exception(f"\nCheck if the TimeTagger device is being used by another instance.")

        #Create combine channels:

        self._combined_apdChans = self.combiner(self._counter["channels"])     # create virtual channel that combines time_tags from apdChans. 

        # # set specified in the params.yaml channels params
        # for channel, params in self._channels_params.items():
        #     channel = self.channel_codes[channel]
        #     if 'delay' in params.keys():
        #         self.delay_channel(delay=params['delay'], channel = channel)
        #     if 'triggerLevel' in params.keys():
        #         self.tagger.setTriggerLevel(channel, params['triggerLevel'])

    def histogram(self, **kwargs):  
        """
        Histogram the clicks in 'channel' with trigger
        It is possible to set values:
        Example:
        channel=1, trigger_channel=5, bins_width=1000, numer_of_bins= 1000
        bins_width is in ps
        get data by .getData()
        get time index by .getIndex()
        """
        for key, value in kwargs.items():
            if key in self._hist.keys():
                self._hist.update({key:int(value)})
        return Histogram(self.tagger,
                            self._hist['channel'],
                            self._hist['trigger_channel'],
                            self._hist['bins_width'],
                            self._hist['number_of_bins'])
    
    def correlation(self, **kwargs):  
        """
        Accumulates time differences between clicks on two channels into a histogram.
        It is possible to set values:
        Example:
        channel_start=1, channel_stop=2, bins_width=1000, numer_of_bins= 1000

        get data by .getData()
        get normalized g2 by .getDataNormalized()
        get time index by .getIndex()
        """
        for key, value in kwargs.items():
            if key in self._corr.keys():
                self._corr.update({key:value})
        return Correlation(self.tagger,
                            self._corr['channel_stop'],
                            self._corr['channel_start'],
                            self._corr['bins_width'],
                            self._corr['number_of_bins'])


    def delay_channel(self, channel, delay):
        """
        Set delay on the channel,
        this delay can be positive or negative,
        if absolute value of the delay not exceed 2000000 ps, this delay will be applied onboard directly.
        """
        self.tagger.setInputDelay(delay=delay, channel=channel)


    def dump(self, dumpPath, filtered_channels=None): 

        if filtered_channels != None:
            self.tagger.setConditionalFilter(filtered=[filtered_channels], trigger=self.apdChans)
        return Dump(self.tagger, dumpPath, self.maxDumps,\
                                    self.allChans)
        
    def countrate(self, channels=None):
        """
        Measures the average count rate on one or more channels.
        get data by .getData(). The output is 1D_array giving the counts per second on the specified channels starting from the very first tag arriving after the instantiation or last call to clear() of the measurement.
        """
        if channels == None:
            channels = self._counter['channels']
        
        return Countrate(self.tagger,
                                channels)

    def counter(self, **kwargs):
        """
        Using a circular buffer to record countrate.
        bins_width: binwidth in ps; n_values: number of bins
        get data by .getData(). The output is 2D_array giving the current values of the circular buffer for each channel.
        """
        for key, value in kwargs.items():
            if key in self._counter.keys():
                self._counter.update({key:value})
            if key == 'refresh_rate' and value != None:
                self._counter['bins_width'] = int(1e12/value)
        return Counter(self.tagger,
                                self._counter['channels'],
                                self._counter['bins_width'],
                                self._counter['n_values'])


    def combiner(self, channels):
        """
        Create virtual channel that combines time_tags from 'combiner channels'. 
        """
        return Combiner(self.tagger, channels)


    def count_between_markers(self, click_channel, begin_channel, n_values, end_channel = None):
        """
        Counts events on a single channel within the time indicated by a “start” and “stop” signals.
        Compared with counter function, this function gives possibility to synchronize the measurements and actions.
        With end_channel on this function accumulate counts within a gate.
        """
        return CountBetweenMarkers(self.tagger,
                                click_channel,
                                begin_channel,
                                end_channel,
                                n_values)     



    def write_into_file(self, filename, apdChans = None, filteredChans = []):
        """
        Writes the time-tag-stream into a file in a binary format with a lossless compression.
        """
        if apdChans is None:
            apdChans = self._counter["channels"]
        if filteredChans == []:
            self.tagger.setConditionalFilter(trigger=[], filtered=[])
        else:
            self.tagger.setConditionalFilter(trigger=apdChans, filtered=filteredChans)
        self.allChans = [ *apdChans, *filteredChans]
        return FileWriter(self.tagger,
        filename, self.allChans)


    def time_differences(self, click_channel, start_channel, scan_trigger_channel, line_trigger_channel, binwidth, n_bins,n_histograms):
        """
        Gives the ability to launch startstop measurement with scan trigger and line trigger.
        make 2d g^2 measurement possible
        """
        return TimeDifferences(self.tagger, 
                                click_channel, 
                                start_channel, 
                                scan_trigger_channel,
                                line_trigger_channel,
                                binwidth, 
                                n_bins,
                                n_histograms)

    