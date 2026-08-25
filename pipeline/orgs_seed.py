"""Curated organization seed rows and provider-name resolution.

Covers the frontier/API-era commercial labs and the systematically swept
Chinese labs. `PROVIDER_TO_ORG` maps vendor prefixes and provider slugs
observed in Tier-1 sources to stable org_ids; models from unmapped
providers are not loaded into core tables (they remain visible in
matched_models.csv and the review queue).
"""

from __future__ import annotations


def _org(org_id, canonical, short, aliases, country, org_type,
         epoch_name="", parent="", notes=""):
    return {
        "org_id": org_id,
        "canonical_name": canonical,
        "short_name": short,
        "aliases": aliases,
        "parent_org_id": parent,
        "country": country,
        "org_type": org_type,
        "is_active": "true",
        "epoch_org_name": epoch_name,
        "notes": notes,
    }


SEED_ORGS = [
    # --- US / EU / other commercial labs ---
    _org("openai", "OpenAI", "OpenAI", "OpenAI Inc|OpenAI LP", "US", "ai_lab", "OpenAI"),
    _org("anthropic", "Anthropic", "Anthropic", "Anthropic PBC", "US", "ai_lab", "Anthropic"),
    _org("google", "Google", "Google", "Alphabet|Google LLC", "US", "big_tech", "Google"),
    _org("google-deepmind", "Google DeepMind", "DeepMind",
         "DeepMind|Google Brain|Google AI", "GB", "ai_lab", "Google DeepMind", parent="google"),
    _org("meta", "Meta", "Meta", "Meta AI|Facebook|Facebook AI Research|FAIR|Meta Platforms",
         "US", "big_tech", "Meta AI"),
    _org("mistral", "Mistral AI", "Mistral", "Mistral|mistralai", "FR", "startup", "Mistral AI"),
    _org("xai", "xAI", "xAI", "x.ai|X AI", "US", "ai_lab", "xAI"),
    _org("cohere", "Cohere", "Cohere", "Cohere Inc|Cohere For AI|CohereLabs|C4AI",
         "CA", "startup", "Cohere"),
    _org("amazon", "Amazon", "Amazon", "AWS|Amazon Web Services|Amazon AGI|Nova",
         "US", "big_tech", "Amazon"),
    _org("microsoft", "Microsoft", "Microsoft", "Microsoft Research|MSR|Azure AI",
         "US", "big_tech", "Microsoft"),
    _org("nvidia", "NVIDIA", "NVIDIA", "Nvidia", "US", "big_tech", "NVIDIA"),
    _org("ai21", "AI21 Labs", "AI21", "AI21|Jamba", "IL", "startup", "AI21 Labs"),
    _org("ibm", "IBM", "IBM", "IBM Research|Granite", "US", "big_tech", "IBM"),
    _org("databricks", "Databricks", "Databricks", "MosaicML|Mosaic ML", "US", "startup", "Databricks"),
    _org("snowflake", "Snowflake", "Snowflake", "Snowflake AI Research", "US", "big_tech", "Snowflake"),
    _org("perplexity", "Perplexity AI", "Perplexity", "Perplexity", "US", "startup", "Perplexity"),
    _org("reka", "Reka AI", "Reka", "Reka", "US", "startup", "Reka AI"),
    _org("liquid-ai", "Liquid AI", "Liquid AI", "LiquidAI|LFM", "US", "startup", "Liquid AI"),
    _org("nous-research", "Nous Research", "Nous", "NousResearch|Hermes", "US", "startup", "Nous Research"),
    _org("allenai", "Allen Institute for AI", "AI2", "AI2|Ai2|OLMo|Tulu", "US", "nonprofit",
         "Allen Institute for AI"),
    _org("tii", "Technology Innovation Institute", "TII", "TII|Falcon|tiiuae", "AE",
         "government", "Technology Innovation Institute"),
    _org("huggingface", "Hugging Face", "Hugging Face", "HuggingFace|HuggingFaceTB|SmolLM",
         "US", "startup", "Hugging Face"),
    _org("eleutherai", "EleutherAI", "EleutherAI", "Eleuther AI", "US", "nonprofit", "EleutherAI"),
    _org("stability", "Stability AI", "Stability", "StabilityAI|StableLM", "GB", "startup",
         "Stability AI"),

    # Chinese labs swept on purpose.
    _org("alibaba", "Alibaba Cloud", "Alibaba",
         "Qwen Team|Tongyi Lab|Alibaba DAMO|Tongyi Qianwen|Alibaba Group|Qwen",
         "CN", "big_tech", "Alibaba"),
    _org("deepseek", "DeepSeek", "DeepSeek", "DeepSeek-AI|deepseek-ai|High-Flyer",
         "CN", "ai_lab", "DeepSeek"),
    _org("moonshot", "Moonshot AI", "Moonshot", "Kimi|moonshotai|Moonshot", "CN", "startup",
         "Moonshot AI"),
    _org("zhipu", "Zhipu AI", "Zhipu", "Z.ai|z-ai|ZhipuAI|THUDM|GLM|Zhipu",
         "CN", "startup", "Zhipu AI"),
    _org("baidu", "Baidu", "Baidu", "ERNIE|Baidu AI|Wenxin|PaddlePaddle", "CN", "big_tech", "Baidu"),
    _org("tencent", "Tencent", "Tencent", "Hunyuan|Tencent AI Lab", "CN", "big_tech", "Tencent"),
    _org("minimax", "MiniMax", "MiniMax", "MiniMaxAI|MiniMax AI", "CN", "startup", "MiniMax"),
    _org("bytedance", "ByteDance", "ByteDance", "Doubao|ByteDance Seed|Seed|Volcano Engine",
         "CN", "big_tech", "ByteDance"),
    _org("meituan", "Meituan", "Meituan", "LongCat|meituan-longcat", "CN", "big_tech", "Meituan"),
    _org("xiaomi", "Xiaomi", "Xiaomi", "MiMo|XiaomiMiMo", "CN", "big_tech", "Xiaomi"),
    _org("01ai", "01.AI", "01.AI", "01-ai|Yi|Zero One AI|LingYiWanWu", "CN", "startup", "01.AI"),
    _org("baichuan", "Baichuan AI", "Baichuan", "Baichuan Intelligence|baichuan-inc",
         "CN", "startup", "Baichuan"),
    _org("iflytek", "iFlytek", "iFlytek", "iFLYTEK|Spark|Xinghuo", "CN", "big_tech", "iFLYTEK"),
    _org("stepfun", "StepFun", "StepFun", "Step|stepfun-ai|Jieyue Xingchen", "CN", "startup",
         "StepFun"),
    _org("shanghai-ai-lab", "Shanghai AI Laboratory", "Shanghai AI Lab",
         "InternLM|Shanghai Artificial Intelligence Laboratory|OpenGVLab", "CN", "academic",
         "Shanghai AI Laboratory"),
    _org("openbmb", "OpenBMB", "OpenBMB", "MiniCPM|ModelBest|Mianbi", "CN", "academic", "OpenBMB"),
    _org("ieit", "IEIT Systems", "IEIT", "Inspur|Yuan|IEITYuan", "CN", "big_tech", "IEIT Systems"),
    _org("skywork", "Skywork", "Skywork", "Kunlun|Kunlun Tech|SkyworkAI", "CN", "big_tech",
         "Skywork"),
    _org("rwkv", "RWKV Foundation", "RWKV", "BlinkDL|RWKV Project", "", "nonprofit",
         "RWKV Foundation"),
    _org("ant-group", "Ant Group", "Ant Group", "Ling|Bailing|inclusionAI|Ant Ling",
         "CN", "big_tech", "Ant Group"),
]

