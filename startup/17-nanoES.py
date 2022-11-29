print(f"Loading {__file__}...")

# High flux sample stages
class SRXNanoStage(Device):
    # x = Cpt(EpicsMotor, 'sx}Mtr')  # XF:05IDD-ES:1{nKB:Smpl-Ax:sx}Mtr.RBV
    # y = Cpt(EpicsMotor, 'sy}Mtr')  # XF:05IDD-ES:1{nKB:Smpl-Ax:sy}Mtr.RBV
    # z = Cpt(EpicsMotor, 'sz}Mtr')  # XF:05IDD-ES:1{nKB:Smpl-Ax:sz}Mtr.RBV
    sx = Cpt(EpicsMotor, 'ssx}Mtr')  # XF:05IDD-ES:1{nKB:Smpl-Ax:ssx}Mtr.RBV
    sy = Cpt(EpicsMotor, 'ssy}Mtr')  # XF:05IDD-ES:1{nKB:Smpl-Ax:ssy}Mtr.RBV
    sz = Cpt(EpicsMotor, 'ssz}Mtr')  # XF:05IDD-ES:1{nKB:Smpl-Ax:ssz}Mtr.RBV
    # th = Cpt(EpicsMotor, 'th}Mtr')  # XF:05IDD-ES:1{nKB:Smpl-Ax:th}Mtr.RBV
    #topx = Cpt(EpicsMotor, 'xth}Mtr')  # XF:05IDD-ES:1{nKB:Smpl-Ax:xth}Mtr.RBV
    #topz = Cpt(EpicsMotor, 'zth}Mtr')  # XF:05IDD-ES:1{nKB:Smpl-Ax:zth}Mtr.RBV


nano_stage = SRXNanoStage('XF:03IDC-ES{PT:Smpl-Ax:', name='nano_stage')

# # Lakeshore temperature monitors
# class SRXNanoTemp(Device):
#     temp_nanoKB_horz = Cpt(EpicsSignalRO, '2}T:C-I')
#     temp_nanoKB_vert = Cpt(EpicsSignalRO, '1}T:C-I')
#     temp_nanoKB_base = Cpt(EpicsSignalRO, '4}T:C-I')
#     temp_microKB_base = Cpt(EpicsSignalRO, '3}T:C-I')


# temp_nanoKB = SRXNanoTemp('XF:05IDD-ES{LS:1-Chan:', name='temp_nanoKB')


# # Interferometers
# class SRXNanoInterferometer(Device):
#     posX = Cpt(EpicsSignalRO, 'POS_0')
#     posY = Cpt(EpicsSignalRO, 'POS_1')
#     posZ = Cpt(EpicsSignalRO, 'POS_2')


# nanoKB_interferometer = SRXNanoInterferometer('XF:05IDD-ES:1{PICOSCALE:1}', name='nanoKB_interferometer')


# stages_to_move = [nano_stage.sx, nano_stage.sy, nano_stage.sz]
stages_to_move = [nano_stage.sx, nano_stage.sy]
velocity_slow = 30
velocity_fast = 300

def set_scanner_velocity(velocity=velocity_slow):
    for d in stages_to_move:
        yield from bps.mv(d.velocity, velocity)
        # d.velocity.set(velocity).wait()

def reset_scanner_velocity():
    for d in stages_to_move:
        yield from bps.mv(d.velocity, velocity_fast)
        # d.velocity.set(velocity_fast).wait()


from datetime import datetime
# LARGE_FILE_DIRECTORY_PATH = "/data" + datetime.now().strftime("/%Y/%m/%d")
LARGE_FILE_DIRECTORY_ROOT = "/data/fip-data-test"
LARGE_FILE_DIRECTORY_PATH = "/data/fip-data-test" + datetime.now().strftime("/%Y/%m/%d")
