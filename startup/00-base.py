print(f"Loading {__file__}...")

from ophyd.signal import EpicsSignalBase
# EpicsSignalBase.set_default_timeout(timeout=10, connection_timeout=10)  # old style
EpicsSignalBase.set_defaults(timeout=10, connection_timeout=10)  # new style

import nslsii
import matplotlib as mpl
from IPython.terminal.prompts import Prompts, Token


class SRXPrompt(Prompts):
    def in_prompt_tokens(self, cli=None):
        return [
            (Token.Prompt, "BlueSky@HXN ["),
            (Token.PromptNum, str(self.shell.execution_count)),
            (Token.Prompt, "]: "),
        ]

ip = get_ipython()

# from databroker.v0 import Broker
# db = Broker.named("hxn")
# nslsii.configure_base(ip.user_ns, db)

nslsii.configure_base(ip.user_ns, "hxn")

ip.log.setLevel('WARNING')

# nslsii.configure_olog(ip.user_ns)
ip.prompts = SRXPrompt(ip)

# Custom Matplotlib configs:
mpl.rcParams["axes.grid"] = True  # grid always on

# Comment it out to enable BEC table:
bec.disable_table()


# Disable BestEffortCallback to plot ring current
bec.disable_plots()

from pathlib import Path

import appdirs

# from bluesky.utils import PersistentDict

# # runengine_metadata_dir = appdirs.user_data_dir(appname="bluesky") / Path("runengine-metadata")
# runengine_metadata_dir = Path('/nsls2/xf05id1/shared/config/runengine-metadata-new')

# RE.md = PersistentDict(runengine_metadata_dir)

# Optional: set any metadata that rarely changes.
RE.md["beamline_id"] = "HXN"
RE.md["md_version"] = "1.0"
