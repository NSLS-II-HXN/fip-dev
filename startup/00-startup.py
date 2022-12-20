import functools
import os
import time
import uuid
import warnings
from collections import deque
from datetime import datetime, timedelta, tzinfo
from pathlib import Path

# The following code allows to call Matplotlib API from threads (experimental)
# Requires https://github.com/tacaswell/mpl-qtthread (not packaged yet)
import matplotlib
import matplotlib.backends.backend_qt
import mpl_qtthread
# set up the teleporter
mpl_qtthread.backend.initialize_qt_teleporter()
# tell Matplotlib to use this backend
matplotlib.use("module://mpl_qtthread.backend_agg")
# suppress (now) spurious warnings for mpl3.3+
mpl_qtthread.monkeypatch_pyplot()

# The following code is expected to fix the issue with MPL windows 'freezing'
#   after completion of a plan.
from IPython import get_ipython
ipython = get_ipython()
ipython.run_line_magic("matplotlib", "")

import certifi
import ophyd
import pandas as pd
import pymongo
import six
from ophyd.signal import EpicsSignalBase

import certifi
import ophyd
import pandas as pd
import pymongo
import six
from ophyd.signal import EpicsSignalBase

EpicsSignalBase.set_defaults(timeout=10, connection_timeout=10)

# Set up a Broker.
# TODO clean this up
from bluesky_kafka import Publisher
from databroker.v0 import Broker
from databroker.assets.mongo import Registry
from databroker.headersource.core import doc_or_uid_to_uid
from databroker.headersource.mongo import MDS
from jsonschema import validate as js_validate
from pymongo import MongoClient

# os.environ["PPMAC_HOST"] = "xf03idc-ppmac1"

# bootstrap_servers = os.getenv("BLUESKY_KAFKA_BOOTSTRAP_SERVERS", None)
# if bootstrap_servers is None:
#     # https://github.com/NSLS-II/nslsii/blob/b332c34813adf798c38184292d21537ef4f653bb/nslsii/__init__.py#L710-L712
#     msg = ("The 'BLUESKY_KAFKA_BOOTSTRAP_SERVERS' environment variable must "
#            "be defined as a comma-delimited list of Kafka server addresses "
#            "or hostnames and ports as a string such as "
#            "``'kafka1:9092,kafka2:9092``")
#     raise RuntimeError(msg)

# kafka_password = os.getenv("BLUESKY_KAFKA_PASSWORD", None)
# if kafka_password is None:
#     msg = "The 'BLUESKY_KAFKA_PASSWORD' environment variable must be set."
#     raise RuntimeError(msg)

# kafka_publisher = Publisher(
#         topic="hxn.bluesky.datum.documents",
#         bootstrap_servers=bootstrap_servers,
#         key=str(uuid.uuid4()),
#         producer_config={
#                 "acks": 1,
#                 "message.timeout.ms": 3000,
#                 "queue.buffering.max.kbytes": 10 * 1048576,
#                 "compression.codec": "snappy",
#                 "security.protocol": "SSL",
#                 "ssl.ca.location": certifi.where(),
#                 "security.protocol": "SASL_SSL",
#                 "sasl.mechanisms": "PLAIN",
#                 "sasl.username": "beamline",
#                 "sasl.password": kafka_password,
#                 },
#         flush_on_stop_doc=True,
#     ) if not os.environ.get('AZURE_TESTING') else None   # Disable on CI

# DB1
db1_name = 'rs'
db1_addr = 'mongodb://xf03id1-mdb01:27017,xf03id1-mdb02:27017,xf03id1-mdb03:27017'

_mds_config_db1 = {'host': db1_addr,
                   'port': 27017,
                   'database': 'datastore-2-fip-delete',
                   'timezone': 'US/Eastern'}

_fs_config_db1 = {'host': db1_addr,
                  'port': 27017,
                  'database': 'filestore-2-fip-delete'}

# Benchmark file
f_benchmark = open("/home/xf03id/benchmark.out", "a+")
datum_counts = {}

def sanitize_np(val):
    "Convert any numpy objects into built-in Python types."
    if isinstance(val, (np.generic, np.ndarray)):
        if np.isscalar(val):
            return val.item()
        return val.tolist()
    return val

def apply_to_dict_recursively(d, f):
    for key, val in d.items():
        if hasattr(val, 'items'):
            d[key] = apply_to_dict_recursively(val, f)
        d[key] = f(val)

