print(f"Loading {__file__}...")

import time as ttime
import numpy as np

from datetime import datetime
import time as ttime
import matplotlib.pyplot as plt
from collections import ChainMap

from ophyd import Device
from ophyd.sim import NullStatus
from ophyd.device import Staged

from bluesky.preprocessors import (stage_decorator,
                                   run_decorator, subs_decorator,
                                   monitor_during_decorator, finalize_wrapper)
import bluesky.plan_stubs as bps
from bluesky.plan_stubs import (one_1d_step, kickoff, collect,
                                complete, abs_set, mv, checkpoint)
from bluesky.plans import (scan, )
from bluesky.callbacks import CallbackBase, LiveGrid

from bluesky import Msg

from hxntools.handlers import register

from bluesky.utils import short_uid

# def _pre_scan(dets, total_points, count_time):
#     # yield Msg('hxn_next_scan_id')
#     yield Msg('hxn_scan_setup', detectors=dets, total_points=total_points,
#               count_time=count_time)


def tic():
    return ttime.monotonic()


def toc(t0, str=''):
    dt = ttime.monotonic() - t0
    print('%s: dt = %f' % (str, dt))


# Define wrapper to time a function
def timer_wrapper(func):
    def wrapper(*args, **kwargs):
        t0 = ttime.monotonic()
        yield from func(*args, **kwargs)
        dt = ttime.monotonic() - t0
        print('%s: dt = %f' % (func.__name__, dt))
    return wrapper


