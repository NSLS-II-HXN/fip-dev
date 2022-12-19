print(f"Loading {__file__}...")

from collections import OrderedDict

from epics import caput, caget
import os
import threading
import h5py
import numpy as np
import time as ttime
from ophyd import Device, EpicsSignal, EpicsSignalRO
from ophyd import Component as Cpt
from hxntools.detectors.zebra import Zebra, EpicsSignalWithRBV
from databroker.assets.handlers import HandlerBase
from ophyd.areadetector.filestore_mixins import resource_factory


xs = None  # No Xspress3
use_sclr1 = False  # Set this False to run zebra without 'sclr1'
# use_sclr1 = True


class ZebraHDF5Handler(HandlerBase):
    HANDLER_NAME = "ZEBRA_HDF51_FLY_STREAM_V1"

    def __init__(self, resource_fn, *, frame_per_point):
        self._frame_per_point = frame_per_point
        self._handle = h5py.File(resource_fn, "r", libver='latest', swmr=True)

    def __call__(self, *, column, point_number):
        n_first = point_number * self._frame_per_point
        n_last = n_first + self._frame_per_point
        ds = self._handle[column]
        ds.id.refresh()
        return ds[n_first:n_last]


db.reg.register_handler(ZebraHDF5Handler.HANDLER_NAME, ZebraHDF5Handler, overwrite=True)


class SISHDF5Handler(HandlerBase):
    HANDLER_NAME = "SIS_HDF51_FLY_STREAM_V1"

    def __init__(self, resource_fn):
        self._handle = h5py.File(resource_fn, "r", libver='latest', swmr=True)

    def __call__(self, *, column):
        return self._handle[column][:]

    def close(self):
        self._handle.close()
        self._handle = None
        super().close()


db.reg.register_handler(SISHDF5Handler.HANDLER_NAME, SISHDF5Handler, overwrite=True)



class ZebraPositionCaptureData(Device):
    """
    Data arrays for the Zebra position capture function and their metadata.
    """

    # Data arrays
    div1 = Cpt(EpicsSignal, "PC_DIV1")
    div2 = Cpt(EpicsSignal, "PC_DIV2")
    div3 = Cpt(EpicsSignal, "PC_DIV3")
    div4 = Cpt(EpicsSignal, "PC_DIV4")
    enc1 = Cpt(EpicsSignal, "PC_ENC1")
    enc2 = Cpt(EpicsSignal, "PC_ENC2")
    enc3 = Cpt(EpicsSignal, "PC_ENC3")
    enc4 = Cpt(EpicsSignal, "PC_ENC4")
    filt1 = Cpt(EpicsSignal, "PC_FILT1")
    filt2 = Cpt(EpicsSignal, "PC_FILT2")
    filt3 = Cpt(EpicsSignal, "PC_FILT3")
    filt4 = Cpt(EpicsSignal, "PC_FILT4")
    time = Cpt(EpicsSignal, "PC_TIME")
    # Array sizes
    num_cap = Cpt(EpicsSignal, "PC_NUM_CAP")
    num_down = Cpt(EpicsSignal, "PC_NUM_DOWN")
    # BOOLs to denote arrays with data
    cap_enc1_bool = Cpt(EpicsSignal, "PC_BIT_CAP:B0")
    cap_enc2_bool = Cpt(EpicsSignal, "PC_BIT_CAP:B1")
    cap_enc3_bool = Cpt(EpicsSignal, "PC_BIT_CAP:B2")
    cap_enc4_bool = Cpt(EpicsSignal, "PC_BIT_CAP:B3")
    cap_filt1_bool = Cpt(EpicsSignal, "PC_BIT_CAP:B4")
    cap_filt2_bool = Cpt(EpicsSignal, "PC_BIT_CAP:B5")
    cap_div1_bool = Cpt(EpicsSignal, "PC_BIT_CAP:B6")
    cap_div2_bool = Cpt(EpicsSignal, "PC_BIT_CAP:B7")
    cap_div3_bool = Cpt(EpicsSignal, "PC_BIT_CAP:B8")
    cap_div4_bool = Cpt(EpicsSignal, "PC_BIT_CAP:B9")


