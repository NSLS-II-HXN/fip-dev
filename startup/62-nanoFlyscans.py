print(f"Loading {__file__}...")

import time as ttime
import numpy as np

import time as ttime
import matplotlib.pyplot as plt
from collections import ChainMap

from ophyd import Device
from ophyd.sim import NullStatus
from ophyd.areadetector.filestore_mixins import resource_factory

from bluesky.preprocessors import (stage_decorator,
                                   run_decorator, subs_decorator,
                                   monitor_during_decorator, finalize_wrapper)
import bluesky.plan_stubs as bps
from bluesky.plan_stubs import (one_1d_step, kickoff, collect,
                                complete, abs_set, mv, checkpoint)
from bluesky.plans import (scan, )
from bluesky.callbacks import CallbackBase, LiveGrid

from hxntools.handlers import register

from bluesky.utils import short_uid

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

    dets_by_name = {d.name : d
                    for d in detectors}

    # # Set up the merlin
    # if 'merlin' in dets_by_name:
    #     dpc = dets_by_name['merlin']
    #     # TODO use stage sigs
    #     # Set trigger mode
    #     # dpc.cam.trigger_mode.put(2)
    #     # Make sure we respect whatever the exposure time is set to
    #     if (dwell < 0.0066392):
    #         print('The Merlin should not operate faster than 7 ms.')
    #         print('Changing the scan dwell time to 7 ms.')
    #         dwell = 0.007
    #     # According to Ken's comments in hxntools, this is a de-bounce time
    #     # when in external trigger mode
    #     dpc.cam.stage_sigs['acquire_time'] = 0.50 * dwell - 0.0016392
    #     dpc.cam.stage_sigs['acquire_period'] = 0.75 * dwell
    #     dpc.cam.stage_sigs['num_images'] = 1
    #     dpc.stage_sigs['total_points'] = xnum
    #     dpc.hdf5.stage_sigs['num_capture'] = xnum
    #     del dpc

    # # Setup dexela
    # if ('dexela' in dets_by_name):
    #     xrd = dets_by_name['dexela']
    #     xrd.cam.stage_sigs['acquire_time'] = dwell
    #     xrd.cam.stage_sigs['acquire_period'] = dwell
    #     del xrd

    # If delta is None, set delta based on time for acceleration
    if delta is None:
        MIN_DELTA = 0.100  # old default value
        v = ((xstop - xstart) / (xnum - 1)) / dwell  # compute "stage speed"
        t_acc = xmotor.acceleration.get()  # acceleration time
        delta = 0.5 * t_acc * v  # distance the stage will travel in t_acc
        delta = np.amax((delta, MIN_DELTA))
        # delta = 0.500 #was 2.5 when npoint scanner drifted

    # Move to start scanning location
    # Calculate move to scan start
    pxsize = (xstop - xstart) / (xnum - 1)
    row_start = xstart - delta - (pxsize / 2)
    row_stop = xstop + delta + (pxsize / 2)
    # yield from mv(xmotor, row_start,
    #               ymotor, ystart)

    # Run a peakup before the map?
    if (align):
        yield from peakup_fine(shutter=shutter)

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
    # md['scan']['theta'] = {'val' : nano_stage.th.user_readback.get(),
    #                        'units' : nano_stage.th.motor_egu.get()}
    md['scan']['delta'] = {'val' : delta,
                           'units' : xmotor.motor_egu.get()}
    md['scan']['snake'] = snake
    md['scan']['shape'] = (xnum, ynum)


    @stage_decorator(flying_zebra.detectors)
    def fly_each_step(motor, step, row_start, row_stop):
        def move_to_start_fly():
            "See http://nsls-ii.github.io/bluesky/plans.html#the-per-step-hook"
            # row_str = short_uid('row')
            # yield from abs_set(xmotor, row_start, group=row_str)
            # yield from one_1d_step([temp_nanoKB], motor, step)
            # yield from bps.wait(group=row_str)

            print(f"Start moving to beginning of the row")
            row_str = short_uid('row')
            yield from bps.checkpoint()
            yield from bps.abs_set(xmotor, row_start, group=row_str)
            yield from bps.abs_set(motor, step, group=row_str)
            yield from bps.wait(group=row_str)
            # yield from bps.trigger_and_read([temp_nanoKB, motor])  ## Uncomment this
            print(f"Finished moving to the beginning of the row")
            print(f"Fast axis: {xmotor.read()} Slow axis: {motor.read()}")

        if verbose:
            t_mvstartfly = tic()
        yield from move_to_start_fly()

        # TODO  Why are we re-trying the move?  This should be fixed at
        # a lower level
        # yield from bps.sleep(1.0)  # wait for the "x motor" to move
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
            toc(t_mvstartfly, str='Move to start fly each')

        # Set the scan speed
        # Is abs_set(wait=True) or mv() faster?
        v = ((xstop - xstart) / (xnum - 1)) / dwell  # compute "stage speed"
        # yield from abs_set(xmotor.velocity, v, wait=True)  # set the "stage speed"
        # if (v > xmotor.velocity.high_limit):
        #     raise ValueError(f'Desired motor velocity too high\nMax velocity: {xmotor.velocity.high_limit}')
        # elif (v < xmotor.velocity.low_limit):
        #     raise ValueError(f'Desired motor velocity too low\nMin velocity: {xmotor.velocity.low_limit}')
        # else:
        #     yield from mv(xmotor.velocity, v)
        yield from mv(xmotor.velocity, v)

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

        # if ('merlin' in dets_by_name):
        #     merlin = dets_by_name['merlin']
        #     yield from abs_set(merlin.hdf5.num_capture, xnum, wait=True)
        #     yield from abs_set(merlin.cam.num_images, xnum, wait=True)

        # if ('dexela' in dets_by_name):
        #     dexela = dets_by_name['dexela']
        #     yield from abs_set(dexela.hdf5.num_capture, xnum, wait=True)
        #     # yield from abs_set(dexela.hdf5.num_frames_chunks, xnum, wait=True)
        #     yield from abs_set(dexela.cam.num_images, xnum, wait=True)

        ion = flying_zebra.sclr
        if ion:
            yield from abs_set(ion.nuse_all, 2*xnum)

        # arm the Zebra (start caching x positions)
        # @timer_wrapper
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
        if verbose:
            t_zebkickoff = tic()
        yield from zebra_kickoff()
        if verbose:
            toc(t_zebkickoff, str='Zebra kickoff')

        if verbose:
            t_datacollect = tic()
        # arm SIS3820, note that there is a 1 sec delay in setting X
        # into motion so the first point *in each row* won't
        # normalize...
        if ion:
            yield from abs_set(ion.erase_start, 1)
        if verbose:
            toc(t_datacollect, str='  reset scaler')

        # trigger all of the detectors
        row_str = short_uid('row')
        if verbose:
            print('Data collection:')
        for d in flying_zebra.detectors:
            if verbose:
                print(f'  triggering {d.name}')
            st = yield from bps.trigger(d, group=row_str)
            st.add_callback(lambda x: toc(t_datacollect, str=f"  status object  {datetime.datetime.strftime(datetime.datetime.now(), '%Y-%m-%d %H:%M:%S.%f')}"))
            if (d.name == 'dexela'):
                yield from bps.sleep(1)
        if verbose:
            toc(t_datacollect, str='  trigger detectors')

        # yield from bps.sleep(1.5)
        if verbose:
            toc(t_datacollect, str='  sleep')

        # start the 'fly'
        def print_watch(*args, **kwargs):
            with open('~/bluesky_output.txt', 'a') as f:
                f.write(datetime.datetime.strftime(datetime.datetime.now(), '%Y-%m-%d %H:%M:%S.%f\n'))
                # print(args)
                f.write(json.dumps(kwargs))
                f.write('\n')
        st = yield from abs_set(xmotor, row_stop, group=row_str)
        # st.watch(print_watch)

        if verbose:
            toc(t_datacollect, str='  move start')

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
        # wait for the motor and detectors to all agree they are done
        yield from bps.wait(group=row_str)
        st.wait()

        if verbose:
            toc(t_datacollect, str='Total time')

        # we still know about ion from above
        if ion:
            yield from abs_set(ion.stop_all, 1)  # stop acquiring scaler

        print(f"Resetting scanner velocity")
        # set speed back
        reset_scanner_velocity()
        print(f"Completed resetting scanner velocity")

        # @timer_wrapper
        def zebra_complete():
            yield from complete(flying_zebra)  # tell the Zebra we are done
        if verbose:
            t_zebcomplete = tic()
        yield from zebra_complete()
        if verbose:
            toc(t_zebcomplete, str='Zebra complete')
        print(f"'zebra_complete' finished")


        # @timer_wrapper
        def zebra_collect():
            yield from collect(flying_zebra)  # extract data from Zebra
        if verbose:
            t_zebcollect = tic()
        yield from zebra_collect()
        if verbose:
            toc(t_zebcollect, str='Zebra collect')
        print(f"'zebra_collect' finished")

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
            livepopup = [SRX1DFlyerPlot(xs.channel1.rois.roi01.value.name,
                                        xstart=xstart,
                                        xstep=(xstop-xstart)/(xnum-1),
                                        xlabel=xmotor.name)]
        else:
            livepopup = [LiveGrid((ynum, xnum+1),
                                  xs.channel1.rois.roi01.value.name,
                                  extent=(xstart, xstop, ystart, ystop),
                                  x_positive='right', y_positive='down')]
    else:
        livepopup = []
    @subs_decorator(livepopup)
    @subs_decorator({'start': at_scan})
    @subs_decorator({'stop': finalize_scan})
    # monitor values from xs
    # @monitor_during_decorator([xs.channel1.rois.roi01.value])  ## Uncomment this
    # @monitor_during_decorator([xs.channel1.rois.roi01.value, xs.array_counter])
    @stage_decorator([flying_zebra])  # Below, 'scan' stage ymotor.
    @run_decorator(md=md)
    def plan():
        # TODO move this to stage sigs
        for d in flying_zebra.detectors:
            yield from bps.mov(d.total_points, xnum)

        # TODO move this to stage sigs
        # yield from bps.mov(xs.external_trig, True)  ## Uncomment this

        ystep = 0
        for step in np.linspace(ystart, ystop, ynum):
            # yield from abs_set(scanrecord.time_remaining,  ## Uncomment this
            #                    (ynum - ystep) * ( dwell * xnum + 3.8 ) / 3600.)  ## Uncomment this
            # 'arm' the all of the detectors for outputting fly data
            print(f"Starting the next row")
            for d in flying_zebra.detectors:
                if d:
                    yield from bps.mov(d.fly_next, True)
            # print('h5 armed\t',time.time())
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
            # Do work
            if verbose:
                print(f'Direction = {direction}')
                print(f'Start = {start}')
                print(f'Stop  = {stop}')
            flying_zebra._encoder.pc.dir.set(direction)
            yield from fly_each_step(ymotor, step, start, stop)
            # print('return from step\t',time.time())
            ystep = ystep + 1

        # TODO this should be taken care of by stage sigs
        ion = flying_zebra.sclr
        if ion:
            yield from bps.mov(xs.external_trig, False,
                               ion.count_mode, 1)
        yield from mv(nano_stage.sx, 0, nano_stage.sy, 0, nano_stage.sz, 0)
        yield from bps.sleep(2)

    # toc(t_setup, str='Setup time')

    # Setup the final scan plan
    if shutter:
        final_plan = finalize_wrapper(plan(),
                                      check_shutters(shutter, 'Close'))
    else:
        final_plan = plan()

    # Open the shutter
    if verbose:
        t_open = tic()
    # yield from check_shutters(shutter, 'Open')  ## Uncomment this
    if verbose:
        toc(t_open, str='Open shutter')

    # Run the scan
    uid = yield from final_plan

    return uid