# changed the flyer device to be aware of fast vs slow axis in a 2D scan
# should abstract this method to use fast and slow axes, rather than x and y
def scan_and_fly_base(detectors, xstart, xstop, xnum, ystart, ystop, ynum, dwell, *,
                      flying_zebra, xmotor, ymotor,
                      delta=None, shutter=False, align=False, plot=False,
                      md=None, snake=False, verbose=False):
    """Read IO from SIS3820.
    Zebra buffers x(t) points as a flyer.
    Xpress3 is our detector.
    The aerotech has the x and y positioners.
    delta should be chosen so that it takes about 0.5 sec to reach the gate??
    ymotor  slow axis
    xmotor  fast axis

    Parameters
    ----------
    Detectors : List[Device]
       These detectors must be known to the zebra

    xstart, xstop : float
    xnum : int
    ystart, ystop : float
    ynum : int
    dwell : float
       Dwell time in seconds

    flying_zebra : SRXFlyer1Axis

    xmotor, ymotor : EpicsMotor, kwarg only
        These should be known to the zebra
        # TODO sort out how to check this

    delta : float, optional, kwarg only
       offset on the ystage start position.  If not given, derive from
       dwell + pixel size
    align : bool, optional, kwarg only
       If True, try to align the beamline
    shutter : bool, optional, kwarg only
       If True, try to open the shutter
    """

    # t_setup = tic()

    # Check for negative number of points
    if xnum < 1 or ynum < 1:
        print('Error: Number of points is negative.')
        return

    # Set metadata
    if md is None:
        md = {}
    # md = get_stock_md(md)

    # Assign detectors to flying_zebra, this may fail
    flying_zebra.detectors = detectors
    # Setup detectors, combine the zebra, sclr, and the just set detector list
    detectors = (flying_zebra.encoder, flying_zebra.sclr) + flying_zebra.detectors
    detectors = [_ for _ in detectors if _ is not None]

    names_stage_once = ("merlin2", "eiger2")
    detectors_stage_once = [_ for _ in flying_zebra.detectors if _.name in names_stage_once]
    detectors_stage_every_row = [_ for _ in flying_zebra.detectors if _.name not in names_stage_once]

    # print(f"detectors_stage_once={detectors_stage_once}")
    # print(f"detectors_stage_every_row={detectors_stage_every_row}")

    dets_by_name = {d.name : d
                    for d in detectors}

    flying_zebra.frame_per_point = xnum

    # Set up the merlin
    for det_name in ("merlin2", "eiger2"):
        if det_name in dets_by_name:
            dpc = dets_by_name[det_name]

            if det_name == "merlin2":
                # # Settings for 'Trigger start rising' trigger mode of Merlin
                # acquire_period = 0.75 * dwell
                # acquire_time = 0.50 * dwell
                # acquire_time = min(acquire_time, acquire_period - 0.0016392)
                # if acquire_time <= 0:
                #     raise ValueError("Acquistion period is too small. Increase dwell time")

                # Settings for 'Trigger enable' mode
                acquire_time = 0.0001
                acquire_period = acquire_time
                # acquire_period = acquire_time + 0.0016392

            elif det_name == "eiger2":
                acquire_time = 0.9 * dwell
                acquire_period = acquire_time
            else:
                raise ValueError(f"Unsupported detector: {det_name!r}")

            if det_name == "eiger2":
                # Acquire one frame with the computed acquire time to avoid 'Invalid frame'
                #   errors in HDF5 plugin. This may be needed because Eiger is using
                #  'autosummation' for longer exposure times, which may result in different
                #  data representation for short and long exposures (just an assumption).
                dpc.hdf5.warmup(acquire_time=acquire_time)

            dpc.cam.stage_sigs['acquire_time'] = acquire_time
            dpc.cam.stage_sigs['acquire_period'] = acquire_period
            dpc.cam.stage_sigs['num_images'] = 1
            dpc.stage_sigs['total_points'] = xnum
            dpc.hdf5.stage_sigs['num_capture'] = xnum * ynum
            dpc.hdf5.frame_per_point = xnum
            del dpc

    # If delta is None, set delta based on time for acceleration
    if delta is None:
        # MIN_DELTA = 0.5  # old default value
        # v = ((xstop - xstart) / (xnum - 1)) / dwell  # compute "stage speed"
        # t_acc = xmotor.acceleration.get()  # acceleration time
        # delta = 0.5 * t_acc * v  # distance the stage will travel in t_acc
        # delta = np.amax((delta, MIN_DELTA))
        delta = 0.500


    # Move to start scanning location
    # Calculate move to scan start
    pxsize = (xstop - xstart) / (xnum - 1)
    # row_start = xstart - delta - (pxsize / 2)
    # row_stop = xstop + delta + (pxsize / 2)
    # row_start = xstart - delta - max(pxsize, 1)
    #row_stop = xstop + delta + max(pxsize, 1)
    row_start = xstart - delta - pxsize
    row_stop = xstop + delta + pxsize

    # row_start, row_stop = xstart - 0.3, xstop + 0.3

    # Run a peakup before the map?
    if (align):
        yield from peakup_fine(shutter=shutter)

    # This is added for consistency with existing HXN plans. Requires custom
    #   setup of RE:   hxntools.scans.setup(RE=RE)
    if not FIP_TESTING:
        yield Msg('hxn_next_scan_id')

    if "scan" not in md:
        md["scan"] = {}
    # Scan metadata
    md['scan']['type'] = 'XRF_FLY'
    md['scan']['scan_input'] = [xstart, xstop, xnum, ystart, ystop, ynum, dwell]
    md['scan']['sample_name'] = ''
    md['scan']['detectors'] = [d.name for d in detectors]
    md['scan']['dwell'] = dwell
    md['scan']['fast_axis'] = {'motor_name' : xmotor.name,
                               'units' : xmotor.motor_egu.get()}
    md['scan']['slow_axis'] = {'motor_name' : ymotor.name,
                               'units' : ymotor.motor_egu.get()}
    # md['scan']['theta'] = {'val' : pt_tomo.th.user_readback.get(),
    #                        'units' : pt_tomo.th.motor_egu.get()}
    md['scan']['delta'] = {'val' : delta,
                           'units' : xmotor.motor_egu.get()}
    md['scan']['snake'] = snake
    md['scan']['shape'] = (xnum, ynum)

    time_start_scan = time.time()

    # Synchronize encoders
    # flying_zebra._encoder.pc.enc_pos1_sync.put(1)
    # flying_zebra._encoder.pc.enc_pos2_sync.put(1)
    # flying_zebra._encoder.pc.enc_pos3_sync.put(1)
    yield from bps.mv(flying_zebra._encoder.pc.enc_pos1_sync, 1)
    yield from bps.mv(flying_zebra._encoder.pc.enc_pos2_sync, 1)
    yield from bps.mv(flying_zebra._encoder.pc.enc_pos3_sync, 1)
    # yield from bps.sleep(1)

    yield from reset_scanner_velocity()

    # Select PV for monitoring
    d_names = [_.name for _ in detectors_stage_once]
    ts_monitor_dec = ts_monitor_during_decorator
    if "merlin2" in d_names:
        roi_pv = merlin2.stats1.ts_total
        roi_pv_force_update = merlin2.stats1.ts.ts_read_proc
    elif "eiger2" in d_names:
        roi_pv = eiger2.stats1.ts_total
        roi_pv_force_update = eiger2.stats1.ts.ts_read_proc
    else:
        roi_pv = None
        roi_pv_force_update = None
        ts_monitor_dec = ts_monitor_during_decorator_disabled

    # print(f"Ready to start the scan !!!")  ##

    # @stage_decorator(flying_zebra.detectors)
    @stage_decorator(detectors_stage_every_row)
    def fly_each_step(motor, step, row_start, row_stop):
        def move_to_start_fly():
            "See http://nsls-ii.github.io/bluesky/plans.html#the-per-step-hook"

            # print(f"Start moving to beginning of the row")
            row_mv_to_start = short_uid('row')
            yield from bps.checkpoint()
            yield from reset_scanner_velocity()
            yield from bps.abs_set(xmotor, row_start, group=row_mv_to_start)
            yield from bps.abs_set(motor, step, group=row_mv_to_start)
            yield from bps.wait(group=row_mv_to_start)
            # yield from bps.trigger_and_read([temp_nanoKB, motor])  ## Uncomment this
            # print(f"Finished moving to the beginning of the row")
            # print(f"Fast axis: {xmotor.read()} Slow axis: {motor.read()}")

        if verbose:
            t_startfly = tic()
            toc(t_startfly, "TIMER (STEP) - STARTING TIMER")

        yield from move_to_start_fly()

        if verbose:
            toc(t_startfly, "TIMER (STEP) - MOTOR IS MOVED TO STARTING POINT")

        x_set = row_start
        x_dial = xmotor.user_readback.get()

        # Get retry deadband value and check against that
        i = 0
        DEADBAND = 0.050  # retry deadband of nPoint scanner
        while (np.abs(x_set - x_dial) > DEADBAND):
            if (i == 0):
                print('Waiting for motor to reach starting position...',
                      end='', flush=True)
            i = i + 1
            yield from mv(xmotor, row_start)
            yield from bps.sleep(0.1)
            x_dial = xmotor.user_readback.get()
        if (i != 0):
            print('done')

        if verbose:
            toc(t_startfly, str='TIMER (STEP) - MOTOR POSITION IS CHECKED')

        # Set the scan speed
        v = ((xstop - xstart) / (xnum - 1)) / dwell  # compute "stage speed"
        if verbose:
            print(f"FORWARD SPEED FOR FAST AXIS: {v} (xnum={xnum} dwell={dwell})")
        yield from mv(xmotor.velocity, v)
        if verbose:
            toc(t_startfly, str='TIMER (STEP) - FORWARD VELOCITY IS SET')

        # set up all of the detectors
        # TODO we should be able to move this out of the per-line call?!
        # if ('xs' in dets_by_name):
        #     xs = dets_by_name['xs']
        #     yield from abs_set(xs.hdf5.num_capture, xnum, group='set')
        #     yield from abs_set(xs.settings.num_images, xnum, group='set')
        #     yield from bps.wait(group='set')
        #     # yield from mv(xs.hdf5.num_capture, xnum,
        #     #               xs.settings.num_images, xnum)
        #     # xs.hdf5.num_capture.put(xnum)
        #     # xs.settings.num_images.put(xnum)

        # if ('xs2' in dets_by_name):
        #     xs2 = dets_by_name['xs2']
        #     # yield from abs_set(xs2.hdf5.num_capture, xnum, wait=True)
        #     # yield from abs_set(xs2.settings.num_images, xnum, wait=True)
        #     yield from mv(xs2.hdf5.num_capture, xnum,
        #                   xs2.settings.num_images, xnum)

        # # Merlin code from the original SRX plan
        if "merlin2" in dets_by_name:
            # print(f"Configuring 'merlin2' ...")
            dpc = dets_by_name["merlin2"]
            yield from abs_set(dpc.cam.num_images, xnum, wait=True)
        if "eiger2" in dets_by_name:
            # print(f"Configuring 'eiger2' ...")
            dpc = dets_by_name["eiger2"]
            yield from abs_set(dpc.cam.num_triggers, xnum, wait=True)
            yield from abs_set(dpc.cam.num_images, 1, wait=True)

        ion = flying_zebra.sclr
        if ion:
            yield from abs_set(ion.nuse_all, xnum, wait=True)
            #yield from abs_set(ion.nuse_all, 2*xnum, wait=True)

        if verbose:
            toc(t_startfly, str='TIMER (STEP) - DETECTORS ARE CONFIGURED')

        def zebra_kickoff():
            # start_zebra, stop_zebra = xstart * 1000000, xstop * 1000000
            start_zebra, stop_zebra = xstart, xstop
            if row_start < row_stop:
                yield from kickoff(flying_zebra,
                                   xstart=start_zebra, xstop=stop_zebra, xnum=xnum, dwell=dwell,
                                   wait=True)
            else:
                yield from kickoff(flying_zebra,
                                   xstart=stop_zebra, xstop=start_zebra, xnum=xnum, dwell=dwell,
                                   wait=True)

        yield from zebra_kickoff()

        if verbose:
            toc(t_startfly, str='TIMER (STEP) - ZEBRA STARTED')

        # arm SIS3820, note that there is a 1 sec delay in setting X
        # into motion so the first point *in each row* won't
        # normalize...
        if ion:
            yield from abs_set(ion.erase_start, 1)
            if verbose:
                toc(t_startfly, str='TIMER (STEP) - SCALAR STARTED')


        # trigger all of the detectors
        row_scan = short_uid('row')
        if verbose:
            print('Data collection:')
        for d in flying_zebra.detectors:
            if verbose:
                print(f'  triggering {d.name}')
            st = yield from bps.trigger(d, group=row_scan)
            st.add_callback(lambda x: toc(t_startfly, str=f"  DETECTOR  {datetime.strftime(datetime.now(), '%Y-%m-%d %H:%M:%S.%f')}"))

            # if (d.name == 'merlin2'):
            if (d.name == 'eiger2'):
                t_wait_detector = tic()
                # while d.cam.num_images_counter.get() != 0:
                # while (d.cam.detector_state.get(as_string=True) != "Acquire"):
                # while not d.cam.acquire.get():
                    # print("Waiting for detector state")
                    # yield from bps.sleep(0.001)
                yield from bps.sleep(0.2)
                if verbose:
                    toc(t_wait_detector, str=f'  waiting for detector {d.name!r}')

        if roi_pv_force_update:
            yield from bps.mv(roi_pv_force_update, 1)

        if verbose:
            toc(t_startfly, str='TIMER (STEP) - DETECTORS TRIGGERED')

        # start the 'fly'
        def print_watch(*args, **kwargs):
            with open('~/bluesky_output.txt', 'a') as f:
                f.write(datetime.strftime(datetime.now(), '%Y-%m-%d %H:%M:%S.%f\n'))
                # print(args)
                f.write(json.dumps(kwargs))
                f.write('\n')
        st = yield from abs_set(xmotor, row_stop, group=row_scan)
        if verbose:
            st.add_callback(lambda x: toc(t_startfly, str=f"  MOTOR  {datetime.strftime(datetime.now(), '%Y-%m-%d %H:%M:%S.%f')}"))

        # st = yield from abs_set(xmotor, row_stop)
        # st.watch(print_watch)

        if verbose:
            toc(t_startfly, str='TIMER (STEP) - MOTOR STARTED')

        if verbose and False:
            ttime.sleep(1)
            while (xmotor.motor_is_moving.get()):
                ttime.sleep(0.001)
            toc(t_datacollect, str='  move end')
            while (xs.settings.detector_state.get()):
                ttime.sleep(0.001)
            toc(t_datacollect, str='  xs done')
            while (sclr1.acquiring.get()):
                ttime.sleep(0.001)
            toc(t_datacollect, str='  sclr1 done')

        # print("Waiting for motor to stop")
        # st.wait()
        # if verbose:
        #     toc(t_startfly, str='Total time: Motor stopped')

        # wait for the motor and detectors to all agree they are done
        if verbose:
            print("Waiting for the row scan to complete ...")
        yield from bps.wait(group=row_scan)
        if verbose:
            print("Row scan is completed")

        # yield from bps.sleep(1)

        if verbose:
            toc(t_startfly, str='TIMER (STEP) - MOTOR STOPPED. ACQUISITION_COMPLETED.')

        # we still know about ion from above
        if ion:
            yield from abs_set(ion.stop_all, 1)  # stop acquiring scaler

        # print(f"Resetting scanner velocity")
        # set speed back
        yield from reset_scanner_velocity()
        # print(f"Completed resetting scanner velocity")

        # @timer_wrapper
        def zebra_complete():
            yield from complete(flying_zebra)  # tell the Zebra we are done
        if verbose:
            t_zebcomplete = tic()
        yield from zebra_complete()
        if verbose:
            toc(t_zebcomplete, str='Zebra complete')

        if verbose:
            toc(t_startfly, str='TIMER (STEP) - ZEBRA ACQUISITION COMPLETED.')

        # @timer_wrapper
        def zebra_collect():
            yield from collect(flying_zebra)  # extract data from Zebra
        if verbose:
            t_zebcollect = tic()
        yield from zebra_collect()
        if verbose:
            toc(t_zebcollect, str='Zebra collect')

        if verbose:
            toc(t_startfly, str='TIMER (STEP) - ZEBRA COLLECTION COMPLETED.')

        # Force update of the respective PV so that all collected monitoring data for the row
        #   is loaded before the plugin is reset. Otherwise data in monitoring stream will not
        #   contain last points of rows.
        if roi_pv_force_update:
            yield from bps.mv(roi_pv_force_update, 1)

        if verbose:
            toc(t_startfly, str='TIMER (STEP) - STEP COMPLETED.')

        if verbose:
            print(f"Step is completed")

    def at_scan(name, doc):
        # scanrecord.current_scan.put(doc['uid'][:6])
        # scanrecord.current_scan_id.put(str(doc['scan_id']))
        # scanrecord.current_type.put(md['scan']['type'])
        # scanrecord.scanning.put(True)
        # scanrecord.time_remaining.put((dwell*xnum + 3.8)/3600)
        pass

    def finalize_scan(name, doc):
        # logscan_detailed('XRF_FLY')
        # scanrecord.scanning.put(False)
        # scanrecord.time_remaining.put(0)
        pass

    # TODO remove this eventually?
    # xs = dets_by_name['xs']
    # xs = dets_by_name['xs2']
    # Not sure if this is always true
    # xs = dets_by_name[flying_zebra.detectors[0].name]  ## Uncomment this

    # yield from mv(xs.erase, 0)  ## Uncomment this

    # Setup LivePlot
    if plot:
        if (ynum == 1):
            livepopup = [
                SRX1DTSFlyerPlot(
                    roi_pv.name,
                    xstart=xstart,
                    xstep=(xstop-xstart)/(xnum-1),
                    xlabel=xmotor.name
                )
            ]
        else:
            livepopup = [
                TSLiveGrid(
                    (ynum, xnum),
                    roi_pv.name,
                    extent=(xstart, xstop, ystart, ystop),
                    x_positive='right',
                    y_positive='down'
                )
            ]
    else:
        livepopup = []

    for d in detectors_stage_once:
        if d:
            yield from bps.mov(d.fly_next, True)

    @subs_decorator(livepopup)
    @subs_decorator({'start': at_scan})
    @subs_decorator({'stop': finalize_scan})
    @ts_monitor_dec([roi_pv])
    # @monitor_during_decorator([xs.channel1.rois.roi01.value])  ## Uncomment this
    # @monitor_during_decorator([xs.channel1.rois.roi01.value, xs.array_counter])
    @stage_decorator([flying_zebra] + detectors_stage_once)  # Below, 'scan' stage ymotor.
    @run_decorator(md=md)
    def plan():
        if verbose:
            print("Starting the plan ...")
            print(f"flying_zebra.detectors={flying_zebra.detectors}")

        # print(f"Plan start (enc1): {flying_zebra._encoder.pc.data.cap_enc1_bool.get()}")
        # print(f"Plan start (enc2): {flying_zebra._encoder.pc.data.cap_enc2_bool.get()}")

        # TODO move this to stage sigs
        for d in flying_zebra.detectors:
            if d.name != "merlin2":
                yield from bps.mov(d.total_points, xnum)

        ystep = 0
        for n_row, step in enumerate(np.linspace(ystart, ystop, ynum)):

            print(f"Scanning row #{n_row + 1} (of {ynum}): Y={step:.3f}")

            if verbose:
                print(f"Starting the next row")
            for d in detectors_stage_every_row:
                # if d and (d.name != "merlin2"):
                if d:
                    yield from bps.mov(d.fly_next, True)

            if (snake is False):
                direction = 0
                start = row_start
                stop = row_stop
            else:
                if ystep % 2 == 0:
                    direction = 0
                    start = row_start
                    stop = row_stop
                else:
                    direction = 1
                    start = row_stop
                    stop = row_start

            if verbose:
                print(f'Direction = {direction}')
                print(f'Start = {start}')
                print(f'Stop  = {stop}')

            yield from bps.mv(flying_zebra._encoder.pc.dir, direction)
            yield from fly_each_step(ymotor, step, start, stop)

            ystep = ystep + 1

    # Setup the final scan plan
    if shutter:
        final_plan = finalize_wrapper(plan(), check_shutters(shutter, 'Close'))
    else:
        final_plan = plan()

    # Open the shutter
    if verbose:
        t_open = tic()
    # yield from check_shutters(shutter, 'Open')  ## Uncomment this
    if verbose:
        toc(t_open, str='Open shutter (dt)')

    # print(f"Before plan start (enc1): {flying_zebra._encoder.pc.data.cap_enc1_bool.get()}")
    # print(f"Before plan start (enc2): {flying_zebra._encoder.pc.data.cap_enc2_bool.get()}")

    # Run the scan
    uid = yield from final_plan

    print(f"SCAN TOTAL TIME: {time.time() - time_start_scan}")

    return uid