class ZebraPositionCapture(Device):
    """
    Signals for the position capture function of the Zebra
    """

    # Configuration settings and status PVs
    enc = Cpt(EpicsSignalWithRBV, "PC_ENC")
    egu = Cpt(EpicsSignalRO, "M1:EGU")
    dir = Cpt(EpicsSignalWithRBV, "PC_DIR")
    tspre = Cpt(EpicsSignalWithRBV, "PC_TSPRE")
    trig_source = Cpt(EpicsSignalWithRBV, "PC_ARM_SEL")
    arm = Cpt(EpicsSignal, "PC_ARM")
    disarm = Cpt(EpicsSignal, "PC_DISARM")
    armed = Cpt(EpicsSignalRO, "PC_ARM_OUT")
    gate_source = Cpt(EpicsSignalWithRBV, "PC_GATE_SEL")
    gate_start = Cpt(EpicsSignalWithRBV, "PC_GATE_START")
    gate_width = Cpt(EpicsSignalWithRBV, "PC_GATE_WID")
    gate_step = Cpt(EpicsSignalWithRBV, "PC_GATE_STEP")
    gate_num = Cpt(EpicsSignalWithRBV, "PC_GATE_NGATE")
    gated = Cpt(EpicsSignalRO, "PC_GATE_OUT")
    pulse_source = Cpt(EpicsSignalWithRBV, "PC_PULSE_SEL")
    pulse_start = Cpt(EpicsSignalWithRBV, "PC_PULSE_START")
    pulse_width = Cpt(EpicsSignalWithRBV, "PC_PULSE_WID")
    pulse_step = Cpt(EpicsSignalWithRBV, "PC_PULSE_STEP")
    pulse_max = Cpt(EpicsSignalWithRBV, "PC_PULSE_MAX")
    pulse = Cpt(EpicsSignalRO, "PC_PULSE_OUT")
    enc_pos1_sync = Cpt(EpicsSignal, "M1:SETPOS.PROC")
    enc_pos2_sync = Cpt(EpicsSignal, "M2:SETPOS.PROC")
    enc_pos3_sync = Cpt(EpicsSignal, "M3:SETPOS.PROC")
    enc_pos4_sync = Cpt(EpicsSignal, "M4:SETPOS.PROC")
    enc_res1 = Cpt(EpicsSignal, "M1:MRES")
    enc_res2 = Cpt(EpicsSignal, "M2:MRES")
    enc_res3 = Cpt(EpicsSignal, "M3:MRES")
    enc_res4 = Cpt(EpicsSignal, "M4:MRES")
    data_in_progress = Cpt(EpicsSignalRO, "ARRAY_ACQ")
    block_state_reset = Cpt(EpicsSignal, "SYS_RESET.PROC")
    data = Cpt(ZebraPositionCaptureData, "")

    pos1_set = Cpt(EpicsSignal, "POS1_SET")

    def stage(self):
        self.arm.put(1)

        super().stage()

    def unstage(self):
        self.disarm.put(1)
        self.block_state_reset.put(1)

        super().unstage()


class SRXZebra(Zebra):
    """
    SRX Zebra device.
    """

    pc = Cpt(ZebraPositionCapture, "")

    def __init__(
        self, prefix, *,
        read_attrs=None, configuration_attrs=None, **kwargs
    ):
        if read_attrs is None:
            read_attrs = []
        if configuration_attrs is None:
            configuration_attrs = []

        super().__init__(
            prefix,
            read_attrs=read_attrs,
            configuration_attrs=configuration_attrs,
            **kwargs,
        )



