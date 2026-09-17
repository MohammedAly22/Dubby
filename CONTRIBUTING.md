# Contributing to Dubby 🐨

Thanks for helping! Dubby grows through contributions of **new models**, **new languages and dialects**, bug fixes and UI polish. This guide shows the exact files to touch for each. Most additions are one Python class plus a registry line, and they show up in the web UI on their own.

- [Development setup](#-development-setup)
- [How Dubby is organized](#-how-dubby-is-organized)
- [Recipe 1 — Add a model (engine)](#-recipe-1--add-a-model-engine)
- [Recipe 2 — Add an engine family (its own venv)](#-recipe-2--add-an-engine-family-its-own-venv)
- [Recipe 3 — Add a language or dialect](#-recipe-3--add-a-language-or-dialect)
- [Making things visible in the UI](#-making-things-visible-in-the-ui)
- [Errors and GPU memory](#-errors-and-gpu-memory)
- [Testing and pull requests](#-testing-and-pull-requests)

---

## 🛠️ Development setup

```bash
git clone https://github.com/MohammedAly22/Dubby.git
cd Dubby
./scripts/setup.sh            # Windows: .\scripts\setup.ps1   ·  add --cpu without an NVIDIA GPU
conda activate dubby

dubby dev                     # backend + Vite UI with hot reload → http://localhost:5173
dubby doctor                  # which engines are importable in each interpreter
```

`dubby dev` reloads the UI on save. Restart it after Python changes: worker processes keep their modules loaded.

---

## 🗺️ How Dubby is organized

```
dubby/
├── languages.py          # every spoken / dub language and its codes for each model
├── recommend.py          # ranked engines per stage and language pair
├── hardware.py           # "does this engine fit the GPU?"
├── errors.py             # raw exceptions → messages with a next step
├── engines/
│   ├── base.py           # Engine, EngineInfo, ParamSpec, quantization helpers
│   ├── registry.py       # engine id → class
│   ├── asr/ translation/ tts/ langid/ separation/
├── workers/main.py       # the process that loads models and runs tasks
├── core/studio.py        # projects and stages (the only writer of project.json)
├── core/jobs.py          # GPU job queue, one worker process per engine family
└── server/app.py         # FastAPI + websocket
ui/src/                   # React UI (components/, panels/, store.ts)
```

A stage runs like this:

```
UI ──REST──▶ Studio ──Job──▶ JobManager ──JSON over stdin──▶ worker (family venv)
 ▲                                                               │ loads your Engine
 └──── websocket ◀── EventBus ◀── progress / results / downloads ┘
```

The studio process **never imports torch or a model**. It only reads each engine's `EngineInfo`. That's why engine modules must import heavy packages *inside methods*.

---

## 🧩 Recipe 1 — Add a model (engine)

Example: an Egyptian Arabic → English Marian translator.

### 1. Write the engine

`dubby/engines/translation/marian_ar_en.py`

```python
from __future__ import annotations

from typing import Any, Dict, Iterator, Optional, Sequence, Tuple

from dubby.engines.asr.common import batched
from dubby.engines.base import EngineInfo, ParamSpec, TranslationEngine, option
from dubby.workers.protocol import TaskContext


class MarianArEnTranslator(TranslationEngine):
    info = EngineInfo(
        id="marian-ar-en",                     # stable id: saved in projects, used by the CLI
        kind="translation",                    # asr | translation | tts | separation
        name="Helsinki-NLP Marian ar→en",
        family="core",                         # which venv runs it (see Recipe 2)
        description="Small, fast Arabic→English translator.",
        source_languages=["ar"],               # codes from dubby/languages.py
        targets=["en"],
        requires=["transformers", "sentencepiece"],   # import names checked by `dubby doctor`
        install="pip install transformers sentencepiece",
        badges=["fast", "small"],
        links={"model": "https://huggingface.co/Helsinki-NLP/opus-mt-tc-big-ar-en"},
        vram_gb=1.5,                           # approximate GPU memory at the default params
        params=[
            ParamSpec("num_beams", "Beams", "number", 4, min=1, max=8, step=1),
            ParamSpec("batch_size", "Batch size", "number", 16, min=1, max=64, step=1,
                      help="Segments translated together"),
        ],
    )
    load_params = ()  # params whose change needs a model reload, e.g. ("model",)

    def load(self, ctx: TaskContext) -> None:
        from transformers import MarianMTModel, MarianTokenizer   # heavy imports live here

        name = "Helsinki-NLP/opus-mt-tc-big-ar-en"
        ctx.progress(0.02, f"Loading {name}…")                   # shows in the UI
        self.tok = MarianTokenizer.from_pretrained(name)
        self.model = MarianMTModel.from_pretrained(name).to(self.device).eval()

    def translate(self, items: Sequence[Dict[str, Any]], source: str, target: str,
                  ctx: TaskContext) -> Iterator[Tuple[str, str]]:
        import torch

        for batch in batched(list(items), int(self.params["batch_size"])):
            enc = self.tok([it["text"] for it in batch], return_tensors="pt",
                           padding=True, truncation=True).to(self.device)
            with torch.inference_mode():
                out = self.model.generate(**enc, num_beams=int(self.params["num_beams"]))
            for it, seq in zip(batch, out):
                # yield as soon as a line is ready: the UI streams it in
                yield it["id"], self.tok.decode(seq, skip_special_tokens=True)
```

What each kind has to implement:

| Kind | Base class | Method | Returns |
| :-- | :-- | :-- | :-- |
| ASR | `ASREngine` | `transcribe(audio_path, language, ctx)` | `[{start, end, text, words: [{text, start, end, score}]}]`. Call `ctx.result("asr_partial", {"segments": [...]})` for live text |
| Translation | `TranslationEngine` | `translate(items, source, target, ctx)` | yields `(segment_id, text)` |
| TTS | `TTSEngine` | `synthesize(items, target, ctx)` | writes `item.out_path` (wav) and yields `(item, duration_seconds)`; `item.duration` is the slot to fit |
| Separation | `SeparationEngine` | `separate(audio, vocals_out, background_out, ctx)` | writes both files |

`Engine.unload()` already frees attributes and GPU cache. Override it only when you need extra cleanup.

### 2. Register it

`dubby/engines/registry.py`

```python
ENGINES = {
    ...
    "marian-ar-en": "dubby.engines.translation.marian_ar_en:MarianArEnTranslator",
}
```

### 3. Recommend it (optional)

`dubby/recommend.py`: add it where it ranks. The first compatible entry becomes the default for that language pair, and params are pre-filled when people pick it.

```python
elif source == "ar" and target == "en":
    recs += [
        R("arzen-llm", "..."),
        R("marian-ar-en", "Tiny and fast; good for MSA-heavy speech", num_beams=4),
    ]
```

### 4. Try it

```bash
dubby doctor                                   # shows "ready" or the pip command
dubby dub video.mp4 --source ar --target en --translation marian-ar-en --translation-param num_beams=2
```

Then open the studio. Your engine is listed in the Translate step with its parameters.

### Parameter types

`ParamSpec(key, label, type, default, options=None, min=None, max=None, step=None, help="")`

| `type` | UI control | Notes |
| :-- | :-- | :-- |
| `select` | animated dropdown | `options=[option("value", "Label"), ...]`; options that don't fit the GPU are greyed out automatically |
| `number` | number input | use `min` / `max` / `step` |
| `bool` | switch | `help` is shown beside it |
| `text` | single-line input | e.g. a custom model id |
| `textarea` | prompt editor | reset-to-default button; `{placeholders}` listed in `help` become insert chips; implement `preview()` for a live preview |

For a big model, add the shared quantization parameter:

```python
from dubby.engines.base import quantization_param, resolve_quantization

SIZES = {"none": 18.0, "8bit": 10.0, "4bit": 6.5}   # GB for 16-bit / 8-bit / 4-bit

params=[quantization_param(), ...]

@classmethod
def required_vram_gb(cls, params, vram_gb=None):
    return SIZES[resolve_quantization(params.get("quantization", "auto"), SIZES, vram_gb)]

@classmethod
def needs_cuda(cls, params, vram_gb=None):
    return resolve_quantization(params.get("quantization", "auto"), SIZES, vram_gb) != "none"

def load(self, ctx):
    mode = resolve_quantization(self.params.get("quantization", "auto"), SIZES, self.gpu_vram_gb())
    kwargs = {"dtype": self.torch_dtype(), "device_map": "cuda:0" if self.is_cuda else "cpu"}
    if mode != "none":
        kwargs["quantization_config"] = self.quantization_config(mode)
    self.model = AutoModelForCausalLM.from_pretrained(MODEL_ID, **kwargs).eval()
```

`auto` loads 16-bit when it fits and 4-bit otherwise. See `engines/translation/hunyuan.py` and `arzen.py` for complete examples.

---

## 🐍 Recipe 2 — Add an engine family (its own venv)

Create a family when a model needs dependencies that conflict with `core` (e.g. an old `transformers`). Each family is a separate interpreter with its own long-lived worker.

1. **Name it** in `dubby/config.py`:

   ```python
   ENGINE_FAMILIES = ("core", "qwen", "nemo", "indic", "mylab")
   ```

2. **Declare its dependencies** as an extra in `pyproject.toml`:

   ```toml
   mylab = ["transformers>=4.40,<4.45", "my-model-package>=1.2"]
   ```

3. **Add an environment file**, `environment-mylab.yml` (copy `environment-indic.yml`):

   ```yaml
   name: dubby-mylab
   channels: [conda-forge]
   dependencies:
     - python=3.11
     - pip
     - ffmpeg
     - pip:
         - --extra-index-url https://download.pytorch.org/whl/cu128
         - torch==2.8.0
         - torchaudio==2.8.0
         - -e .[mylab]
   ```

4. **Wire the setup scripts:** add a `--mylab` flag in `scripts/setup.sh` and `scripts/setup.ps1` that calls `create_env environment-mylab.yml dubby-mylab`.

5. **Colab:** in `notebooks/Dubby_Colab.ipynb`, cell 5 (optional families), add a checkbox and `family("mylab", "mylab")`. It installs into `/content/envs/dubby-mylab`.

6. **Set `family="mylab"`** in your engines' `EngineInfo`.

Dubby finds the interpreter automatically, in this order: *Settings → Engine family interpreters*, then the `DUBBY_PYTHON_MYLAB` environment variable, then a conda env named `dubby-mylab`, then `/content/envs/dubby-mylab` on Colab. Check it with:

```bash
conda env create -f environment-mylab.yml
dubby doctor          # the new family appears with its python, torch and engines
```

With *exclusive GPU* on (the default), starting a job in one family stops the others, so they never compete for VRAM.

---

## 🌍 Recipe 3 — Add a language or dialect

Example: **Levantine Arabic** as a dub language.

### 1. Describe it: `dubby/languages.py`

```python
Language(
    "apc",                # code used everywhere in Dubby
    "Levantine Arabic",   # English name
    "شامي",               # native name
    "sy",                 # flag key (UI, step 4)
    "ar",                 # ISO 639-1 for ASR engines and aligners
    "apc",                # OmniVoice language id (check the model's language list)
    "apc_Arab",           # NLLB-200 / FLORES code
    "Arabic",             # language name for Qwen3-ASR / Qwen3-TTS
    "Levantine Arabic",   # name used in translation prompts
    "黎凡特阿拉伯语",       # Chinese name (Hunyuan-MT's Chinese template)
    rtl=True,
    source=False,         # dub-only; set True if ASR engines can transcribe it
),
```

`spaced=False` is for scripts written without spaces (Chinese, Japanese): chunking and word joins switch to per-character.

### 2. Let engines accept it

Add the code to `source_languages` / `targets` in the engines that support it. Engines built from `L.SOURCE_CODES` / `L.TARGET_CODES` (NLLB, the LLM translator) pick it up automatically.

### 3. Rank engines for it: `dubby/recommend.py`

```python
TTS["apc"] = [
    R("lahgtna-omnivoice", "OmniVoice fine-tuned on 13 Arabic dialects, including Levantine"),
    R("omnivoice", "Base OmniVoice"),
]
```

For ASR (spoken languages) add an `ASR["apc"]` list. For translation, add a branch in `_translation()`. If it's a dialect of an existing language, also check `same_language()` and `is_arabic()` in `languages.py`.

Give the LLM translator a speaking style in `dubby/engines/translation/llm.py`:

```python
STYLE["apc"] = "Write natural spoken Levantine Arabic (شامي) as a Damascus voice actor would say it, in Arabic script."
```

### 4. Show it in the UI: `ui/src/components/Flags.tsx`

```tsx
import syriaFlag from '../../../assets/Syria.png'               // add the image to /assets

export type FlagCode = 'eg' | 'sa' | ... | 'sy'
const FLAGS = { ..., sy: { src: syriaFlag, name: 'Syria', position: 'center' } }

export const LANGS = {
  ...,
  apc: { flag: 'sy', name: 'Levantine Arabic', native: 'شامي', short: 'LEV', rtl: true, arabic: true, hint: 'Syrian, Lebanese, Palestinian, Jordanian' },
}

export const TARGET_CODES = [..., 'apc'] as const             // SOURCE_CODES for spoken languages
```

`arabic: true` enables the tashkeel bar in the voice step.

### 5. Teach the text normalizer the language: `dubby/text/`

Before TTS, every line goes through a per-language normalizer (numbers, money, dates, times, units, emails, abbreviations…). Add a `Rules` subclass. The shared pipeline in `dubby/text/common.py` does the pattern matching, so you only supply the language's words:

```python
# dubby/text/apc.py
from dubby.text.common import Money, Noun, Rules
from dubby.text.arb import MSARules   # a dialect can start from a close language


class LevantineRules(MSARules):
    code = "apc"
    words = {**MSARules.words, "percent": "بالمية"}

    def cardinal(self, n: int) -> str:
        ...  # spoken number words

    def time(self, hour, minute, period):
        ...  # "الساعة عشرة ونص"
```

Register it in `dubby/text/__init__.py` (`_RULES["apc"] = ("dubby.text.apc", "LevantineRules")`) and add cases to `tests/test_text_normalization.py`:

```bash
pip install -e ".[dev]" && python -m pytest tests/test_text_normalization.py -q
```

Useful hooks: `ordinal()`, `count()` (number + noun agreement), `money()`, `date()`, `is_year()`, `cardinal_before()` (gender from the next word) and `before()` / `after()` for extra regex passes. Languages without rules still get whitespace cleanup.

### 6. Check

```bash
dubby languages       # the new row, with recommended engines per stage
```

---

## 🖥️ Making things visible in the UI

Most additions need **no UI code**:

| You add | The UI shows it because… |
| :-- | :-- |
| an engine | `GET /api/engines` lists every registered engine; cards, "ready / not installed" and install commands come from `EngineInfo` and `dubby doctor` |
| parameters | `ParamSpec` types map to controls (table above) |
| a VRAM estimate | cards and options that can't fit the detected GPU are disabled with an explanation, and "Apply fix" switches to one that fits |
| a recommendation | "★ Top pick", "Recommended #2" and *Use recommended* come from `recommend.py` |
| progress / downloads | `ctx.progress()` drives the stage bar; Hugging Face downloads become progress bars in the logs automatically |
| caption styling | the player overlay (`ui/src/captionStyle.ts`) and the export renderer (`STYLE` in `dubby/pipeline/captions.py`) share one spec in CSS px for a 760 px wide video. Change both together so exports keep matching the preview |
| requests | every job and model load appears in **Logs → Requests** automatically. Wrap each API call, batch or pass inside a job with `with track("tts", f"My TTS · batch {i}", items=n):` (`from dubby.workers.protocol import track`) so it gets its own row, status and duration. Studio-side work uses `studio.track(...)` |

Only **languages** need a UI edit (`Flags.tsx`, Recipe 3). After changing the UI, `dubby build-ui` refreshes the bundle that `dubby serve` uses, and `dubby dev` does it live.

---

## 🛡️ Errors and GPU memory

- **Raise, don't print.** Let exceptions propagate from `load()` / `translate()` / … The worker frees GPU memory, explains the error with `dubby/errors.py` and marks the stage failed with a hint.
- **Teach Dubby a new failure.** If users hit an error that deserves a better message, add a pattern to `explain()` in `dubby/errors.py`, returning a message and a *next step*.
- **Keep VRAM estimates honest** (weights + working memory). The worker refuses to load a model whose `required_vram_gb` exceeds the GPU. That protects everyone from half-loaded models that leave memory behind.
- **Mark GPU-only configurations** with `needs_cuda()` (bitsandbytes checkpoints, CUDA kernels) so CPU users get a clear message instead of a crash.

---

## ✅ Testing and pull requests

Before opening a PR:

- [ ] `python -m compileall -q dubby` passes, and `dubby doctor` lists your engine
- [ ] A real run works: `dubby dub <short clip> --translation your-engine` (or the studio)
- [ ] UI changes: `cd ui && npx tsc --noEmit -p . && npm run build`
- [ ] Heavy imports are inside methods (`python -c "import dubby.engines.registry as r; [r.get_info(e) for e in r.ENGINES]"` works without torch)
- [ ] You added links to the model card and noted its **license** in `description` or `links`
- [ ] README: add a row to the engines or languages table

Pull request tips:

- One model or language per PR is easiest to review.
- Include a sample: a short before/after (transcript, translation or audio) helps a lot.
- Say which GPU you tested on and the VRAM it used.
- Keep the UI black & white. Accent colors are only for focus rings, progress and subtitles.

Questions or ideas? Open an issue. Thank you for making Dubby speak more languages 🐨💚