def nano_scan_and_fly(*args, extra_dets=None, **kwargs):
    # RE(nano_scan_and_fly(-10, 10, 21, -1, 1, 5, 0.1, verbose=True))
    kwargs.setdefault('xmotor', pt_tomo.ssx)
    kwargs.setdefault('ymotor', pt_tomo.ssy)
    kwargs.setdefault('flying_zebra', nano_flying_zebra)
    # print(kwargs['xmotor'].name)
    # print(kwargs['ymotor'].name)
    # print(kwargs['flying_zebra'].name)
    yield from abs_set(nano_flying_zebra.fast_axis, 'NANOHOR')
    yield from abs_set(nano_flying_zebra.slow_axis, 'NANOVER')

    _xs = kwargs.pop('xs', xs)
    if extra_dets is None:
        extra_dets = []
    dets = [] if  _xs is None else [_xs]
    dets = dets + extra_dets
    # print(f"dets={dets}")
    print('Scan starting. Centering the scanner...')
    # yield from mv(pt_tomo.ssx, 0, pt_tomo.ssy, 0, pt_tomo.ssz, 0)
    yield from bps.sleep(2)
    yield from scan_and_fly_base(dets, *args, **kwargs)
    print('Scan finished. Centering the scanner...')
    # yield from bps.sleep(1)
    yield from set_scanner_velocity(30)
    # yield from bps.sleep(1)
    # print("Centering X-axis ...")
    # yield from mv(pt_tomo.ssx, 0)
    # print("Centering Y-axis ...")
    # yield from mv(pt_tomo.ssy, 0)
    # print("Centering Z-axis ...")
    # yield from mv(pt_tomo.ssz, 0)
    # yield from bps.sleep(2)


