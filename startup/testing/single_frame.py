import time
from bluesky import plan_stubs as bps, preprocessors as bpp

def single_frame(dwell=1):

    t_start = time.time()

    @bpp.stage_decorator([eiger2])
    @bpp.run_decorator()
    def plan():
        eiger2.cam.image_mode.set(0).wait()
        eiger2.cam.trigger_mode.set(0).wait()
        yield from bps.trigger_and_read([eiger2])
        # yield from bps.sleep(dwell)

    yield from plan()