def _write_to_file(col_name, method_name, t1, t2):
        f_benchmark.write(
            "{0}: {1}, t1: {2} t2:{3} time:{4} \n".format(
                col_name, method_name, t1, t2, (t2-t1),))
        f_benchmark.flush()


class CompositeRegistry(Registry):
    '''Composite registry.'''

    def _register_resource(self, col, uid, spec, root, rpath, rkwargs,
                              path_semantics):

        run_start=None
        ignore_duplicate_error=False
        duplicate_exc=None

        if root is None:
            root = ''

        resource_kwargs = dict(rkwargs)
        if spec in self.known_spec:
            js_validate(resource_kwargs, self.known_spec[spec]['resource'])

        resource_object = dict(spec=str(spec),
                               resource_path=str(rpath),
                               root=str(root),
                               resource_kwargs=resource_kwargs,
                               path_semantics=path_semantics,
                               uid=uid)

        try:
            col.insert_one(resource_object)
        except duplicate_exc:
            if ignore_duplicate_error:
                warnings.warn("Ignoring attempt to insert Datum with duplicate "
                          "datum_id, assuming that both ophyd and bluesky "
                          "attempted to insert this document. Remove the "
                          "Registry (`reg` parameter) from your ophyd "
                          "instance to remove this warning.")
            else:
                raise

        resource_object['id'] = resource_object['uid']
        resource_object.pop('_id', None)
        ret = resource_object['uid']

        return ret

    def register_resource(self, spec, root, rpath, rkwargs,
                              path_semantics='posix'):

        uid = str(uuid.uuid4())
        datum_counts[uid] = 0
        method_name = "register_resource"
        col = self._resource_col
        ret = self._register_resource(col, uid, spec, root, rpath,
                                      rkwargs, path_semantics=path_semantics)

        return ret

    def _insert_datum(self, col, resource, datum_id, datum_kwargs, known_spec,
                     resource_col, ignore_duplicate_error=False,
                     duplicate_exc=None):
        if ignore_duplicate_error:
            assert duplicate_exc is not None
        if duplicate_exc is None:
            class _PrivateException(Exception):
                pass
            duplicate_exc = _PrivateException
        try:
            resource['spec']
            spec = resource['spec']

            if spec in known_spec:
                js_validate(datum_kwargs, known_spec[spec]['datum'])
        except (AttributeError, TypeError):
            pass
        resource_uid = self._doc_or_uid_to_uid(resource)
        if type(datum_kwargs) == str and '/' in datum_kwargs:
            datum_kwargs = {'point_number': datum_kwargs.split('/')[-1]}

        datum = dict(resource=resource_uid,
                     datum_id=str(datum_id),
                     datum_kwargs=dict(datum_kwargs))
        apply_to_dict_recursively(datum, sanitize_np)
        # We are transitioning from ophyd objects inserting directly into a
        # Registry to ophyd objects passing documents to the RunEngine which in
        # turn inserts them into a Registry. During the transition period, we allow
        # an ophyd object to attempt BOTH so that configuration files are
        # compatible with both the new model and the old model. Thus, we need to
        # ignore the second attempt to insert.
        try:
            kafka_publisher('datum', datum)
            #col.insert_one(datum)
        except duplicate_exc:
            if ignore_duplicate_error:
                warnings.warn("Ignoring attempt to insert Resource with duplicate "
                              "uid, assuming that both ophyd and bluesky "
                              "attempted to insert this document. Remove the "
                              "Registry (`reg` parameter) from your ophyd "
                              "instance to remove this warning.")
            else:
                raise
        # do not leak mongo objectID
        datum.pop('_id', None)

        return datum


    def register_datum(self, resource_uid, datum_kwargs, validate=False):

        if validate:
            raise RuntimeError('validate not implemented yet')

        res_uid = resource_uid
        datum_count = datum_counts[res_uid]

        datum_uid = res_uid + '/' + str(datum_count)
        datum_counts[res_uid] = datum_count + 1

        col = self._datum_col
        datum = self._insert_datum(col, resource_uid, datum_uid, datum_kwargs, {}, None)
        ret = datum['datum_id']

        return ret

    def _doc_or_uid_to_uid(self, doc_or_uid):

        if not isinstance(doc_or_uid, six.string_types):
            try:
                doc_or_uid = doc_or_uid['uid']
            except TypeError:
                pass

        return doc_or_uid

    def _bulk_insert_datum(self, col, resource, datum_ids,
                           datum_kwarg_list):

        resource_id = self._doc_or_uid_to_uid(resource)

        to_write = []

        d_uids = deque()

        for d_id, d_kwargs in zip(datum_ids, datum_kwarg_list):
            dm = dict(resource=resource_id,
                      datum_id=str(d_id),
                      datum_kwargs=dict(d_kwargs))
            apply_to_dict_recursively(dm, sanitize_np)
            to_write.append(pymongo.InsertOne(dm))
            d_uids.append(dm['datum_id'])

        col.bulk_write(to_write, ordered=False)

        return d_uids

    def bulk_register_datum_table(self, resource_uid, dkwargs_table, validate=False):

        res_uid = resource_uid['uid']
        datum_count = datum_counts[res_uid]

        if validate:
            raise RuntimeError('validate not implemented yet')

        d_ids = [res_uid + '/' + str(datum_count+j) for j in range(len(dkwargs_table))]
        datum_counts[res_uid] = datum_count + len(dkwargs_table)

        dkwargs_table = pd.DataFrame(dkwargs_table)
        datum_kwarg_list = [ dict(r) for _, r in dkwargs_table.iterrows()]

        method_name = "bulk_register_datum_table"

        self._bulk_insert_datum(self._datum_col, resource_uid, d_ids, datum_kwarg_list)
        return d_ids


