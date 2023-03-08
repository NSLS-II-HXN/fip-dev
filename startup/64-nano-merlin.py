print(f'Loading {__file__}...')

import copy
import datetime
from enum import Enum
import itertools
import sys
import numpy as np
from pathlib import PurePath
import traceback

from ophyd import Signal
from ophyd import Component as Cpt

from ophyd.areadetector.base import ADComponent
from ophyd.areadetector import (AreaDetector, PixiradDetectorCam, ImagePlugin,
                                TIFFPlugin, StatsPlugin, HDF5Plugin,
                                ProcessPlugin, ROIPlugin, TransformPlugin,
                                OverlayPlugin)
from ophyd.areadetector.plugins import PluginBase, HDF5Plugin_V33, TimeSeriesPlugin_V33

from ophyd.areadetector.cam import AreaDetectorCam
from ophyd.device import BlueskyInterface
from ophyd.utils.epics_pvs import set_and_wait
from ophyd.areadetector.trigger_mixins import SingleTrigger
from ophyd.areadetector.filestore_mixins import (FileStoreIterativeWrite,
                                                 FileStoreHDF5IterativeWrite,
                                                 FileStoreTIFFSquashing,
                                                 FileStoreTIFF,
                                                 FileStoreHDF5,
                                                 new_short_uid,
                                                 FileStoreBase,
                                                 FileStorePluginBase,
                                                 )

from nslsii.ad33 import CamV33Mixin, SingleTriggerV33

import logging
logger = logging.getLogger('bluesky')

try:
    from area_detector_handlers import HandlerBase
    from area_detector_handlers.handlers import Xspress3HDF5Handler
except ImportError:
    from databroker.assets.handlers import Xspress3HDF5Handler, HandlerBase


class BulkXspress(HandlerBase):
    HANDLER_NAME = "XPS3_FLY"
    def __init__(self, resource_fn):
        self._handle = h5py.File(resource_fn, "r")

    def __call__(self):
        return self._handle["entry/instrument/detector/data"][:]


class BulkMerlin(HandlerBase):
    HANDLER_NAME = 'MERLIN_FLY_STREAM_V2'

    def __init__(self, resource_fn, *, frame_per_point):
        self._frame_per_point = frame_per_point
        self._handle = h5py.File(resource_fn, "r", libver='latest', swmr=True)

    def __call__(self, point_number):
        n_first = point_number * self._frame_per_point
        n_last = n_first + self._frame_per_point
        ds = self._handle['entry/instrument/detector/data']
        ds.id.refresh()
        return ds[n_first:n_last, :, :]


db.reg.register_handler(BulkMerlin.HANDLER_NAME, BulkMerlin,  overwrite=True)

class SRXMode(Enum):
    step = 1
    fly = 2

class MerlinFileStoreHDF5(FileStoreBase):

    _spec = 'TPX_HDF5'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.stage_sigs.update([('auto_increment', 'Yes'),
                                ('array_counter', 0),
                                ('auto_save', 'Yes'),
                                ('num_capture', 0),  # will be updated later
                                (self.file_template, '%s%s_%6.6d.h5'),
                                (self.file_write_mode, 'Stream'),
                                (self.compression, 'zlib'),
                                (self.capture, 1),
                                (self.queue_size, 2000),  # Make the queue large enough
                                ])

        self._point_counter = None
        self.frame_per_point = None

    def unstage(self):
        self._point_counter = None
        return super().unstage()

    def make_filename(self):
        filename = new_short_uid()
        formatter = datetime.now().strftime
        write_path = formatter(self.write_path_template)
        read_path = formatter(self.read_path_template)

        fn, read_path, write_path = filename, read_path, write_path
        return fn, read_path, write_path

    @property
    def filestore_spec(self):
        if self.parent._mode == SRXMode.fly:
            return BulkMerlin.HANDLER_NAME
        return 'TPX_HDF5'

    def generate_datum(self, key, timestamp, datum_kwargs):
        if self.parent._mode is SRXMode.fly:
            i = next(self._point_counter)
            datum_kwargs = datum_kwargs or {}
            datum_kwargs.update({'point_number': i})
            return super().generate_datum(key, timestamp, datum_kwargs)
        elif self.parent._mode is SRXMode.step:
            i = next(self._point_counter)
            datum_kwargs = datum_kwargs or {}
            datum_kwargs.update({'point_number': i})
            return super().generate_datum(key, timestamp, datum_kwargs)

    def stage(self):
        # Make a filename.
        filename, read_path, write_path = self.make_filename()

        if self.frame_per_point:
            self.stage_sigs[self.num_frames_flush] = self.frame_per_point

        # Ensure we do not have an old file open.
        # set_and_wait(self.capture, 0)
        self.capture.set(0).wait()
        # These must be set before parent is staged (specifically
        # before capture mode is turned on. They will not be reset
        # on 'unstage' anyway.
        # set_and_wait(self.file_path, write_path)
        self.file_path.set(write_path).wait()
        # set_and_wait(self.file_name, filename)
        self.file_name.set(filename).wait()
        # set_and_wait(self.file_number, 0)
        self.file_number.set(0).wait()
        staged = super().stage()

        # AD does this same templating in C, but we can't access it
        # so we do it redundantly here in Python.
        # file_number is *next* iteration
        self._fn = self.file_template.get() % (read_path,
                                               filename,
                                               self.file_number.get() - 1)
        self._fp = read_path

        if not self.file_path_exists.get():
            raise IOError("Path %s does not exist on IOC." % self.file_path.get())

        self._point_counter = itertools.count()

        if self.parent._mode is SRXMode.fly:
            if self.frame_per_point is None:
                raise ValueError("'frame_per_point' is not set before staging")
            res_kwargs = {'frame_per_point': self.frame_per_point}
        else:
            res_kwargs = {'frame_per_point': 1}

        logger.debug("Inserting resource with filename %s", self._fn)
        self._generate_resource(res_kwargs)

        return staged

    def pause(self):
        super().pause()
        self.unstage()

    def resume(self):
        self.stage()
        super().resume()