def nano_y_scan_and_fly(*args, extra_dets=None, **kwargs):
    kwargs.setdefault('xmotor', pt_tomo.ssy)
    kwargs.setdefault('ymotor', pt_tomo.ssx)
    kwargs.setdefault('flying_zebra', nano_flying_zebra)
    # print(kwargs['xmotor'].name)
    # print(kwargs['ymotor'].name)
    # print(kwargs['flying_zebra'].name)
    yield from abs_set(nano_flying_zebra.fast_axis, 'NANOVER')
    yield from abs_set(nano_flying_zebra.slow_axis, 'NANOHOR')

    _xs = kwargs.pop('xs', xs)
    if extra_dets is None:
        extra_dets = []
    #dets = [_xs] + extra_dets
    dets = [] if  _xs is None else [_xs]
    dets = dets + extra_dets
    # print(f"dets={dets}")
    print('Scan starting. Centering the scanner...')
    yield from bps.sleep(2)
    yield from scan_and_fly_base(dets, *args, **kwargs)
    print('Scan finished. Centering the scanner...')
    #yield from mv(pt_tomo.ssx, 0, pt_tomo.ssy, 0, pt_tomo.ssz, 0)
    #yield from mv(pt_tomo.ssx, 0, pt_tomo.ssy, 0)
    #yield from bps.sleep(2)

    # yield from mv(pt_tomo.ssx, 0, pt_tomo.ssy, 0, pt_tomo.ssz, 0)

    set_scanner_velocity(30)