mds_db1 = MDS(_mds_config_db1, auth=False)
db1 = Broker(mds_db1, CompositeRegistry(_fs_config_db1))


# wrapper for two databases
class CompositeBroker(Broker):
    """wrapper for two databases"""

    # databroker.headersource.MDSROTemplate
    def _bulk_insert_events(self, event_col, descriptor, events, validate, ts):

        descriptor_uid = doc_or_uid_to_uid(descriptor)

        to_write = []
        for ev in events:
            data = dict(ev['data'])

            # Replace any filled data with the datum_id stashed in 'filled'.
            for k, v in six.iteritems(ev.get('filled', {})):
                if v:
                    data[k] = v
            # Convert any numpy types to native Python types.
            apply_to_dict_recursively(data, sanitize_np)
            timestamps = dict(ev['timestamps'])
            apply_to_dict_recursively(timestamps, sanitize_np)

            # check keys, this could be expensive
            if validate:
                if data.keys() != timestamps.keys():
                    raise ValueError(
                        BAD_KEYS_FMT.format(data.keys(),
                                            timestamps.keys()))
            ev_uid = ts + '-' + ev['uid']

            ev_out = dict(descriptor=descriptor_uid, uid=ev_uid,
                          data=data, timestamps=timestamps,
                          time=ev['time'],
                          seq_num=ev['seq_num'])

            to_write.append(pymongo.InsertOne(ev_out))

        event_col.bulk_write(to_write, ordered=True)

    # databroker.headersource.MDSROTemplate
    # databroker.headersource.MDSRO(MDSROTemplate)
    def _insert(self, name, doc, event_col, ts):
        for desc_uid, events in doc.items():
            # If events is empty, mongo chokes.
            if not events:
                continue
            self._bulk_insert_events(event_col,
                                     descriptor=desc_uid,
                                     events=events,
                                     validate=False, ts=ts)


    def insert(self, name, doc):

        if name == "start":
            f_benchmark.write("\n scan_id: {} \n".format(doc['scan_id']))
            f_benchmark.flush()
            datum_counts = {}

        ts =  str(datetime.now().timestamp())

        if name in {'bulk_events'}:
            ret2 = self._insert(name, doc, db1.mds._event_col, ts)
        else:
            ret2 = db1.insert(name, doc)
        return ret2

db = CompositeBroker(mds_db1, CompositeRegistry(_fs_config_db1))

from hxntools.handlers import register as _hxn_register_handlers

_hxn_register_handlers(db)
del _hxn_register_handlers
# do the rest of the standard configuration
from IPython import get_ipython
from nslsii import configure_base, configure_olog

configure_base(
    get_ipython().user_ns,
    db,
    bec=False,
    ipython_logging=False,
    publish_documents_with_kafka=False
)
# configure_olog(get_ipython().user_ns)

# bec.disable_table()
# bec.disable_plots()

