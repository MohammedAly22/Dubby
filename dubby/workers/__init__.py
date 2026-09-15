"""Model workers.

Every model stage runs in a long-lived worker subprocess, one per *engine family*
(``core``, ``qwen``, ``nemo``). Families may use different Python interpreters,
which keeps incompatible stacks (e.g. transformers 4.x vs 5.x) apart, frees GPU
memory when a family is stopped and makes cancellation a simple process kill.
"""
