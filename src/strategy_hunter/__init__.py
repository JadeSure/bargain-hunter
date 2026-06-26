"""Strategy Hunter: daily collection of money-saving guide material.

A separate pipeline from ``bargain_hunter``: instead of alerting on individual
deals, it harvests free-text discussion (forum threads, Reddit posts) where
people share *combinations* of techniques to buy things cheaply, normalises it
into a corpus in the repo, and produces an LLM-ready digest. A local model
(run by the maintainer) then distils the digest into structured guides.

Stage 1 (this package) is fully automated on GitHub Actions. Stages 2 (LLM
extraction) and 3 (website rendering) consume the artifacts it writes.
"""
