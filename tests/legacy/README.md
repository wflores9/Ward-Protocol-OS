# Archived adapter tests

`adapter_tests.py.txt` preserves the historical multi-chain adapter tests formerly embedded in `tests/test_ward.py`. The public repository has never shipped `ward.adapters`; these tests describe unavailable exploratory implementations, not supported public functionality. They are explicitly archived, not skipped or counted as passing. No private implementation has been imported to make this suite pass.

All XRPL core and adversarial tests remain active in `tests/test_ward.py`. Restore adapter tests to normal discovery only together with a reviewed, publicly supported implementation and its dependencies.
