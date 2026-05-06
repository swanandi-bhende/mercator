# CONTRACTS

## AgentRegistry

Schema for AgentRegistry contract data model (implementation checklist):

- Per-agent Box record (`AgentRecord`):
  - `agent_name`: string, max 64 characters
  - `role`: string, one of "buyer", "curator", or "seller"
  - `registered_at_round`: UInt64 (Algorand round number at registration)
  - `active`: Bool (True on registration, False on deregistration)
  - `signed_manifest`: string (base64-encoded signature produced by `algosdk.util.sign_bytes`)
  - `total_transactions`: UInt64 (increments each time the agent successfully interacts with InsightListing or Escrow)

- Global state (contract-level):
  - `owner`: arc4.Address (deployer wallet; only this address may call `deregister`)
  - `total_registered`: arc4.UInt64 (count of currently active registered agents)
  - `registry_version`: arc4.UInt64 (start at 1; increment on upgrades)

- Box map configuration:
  - Box map keyed by `arc4.Address` (wallet address)
  - `key_prefix` MUST be set and stable (use `b"reg_"`) — changing it later invalidates existing keys
  - Remember Box MBR: contract account must fund additional ALGO for each Box created; Box reads on non-existent keys must be guarded by `.exists` checks

Notes / constraints:
- `signed_manifest` stored as base64 string on-chain; on-chain verification must decode to raw 64-byte signature bytes before calling `op.ed25519verify_bare`.
- All Box reads must check `.exists` first because reading a non-existent Box raises an error.
- Box key encoding must be consistent across all callers — use `arc4.Address` typed keys and the same `key_prefix`.

This CONTRACTS.md entry is the authoritative data-model reference for `AgentRegistry` and will be used as the implementation checklist.
