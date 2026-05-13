#!/bin/bash
patterns='atc\.execute\(|simulate\(|release_for_subscriber|record_fee_collected|increment_transaction_count|create_listing_prepared|/list|upload_insight_to_ipfs|store_cid_in_listing|AtomicGroupResult'
grep -r -E "$patterns" backend/ contract/ --include="*.py" --include="*.go" --include="*.teal" --include="*.js" --include="*.ts" --exclude-dir=".venv" --exclude-dir="node_modules" | while read -r line; do
    file=$(echo "$line" | cut -d: -f1)
    match_str=$(echo "$line" | cut -d: -f2-)
    if [[ -z "$match_str" ]]; then continue; fi
    lineno=$(grep -nF "$match_str" "$file" | head -n 1 | cut -d: -f1)
    if [[ -z "$lineno" ]]; then continue; fi
    echo "--- $file : $lineno ---"
    sed -n "$((lineno-2)),$((lineno+2))p" "$file"
done