class SRXFlyer1Axis(Device):
    """
    This is the Zebra.
    """
    LARGE_FILE_DIRECTORY_WRITE_PATH = LARGE_FILE_DIRECTORY_PATH
    LARGE_FILE_DIRECTORY_READ_PATH = LARGE_FILE_DIRECTORY_PATH
    LARGE_FILE_DIRECTORY_ROOT = LARGE_FILE_DIRECTORY_ROOT
    KNOWN_DETS = {"xs", "xs2", "merlin2", "eiger2", "dexela"}
    fast_axis = Cpt(Signal, value="HOR", kind="config")
    slow_axis = Cpt(Signal, value="VER", kind="config")

    @property
    def encoder(self):
        return self._encoder

    @property
    def detectors(self):
        return tuple(self._dets)

    @detectors.setter
    def detectors(self, value):
        dets = tuple(value)
        if not all(d.name in self.KNOWN_DETS for d in dets):
            raise ValueError(
                f"One or more of {[d.name for d in dets]}"
                f"is not known to the zebra. "
                f"The known detectors are {self.KNOWN_DETS})"
            )
        self._dets = dets

    @property
    def sclr(self):
        return self._sis

    def __init__(self, dets, sclr1, zebra, *, reg=db.reg, **kwargs):
        super().__init__("", parent=None, **kwargs)
        self._mode = "idle"
        self._dets = dets
        self._sis = sclr1
        self._filestore_resource = None
        self._encoder = zebra

        # # Gating info for encoder capture
        self.stage_sigs[self._encoder.pc.gate_num] = 1
        self.stage_sigs[self._encoder.pc.pulse_start] = 0

        # This is for the merlin
        self.stage_sigs[self._encoder.output1.ttl.addr] = 31

        if self._sis is not None:
            # Put SIS3820 into single count (not autocount) mode
            # self.stage_sigs[self._sis.count_mode] = 0
            # Stop the SIS3820
            self._sis.stop_all.put(1)

        # self._encoder.pc.block_state_reset.put(1)
        self.reg = reg
        self._document_cache = []
        self._last_bulk = None

        self._point_counter = None
        self.frame_per_point = None

        self._data_exporter = ExportNanoZebraData()

    def _select_captured_data(self):
        """
        Select the data to be captured by Zebra. Capturing unnecessary data slows down
        the scans, so only necessary sources should be selected. Setting the respective
        PVs can not be done in a fast sequence (technically setting PV is fast, but Zebra
        parameters remain unchanged unless there is a pause after writing to each PV),
        so the configuration can not be performed using 'stage_sigs'.
        """
        dir = self.fast_axis.get()

        sigs = {_: 0 for _ in [
            self._encoder.pc.data.cap_enc1_bool,
            self._encoder.pc.data.cap_enc2_bool,
            self._encoder.pc.data.cap_enc3_bool,
            self._encoder.pc.data.cap_enc4_bool,
            self._encoder.pc.data.cap_filt1_bool,
            self._encoder.pc.data.cap_filt2_bool,
            self._encoder.pc.data.cap_div1_bool,
            self._encoder.pc.data.cap_div2_bool,
            self._encoder.pc.data.cap_div3_bool,
            self._encoder.pc.data.cap_div4_bool
        ]}

        if dir == "NANOHOR":
            sigs[self._encoder.pc.data.cap_enc1_bool] = 1
        elif dir == "NANOVER":
            sigs[self._encoder.pc.data.cap_enc2_bool] = 1
        elif dir == "NANOZ":
            sigs[self._encoder.pc.data.cap_enc3_bool] = 1
        else:
            raise ValueError(f"Unknown value: dir={dir!r}")

        # Change the PV values only if the new values is different from the current values.
        for sig, value in sigs.items():
            current_value = sig.get()
            if current_value != value:
                sig.set(value).wait()
                ttime.sleep(0.2)  # Determined experimentally

    def stage(self):
        self._point_counter = 0
        dir = self.fast_axis.get()

        self._select_captured_data()

        if dir == "NANOHOR":
            self.stage_sigs[self._encoder.pc.enc] = "Enc1"
            # self.stage_sigs[self._encoder.pc.dir] = "Positive"
            # self.stage_sigs[self._encoder.pc.enc_res2] = 9.5368e-05
        elif dir == "NANOVER":
            self.stage_sigs[self._encoder.pc.enc] = "Enc2"
            # self.stage_sigs[self._encoder.pc.dir] = "Positive"
            # self.stage_sigs[self._encoder.pc.enc_res2] = 9.5368e-05
        elif dir == "NANOZ":
            self.stage_sigs[self._encoder.pc.enc] = "Enc3"
            # self.stage_sigs[self._encoder.pc.dir] = "Positive"
            # self.stage_sigs[self._encoder.pc.enc_res2] = 9.5368e-05
        else:
            raise ValueError(f"Unknown value: dir={dir!r}")

        print(f"stage_sigs={self.stage_sigs}") ##

        self.__filename = "{}.h5".format(uuid.uuid4())
        self.__filename_sis = "{}.h5".format(uuid.uuid4())
        self.__read_filepath = os.path.join(
            self.LARGE_FILE_DIRECTORY_READ_PATH, self.__filename
        )
        self.__read_filepath_sis = os.path.join(
            self.LARGE_FILE_DIRECTORY_READ_PATH, self.__filename_sis
        )
        self.__write_filepath = os.path.join(
            self.LARGE_FILE_DIRECTORY_WRITE_PATH, self.__filename
        )
        self.__write_filepath_sis = os.path.join(
            self.LARGE_FILE_DIRECTORY_WRITE_PATH, self.__filename_sis
        )

        self.__filestore_resource, self._datum_factory_z = resource_factory(
            ZebraHDF5Handler.HANDLER_NAME,
            root=self.LARGE_FILE_DIRECTORY_ROOT,
            resource_path=self.__read_filepath,
            resource_kwargs={"frame_per_point": self.frame_per_point},
            path_semantics="posix",
        )
        self.__filestore_resource_sis, self._datum_factory_sis = resource_factory(
            SISHDF5Handler.HANDLER_NAME,
            root=self.LARGE_FILE_DIRECTORY_ROOT,
            resource_path=self.__read_filepath_sis,
            resource_kwargs={"frame_per_point": self.frame_per_point},
            path_semantics="posix",
        )

        resources = [self.__filestore_resource]
        if self._sis:
            resources.append(self.__filestore_resource_sis)
        self._document_cache.extend(("resource", _) for _ in resources)

        self._data_exporter.open(self.__write_filepath)

        super().stage()

    def unstage(self):
        self._point_counter = None
        self._data_exporter.close()
        super().unstage()

    def describe_collect(self):

        ext_spec = "FileStore:"

        spec = {
            "external": ext_spec,
            "dtype": "array",
            "shape": [self._npts],
            "source": "",  # make this the PV of the array the det is writing
        }

        desc = OrderedDict()
        for chan in ("time", "enc1", "enc2", "enc3"):
            desc[chan] = spec
            desc[chan]["source"] = getattr(self._encoder.pc.data, chan).pvname

        # Handle the detectors we are going to get
        for d in self._dets:
            desc.update(d.describe())

        # Handle the ion chamber that the zebra is collecting
        if self._sis is not None:
            sis_mca_names = self._sis_mca_names()
            for n, name in enumerate(sis_mca_names):
                desc[name] = spec
                desc[name]["source"] = self._sis.mca_by_index[n + 1].spectrum.pvname

        return {"primary": desc}

    def kickoff(self, *, xstart, xstop, xnum, dwell):
        print(f"Kickoff: xstart={xstart} xtop={xstop} dwell={dwell}")

        self._data_exporter.set_fixed_positions()

        dets_by_name = {d.name: d for d in self.detectors}

        self._encoder.pc.arm.put(0)
        self._mode = "kicked off"
        self._npts = int(xnum)
        if xstart < xstop:
            direction = 1
        else:
            direction = -1
        pxsize = np.abs(xstop - xstart) / (xnum - 1)
        extent = np.abs(xstop - xstart) + pxsize
        # 2 ms delay between pulses
        decrement = (pxsize / dwell) * 0.0005
        decrement = max(decrement, 1e-5)

        print(f"gate_start={xstart - direction * (pxsize/2)}")
        print(f"extent={extent}")
        self._encoder.pc.gate_start.put(xstart - direction * (pxsize / 2))
        self._encoder.pc.gate_step.put(extent + 0.060)
        self._encoder.pc.gate_width.put(extent + 0.050)

        self._encoder.pc.pulse_start.put(0.0)
        self._encoder.pc.pulse_max.put(xnum)
        self._encoder.pc.pulse_step.put(pxsize)
        # self._encoder.pc.pulse_width.put(pxsize - decrement)
        self._encoder.pc.pulse_width.put(pxsize * 0.9)
        # If decrement is too small, then zebra will not send individual pulses
        # but integrate over the entire line
        # Hopefully taken care of with decrement check above

        # Arm the zebra
        self._encoder.pc.arm.put(1)

        # TODO Return a status object *first* and do the above asynchronously.
        return NullStatus()

    def _sis_mca_names(self):
        n_mcas = n_scaler_mca
        return [getattr(self._sis.channels, f"chan{_}").name for _ in range(1, n_mcas + 1)]

    def complete(self):
        """
        Call this when all needed data has been collected. This has no idea
        whether that is true, so it will obligingly stop immediately. It is
        up to the caller to ensure that the motion is actually complete.
        """

        amk_debug_flag = False

        print(f"Complete 1")
        # Our acquisition complete PV is: XF:05IDD-ES:1{Dev:Zebra1}:ARRAY_ACQ
        while self._encoder.pc.data_in_progress.get() == 1:
            ttime.sleep(0.01)
        print(f"Complete 2")
        # ttime.sleep(.1)
        self._mode = "complete"
        self._encoder.pc.block_state_reset.put(1)
        # see triggering errors of the xspress3 on suspension.  This is
        # to test the reset of the xspress3 after a line.

        print(f"Complete 3")

        for d in self._dets:
            d.stop(success=True)

        print(f"Complete 4")

        time_datum = self._datum_factory_z({"column": "time", "point_number": self._point_counter})
        enc1_datum = self._datum_factory_z({"column": "enc1", "point_number": self._point_counter})
        enc2_datum = self._datum_factory_z({"column": "enc2", "point_number": self._point_counter})
        enc3_datum = self._datum_factory_z({"column": "enc3", "point_number": self._point_counter})
        if self._sis:
            sis_mca_names = self._sis_mca_names()
            sis_datum = []
            for name in sis_mca_names:
                sis_datum.append(self._datum_factory_sis({"column": name, "point_number": self._point_counter}))

        self._document_cache.extend(
            ("datum", d)
            for d in (
                time_datum,
                enc1_datum,
                enc2_datum,
                enc3_datum,
            )
        )

        if self._sis:
            self._document_cache.extend(("datum", d) for d in sis_datum)

        # grab the asset documents from all of the child detectors
        for d in self._dets:
            self._document_cache.extend(d.collect_asset_docs())

        # Write the file.
        # @timer_wrapper
        def get_zebra_data():
            self._data_exporter.export(self._encoder, self.fast_axis.get())

        if amk_debug_flag:
            t_getzebradata = tic()
        get_zebra_data()
        if amk_debug_flag:
            toc(t_getzebradata, str='Get Zebra data')

        # @timer_wrapper
        def get_sis_data():
            if self._sis is None:
                return
            export_sis_data(
                self._sis, sis_mca_names, self.__write_filepath_sis, self._encoder
            )

        if amk_debug_flag:
            t_sisdata = tic()
        get_sis_data()
        if amk_debug_flag:
            toc(t_sisdata, str='Get SIS data')

        # Yield a (partial) Event document. The RunEngine will put this
        # into metadatastore, as it does all readings.
        self._last_bulk = {
            "time": ttime.time(),
            "seq_num": 1,
            "data": {
                "time": time_datum["datum_id"],
                "enc1": enc1_datum["datum_id"],
                "enc2": enc2_datum["datum_id"],
                "enc3": enc3_datum["datum_id"],
            },
            "timestamps": {
                "time": time_datum["datum_id"],  # not a typo#
                "enc1": time_datum["datum_id"],
                "enc2": time_datum["datum_id"],
                "enc3": time_datum["datum_id"],
            },
        }
        if self._sis:
            self._last_bulk["data"].update({k: v["datum_id"] for k, v in zip(sis_mca_names, sis_datum)})
            self._last_bulk["timestamps"].update({k: v["datum_id"] for k, v in zip(sis_mca_names, sis_datum)})
        for d in self._dets:
            reading = d.read()
            self._last_bulk["data"].update(
                {k: v["value"] for k, v in reading.items()}
                )
            self._last_bulk["timestamps"].update(
                {k: v["timestamp"] for k, v in reading.items()}
            )

        return NullStatus()

    def collect(self):
        # Create records in the FileStore database.
        # move this to stage because I thinkt hat describe_collect needs the
        # resource id
        # TODO use ophyd.areadectector.filestoer_mixins.resllource_factory here
        if self._last_bulk is None:
            raise Exception(
                "the order of complete and collect is brittle and out "
                "of sync. This device relies on in-order and 1:1 calls "
                "between complete and collect to correctly create and stash "
                "the asset registry documents"
            )
        yield self._last_bulk
        self._point_counter += 1
        self._last_bulk = None
        self._mode = "idle"

    def collect_asset_docs(self):
        yield from iter(list(self._document_cache))
        self._document_cache.clear()

    def stop(self):
        self._encoder.pc.block_state_reset.put(1)
        pass

    def pause(self):
        "Pausing in the middle of a kickoff nukes the partial dataset."
        self._encoder.pc.block_state_reset.put(1)
        if self._sis is not None:
            self._sis.stop_all.put(1)
        for d in self._dets:
            if hasattr(d, "settings"):
                d.settings.acquire.put(0)
            if hasattr(d, "cam"):
                d.cam.acquire.put(0)
        self._mode = "idle"
        self.unstage()

    def resume(self):
        self.unstage()
        self.stage()


