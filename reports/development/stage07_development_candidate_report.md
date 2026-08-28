# Stage 7 DEVELOPMENT candidate report

Verdict: `STAGE_7_DEVELOPMENT_CANDIDATE_NOT_READY` pending the required offline owner qualitative review.

Contract: `stage07_libpostal_parsing_contract_v1`; profile:
`stage07_libpostal_parsing_profile_v1`. Exact input is
`stage06_candidate_lower`; context and hints are none; Stage 6 science is
unchanged. Published statuses are only `PARSED_NONEMPTY` and `PARSED_EMPTY`.
The ordered nested field is a non-null LargeList of non-null structs with
LargeString `label` and `value`; ordering and duplicates are preserved. Any
child crash is retried once exactly and aborts publication if unresolved.

Implementation SHA: `4a5f7495cf55121198981eae92ac3db8c73ad1fa`.
Final evidence SHA: `29d5afe2233a5a0712b2f1bab4cefbbd79d4f684`.
Base main: `76435eb7ca5cd9a47a2a77fb36278568ba3bfc29`.

Authoritative job `1760221` completed in 00:09:56 with 180 GiB, one
synchronous child, no internal address-space cap, and no candidate timeout.
It produced exactly 51,779 rows in 13 shards: 51,774 `PARSED_NONEMPTY` and 5
`PARSED_EMPTY`; 0 crashes, 0 retries, 0 unhandled failures, and 6,106,088
components. Maximum component count was 881,338; maximum nested Arrow row size
was 48,760,156 bytes; output bytes were 92,546,225.

Independent validation job `1760226` passed all 51,779 rows, exact Stage 6
preservation, fingerprints, and complete 69,747-occurrence map-back (34,822
STANDARD; 34,925 NATIVE).

Review job `1760494` passed fixed-500 verification: 500 source rows, 937
occurrences, 613 unique candidates, 324 duplicate occurrences, 0 mismatches,
and 0 cross-wires. It selected 120 candidates with fingerprint
`1507900b27e4503eb33836c8465217092e9ffb8de2f1b6ef05026690be11a844`.

The owner-only qualitative surface remains `AWAITING_OFFLINE_OWNER_REVIEW`, so
no qualitative classification totals are claimed. The first diagnostic’s 48
GiB ceiling and 4/23 crashes remain immutable history; job `1760182` showed
23/23 success under 180 GiB. HOLDOUT, production Stages 2–7, Stage 8, and
geocoding were not used.
