print(f"Loading {__file__}...")

# XF:03IDC-ES{PT:BS-Ax:X}Mtr
# XF:03IDC-ES{PT:BS-Ax:Y}Mtr
# XF:03IDC-ES{PT:BS-Ax:Z}Mtr
# XF:03IDC-ES{PT:BS-Ax:rz}Mtr

# XF:03IDC-ES{PT:HM-Ax:X}Mtr
# XF:03IDC-ES{PT:HM-Ax:Y}Mtr
# XF:03IDC-ES{PT:HM-Ax:Z}Mtr
# XF:03IDC-ES{PT:HM-Ax:ry}Mtr
# XF:03IDC-ES{PT:OP-Ax:X}Mtr
# XF:03IDC-ES{PT:OP-Ax:Y}Mtr
# XF:03IDC-ES{PT:OP-Ax:Z}Mtr
# XF:03IDC-ES{PT:OP-Ax:rx}Mtr
# XF:03IDC-ES{PT:OP-Ax:ry}Mtr
# XF:03IDC-ES{PT:OSA-Ax:X}Mtr
# XF:03IDC-ES{PT:OSA-Ax:Y}Mtr
# XF:03IDC-ES{PT:OSA-Ax:Z}Mtr

# XF:03IDC-ES{PT:Smpl-Ax:cx}Mtr
# XF:03IDC-ES{PT:Smpl-Ax:cz}Mtr
# XF:03IDC-ES{PT:Smpl-Ax:ssx}Mtr
# XF:03IDC-ES{PT:Smpl-Ax:ssy}Mtr
# XF:03IDC-ES{PT:Smpl-Ax:ssz}Mtr
# XF:03IDC-ES{PT:Smpl-Ax:th}Mtr

# XF:03IDC-ES{PT:SmplBase-Ax:X}Mtr
# XF:03IDC-ES{PT:SmplBase-Ax:Y}Mtr
# XF:03IDC-ES{PT:SmplBase-Ax:Z}Mtr
# XF:03IDC-ES{PT:VM-Ax:X}Mtr
# XF:03IDC-ES{PT:VM-Ax:Y}Mtr
# XF:03IDC-ES{PT:VM-Ax:Z}Mtr
# XF:03IDC-ES{PT:VM-Ax:rx}Mtr
# XF:03IDC-ES{PT:VM-Ax:rz}Mtr
# XF:03IDC-ES{Slt:4-Ax:Top}Mtr
# XF:03IDC-ES{Slt:4-Ax:X}Mtr
# XF:03IDC-ES{Slt:4-Ax:Y}Mtr
# XF:03IDC-ES{Slt:4-Ax:Z}Mtr