from bluesky.callbacks.best_effort import BestEffortCallback

bec = BestEffortCallback()

# un import *
ns = get_ipython().user_ns
for m in [bp, bps, bpp]:
    for n in dir(m):
        if (not n.startswith('_')
               and n in ns
               and getattr(ns[n], '__module__', '')  == m.__name__):
            del ns[n]
del ns
from bluesky.magics import BlueskyMagics

from bluesky.utils import PersistentDict
runengine_metadata_dir = Path("/nsls2/data/hxn/shared/config/runengine-metadata-fip-delete")
RE.md = PersistentDict(runengine_metadata_dir)

# set some default meta-data
RE.md['group'] = ''
RE.md['config'] = {}
RE.md['beamline_id'] = 'HXN'
RE.verbose = True


from hxntools.scan_number import HxnScanNumberPrinter
from hxntools.scan_status import HxnScanStatus
from ophyd import EpicsSignal
# set up some HXN specific callbacks
from ophyd.callbacks import UidPublish

# uid_signal = EpicsSignal('XF:03IDC-ES{BS-Scan}UID-I', name='uid_signal')
# uid_broadcaster = UidPublish(uid_signal)
# scan_number_printer = HxnScanNumberPrinter()
# hxn_scan_status = HxnScanStatus('XF:03IDC-ES{Status}ScanRunning-I')


# def flush_on_stop_doc(name, doc):
#     if name=='stop':
#         kafka_publisher.flush()

# # This is needed to prevent the local buffer from filling.
# RE.subscribe(flush_on_stop_doc, 'stop')

# # Pass on only start/stop documents to a few subscriptions
# for _event in ('start', 'stop'):
#     RE.subscribe(scan_number_printer, _event)
#     RE.subscribe(uid_broadcaster, _event)
#     RE.subscribe(hxn_scan_status, _event)


# def ensure_proposal_id(md):
#     if 'proposal_id' not in md:
#         raise ValueError("You forgot the proposal id.")
# RE.md_validator = ensure_proposal_id


# be nice on segfaults
import faulthandler

faulthandler.enable()

# set up logging framework
import logging
import sys

handler = logging.StreamHandler(sys.stderr)
fmt = logging.Formatter("%(asctime)-15s [%(name)5s:%(levelname)s] %(message)s")
handler.setFormatter(fmt)
handler.setLevel(logging.INFO)

logging.getLogger('hxntools').addHandler(handler)
logging.getLogger('hxnfly').addHandler(handler)
logging.getLogger('ppmac').addHandler(handler)

logging.getLogger('hxnfly').setLevel(logging.INFO)
logging.getLogger('hxntools').setLevel(logging.INFO)
logging.getLogger('ppmac').setLevel(logging.INFO)

# logging.getLogger('ophyd').addHandler(handler)
# logging.getLogger('ophyd').setLevel(logging.DEBUG)

# Flyscan results are shown using pandas. Maximum rows/columns to use when
# printing the table:
pd.options.display.width = 180
pd.options.display.max_rows = None
pd.options.display.max_columns = 10

from bluesky.plan_stubs import mov

# from bluesky.utils import register_transform

def register_transform(RE, *, prefix='<'):
    '''Register RunEngine IPython magic convenience transform
    Assuming the default parameters
    This maps `< stuff(*args, **kwargs)` -> `RE(stuff(*args, **kwargs))`
    RE is assumed to be available in the global namespace
    Parameters
    ----------
    RE : str
        The name of a valid RunEngine instance in the global IPython namespace
    prefix : str, optional
        The prefix to trigger this transform on.  If this collides with
        valid python syntax or an existing transform you are on your own.
    '''
    import IPython

    # from IPython.core.inputtransformer2 import StatelessInputTransformer

 #   @StatelessInputTransformer.wrap
    def tr_re(lines):
        new_lines = []
        for line in lines:
            if line.startswith(prefix):
                line = line[len(prefix):].strip()
                new_lines.append('{}({})'.format(RE, line))
            else:
                new_lines.append(line)
        return new_lines

    ip = IPython.get_ipython()
    # ip.input_splitter.line_transforms.append(tr_re())
    # ip.input_transformer_manager.logical_line_transforms.append(tr_re())
    ip.input_transformer_manager.line_transforms.append(tr_re)

register_transform('RE', prefix='<')

