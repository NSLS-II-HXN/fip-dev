def script():
    x_start, x_stop = -10, 10
    pt_tomo.ssx.velocity.set(300).wait()
    for n in range(10):
        t1 = tic()
        pt_tomo.ssx.set(x_start).wait()
        toc(t1, "Step1")
        t2 = tic()
        pt_tomo.ssx.set(x_stop).wait()
        toc(t2, "Step2")


def plan():
    x_start, x_stop = -10, 10
    yield from set_scanner_velocity(300)
    for n in range(10):
        t1 = tic()
        yield from bps.mv(pt_tomo.ssx, x_start)
        toc(t1, "Step1")
        t2 = tic()
        yield from bps.mv(pt_tomo.ssx, x_stop)
        toc(t2, "Step1")


def plan2():
    x_start, x_stop = -10, 10
    y_start, y_stop = -10, 10
    yield from set_scanner_velocity(300)
    for n in range(10):
        t1 = tic()
        yield from bps.abs_set(pt_tomo.ssx, x_start, group="abc")
        yield from bps.abs_set(pt_tomo.ssy, y_start, group="abc")
        yield from bps.wait(group="abc")
        toc(t1, "Step1")
        t2 = tic()
        yield from bps.abs_set(pt_tomo.ssx, x_stop, group="abc")
        yield from bps.abs_set(pt_tomo.ssy, y_stop, group="abc")
        yield from bps.wait(group="abc")
        toc(t2, "Step1")