class HXN_NanoStage(Device):
    ssx = Cpt(EpicsMotor, '{PT:Smpl-Ax:ssx}Mtr')  # Scanning piezo X
    ssy = Cpt(EpicsMotor, '{PT:Smpl-Ax:ssy}Mtr')
    ssz = Cpt(EpicsMotor, '{PT:Smpl-Ax:ssz}Mtr')
    th = Cpt(EpicsMotor, '{PT:Smpl-Ax:th}Mtr')
    cx = Cpt(EpicsMotor, '{PT:Smpl-Ax:cx}Mtr')  
    cz = Cpt(EpicsMotor, '{PT:Smpl-Ax:cz}Mtr') 

    bs_x = Cpt(EpicsMotor, '{PT:BS-Ax:X}Mtr')  
    bs_y = Cpt(EpicsMotor, '{PT:BS-Ax:Y}Mtr')
    bs_z = Cpt(EpicsMotor, '{PT:BS-Ax:Z}Mtr')
    bs_rz = Cpt(EpicsMotor, '{PT:BS-Ax:rz}Mtr')

    hm_x = Cpt(EpicsMotor, '{PT:HM-Ax:X}Mtr')  
    hm_y = Cpt(EpicsMotor, '{PT:HM-Ax:Y}Mtr')
    hm_z = Cpt(EpicsMotor, '{PT:HM-Ax:Z}Mtr')
    hm_ry = Cpt(EpicsMotor, '{PT:HM-Ax:ry}Mtr')

    zp_x = Cpt(EpicsMotor, '{PT:OP-Ax:X}Mtr')  
    zp_y = Cpt(EpicsMotor, '{PT:OP-Ax:Y}Mtr')
    zp_z = Cpt(EpicsMotor, '{PT:OP-Ax:Z}Mtr')
    zp_rx = Cpt(EpicsMotor, '{PT:OP-Ax:rx}Mtr')
    zp_ry = Cpt(EpicsMotor, '{PT:OP-Ax:ry}Mtr')

    osa_x = Cpt(EpicsMotor, '{PT:OSA-Ax:X}Mtr')  
    osa_y = Cpt(EpicsMotor, '{PT:OSA-Ax:Y}Mtr')
    osa_z = Cpt(EpicsMotor, '{PT:OSA-Ax:Z}Mtr')

    sb_x = Cpt(EpicsMotor, '{PT:SmplBase-Ax:X}Mtr')  
    sb_y = Cpt(EpicsMotor, '{PT:SmplBase-Ax:Y}Mtr')
    sb_z = Cpt(EpicsMotor, '{PT:SmplBase-Ax:Z}Mtr')

    vm_x = Cpt(EpicsMotor, '{PT:VM-Ax:X}Mtr')  
    vm_y = Cpt(EpicsMotor, '{PT:VM-Ax:Y}Mtr')
    vm_z = Cpt(EpicsMotor, '{PT:VM-Ax:Z}Mtr')
    vm_rx = Cpt(EpicsMotor, '{PT:VM-Ax:rx}Mtr')  
    vm_rz = Cpt(EpicsMotor, '{PT:VM-Ax:rz}Mtr')

    slt_vgap = Cpt(EpicsMotor, '{Slt:4-Ax:X}Mtr')  
    slt_vcen = Cpt(EpicsMotor, '{Slt:4-Ax:Y}Mtr')
    slt_hgap = Cpt(EpicsMotor, '{Slt:4-Ax:Z}Mtr')
    slt_hcen = Cpt(EpicsMotor, '{Slt:4-Ax:Top}Mtr')  


pt_tomo = HXN_NanoStage('XF:03IDC-ES', name='pt_tomo')

# Temporary disable a motor (e.g. if the motor is not functioning and PVs are not accessible)
setattr(pt_tomo.ssx, "is_disabled", False)
setattr(pt_tomo.ssy, "is_disabled", False)
setattr(pt_tomo.ssz, "is_disabled", True)


sd.baseline.extend([
    pt_tomo.ssx,
    pt_tomo.ssy,
    # pt_tomo.ssz,
    pt_tomo.cx,
    pt_tomo.cz,
    pt_tomo.th,

    pt_tomo.bs_x,
    pt_tomo.bs_y,
    pt_tomo.bs_z,
    pt_tomo.bs_rz,

    pt_tomo.hm_x,
    pt_tomo.hm_y,
    pt_tomo.hm_z,
    pt_tomo.hm_ry,

    pt_tomo.zp_x,
    pt_tomo.zp_y,
    pt_tomo.zp_z,
    pt_tomo.zp_rx,
    pt_tomo.zp_ry,

    pt_tomo.osa_x,
    pt_tomo.osa_y,
    pt_tomo.osa_z,

    pt_tomo.sb_x,
    pt_tomo.sb_y,
    pt_tomo.sb_z,

    pt_tomo.vm_x,
    pt_tomo.vm_y,
    pt_tomo.vm_z,
    pt_tomo.vm_rx,
    pt_tomo.vm_rz,

    pt_tomo.slt_vgap,
    pt_tomo.slt_vcen,
    pt_tomo.slt_hgap,
    pt_tomo.slt_hcen,
])

# # Interferometers
# class SRXNanoInterferometer(Device):
#     posX = Cpt(EpicsSignalRO, 'POS_0')
#     posY = Cpt(EpicsSignalRO, 'POS_1')
#     posZ = Cpt(EpicsSignalRO, 'POS_2')


# nanoKB_interferometer = SRXNanoInterferometer('XF:05IDD-ES:1{PICOSCALE:1}', name='nanoKB_interferometer')


stages_to_move = [pt_tomo.ssx, pt_tomo.ssy, pt_tomo.ssz]
velocity_slow = 30
velocity_fast = 300

def set_scanner_velocity(velocity=velocity_slow):
    for d in stages_to_move:
        if not getattr(d, "is_disabled", False):
            yield from bps.mv(d.velocity, velocity)

def reset_scanner_velocity():
    for d in stages_to_move:
        if not getattr(d, "is_disabled", False):
            yield from bps.mv(d.velocity, velocity_fast)


