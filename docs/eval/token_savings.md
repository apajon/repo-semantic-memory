# Token-savings metrics

RSM reports deterministic approximate token-savings metrics for benchmark comparisons.

## Approximation

Token estimates are directional and use:

```text
estimated_tokens = chars / 4
```

They are not tokenizer-accurate and should not be presented as exact model-token accounting.

## Interpretation rule

A smaller context pack is useful only when relevant coverage is preserved. Discuss token savings together with gold file and symbol coverage from `rsm eval compare`.

## Safe wording

Use wording like:

- “On the current internal benchmark, this run reduced estimated context size while preserving gold coverage.”
- “Token estimates are approximate and directional.”

Avoid broad claims that RSM is generally superior or that smaller output alone means higher quality.
