# Mercator Atomic Group Audit

Date: 2026-05-13
Scope: Python backend transaction assembly plus ARC-4 contract methods under backend and contract modules.

## Sequence 1: x402 payment + escrow release in purchase flow
Current behavior:
- payment transfer and escrow release can be assembled in separate steps.
- a legacy post-payment path can still run escrow as a follow-up call.
Failure mode:
- payment confirms, follow-up release fails or is dropped, leaving settlement inconsistent.
Fix approach:
- build one outer group with AtomicTransactionComposer:
- index 0: AssetTransfer payment
- index 1: Escrow.release_after_payment ABI call
- route execution through execute_with_simulation()
Fee implications:
- escrow call fee must fund inner activity; using 6000 microALGO covers 2 inner transfers + 3 app calls + outer call baseline.

## Sequence 2: Escrow.release_after_payment inner transfers + app calls
Current behavior:
- seller payout and treasury fee transfers are grouped.
- FeeConfig/Reputation/mark sold updates occur in the same method context.
Failure mode:
- if transfer grouping is not explicit, maintainers can accidentally split inner submit semantics.
Fix approach:
- explicit inner group with itxn.begin(), itxn.next(), itxn.submit() for both USDC transfers.
- retain FeeConfig.record_fee_collected + Reputation.record_purchase + InsightListing.mark_sold as ABI calls in the same outer method.
- enforce conservation invariant: seller_payout + fee == amount.
Fee implications:
- required floor: 1 outer + 2 inner transfers + 3 app calls = 6000 microALGO.

## Sequence 3: SubscriptionManager.subscribe payment + state write
Current behavior:
- contract reads payment at gtxn index 0 and writes subscription state in method call at index 1.
Failure mode:
- if a developer submits call without grouped payment, contract assumptions break.
Fix approach:
- keep current contract atomicity and enforce explicit payment conservation check.
- add backend helper that always assembles payment (index 0) + subscribe() call (index 1) in one ATC group.
Fee implications:
- group baseline 2000 microALGO (one payment tx + one method call).

## Sequence 4: IPFS pin + on-chain listing creation
Current behavior:
- IPFS upload is off-chain and can succeed before chain write.
Failure mode:
- simulation or execution failure leaves orphaned pinned CID.
Fix approach:
- two-phase create_listing_prepared flow:
- pin CID
- simulate listing transaction
- unpin on simulation failure
- execute only after simulation success
- persist attempt lifecycle in listing_preparation_log.
Fee implications:
- listing creation must include outer fee plus inner ASA config cost budget.

## Sequence 5: Subscriber release path ordering
Current behavior:
- subscriber entitlement check and downstream updates are in one escrow method.
Failure mode:
- wrong call ordering can create hard-to-debug partial semantics if future edits introduce early state writes.
Fix approach:
- enforce and document order:
- verify entitlement
- record reputation
- mark sold/access state
- optional registry count increment
- assert post-condition with _verify_subscription_access_granted().
Fee implications:
- single outer app call; no standalone extra transaction should be emitted for reputation.

## Sequence 6: Seller upload flow in API
Current behavior:
- /list endpoint performs IPFS + chain operations in sequence.
Failure mode:
- execution error after pin creates orphan content.
Fix approach:
- route /list through create_listing_prepared() with simulation gate and cleanup.
Fee implications:
- on-chain fee unaffected; operational cost reduced by cleanup.

## Sequence 7: FeeConfig.record_fee_collected call timing
Current behavior:
- called from escrow release method body.
Failure mode:
- if detached to a separate tx, fee accounting can diverge from settlement.
Fix approach:
- keep call inside release_after_payment method execution context.
Fee implications:
- include one app-call fee unit in escrow fee estimate.

## Sequence 8: AgentRegistry.increment_transaction_count call timing
Current behavior:
- invoked from contract methods as ABI call.
Failure mode:
- if emitted as fire-and-forget tx, counters can drift from real business events.
Fix approach:
- keep invocation in transaction context of parent method only.
Fee implications:
- include one app-call fee unit where invoked.

## Global controls applied
- Shared execute_with_simulation wrapper is the preferred ATC execution path.
- validate_atomic_group enforces size, network hash consistency, fee sufficiency, signer alignment, and duplicate-submission guard.
- estimate_group_fee is standardized as (outer_tx_count + inner_tx_count) * 1000.