def nano_scan_and_fly(*args, extra_dets=None, **kwargs):
    # RE(nano_scan_and_fly(-10, 10, 21, -1, 1, 5, 0.1, verbose=True))
    kwargs.setdefault('xmotor', nano_stage.sx)
    kwargs.setdefault('ymotor', nano_stage.sy)
    kwargs.setdefault('flying_zebra', nano_flying_zebra)
    print(kwargs['xmotor'].name)
    print(kwargs['ymotor'].name)
    print(kwargs['flying_zebra'].name)
    yield from abs_set(nano_flying_zebra.fast_axis, 'NANOHOR')
    yield from abs_set(nano_flying_zebra.slow_axis, 'NANOVER')

    _xs = kwargs.pop('xs', xs)
    if extra_dets is None:
        extra_dets = []
    dets = [] if  _xs is None else [_xs]
    dets = dets + extra_dets
    print(f"dets={dets}")
    print('Scan starting. Centering the scanner...')
    # yield from mv(nano_stage.sx, 0, nano_stage.sy, 0, nano_stage.sz, 0)
    yield from bps.sleep(2)
    yield from scan_and_fly_base(dets, *args, **kwargs)
    print('Scan finished. Centering the scanner...')
    yield from mv(nano_stage.sx, 0, nano_stage.sy, 0, nano_stage.sz, 0)
    yield from bps.sleep(2)