# Vendor prefixes / provider slugs (lowercased) observed in Tier-1 sources.
PROVIDER_TO_ORG = {
    "openai": "openai", "azure-openai": "openai",
    "anthropic": "anthropic", "claude": "anthropic",
    "google": "google", "google-vertex": "google", "google-ai-studio": "google",
    "gemini": "google", "vertex": "google", "google-deepmind": "google-deepmind",
    "meta": "meta", "meta-llama": "meta", "facebook": "meta", "llama": "meta",
    "mistral": "mistral", "mistralai": "mistral",
    "xai": "xai", "x-ai": "xai", "grok": "xai",
    "cohere": "cohere", "coherelabs": "cohere", "cohereforai": "cohere",
    "amazon": "amazon", "amazon-bedrock": "amazon", "bedrock": "amazon", "nova": "amazon",
    "microsoft": "microsoft", "azure": "microsoft", "phi": "microsoft",
    "nvidia": "nvidia",
    "ai21": "ai21",
    "ibm": "ibm", "ibm-granite": "ibm", "watsonx": "ibm",
    "databricks": "databricks", "mosaicml": "databricks",
    "snowflake": "snowflake",
    "perplexity": "perplexity",
    "reka": "reka", "rekaai": "reka",
    "liquid": "liquid-ai", "liquidai": "liquid-ai",
    "nousresearch": "nous-research", "nous": "nous-research",
    "allenai": "allenai", "allen-ai": "allenai", "ai2": "allenai",
    "tii": "tii", "tiiuae": "tii",
    "huggingface": "huggingface", "huggingfaceh4": "huggingface", "huggingfacetb": "huggingface",
    "eleutherai": "eleutherai",
    "stabilityai": "stability", "stability-ai": "stability",
    # Chinese labs
    "alibaba": "alibaba", "alibaba-cn": "alibaba", "alibaba-intl": "alibaba",
    "qwen": "alibaba", "tongyi": "alibaba",
    "deepseek": "deepseek", "deepseek-ai": "deepseek",
    "moonshot": "moonshot", "moonshotai": "moonshot", "kimi": "moonshot",
    "zhipu": "zhipu", "zhipuai": "zhipu", "z-ai": "zhipu", "zai-org": "zhipu",
    "thudm": "zhipu", "glm": "zhipu",
    "baidu": "baidu", "ernie": "baidu", "wenxin": "baidu",
    "tencent": "tencent", "hunyuan": "tencent",
    "minimax": "minimax", "minimaxai": "minimax",
    "bytedance": "bytedance", "bytedance-seed": "bytedance", "doubao": "bytedance",
    "seed": "bytedance", "volcengine": "bytedance",
    "meituan": "meituan", "meituan-longcat": "meituan", "longcat": "meituan",
    "xiaomi": "xiaomi", "xiaomimimo": "xiaomi", "mimo": "xiaomi",
    "01-ai": "01ai", "01ai": "01ai", "yi": "01ai",
    "baichuan": "baichuan", "baichuan-inc": "baichuan",
    "iflytek": "iflytek", "iflytekspark": "iflytek", "spark": "iflytek",
    "stepfun": "stepfun", "stepfun-ai": "stepfun", "step": "stepfun",
    "internlm": "shanghai-ai-lab", "shanghai-ai-lab": "shanghai-ai-lab",
    "opengvlab": "shanghai-ai-lab",
    "openbmb": "openbmb", "minicpm": "openbmb",
    "ieit": "ieit", "ieityuan": "ieit", "inspur": "ieit", "yuan": "ieit",
    "skywork": "skywork", "skyworkai": "skywork", "kunlun": "skywork",
    "rwkv": "rwkv", "blinkdl": "rwkv",
    "ant": "ant-group", "ant-group": "ant-group", "inclusionai": "ant-group",
    "ling": "ant-group", "bailing": "ant-group",
    # Family-name tokens (used when no curated vendor namespace is present)
    "gpt": "openai", "claude": "anthropic", "gemma": "google",
    "mixtral": "mistral", "ministral": "mistral", "codestral": "mistral",
    "devstral": "mistral", "pixtral": "mistral", "voxtral": "mistral",
    "magistral": "mistral", "command": "cohere", "granite": "ibm",
    "olmo": "allenai", "tulu": "allenai", "falcon": "tii",
    "smollm": "huggingface", "jamba": "ai21", "dbrx": "databricks",
    "arctic": "snowflake", "sonar": "perplexity", "hermes": "nous-research",
    "qwq": "alibaba", "qvq": "alibaba", "nemotron": "nvidia",
}


def resolve_org(*candidates: str) -> str:
    """First org_id resolvable from the given provider/prefix strings."""
    for candidate in candidates:
        if candidate and candidate.lower() in PROVIDER_TO_ORG:
            return PROVIDER_TO_ORG[candidate.lower()]
    return ""