def nano_z_scan_and_fly(*args, extra_dets=None, **kwargs):
    kwargs.setdefault('xmotor', pt_tomo.ssz)
    kwargs.setdefault('ymotor', pt_tomo.ssx)
    kwargs.setdefault('flying_zebra', nano_flying_zebra)
    # print(kwargs['xmotor'].name)
    # print(kwargs['ymotor'].name)
    # print(kwargs['flying_zebra'].name)
    yield from abs_set(nano_flying_zebra.fast_axis, 'NANOZ')
    yield from abs_set(nano_flying_zebra.slow_axis, 'NANOHOR')

    _xs = kwargs.pop('xs', xs)
    if extra_dets is None:
        extra_dets = []
    dets = [_xs] + extra_dets
    dets = [] if  _xs is None else [_xs]
    # print(f"dets={dets}")
    print('Scan starting. Centering the scanner...')
    yield from bps.sleep(2)
    yield from scan_and_fly_base(dets, *args, **kwargs)
    print('Scan finished. Centering the scanner...')
    yield from mv(pt_tomo.ssx, 0, pt_tomo.ssy, 0, pt_tomo.ssz, 0)
    # yield from mv(pt_tomo.ssx, 0, pt_tomo.ssy, 0, pt_tomo.ssz, 0)