class HDF5PluginWithFileStoreMerlin(HDF5Plugin_V33, MerlinFileStoreHDF5):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 'swmr_mode' must be set first. Rearrange 'stage_sigs'.
        self.stage_sigs[self.swmr_mode] = 1
        self.stage_sigs[self.num_frames_flush] = 1  # Set later
        self.stage_sigs.move_to_end(self.num_frames_flush, last=False)
        self.stage_sigs.move_to_end(self.swmr_mode, last=False)


    def stage(self):

        if np.array(self.array_size.get()).sum() == 0:
            raise Exception("you must warmup the hdf plugin via the `warmup()` "
                            "method on the hdf5 plugin.")

        if self.frame_per_point:
            self.stage_sigs[self.num_frames_flush] = self.frame_per_point

        return super().stage()

    def describe(self):
        desc = super().describe()

        # Replace the shape for 'merlin2_image'. Height and width should be acquired directly
        # from HDF5 plugin, since the size of the image could be restricted by ROI.
        for k, v in desc.items():
            if k.endswith("_image") and ("shape" in v) and (len(v["shape"]) >= 2):
                height = self.height.get()
                width = self.width.get()
                orig_shape = v["shape"]
                v["shape"] = orig_shape[:-2] + (height, width)
                print(f"Descriptor: shape of {k!r} was updated. The shape {orig_shape} was replaced by {v['shape']}")

        return desc


class MerlinDetectorCam(AreaDetectorCam, CamV33Mixin):
    pass


class MerlinDetector(AreaDetector):
    cam = Cpt(MerlinDetectorCam, 'cam1:',
              read_attrs=[],
              configuration_attrs=['image_mode', 'trigger_mode',
                                   'acquire_time', 'acquire_period'],
              )

class TimeSeriesPluginHXN(TimeSeriesPlugin_V33):
    ts_read_scan = ADComponent(EpicsSignal, "TSRead.SCAN")
    ts_read_proc = ADComponent(EpicsSignal, "TSRead.PROC")


class StatsPluginHXN(StatsPlugin):
    ts = ADComponent(TimeSeriesPluginHXN, "TS:")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.stage_sigs[self.queue_size] = 2000
        self.stage_sigs[self.ts.queue_size] = 2000
        self.stage_sigs[self.ts.ts_acquire_mode] = "Fixed length"


