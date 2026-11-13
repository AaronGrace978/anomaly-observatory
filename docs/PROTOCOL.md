# Controlled experiment workflow

1. Write a specific prediction: measured quantity, units, time window, location, expected magnitude and active versus control comparison.
2. Choose channel bandwidths and calibrate with known signals before data collection. Establish baseline stability, offsets, noise and timing uncertainty.
3. Record an independent baseline and create the protocol before the trial. Archive its hash in an independently timestamped registry. Three times baseline RMS is only a demonstration screening threshold; a scientific study needs a justified statistical rule and power analysis.
4. Generate a balanced randomized plan with active, sham and empty conditions. The private operator key stays with an independent custodian; do not commit it or give it to analysts or the model. Public plans include pseudonymous run IDs and alternating observation pods. Pod assignment is deterministic alternating, not fully counterbalanced against each randomized condition.
5. Collect all runs with comparable operators and conditions. Swap pod locations as indicated. Preserve native-rate raw recordings, dropouts, acquisition manifests and environmental activity logs. Operators know the condition; analysts should not.
6. Analyze each coded recording against the archived protocol, then freeze reports before the custodian reveals labels. This release generates a blind key but does not enforce custody, lock files or automate unblinding.
7. Investigate flags using dummy inputs, calibration sources, wiring checks, independent references and repeated runs. The paired RMS statistic is symmetric: pod swapping probes artifacts but does not estimate a directed treatment effect.
8. Replicate on independent equipment and sites before interpreting a reproducible unexplained physical signal. A null result constrains only the stated hypothesis and sensitivity. An unexplained reading supplies no specific evidence of spirits or deceased individuals.

AI explanations may suggest follow-up checks. They are not evidence, calibration, preregistration, or an independent replication.
