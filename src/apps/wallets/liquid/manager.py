from ..manager import *
from gui.common import format_addr

from bitcoin import script, bip32, ec, compact, hashes
from bitcoin.liquid.psetview import PSETView
from bitcoin.liquid.networks import NETWORKS
from bitcoin.liquid.transaction import LSIGHASH as SIGHASH
from bitcoin.liquid.addresses import address as liquid_address
from .wallet import WalletError, LWallet
from helpers import is_liquid
import secp256k1

# asset management
ADD_ASSET = 0xA7
DUMP_ASSETS = 0xA8

SIGHASH_NAMES = {
    SIGHASH.ALL: "ALL",
    SIGHASH.NONE: "NONE",
    SIGHASH.SINGLE: "SINGLE",
}
# add sighash | anyonecanpay
for sh in list(SIGHASH_NAMES):
    SIGHASH_NAMES[sh | SIGHASH.ANYONECANPAY] = SIGHASH_NAMES[sh] + " | ANYONECANPAY"
# add sighash | rangeproof
for sh in list(SIGHASH_NAMES):
    SIGHASH_NAMES[sh | SIGHASH.RANGEPROOF] = SIGHASH_NAMES[sh] + " | RANGEPROOF"

class LWalletManager(WalletManager):
    """
    WalletManager class manages your wallets.
    It stores public information about the wallets
    in the folder and signs it with keystore's id key
    """

    prefixes = WalletManager.prefixes + [b"addasset", b"dumpassets"]
    PSBTViewClass = PSETView
    B64PSBT_PREFIX = b"cHNl"
    WalletClass = LWallet
    # supported networks
    Networks = {"liquidv1": NETWORKS["liquidv1"], "elementsregtest": NETWORKS["elementsregtest"]}
    DEFAULT_SIGHASH = (SIGHASH.ALL | SIGHASH.RANGEPROOF)


    def __init__(self, path):
        super().__init__(path)
        self.assets = {}


    def init(self, keystore, network, *args, **kwargs):
        """Loads or creates default wallets for new keystore or network"""
        super().init(keystore, network, *args, **kwargs)
        self.load_assets()


    def get_sighash_info(self, sighash):
        if sighash not in SIGHASH_NAMES:
            raise WalletError("Unknown sighash type: %d!" % sighash)
        return { "name": SIGHASH_NAMES[sighash], "warning": "" }


    def get_address(self, psbtout):
        """Helper function to get an address for every output"""
        network = self.Networks[self.network]
        # liquid fee
        if psbtout.script_pubkey.data == b"":
            return "Fee"
        if psbtout.blinding_pubkey is not None:
            # TODO: check rangeproof if it's present,
            # otherwise generate it ourselves if sighash is | RANGEPROOF
            bpub = ec.PublicKey.parse(psbtout.blinding_pubkey)
            return liquid_address(psbtout.script_pubkey, bpub, network)
        # finally just return unconfidential address
        return super().get_address(psbtout)


    def parse_stream(self, stream):
        prefix = self.get_prefix(stream)
        # if we have prefix
        if prefix is not None:
            if prefix == b"addasset":
                return ADD_ASSET, stream
            elif prefix == b"dumpassets":
                return DUMP_ASSETS, stream
        stream.seek(0)
        return super().parse_stream(stream)


    async def process_host_command(self, stream, show_screen):
        platform.delete_recursively(self.tempdir)
        cmd, stream = self.parse_stream(stream)
        if cmd == ADD_ASSET:
            arr = stream.read().decode().split(" ")
            if len(arr) != 2:
                raise WalletError("Invalid number of arguments. Usage: addasset <hex_asset> asset_lbl")
            hexasset, assetlbl = arr
            if await show_screen(Prompt("Import asset?",
                    "Asset:\n\n"+format_addr(hexasset, letters=8, words=2)+"\n\nLabel: "+assetlbl)):
                asset = bytes(reversed(unhexlify(hexasset)))
                self.assets[asset] = assetlbl
                self.save_assets()
            return BytesIO(b"success"), {}
        elif cmd == DUMP_ASSETS:
            return BytesIO(self.assets_json()), {}
        else:
            stream.seek(0)
            return await super().process_host_command(stream, show_screen)


    async def confirm_transaction(self, wallets, meta, show_screen):
        """
        Checks parsed metadata, asks user about unclear options:
        - label unknown assets?
        - sign with provided sighashes or only with default?
        - sign if unknown wallet in inputs?
        - final tx confirmation
        Returns dict with options to pass to sign_psbtview function.
        """
        # ask the user to label assets
        await self.check_unknown_assets(meta, show_screen)

        return await super().confirm_transaction(wallets,meta, show_screen)


    async def check_unknown_assets(self, meta, show_screen):
        if len(meta.get("unknown_assets",[])) == 0:
            return
        scr = Prompt(
            "Warning!",
            "\nUnknown assets in the transaction!\n\n\n"
            "Do you want to label them?\n"
            "Otherwise they will be rendered with partial hex id.",
        )
        if await show_screen(scr):
            for asset in meta["unknown_assets"]:
                # return False if the user cancelled
                scr = InputScreen("Asset\n\n"+format_addr(hexlify(bytes(reversed(asset))).decode(), letters=8, words=2),
                            note="\nChoose a label for unknown asset.\nBetter to keep it short, like LBTC or LDIY")
                scr.ta.set_pos(190, 350)
                scr.ta.set_width(100)
                lbl = await show_screen(scr)
                # if user didn't label the asset - go to the next one
                if not lbl:
                    continue
                else:
                    self.assets[asset] = lbl
            self.save_assets()
        # replace labels we just saved
        for sc in meta["inputs"] + meta["outputs"]:
            if sc.get("raw_asset"):
                sc["asset"] = self.asset_label(sc["raw_asset"])


    def create_default_wallet(self, path):
        """Creates default p2wpkh wallet with name `Default`"""
        der = "m/84h/%dh/0h" % self.Networks[self.network]["bip32"]
        xpub = self.keystore.get_xpub(der)
        desc = "wpkh([%s%s]%s/{0,1}/*)" % (
            hexlify(self.keystore.fingerprint).decode(),
            der[1:],
            xpub.to_base58(self.Networks[self.network]["xpub"]),
        )
        # add blinding key to the descriptor
        desc = "blinded(slip77(%s),%s)" % (self.keystore.slip77_key, desc)
        w = self.WalletClass.parse("Default&"+desc, path)
        # pass keystore to encrypt data
        w.save(self.keystore)
        platform.sync()
        return w

    def preprocess_psbt(self, stream, fout):
        """
        Processes incoming PSBT, fills missing information and writes to fout.
        Returns:
        - PSBTView class to use (PSBTView or PSETView)
        - wallets in inputs: list of tuples (wallet, amount)
        - metadata for tx display including warnings that require user confirmation
        - default sighash to use for signing
        """
        # compress = True flag will make sure large fields won't be loaded to RAM
        psbtv = self.PSBTViewClass.view(stream, compress=True)

        # Start with global fields of PSBT

        # On Liquid we check if txseed is provided (for deterministic blinding)
        # It will be None if it is not there.
        blinding_seed = psbtv.get_value(b"\xfc\x07specter\x00")
        if blinding_seed:
            hseed = hashes.tagged_hash_init("liquid/txseed", blinding_seed)
            vals = [] # values
            abfs = [] # asset blinding factors
            vbfs = [] # value blinding factors

        # Write global scope first
        psbtv.stream.seek(psbtv.offset)
        res = read_write(psbtv.stream, fout, psbtv.first_scope-psbtv.offset)

        # string representation of the Bitcoin for wallet processing
        default_asset = "LBTC" if self.network == "liquidv1" else "tLBTC"
        fee = { default_asset: 0 }

        # here we will store all wallets that we detect in inputs
        # wallet: {asset: amount}
        # For BTC it will be always { default_asset: amount }
        wallets = {}
        meta = {
            "inputs": [{} for i in range(psbtv.num_inputs)],
            "outputs": [{} for i in range(psbtv.num_outputs)],
            "default_asset": default_asset,
        }

        fingerprint = self.keystore.fingerprint
        # We need to detect wallets owning inputs and outputs,
        # in case of liquid - unblind them.
        # Fill all necessary information:
        # For Bitcoin: bip32 derivations, witness script, redeem script
        # For Liquid: same + values, assets, commitments, proofs etc.
        # At the end we should have the most complete PSBT / PSET possible
        for i in range(psbtv.num_inputs):
            # load input to memory, verify it (check prevtx hash)
            inp = psbtv.input(i)
            metainp = meta["inputs"][i]
            # verify, do not require non_witness_utxo if witness_utxo is set
            inp.verify(ignore_missing=True)

            # check sighash in the input
            if inp.sighash_type is not None and inp.sighash_type != self.DEFAULT_SIGHASH:
                metainp["sighash"] = self.get_sighash_info(inp.sighash_type)["name"]

            # in Liquid we may need to rewind the rangeproof to get values
            rangeproof_offset = None
            if is_liquid(self.network):
                off = psbtv.seek_to_scope(i)
                # find offset of the rangeproof if it exists
                rangeproof_offset = psbtv.seek_to_value(b'\xfc\x04pset\x0e', from_current=True)
                # add scope offset
                if rangeproof_offset is not None:
                    rangeproof_offset += off

            # Find wallets owning the inputs and fill scope data:
            # first we check already detected wallet owns the input
            # as in most common case all inputs are owned by the same wallet.
            wallet = None
            for w in wallets:
                # pass rangeproof offset if it's in the scope
                if w.fill_scope(inp, fingerprint,
                                stream=psbtv.stream, rangeproof_offset=rangeproof_offset):
                    wallet = w
                    break
            if wallet is None:
                # find wallet and append it to wallets
                for w in self.wallets:
                    # pass rangeproof offset if it's in the scope
                    if w.fill_scope(inp, fingerprint,
                                    stream=psbtv.stream, rangeproof_offset=rangeproof_offset):
                        wallet = w
                        break
            # add wallet to tx wallets dict
            if wallet not in wallets:
                wallets[wallet] = {}

            # Get values (and assets) and store in metadata and wallets dict
            if not is_liquid(self.network):
                # bitcoin it easy, just add value to the asset
                asset = default_asset
                value = inp.utxo.value
            else:
                # we don't know yet if we unblinded stuff or not
                asset = inp.asset or inp.utxo.asset
                value = inp.value or inp.utxo.value
                # blinded assets are 33-bytes long, unblinded - 32
                if not (len(asset) == 32 and isinstance(value, int)):
                    asset = None
                    value = 0
                if blinding_seed:
                    # update blinding seed
                    hseed.update(bytes(reversed(inp.txid)))
                    hseed.update(inp.vout.to_bytes(4,'little'))
                    vals.append(value)
                    abfs.append(inp.asset_blinding_factor or b"\x00"*32)
                    vbfs.append(inp.value_blinding_factor or b"\x00"*32)

            wallets[wallet][asset] = wallets[wallet].get(asset, 0) + value
            metainp.update({
                "label": wallet.name if wallet else "Unknown wallet",
                "value": value,
            })
            if asset != default_asset:
                metainp.update({"asset": self.asset_label(asset)})
                if asset not in self.assets:
                    metainp.update({"raw_asset": asset})
            inp.write_to(fout)

        # if blinding seed is set - blind outputs that are missing proofs
        if is_liquid(self.network) and blinding_seed:
            blinding_out_indexes = []
            for i in range(psbtv.num_outputs):
                out = psbtv.output(i)
                hseed.update(out.script_pubkey.serialize())
            txseed = hseed.digest()
            for i in range(psbtv.num_outputs):
                out = psbtv.output(i)
                if out.blinding_pubkey:
                    blinding_out_indexes.append(i)
                    abfs.append(hashes.tagged_hash("liquid/abf", txseed+i.to_bytes(4,'little')))
                    vbfs.append(hashes.tagged_hash("liquid/vbf", txseed+i.to_bytes(4,'little')))
                    vals.append(out.value)
            # get last vbf from scope
            out = psbtv.output(blinding_out_indexes[-1])
            if out.value_blinding_factor:
                vbfs[-1] = out.value_blinding_factor
            else:
                raise NotImplementedError()
                vbfs[-1] = secp256k1.pedersen_blind_generator_blind_sum(vals, abfs, vbfs, psbtv.num_inputs)

            # calculate commitments (surj proof etc)

            # in_tags = [inp.asset for inp in self.inputs]
            # in_gens = [secp256k1.generator_parse(inp.utxo.asset) for inp in self.inputs]

            # for i, out in enumerate(self.outputs):
            #     if out.blinding_pubkey is None:
            #         continue
            #     gen = secp256k1.generator_generate_blinded(out.asset, out.asset_blinding_factor)
            #     out.asset_commitment = secp256k1.generator_serialize(gen)
            #     value_commitment = secp256k1.pedersen_commit(out.value_blinding_factor, out.value, gen)
            #     out.value_commitment = secp256k1.pedersen_commitment_serialize(value_commitment)

            #     proof_seed = hashes.tagged_hash("liquid/surjection_proof", txseed+i.to_bytes(4,'little'))
            #     proof, in_idx = secp256k1.surjectionproof_initialize(in_tags, out.asset, seed=proof_seed)
            #     secp256k1.surjectionproof_generate(proof, in_idx, in_gens, gen, self.inputs[in_idx].asset_blinding_factor, out.asset_blinding_factor)
            #     out.surjection_proof = secp256k1.surjectionproof_serialize(proof)

            #     # generate range proof
            #     rangeproof_nonce = hashes.tagged_hash("liquid/range_proof", txseed+i.to_bytes(4,'little'))
            #     out.reblind(rangeproof_nonce)
        # otherwise - verify all outputs
        for i in range(psbtv.num_outputs):
            out = psbtv.output(i)
            metaout = meta["outputs"][i]
            rangeproof_offset = None
            # surj_proof_offset = None
            # find rangeproof and surjection proof
            if is_liquid(self.network):
                off = psbtv.seek_to_scope(psbtv.num_inputs+i)
                # find offset of the rangeproof if it exists
                rangeproof_offset = psbtv.seek_to_value(b'\xfc\x04pset\x04', from_current=True)
                if rangeproof_offset is None:
                    psbtv.seek_to_scope(psbtv.num_inputs+i)
                    # alternative key definition (psetv0)
                    rangeproof_offset = psbtv.seek_to_value(b'\xfc\x08elements\x04', from_current=True)
                if rangeproof_offset is not None:
                    rangeproof_offset += off
                # psbtv.seek_to_scope(psbtv.num_inputs+i)
                # surj_proof_offset = psbtv.seek_to_value(b'\xfc\x04pset\x05', from_current=True)
                # if surj_proof_offset is None:
                #     psbtv.seek_to_scope(psbtv.num_inputs+i)
                #     # alternative key definition (psetv0)
                #     surj_proof_offset = psbtv.seek_to_value(b'\xfc\x08elements\x04', from_current=True)
                # if surj_proof_offset is not None:
                #     surj_proof_offset += off
            wallet = None
            for w in wallets:
                # pass rangeproof offset if it's in the scope
                if w.fill_scope(out, fingerprint,
                                stream=psbtv.stream,
                                rangeproof_offset=rangeproof_offset,
                                # surj_proof_offset=surj_proof_offset,
                ):
                    wallet = w
                    break
            if wallet is None:
                # find wallet and append it to wallets
                for w in self.wallets:
                    # pass rangeproof offset if it's in the scope
                    if w.fill_scope(out, fingerprint,
                                    stream=psbtv.stream,
                                    rangeproof_offset=rangeproof_offset,
                                    # surj_proof_offset=surj_proof_offset,
                    ):
                        wallet = w
                        break
            # - lq: generate commitments and rangeproofs
            #       if blinding pubkey is set and seed is set.
            # Get values (and assets) and store in metadata and wallets dict
            if not is_liquid(self.network):
                # bitcoin it easy, just add value to the asset
                asset = default_asset
                value = out.value
            else:
                # we don't know yet if we unblinded stuff or not
                asset = out.asset or out.asset_commitment
                value = out.value or out.value_commitment
                # blinded assets are 33-bytes long, unblinded - 32
                if not (len(asset) == 32 and isinstance(value, int)):
                    asset = None
                    value = 0
            metaout.update({
                "label": wallet.name if wallet else "",
                "change": wallet is not None,
                "value": value,
                "address": self.get_address(out),
            })
            if asset != default_asset:
                metaout.update({"asset": self.asset_label(asset)})
                if asset not in self.assets:
                    metaout.update({"raw_asset": asset})
            out.write_to(fout, skip_separator=True)
            # write rangeproofs and surjection proofs
            # separator
            fout.write(b"\x00")

        return wallets, meta

    def sign_psbtview(self, psbtv, out_stream, wallets, sighash):
        for w, _ in wallets:
            if w is None:
                continue
            # fill derivation paths from proprietary fields
            w.update_gaps(psbtv=psbtv)
            w.save(self.keystore)
        sig_count = 0
        with open(self.tempdir+"/sigs", "wb") as sig_stream:
            for i in range(psbtv.num_inputs):
                self.show_loader(title="Signing input %d of %d" % (i+1, psbtv.num_inputs))
                inp = psbtv.input(i)
                for w, _ in wallets:
                    if w is None:
                        continue
                    w.fill_scope(inp, self.keystore.fingerprint)
                    # sign with wallet if it has private keys
                    if w.has_private_keys:
                        sig_count += w.sign_input(psbtv, i, sig_stream, sighash, inp)
                # sign with keystore
                sig_count += self.keystore.sign_input(psbtv, i, sig_stream, sighash, inp)
                # add separator
                sig_stream.write(b"\x00")
        if sig_count == 0:
            raise WalletError("We didn't add any signatures!\n\nMaybe you forgot to import the wallet?\n\nScan the wallet descriptor to import it.")
        # remove unnecessary stuff:
        with open(self.tempdir+"/sigs", "rb") as sig_stream:
            psbtv.write_to(out_stream, compress=True, extra_input_streams=[sig_stream])


    ##### assets stuff ######
    # TODO: move to a separate app?

    def asset_label(self, asset):
        if asset is None:
            return "Undefined"
        # passing "BTC" shouldn't break things
        if isinstance(asset, str):
            return asset
        if asset in self.assets:
            return self.assets[asset]
        h = hexlify(bytes(reversed(asset))).decode()
        # hex repr of the asset
        return "L-"+h[:4]+"..."+h[-4:]

    def assets_json(self):
        assets = {}
        # no support for bytes...
        for asset in self.assets:
            assets[hexlify(bytes(reversed(asset))).decode()] = self.assets[asset]
        return json.dumps(assets)

    @property
    def assets_path(self):
        return self.root_path + "/uid" + self.keystore.uid

    @property
    def assets_file(self):
        return self.assets_path + "/assets_" + self.network

    def save_assets(self):
        platform.maybe_mkdir(self.assets_path)
        assets = self.assets_json()
        self.keystore.save_aead(self.assets_file, plaintext=assets.encode(), key=self.keystore.userkey)

    def load_assets(self):
        self.assets = {}
        # known Liquid assets
        if self.network == "liquidv1":
            self.assets.update({
                bytes(reversed(unhexlify("6f0279e9ed041c3d710a9f57d0c02928416460c4b722ae3457a11eec381c526d"))): "LBTC",
                bytes(reversed(unhexlify("ce091c998b83c78bb71a632313ba3760f1763d9cfcffae02258ffa9865a37bd2"))): "USDt",
            })
        platform.maybe_mkdir(self.assets_path)
        if platform.file_exists(self.assets_file):
            _, assets = self.keystore.load_aead(self.assets_file, key=self.keystore.userkey)
            assets = json.loads(assets.decode())
            # no support for bytes...
            for asset in assets:
                self.assets[bytes(reversed(unhexlify(asset)))] = assets[asset]
