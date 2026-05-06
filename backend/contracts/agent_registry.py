from algopy import ARC4Contract, arc4, GlobalState, BoxMap, Txn, Global, op, UInt64, Bytes, String


class AgentRecord(arc4.Struct):
    agent_name: arc4.String
    role: arc4.String
    registered_at_round: arc4.UInt64
    active: arc4.Bool
    signed_manifest: arc4.String
    total_transactions: arc4.UInt64


class AgentRegistry(ARC4Contract):
    # Global state
    owner: GlobalState[arc4.Address]
    total_registered: GlobalState[arc4.UInt64]
    registry_version: GlobalState[arc4.UInt64]

    # Box map: keyed by wallet address; stable key_prefix is critical
    registry: BoxMap[arc4.Address, AgentRecord]

    def __init__(self) -> None:
        self.owner = GlobalState(arc4.Address)
        self.total_registered = GlobalState(arc4.UInt64)
        self.registry_version = GlobalState(arc4.UInt64)
        self.registry = BoxMap(arc4.Address, AgentRecord, key_prefix=b"reg_")
        # Set deployer as owner and initialize counters
        self.owner.value = arc4.Address(Txn.sender)
        self.total_registered.value = arc4.UInt64(0)
        self.registry_version.value = arc4.UInt64(1)

    @arc4.abimethod(allow_actions=["NoOp"])
    def register(self, agent_name: arc4.String, role: arc4.String, signed_manifest: arc4.String) -> None:
        # Role validation (on-chain constraint)
        assert role == "buyer" or role == "curator" or role == "seller", "Role must be buyer, curator, or seller"

        caller = arc4.Address(Txn.sender)
        exists = caller in self.registry

        # Verify signature against a deterministic byte payload.
        expected_manifest = (
            Bytes(b"mercator:v1|")
            + agent_name.native.bytes
            + Bytes(b"|")
            + Txn.sender.bytes
            + Bytes(b"|")
            + role.native.bytes
        )

        # Decode base64-encoded signature into raw bytes for verification on-chain
        signed_manifest_bytes = op.base64_decode(op.Base64.StdEncoding, signed_manifest.native.bytes)

        assert op.ed25519verify_bare(
            expected_manifest, signed_manifest_bytes, Txn.sender.bytes
        ), "Manifest signature verification failed — ensure the manifest was signed with the caller's private key"

        if exists:
            record = self.registry[caller].copy()
            if record.active:
                # idempotent re-registration: update name and role, keep registered_at_round
                self.registry[caller] = record._replace(
                    agent_name=agent_name,
                    role=role,
                    signed_manifest=signed_manifest,
                )
            else:
                # previously deregistered — reactivate and update fields
                self.registry[caller] = record._replace(
                    agent_name=agent_name,
                    role=role,
                    active=arc4.Bool(True),
                    registered_at_round=arc4.UInt64(Global.round),
                    signed_manifest=signed_manifest,
                )
                self.total_registered.value = arc4.UInt64(self.total_registered.value.as_uint64() + 1)
        else:
            # new registration: create box entry and increment counter
            self.registry[caller] = AgentRecord(
                agent_name,
                role,
                arc4.UInt64(Global.round),
                arc4.Bool(True),
                signed_manifest,
                arc4.UInt64(0),
            )
            self.total_registered.value = arc4.UInt64(self.total_registered.value.as_uint64() + 1)

        # Emit an event for indexers to pick up registration changes
        arc4.emit("AgentRegistered", caller, agent_name, role)

    @arc4.abimethod(readonly=True)
    def is_registered(self, wallet: arc4.Address) -> arc4.Bool:
        exists = self.registry.maybe(wallet)[1]
        if not exists:
            return arc4.Bool(False)
        return self.registry[wallet].active

    @arc4.abimethod(readonly=True)
    def get_record(self, wallet: arc4.Address) -> AgentRecord:
        exists = self.registry.maybe(wallet)[1]
        assert exists, "No record found for this wallet"
        return self.registry[wallet]

    @arc4.abimethod(readonly=True)
    def get_config(self) -> arc4.Tuple[arc4.Address, arc4.UInt64, arc4.UInt64]:
        return arc4.Tuple((self.owner.value, self.total_registered.value, self.registry_version.value))

    @arc4.abimethod(allow_actions=["NoOp"])
    def deregister(self, wallet: arc4.Address) -> None:
        # Owner-only guard must run first to fail fast before any Box reads
        assert Txn.sender == self.owner.value.native, "Only the contract owner can deregister agents"

        target = wallet
        exists = self.registry.maybe(target)[1]
        assert exists, "Wallet not found in registry"

        record = self.registry[target].copy()
        self.registry[target] = record._replace(active=arc4.Bool(False))

        # decrement active count
        # Note: allow underflow to revert naturally if incorrect; deployment should ensure consistency
        self.total_registered.value = arc4.UInt64(self.total_registered.value.as_uint64() - 1)

        arc4.emit("AgentDeregistered", target, record.agent_name, record.role)

    @arc4.abimethod(allow_actions=["NoOp"])
    def increment_transaction_count(self, wallet: arc4.Address) -> None:
        # Deliberately no owner check: any registered contract (InsightListing, Escrow)
        # should be able to call this after a successful transaction to record activity.
        # This is intentional so external callers can update activity without requiring owner privileges.
        target = wallet
        exists = self.registry.maybe(target)[1]
        assert exists, "Wallet not registered"
        record = self.registry[target].copy()
        self.registry[target] = record._replace(total_transactions=arc4.UInt64(record.total_transactions.as_uint64() + 1))