class ExportNanoZebraData:
    def __init__(self):
        self._fp = None
        self._filepath = None

        self._sx_fixed = 0
        self._sy_fixed = 0
        self._sz_fixed = 0

    def open(self, filepath):
        self.close()
        self._filepath = filepath
        self._fp = h5py.File(filepath, "w", libver="latest")

        self._fp.swmr_mode = True

        def create_ds(ds_name):
            ds = self._fp.create_dataset(ds_name, data=np.array([], dtype="f"), maxshape=(None,), dtype="f")

        for ds_name in ("time", "enc1", "enc2", "enc3"):
            create_ds(ds_name)

        self._fp.flush()

    def close(self):
        if self._fp:
            self._fp.close()
            self._fp = None

    def __del__(self):
        self.close()

    def set_fixed_positions(self):
        """
        Read and save the positions from motor controller. It is assumed that only the fast
        axis is read from Zebra. Positions for the other axes are generated based on fixed
        positions loadeded by calling this function.
        """
        def get_position(obj):
            if not getattr(obj, "is_disabled", False):
                return obj.get().user_readback
            else:
                return 0

        self._sx_fixed = get_position(nano_stage.sx)
        self._sy_fixed = get_position(nano_stage.sy)
        self._sz_fixed = get_position(nano_stage.sz)

    def export(self, zebra, fastaxis):
        j = 0
        while zebra.pc.data_in_progress.get() == 1:
            print("Waiting for zebra...")
            ttime.sleep(0.1)
            j += 1
            if j > 10:
                print("THE ZEBRA IS BEHAVING BADLY CARRYING ON")
                break


        pxsize = zebra.pc.pulse_step.get()  # Pixel size
        encoder = zebra.pc.enc.get(as_string=True)  # Encoder ('Enc1', 'Enc2' or 'Enc3')

        print(f"Loading from Zebra: time")
        time_d = zebra.pc.data.time.get()

        if fastaxis == "NANOHOR":
            enc1_d = zebra.pc.data.enc1.get()
            enc2_d = [self._sy_fixed] * len(enc1_d)
            enc3_d = [self._sz_fixed] * len(enc1_d)
        elif fastaxis == "NANOVER":
            enc2_d = zebra.pc.data.enc2.get()
            enc1_d = [self._sx_fixed] * len(enc2_d)
            enc3_d = [self._sz_fixed] * len(enc2_d)
        elif fastaxis == "NANOZ":
            enc3_d = zebra.pc.data.enc3.get()
            enc1_d = [self._sx_fixed] * len(enc3_d)
            enc2_d = [self._sy_fixed] * len(enc3_d)
        else:
            raise Exception(f"Unknown value for 'fastaxis': {fastaxis!r}")

        # Correction for the encoder values so that they represent the centers of the bins
        if encoder.lower() == "enc1":
            enc1_d += pxsize / 2
        elif encoder.lower() == "enc2":
            enc2_d += pxsize / 2
        elif encoder.lower() == "enc3":
            enc3_d += pxsize / 2
        else:
            print(f"Unrecognized encoder name: {encoder}")

        print(f"===================================================")
        print(f"COLLECTED DATA:")
        print(f"time_d={time_d}")
        print(f"enc1_d={enc1_d}")
        print(f"enc2_d={enc2_d}")
        print(f"enc3_d={enc3_d}")
        print(f"===================================================")

        px = zebra.pc.pulse_step.get()
        if fastaxis == 'NANOHOR':
            # Add half pixelsize to correct encoder
            enc1_d = enc1_d + (px / 2)
        elif fastaxis == 'NANOVER':
            # Add half pixelsize to correct encoder
            enc2_d = enc2_d + (px / 2)
        elif fastaxis == 'NANOZ':
            # Add half pixelsize to correct encoder
            enc3_d = enc3_d + (px / 2)


        n_new_pts = len(time_d)

        def add_data(ds_name, data):
            ds = self._fp[ds_name]
            n_ds = ds.shape[0]
            ds.resize((n_ds + n_new_pts,))
            ds[n_ds:] = np.array(data)

        add_data("time", time_d)
        add_data("enc1", enc1_d)
        add_data("enc2", enc2_d)
        add_data("enc3", enc3_d)

        self._fp.flush()


