"""Engine A: Qaari — Urdu Nastaliq OCR (LoRA adapter on Qwen2-VL-2B-Instruct).

The public adapter's config names a bitsandbytes-4bit base (CUDA-only). We
load the same architecture in full precision instead so the engine runs on
CPU (dev/eval) and GPU (Space/Colab) alike, then merge the LoRA weights once.
Lazy: nothing heavy is imported or downloaded until first read().

Adapter caveat: the adapter was saved against unsloth's module layout, which
differs from current transformers (language layers under ``language_model``,
vision tower under ``model.model``, keys without the adapter name). PEFT's
own loader silently skips every mismatched key, so we remap the state dict
ourselves and fail loudly unless every adapter slot is filled.
"""
from __future__ import annotations

import re
import warnings

from PIL import Image

from ..schema import OCRResult
from .base import OCREngine

BASE_MODEL = "Qwen/Qwen2-VL-2B-Instruct"
ADAPTER = "oddadmix/Qaari-0.1-Urdu-OCR-VL-2B-Instruct"
# Verbatim prompt from the Qaari model card (its WER numbers were measured with it).
PROMPT = (
    "Below is the image of one page of a document, as well as some raw textual "
    "content that was previously extracted for it. Just return the plain text "
    "representation of this document as if you were reading it naturally. "
    "Do not hallucinate."
)


def remap_adapter_key(key: str) -> str:
    """Adapter layout (unsloth) -> current transformers + PEFT layout."""
    key = key.replace(
        "base_model.model.model.layers.",
        "base_model.model.model.language_model.layers.",
    )
    key = key.replace(
        "base_model.model.visual.",
        "base_model.model.model.visual.",
    )
    return re.sub(r"\.lora_([AB])\.weight$", r".lora_\1.default.weight", key)


class QaariEngine(OCREngine):
    name = "qaari"

    def __init__(self, max_new_tokens: int = 2000) -> None:
        self.max_new_tokens = max_new_tokens
        self._model = None
        self._processor = None
        self._device = None

    @property
    def available(self) -> bool:
        try:  # heavy deps present?
            import transformers  # noqa: F401
            import peft  # noqa: F401
        except ImportError:
            return False
        return True

    def _load(self) -> None:
        if self._model is not None:
            return
        import torch
        from huggingface_hub import hf_hub_download
        from peft import PeftModel
        from safetensors.torch import load_file
        from transformers import AutoProcessor, Qwen2VLForConditionalGeneration

        device = "cuda" if torch.cuda.is_available() else "cpu"
        # T4 (Turing) has no bf16 — fp16 on GPU, fp32 on CPU.
        dtype = torch.float16 if device == "cuda" else torch.float32
        base = Qwen2VLForConditionalGeneration.from_pretrained(BASE_MODEL, torch_dtype=dtype)
        with warnings.catch_warnings():
            # PEFT's own load reports every key below as missing; we load them next.
            warnings.filterwarnings("ignore", message=".*missing adapter keys.*")
            model = PeftModel.from_pretrained(base, ADAPTER)

        raw = load_file(hf_hub_download(ADAPTER, "adapter_model.safetensors"))
        variants = {
            "as-saved": raw,
            "remapped": {remap_adapter_key(k): v for k, v in raw.items()},
        }
        model_keys = set(model.state_dict())
        layout, tensors = max(
            variants.items(), key=lambda kv: len(set(kv[1]) & model_keys)
        )
        unfilled = sorted(k for k in model_keys if ".lora_" in k and k not in tensors)
        stray = sorted(k for k in tensors if k not in model_keys)
        if unfilled or stray:
            raise RuntimeError(
                f"Qaari adapter does not fit this transformers/peft version "
                f"(layout={layout!r}): {len(unfilled)} adapter slots unfilled, "
                f"{len(stray)} stray keys. unfilled[:3]={unfilled[:3]} "
                f"stray[:3]={stray[:3]}"
            )
        model.load_state_dict(tensors, strict=False)
        model = model.merge_and_unload()
        model.eval().to(device)
        processor = AutoProcessor.from_pretrained(ADAPTER)
        self._model, self._processor, self._device = model, processor, device

    def warmup(self) -> "QaariEngine":
        self._load()
        return self

    def read(self, image: Image.Image) -> OCRResult:
        import torch
        from qwen_vl_utils import process_vision_info

        if self._model is None:
            self._load()
        assert self._model is not None and self._processor is not None

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image.convert("RGB")},
                    {"type": "text", "text": PROMPT},
                ],
            }
        ]
        text = self._processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = self._processor(
            text=[text],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        ).to(self._device)
        with torch.inference_mode():
            # Official usage is model.generate(**inputs, max_new_tokens=2000);
            # repetition_penalty=1.05 is our one deliberate deviation — greedy
            # decoding of full-page table invoices otherwise degenerates into
            # exact-repetition loops before reaching the totals section.
            generated = self._model.generate(
                **inputs, max_new_tokens=self.max_new_tokens, repetition_penalty=1.05
            )
        trimmed = [out[len(inp):] for inp, out in zip(inputs.input_ids, generated)]
        output = self._processor.batch_decode(
            trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )[0]
        return self._result(self.name, output.splitlines())
