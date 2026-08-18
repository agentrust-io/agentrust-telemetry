# Contributing

Contract changes require:

1. a documented semantic reason;
2. a schema update;
3. at least one valid fixture;
4. an invalid or boundary fixture that would catch a plausible defect;
5. conformance tests;
6. migration notes for wire-incompatible changes.

No attribute may be added without identifying the signal that carries it and how an instrumentor obtains it at runtime. New content-bearing fields require security and privacy review.