class SRXMerlin(SingleTriggerV33, MerlinDetector):
    total_points = Cpt(Signal,
                       value=1,
                       doc="The total number of points to be taken")
    fly_next = Cpt(Signal,
                   value=False,
                   doc="latch to put the detector in 'fly' mode")

    hdf5 = Cpt(HDF5PluginWithFileStoreMerlin, 'HDF1:',
               read_attrs=[],
               # read_path_template='/nsls2/xf05id1/XF05ID1/MERLIN/%Y/%m/%d/',
               # read_path_template='/nsls2/xf05id1/XF05ID1/MERLIN/2021/02/11/',
               # read_path_template='/nsls2/data/srx/assets/merlin/%Y/%m/%d/',
               # read_path_template = LARGE_FILE_DIRECTORY_ROOT + '/%Y/%m/%d/',
               read_path_template = LARGE_FILE_DIRECTORY_PATH,
               configuration_attrs=[],
               # write_path_template='/epicsdata/merlin/%Y/%m/%d/',
               # write_path_template='/epicsdata/merlin/2021/02/11/',
               # write_path_template='/nsls2/data/srx/assets/merlin/%Y/%m/%d/',
               # write_path_template=LARGE_FILE_DIRECTORY_ROOT + '/%Y/%m/%d/',
               write_path_template = LARGE_FILE_DIRECTORY_PATH,
               root=LARGE_FILE_DIRECTORY_ROOT)

    stats1 = Cpt(StatsPluginHXN, 'Stats1:')
    stats2 = Cpt(StatsPluginHXN, 'Stats2:')
    stats3 = Cpt(StatsPluginHXN, 'Stats3:')
    stats4 = Cpt(StatsPluginHXN, 'Stats4:')
    stats5 = Cpt(StatsPluginHXN, 'Stats5:')
    proc1 = Cpt(ProcessPlugin, 'Proc1:')
    transform1 = Cpt(TransformPlugin, 'Trans1:')

    roi1 = Cpt(ROIPlugin, 'ROI1:')
    roi2 = Cpt(ROIPlugin, 'ROI2:')
    roi3 = Cpt(ROIPlugin, 'ROI3:')
    roi4 = Cpt(ROIPlugin, 'ROI4:')

    image1 = Cpt(ImagePlugin, 'image1:')

    # def __init__(self, prefix, *, configuration_attrs=None, read_attrs=None,
    #              **kwargs):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._mode = SRXMode.step
        self.cam.ensure_nonblocking()

    def stop(self, success=False):
        ret = super().stop(success=success)
        self.hdf5.stop()
        return ret

    def stage(self):
        # do the latching
        print("Staging Merlin - starting")
        if self.fly_next.get():
            self.fly_next.put(False)
            # According to Ken's comments in hxntools, this is a de-bounce time
            # when in external trigger mode

            # moved this to the plan
            # self.stage_sigs[self.cam.acquire_time] = 0.005
            # self.stage_sigs[self.cam.acquire_period] = 0.0066392

            self.stage_sigs[self.cam.image_mode] = 1  # 0 -single, 1 - multiple
            self.stage_sigs[self.cam.trigger_mode] = 1  # 0 - internal, 1 - trigger enable, 2 - start rising
            # self.stage_sigs[self.cam.trigger_mode] = 2  # 0 - internal, 1 - trigger enable, 2 - start rising

            self.stats1.ts.ts_acquire.set(1).wait()

            self._mode = SRXMode.fly
        else:
            # Set trigger mode
            self.stage_sigs[self.cam.trigger_mode] = 0

            # Make sure we respect whatever the exposure time is set to
            count_time = self.cam.acquire_time.get()
            if count_time is not None:
                self.stage_sigs[self.cam.acquire_time] = count_time
                self.stage_sigs[self.cam.acquire_period] = count_time + 0.005

            # self.stage_sigs.pop(self.cam.acquire_time)
            # self.stage_sigs.pop(self.cam.acquire_period)
            # self.stage_sigs[self.cam.trigger_mode] = 0

            self._mode = SRXMode.step

        print("Staging Merlin - superclass")
        st = super().stage()
        print("Staging Merlin - finished ")
        return st

    def unstage(self):
        try:
            ret = super().unstage()
            self.stats1.ts.ts_acquire.set(0).wait()
        finally:
            self._mode = SRXMode.step
        return ret

    def pause(self):
        super().pause()
        self.hdf5.pause()

    def resume(self):
        super().resume()
        self.hdf5.resume()

    def trigger(self):
        self.stats1.ts.ts_acquire.set(1).wait()
        return super().trigger()


try:
    # raise Exception("'merlin2' is disabled.")
    merlin2 = SRXMerlin('XF:03IDC-ES{Merlin:2}',
                       name='merlin2',
                       # read_attrs=['hdf5', 'cam', 'stats1'])
                       read_attrs=['hdf5', 'cam'])
    merlin2.hdf5.read_attrs = []
    merlin2.cam.acquire_period.tolerance = 0.002  # default is 0.001

    # Should be set before warmup
    merlin2.hdf5.nd_array_port.set("MERLIN").wait()
    # merlin2.hdf5.nd_array_port.set("ROI1").wait()

    merlin2.hdf5.warmup()
except TimeoutError as ex:
    print('\nCannot connect to Merlin. Continuing without device.\n')
    # print(f"Exception: {ex}")
    traceback.print_exc()
    print()
except Exception:
    print('\nUnexpected error connecting to Merlin.\n',
          sys.exc_info()[0],
          end='\n\n')
    traceback.print_exc()
    print()
