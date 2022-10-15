
from ophyd import Component as Cpt

from hxntools.detectors import HxnMerlinDetector as _HMD
from hxntools.detectors.merlin import HDF5PluginWithFileStore as _mhdf

from nslsii.ad33 import StatsPluginV33


class HxnMerlinDetector(_HMD):
    stats1 = Cpt(StatsPluginV33, 'Stats1:')
    stats2 = Cpt(StatsPluginV33, 'Stats2:')
    stats3 = Cpt(StatsPluginV33, 'Stats3:')
    stats4 = Cpt(StatsPluginV33, 'Stats4:')
    stats5 = Cpt(StatsPluginV33, 'Stats5:')

    hdf5 = Cpt(_mhdf, 'HDF1:',
               read_attrs=[],
               configuration_attrs=[],
               write_path_template=LARGE_FILE_DIRECTORY_PATH,
               root=LARGE_FILE_DIRECTORY_ROOT,
               reg=db.reg)


merlin2 = HxnMerlinDetector('XF:03IDC-ES{Merlin:2}', name='merlin2',
                            image_name='merlin2',
                            read_attrs=['hdf5', 'cam', 'stats1'])
merlin2.hdf5.read_attrs = []

# merlin = merlin2
