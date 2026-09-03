from embit.descriptor.descriptor import Descriptor
from embit.descriptor.errors import DescriptorError
from embit.descriptor.taptree import TapTree


_BRANCH_ERROR = "All branches should have the same length"


def apply_descriptor_branch_compatibility():
    """Allow BIP-389 descriptors that mix multipath and fixed-path keys."""
    if hasattr(Descriptor, "_specter_branch_compat_original_init"):
        return

    original_init = Descriptor.__init__
    Descriptor._specter_branch_compat_original_init = original_init

    def compatible_init(
        self,
        miniscript=None,
        sh=False,
        wsh=True,
        key=None,
        wpkh=True,
        taproot=False,
        taptree=None,
    ):
        try:
            original_init(self, miniscript, sh, wsh, key, wpkh, taproot, taptree)
            return
        except DescriptorError as error:
            if str(error) != _BRANCH_ERROR or miniscript is None:
                raise

            # embit v0.8.2 counts fixed paths as one-element branch sets. Remove
            # this workaround once an upgraded embit accepts mixed BIP-389 keys.
            branch_lengths = {
                len(k.branches) for k in miniscript.keys if k.branches is not None
            }
            if len(branch_lengths) != 1:
                raise

        self.sh = sh
        self.wsh = wsh
        self.key = key
        self.miniscript = miniscript
        self.wpkh = wpkh
        self.taproot = taproot
        self.taptree = taptree or TapTree()
        for descriptor_key in self.keys:
            descriptor_key.taproot = taproot

    Descriptor.__init__ = compatible_init
