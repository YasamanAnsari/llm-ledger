# Methodology

## Who gets in

A model is in if it is a **named trained checkpoint from a lab**.
Quant packs (GGUF, GPTQ, AWQ), LoRA adapters, and community merges stay
out unless the thing is famous on its own.

If we keep a derivative, we mark `is_derivative=true` and point at
`base_model_id`.

We care most about LLMs, VLMs, and multimodal models, in this order:

1. Frontier / API labs (OpenAI, Anthropic, Google, Meta, Mistral, xAI,
   Cohere, Amazon)
2. Chinese labs we sweep on purpose: Qwen, DeepSeek, Moonshot, Zhipu,
   Baidu, Tencent, MiniMax, ByteDance, Meituan, Xiaomi, 01.AI, Baichuan,
   iFlytek, StepFun, Shanghai AI Lab, OpenBMB, IEIT, Skywork, RWKV,
   Ant Group
3. Other open-weight models (Hugging Face; ModelScope if we have a
   login)
4. Older models (GPT-1/2/3, BERT era), usually as leads first

## How we date a row

1. Use the primary source in [sources.md](sources.md).
2. If the page looks undated or edited later, check Wayback.
3. Save the URL we actually opened.
4. Papers: arXiv **v1** date, not a later revision.
5. Weights: prefer Hugging Face `createdAt`. If the blog differs by
   more than two days, keep the Hub date and put the blog date in
   `announced` or `notes`.

If the source only gives a month, we store the first of that month and
`precision=month`. We do not invent a day.

## How sure we are

- `verified`: we opened a primary source (or a Hub / API timestamp).
  `verified_by` and `verified_date` are required.
  `verified_by=llm-ledger` means a project-level check; any other value
  is a named person.
- `inferred`: catalog or secondary source only.
- `disputed`: sources disagree. Best-evidenced date stays in `date`;
  every other value and URL goes in `notes`.

See also `data/generated/disagreement_report.md`.

## How we update

The file is updated regularly.

Weekly: `make pull`, then `make match reconcile`. Look at
`data/staging/review_queue.csv`. Then `make build validate`.

Monthly: check Chinese collections and deprecation pages, rebuild,
append `CHANGELOG.md`, tag `vYYYY.MM`.

Fixes edit the row. `record_created` / `record_updated` and the
changelog keep history.

## Name matching

`pipeline/match.py` cleans names, then exact-matches, then fuzzy
matches. Score >= 97 joins. 92-97 waits for a person. Below 92 is no
match. We keep that bar high on purpose.

## Limits

- Hugging Face `createdAt` before March 2022 is a fake backfill. Do
  not treat 2022-03-02 as a weights date.
- No ModelScope token: we use Hugging Face instead of inventing rows.
- `region=global` unless a source says otherwise.