def export_sis_data(ion, mca_names, filepath, zebra):
    print(f"EXPORTING SCALER DATA .................................")
    N = ion.nuse_all.get()

    n_mcas = len(mca_names)

    print("Step1")
    mca_data = []
    for n in range(1, n_mcas + 1):
        mca = ion.mca_by_index[n].spectrum.get(timeout=5.0)
        mca_data.append(mca)

    print("Step2")
    correct_length = int(zebra.pc.data.num_down.get())

    print(f"File name: {filepath!r}")

    with h5py.File(filepath, "w") as f:
        print("Step3")
        for n in range(len(mca_data)):
            mca = mca_data[n]
            mca = mca[1::2]
            if len(mca) != correct_length:
                print(f"Incorrect number of points ({len(mca)}) loaded from MCA{n + 1}: {correct_length} points are expected")
                if len(mca > correct_length):
                    mca = mca[:correct_length]
                else:
                    mca = np.append(mca, [1e10] * (correct_length - len(mca)))
            mca_data[n] = mca

        print("Step4")
        for n, name in enumerate(mca_names):
            dset = f.create_dataset(name, (correct_length,), dtype="f")
            dset[...] = np.asarray(mca_data[n])

    print(f"FINISHED EXPORTING SCALER DATA")


try:
    nanoZebra = SRXZebra("XF:03IDC-ES{Zeb:3}:", name="nanoZebra",
        read_attrs=["pc.data.enc1", "pc.data.enc2", "pc.data.enc3", "pc.data.time"],
    )
    nano_flying_zebra = SRXFlyer1Axis(
        list(xs for xs in [xs] if xs is not None), sclr1 if use_sclr1 else None, nanoZebra, name="nano_flying_zebra"
    )
    # print('huge success!')
except Exception as ex:
    print("Cannot connect to nanoZebra. Continuing without device.\n", ex)
    nano_flying_zebra = None


# Enable capture for 'enc1', 'enc2' and 'enc3'. At SRX capture is enabled via CSS.
# caput("XF:03IDC-ES{Zeb:3}:PC_BIT_CAP:B0", 1)
# caput("XF:03IDC-ES{Zeb:3}:PC_BIT_CAP:B1", 1)
# caput("XF:03IDC-ES{Zeb:3}:PC_BIT_CAP:B2", 1)