def nano_y_scan_and_fly(*args, extra_dets=None, **kwargs):
    kwargs.setdefault('xmotor', nano_stage.sy)
    kwargs.setdefault('ymotor', nano_stage.sx)
    kwargs.setdefault('flying_zebra', nano_flying_zebra)
    print(kwargs['xmotor'].name)
    print(kwargs['ymotor'].name)
    print(kwargs['flying_zebra'].name)
    yield from abs_set(nano_flying_zebra.fast_axis, 'NANOVER')
    yield from abs_set(nano_flying_zebra.slow_axis, 'NANOHOR')

    _xs = kwargs.pop('xs', xs)
    if extra_dets is None:
        extra_dets = []
    dets = [_xs] + extra_dets
    dets = [] if  _xs is None else [_xs]
    print(f"dets={dets}")
    print('Scan starting. Centering the scanner...')
    yield from bps.sleep(2)
    yield from scan_and_fly_base(dets, *args, **kwargs)
    print('Scan finished. Centering the scanner...')
    yield from mv(nano_stage.sx, 0, nano_stage.sy, 0, nano_stage.sz, 0)
    yield from bps.sleep(2)

    # yield from mv(nano_stage.sx, 0, nano_stage.sy, 0, nano_stage.sz, 0)



def nano_z_scan_and_fly(*args, extra_dets=None, **kwargs):
    kwargs.setdefault('xmotor', nano_stage.sz)
    kwargs.setdefault('ymotor', nano_stage.sx)
    kwargs.setdefault('flying_zebra', nano_flying_zebra)
    print(kwargs['xmotor'].name)
    print(kwargs['ymotor'].name)
    print(kwargs['flying_zebra'].name)
    yield from abs_set(nano_flying_zebra.fast_axis, 'NANOZ')
    yield from abs_set(nano_flying_zebra.slow_axis, 'NANOHOR')

    _xs = kwargs.pop('xs', xs)
    if extra_dets is None:
        extra_dets = []
    dets = [_xs] + extra_dets
    dets = [] if  _xs is None else [_xs]
    print(f"dets={dets}")
    print('Scan starting. Centering the scanner...')
    yield from bps.sleep(2)
    yield from scan_and_fly_base(dets, *args, **kwargs)
    print('Scan finished. Centering the scanner...')
    yield from mv(nano_stage.sx, 0, nano_stage.sy, 0, nano_stage.sz, 0)
    # yield from mv(nano_stage.sx, 0, nano_stage.sy, 0, nano_stage.sz, 0)
