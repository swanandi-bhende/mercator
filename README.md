# Mercator

Mercator is an Agentic Commerce marketplace on Algorand TestNet where human sellers list trading insights and AI agents discover, evaluate, and purchase them.

## Round 2 Status

- [x] InsightListing contract implemented in ARC4
- [x] Escrow contract implemented in ARC4
- [x] Reputation contract implemented in ARC4
- [x] Contracts compiled and TEAL generated
- [x] ARC specs and typed clients generated
- [x] Contracts deployed to TestNet
- [x] Phase 6 `/list` backend endpoint (validation -> IPFS pin -> on-chain ASA mint -> confirmation polling)
- [x] Phase 7 agent scaffolding (`backend/agent.py` with Gemini init + tool placeholders)
- [~] Phase 7 agent uses graceful fallback on Gemini free-tier limits/model availability (returns non-crashing offline response when API is unavailable)
- [~] Local end-to-end tests (no automated test suite yet)

## TestNet Identifiers

- `INSIGHT_LISTING_APP_ID=758022443`
- `ESCROW_APP_ID=758022447`
- `REPUTATION_APP_ID=758022459`
- `ESCROW_ADDRESS=262TFFBGXEAOOLQECJ4SNEVNQ2QFCCCVZ5K6ZT42ETIWBYDI63JLKSGHDI`
- `SAMPLE_ASA_ID=758023286`

## Environment Files

- `.env`: local working configuration
- `.env.testnet`: TestNet deployment configuration

## Manual TestNet Validation

- create_listing succeeded on InsightListing (`LISTING_ID` advanced from `1` to `2`)
- escrow release flow succeeded with grouped payment (`release_after_payment` returned `true`)
- reputation initialized and updated (`get_score` before `0`, after `update_score` -> `77`)
- IPFS helper test succeeded (`CID=QmSqR9oHZWbHDj1jgoyeKw7nuzYB6bDiLgySC7SxXjzwWF`) and CID-linked listing call confirmed on explorer
- Phase 6 live `/list` API call succeeded (`listing_id=3`, `asa_id=758048084`) with explorer tx: https://testnet.explorer.algorand.org/tx/WOZDMPMPHAVBAZ4RMCY4Y3MVC5V2HNTIROPMLUOVKRP5GEETAPKA
- explorer links:
	- https://testnet.algoexplorer.io/tx/3TSEMSSU4GHZJ4SQAR6D64BGRPZZOUXCAUHRTOCAZGV5GUX2B7KQ
	- https://testnet.algoexplorer.io/tx/VZDJCINLUM72I6TTGNMVO7XXOK4ZI3HSS2XH3EICQVUJME6A5EMQ
	- https://testnet.algoexplorer.io/tx/33M5NFCM376EVMHD4LBBL2L3HWNQ5Y7Y6BS3W6GWKTMRRKDEXTSQ
	- https://testnet.algoexplorer.io/tx/T3CZ7OQU63NWW3ZXWH5C5DZDH6BS4JFL5FLBYQWEUAHE2R5XPZZQ
	- https://testnet.algoexplorer.io/tx/VU4ANW2TFIDVKQXDYSJK7MNWANHEDFY5ZDLSWGGVPBMRURBFULTA
	- https://testnet.algoexplorer.io/tx/224C63VBDIBVPE5XMWR4ULJORGHQMIWN6FK6M2RW2H3ZC76LUESQ
	- https://testnet.algoexplorer.io/tx/EDJZHOLXVNCOCMFE3VBFJWRI6244E2GC775FWDZ5ZW7FSWHEJWLQ
