from hxntools.struck_scaler import (HxnTriggeringScaler, StruckScaler)

# - 3IDC RG:C4 VME scalers
# -- scaler 1 is used for data acquisition. HxnScaler takes care of setting
#    that up:
sclr1 = HxnTriggeringScaler('XF:03IDC-ES{Sclr:1}', name='sclr1')
# let the scans know which detectors sclr1 triggers:
# sclr1.scan_type_triggers['step'] = [zebra, merlin1, xspress3]
# sclr1.scan_type_triggers['step'] = [zebra, xspress3]  ##!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
sclr1.scan_type_triggers['fly'] = []


sclr1.read_attrs = ['channels', 'calculations']
sclr1.mcas.kind = 'omitted'
sclr1.channels.read_attrs = [f'chan{j}' for j in range(1, 17)]
sclr1.calculations.read_attrs = ['calc5']
# sclr1.hints = {'fields': [f'sclr1_ch{j}' for j in (1, 2, 3)]}


#[.chan1', 'channels.chan2', 'channels.chan3',
#                    'channels.chan4', 'channels.chan5', 'channels.chan6',
#                    'channels.chan7','channels.chan8', 'calculations.calc5',

sclr1_ch1 = sclr1.channels.chan1
sclr1_ch2 = sclr1.channels.chan2
sclr1_ch3 = sclr1.channels.chan3
sclr1_ch4 = sclr1.channels.chan4
sclr1_ch5 = sclr1.channels.chan5

sclr1_ch5_calc = sclr1.calculations.calc5.value

n_scaler_mca = 16
sclr1_mca = [sclr1.mca_by_index[i] for i in range(1, n_scaler_mca + 1)]

for mca in sclr1_mca:
    mca.name = 'sclr1_mca{}'.format(mca.index)

# -- scaler 2, on the other hand, is just used as a regular scaler, however the
#    user desires
sclr2 = StruckScaler('XF:03IDC-ES{Sclr:2}', name='sclr2')
sclr2.read_attrs = ['channels', 'calculations']

sclr2.mcas.kind = 'omitted'
sclr2.channels.read_attrs = [f'chan{j}' for j in range(1, 17)]
sclr2.calculations.read_attrs = ['calc5']
# sclr2.hints = {'fields': [f'sclr2_ch{j}' for j in (2, 3, 4)]}

sclr2_ch1 = sclr2.channels.chan1
sclr2_ch2 = sclr2.channels.chan2
sclr2_ch3 = sclr2.channels.chan3
sclr2_ch4 = sclr2.channels.chan4
sclr2_ch5 = sclr2.channels.chan5

sclr2_ch4_calc = sclr2.calculations.calc4.value


# Rename all scaler channels according to a common format.
def setup_scaler_names(scaler, channel_format, calc_format):
    for i in range(1, 33):
        channel = getattr(scaler.channels, 'chan{}'.format(i))
        channel.name = channel_format.format(i)

    for i in range(1, 9):
        c = getattr(scaler.calculations, 'calc{}'.format(i))
        c.name = calc_format.format(i)
        c.value.name = calc_format.format(i)


setup_scaler_names(sclr1, 'sclr1_ch{}', 'sclr1_ch{}_calc')
setup_scaler_names(sclr2, 'sclr2_ch{}', 'sclr2_ch{}_calc')

# TODO fix this
def hint_sclr_channels(sclr, chans):
    nm = sclr.name
    sclr.hints = {'fields': [f'{nm}_ch{j}' for j in chans]}