# -HACK- Patching set_and_wait in ophyd.device to make stage and unstage more
# reliable

_set_and_wait = ophyd.device.set_and_wait

@functools.wraps(_set_and_wait)
def set_and_wait_again(signal, val, **kwargs):
    logger = logging.getLogger('ophyd.utils.epics_pvs')
    start_time = time.monotonic()
    deadline = start_time + set_and_wait_again.timeout
    attempts = 0
    while True:
        attempts += 1
        try:
            return _set_and_wait(signal, val, **kwargs)
        except TimeoutError as ex:
            remaining = max((deadline - time.monotonic(), 0))
            if remaining <= 0:
                error_msg = (
                    f'set_and_wait({signal}, {val}, **{kwargs!r}) timed out '
                    f'after {time.monotonic() - start_time:.1f} sec and '
                    f'{attempts} attempts'
                )
                logger.error(error_msg)
                raise TimeoutError(error_msg) from ex
            else:
                logger.warning('set_and_wait(%s, %s, **%r) raised %s. '
                               '%.1f sec remaining until this will be marked as a '
                               'failure. (attempt #%d): %s',
                               signal, val, kwargs, type(ex).__name__,
                               remaining, attempts, ex
                               )

# Ivan: try a longer timeout for debugging
#set_and_wait_again.timeout = 300
set_and_wait_again.timeout = 1200
ophyd.device.set_and_wait = set_and_wait_again
# -END HACK-


# - HACK #2 -  patch EpicsSignal.get to retry when timeouts happen

def _epicssignal_get(self, *, as_string=None, connection_timeout=1.0, **kwargs):
    '''Get the readback value through an explicit call to EPICS

    Parameters
    ----------
    count : int, optional
        Explicitly limit count for array data
    as_string : bool, optional
        Get a string representation of the value, defaults to as_string
        from this signal, optional
    as_numpy : bool
        Use numpy array as the return type for array data.
    timeout : float, optional
        maximum time to wait for value to be received.
        (default = 0.5 + log10(count) seconds)
    use_monitor : bool, optional
        to use value from latest monitor callback or to make an
        explicit CA call for the value. (default: True)
    connection_timeout : float, optional
        If not already connected, allow up to `connection_timeout` seconds
        for the connection to complete.
    '''
    if as_string is None:
        as_string = self._string

    ###########################################
    # Usedf only for old ophyd 1.3.3 and older.
    import packaging
    import ophyd

    if packaging.version.parse(ophyd.__version__) < packaging.version.parse("1.4"):
        self._metadata_lock = self._lock
    ###########################################

    with self._metadata_lock:
        if not self._read_pv.connected:
            if not self._read_pv.wait_for_connection(connection_timeout):
                raise TimeoutError('Failed to connect to %s' %
                                   self._read_pv.pvname)

        ret = None
        attempts = 0
        max_attempts = 4
        while ret is None and attempts < max_attempts:
            attempts += 1
            #Ivan debug: change get option:
            ret = self._read_pv.get(as_string=as_string, **kwargs)
            #ret = self._read_pv.get(as_string=as_string, use_monitor=False, timeout=1.2, **kwargs)
            if ret is None:
                print(f'*** PV GET TIMED OUT {self._read_pv.pvname} *** attempt #{attempts}/{max_attempts}')
            elif as_string and ret in (b'None', 'None'):
                print(f'*** PV STRING GET TIMED OUT {self._read_pv.pvname} *** attempt #{attempts}/{max_attempts}')
                ret = None
        if ret is None:
            print(f'*** PV GET TIMED OUT {self._read_pv.pvname} *** return `None` as value :(')
            # TODO we really want to raise TimeoutError here, but that may cause more
            # issues in the codebase than we have the time to fix...
            # If this causes issues, remove it to keep the old functionality...
            raise TimeoutError('Failed to get %s after %d attempts' %
                               (self._read_pv.pvname, attempts))
        if attempts > 1:
            print(f'*** PV GET succeeded {self._read_pv.pvname} on attempt #{attempts}')

    if as_string:
        return ophyd.signal.waveform_to_string(ret)

    return ret


from ophyd import EpicsSignal, EpicsSignalRO
from ophyd.areadetector import EpicsSignalWithRBV

EpicsSignal.get = _epicssignal_get
EpicsSignalRO.get = _epicssignal_get
EpicsSignalWithRBV.get = _epicssignal_get
