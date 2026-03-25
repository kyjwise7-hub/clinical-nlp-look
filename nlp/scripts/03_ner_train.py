#!/usr/bin/env python3
"""
INFECT-GUARD Phase 3: NER Training Pipeline
============================================
1) auto-label : synthetic parsed_documents → character-level entity spans
2) train      : Fine-tune KM-BERT for token classification (BIO tagging)
3) predict    : Run inference → NER predictions JSONL for pipeline integration

Usage:
    # Train
    python 03_ner_train.py train \
        --input nlp/data/parsed_documents.jsonl \
        --output-dir nlp/models/ner

    # Predict
    python 03_ner_train.py predict \
        --input nlp/data/parsed_documents.jsonl \
        --model nlp/models/ner/best \
        --output nlp/data/ner_predictions.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from typing import Any, Optional
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import Dataset
from transformers import (
    AutoModelForTokenClassification,
    AutoTokenizer,
    DataCollatorForTokenClassification,
    Trainer,
    TrainingArguments,
)
from seqeval.metrics import classification_report, f1_score


# ============================================================
# 엔티티 레이블 (04_ner_extractor.py의 LABEL_TO_SLOT과 대응)
# ============================================================
ENTITY_LABELS = [
    "PAIN_NRS", "PAIN_LOCATION",
    "DYSPNEA", "WOB", "NAUSEA", "DIARRHEA",
    "O2_DEVICE", "O2_FLOW",
    "SPO2", "TEMP", "HR", "RR", "BP_SYS", "BP_DIA",
    "ISOLATION_REQUIRED", "MDRO_FLAG", "CULTURE_ORDERED", "ABX_EVENT",
]

LABEL_LIST = ["O"]
for _ent in ENTITY_LABELS:
    LABEL_LIST.append(f"B-{_ent}")
    LABEL_LIST.append(f"I-{_ent}")

LABEL2ID = {l: i for i, l in enumerate(LABEL_LIST)}
ID2LABEL = {i: l for i, l in enumerate(LABEL_LIST)}
NUM_LABELS = len(LABEL_LIST)

SCRIPT_DIR = Path(__file__).resolve().parent
NLP_ROOT = SCRIPT_DIR.parent
DEFAULT_NER_MODEL_DIR = str(NLP_ROOT / "models" / "ner")


# ============================================================
# 1. Auto-labeling
# ============================================================

# ---- symptom keywords ----
SYMPTOM_PATTERNS: dict[str, list[str]] = {
    "DYSPNEA": [
        r"호흡\s*곤란", r"dyspnea", r"숨[이]?\s*[차찬]",
        r"shortness\s+of\s+breath", r"\bSOB\b",
    ],
    "WOB": [
        r"wheezing", r"accessory\s*muscle", r"호흡\s*보조근",
        r"labored\s*breathing", r"work\s*of\s*breathing",
        r"stridor", r"삼출음", r"수포음", r"crackle",
    ],
    "NAUSEA": [
        r"구역[질감]?", r"구토", r"nausea", r"vomiting",
        r"emesis", r"retching", r"bile\s*구토",
    ],
    "DIARRHEA": [
        r"설사", r"diarrhea", r"watery\s*stool",
        r"loose\s*stool", r"물\s*변",
    ],
    "PAIN_LOCATION": [
        r"복[부통]", r"abdomen", r"abdominal\s*pain",
        r"flank", r"옆구리", r"chest\s*pain", r"흉통",
        r"headache", r"두통", r"수술\s*부위",
    ],
}

# ---- clinical action keywords ----
CLINICAL_PATTERNS: dict[str, list[str]] = {
    "ISOLATION_REQUIRED": [
        r"contact\s*precaution[s]?", r"droplet\s*precaution[s]?",
        r"airborne\s*precaution[s]?", r"enteric\s*precaution[s]?",
        r"격리\s*(?:시행|적용|유지|필요)", r"(?:strict\s*)?isolation",
    ],
    "MDRO_FLAG": [
        r"\bMDRO\b", r"\bVRE\b", r"\bMRSA\b", r"\bCRE\b",
        r"\bESBL\b", r"다제\s*내성",
    ],
    "CULTURE_ORDERED": [
        r"culture\s*(?:ordered|시행|확인|결과)",
        r"specimen\s*collection", r"배양\s*검사",
        r"C\.\s*diff\s*toxin", r"blood\s*culture",
        r"urine\s*culture", r"stool\s*culture",
    ],
    "ABX_EVENT": [
        r"항생제\s*(?:투여|시작|변경|중단)",
        r"antibiotic[s]?\s*(?:start|change|stop|switch)",
        r"\b(?:vancomycin|meropenem|cefepime|piperacillin|tazobactam"
        r"|metronidazole|levofloxacin|ampicillin|ciprofloxacin"
        r"|ceftriaxone|amikacin|colistin)\b",
    ],
}

# ---- negation context (within 5 chars after keyword) ----
_NEG_AFTER = re.compile(r"(?:없|안\s|부인|deny|no\s|not\s|negative|resolved)", re.IGNORECASE)


def _is_negated(text: str, span_end: int, window: int = 8) -> bool:
    """Check if an entity span is immediately followed by a negation cue."""
    after = text[span_end:span_end + window]
    return bool(_NEG_AFTER.search(after))


def _find_spans(text: str, pattern: str, label: str, *, skip_negated: bool = True) -> list[tuple]:
    spans = []
    for m in re.finditer(pattern, text, re.IGNORECASE):
        if skip_negated and _is_negated(text, m.end()):
            continue
        spans.append((m.start(), m.end(), label))
    return spans


def _resolve_overlaps(spans: list[tuple]) -> list[tuple]:
    """Remove overlapping spans — keep longer spans."""
    if not spans:
        return spans
    spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))
    result = []
    last_end = -1
    for start, end, label in spans:
        if start >= last_end:
            result.append((start, end, label))
            last_end = end
    return result


def auto_label_document(doc: dict) -> list[tuple]:
    """
    Generate character-level entity spans [(start, end, label), ...]
    from structured fields + keyword matching on raw_text.
    """
    raw_text: str = doc.get("raw_text", "")
    if not raw_text:
        return []

    spans: list[tuple] = []

    # ── Vital Signs ──
    # Pattern: V/S) 120/70 - 75 - 16 - 36.8 - 97%
    vs_pat = (
        r"V/S[):\s]+"
        r"(\d+)/(\d+)"           # BP_SYS / BP_DIA
        r"\s*-\s*(\d+)"          # HR
        r"\s*-\s*(\d+)"          # RR
        r"\s*-\s*(\d+\.?\d*)"    # TEMP
        r"\s*-\s*(\d+)\s*%?"     # SPO2
    )
    for m in re.finditer(vs_pat, raw_text):
        spans.extend([
            (m.start(1), m.end(1), "BP_SYS"),
            (m.start(2), m.end(2), "BP_DIA"),
            (m.start(3), m.end(3), "HR"),
            (m.start(4), m.end(4), "RR"),
            (m.start(5), m.end(5), "TEMP"),
            (m.start(6), m.end(6), "SPO2"),
        ])

    # ── O2 Device ──
    if doc.get("o2_device"):
        o2_dev_pats = [
            r"Nasal\s*Cannula", r"\bNC\b(?!\s*notify)",
            r"Room\s*Air", r"\bRA\b",
            r"Simple\s*Mask", r"\bSM\b",
            r"Venturi\s*Mask", r"\bVM\b",
            r"Non-?rebreather", r"\bNRM\b",
            r"\bHFNC\b", r"High\s*Flow\s*Nasal\s*Cannula",
        ]
        for pat in o2_dev_pats:
            found = _find_spans(raw_text, pat, "O2_DEVICE", skip_negated=False)
            if found:
                spans.extend(found[:2])
                break

    # ── O2 Flow ──
    if doc.get("o2_flow"):
        flow_pats = [
            r"(\d+\.?\d*)\s*L/?min",
            r"O2\s+(\d+\.?\d*)\s*L",
            r"(\d+\.?\d*)\s*L\b",
        ]
        for pat in flow_pats:
            for m in re.finditer(pat, raw_text):
                spans.append((m.start(1), m.end(1), "O2_FLOW"))

    # ── Pain NRS ──
    nrs_pats = [
        r"(?:통증|pain)\s*(\d+)\s*/\s*10",
        r"NRS\s*[:=]?\s*(\d+)",
        r"(\d+)\s*/\s*10\s*\(?NRS\)?",
    ]
    for pat in nrs_pats:
        m = re.search(pat, raw_text, re.IGNORECASE)
        if m:
            spans.append((m.start(1), m.end(1), "PAIN_NRS"))
            break

    # ── Symptom keywords ──
    for label, patterns in SYMPTOM_PATTERNS.items():
        for pat in patterns:
            spans.extend(_find_spans(raw_text, pat, label))

    # ── Clinical action keywords ──
    for label, patterns in CLINICAL_PATTERNS.items():
        for pat in patterns:
            spans.extend(_find_spans(raw_text, pat, label, skip_negated=False))

    return _resolve_overlaps(spans)


def label_stats(examples: list[dict]) -> dict:
    """Aggregate label distribution statistics."""
    counts: dict[str, int] = {}
    for ex in examples:
        for _, _, label in ex["spans"]:
            counts[label] = counts.get(label, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: -x[1]))


# ============================================================
# 2. Dataset
# ============================================================

class NERDataset(Dataset):
    def __init__(self, examples: list[dict], tokenizer, max_length: int = 512):
        self.encodings = []
        for ex in examples:
            enc = self._encode(ex["text"], ex["spans"], tokenizer, max_length)
            if enc is not None:
                self.encodings.append(enc)

    @staticmethod
    def _encode(text: str, spans: list[tuple], tokenizer, max_length: int):
        if not text:
            return None
        tok = tokenizer(
            text,
            max_length=max_length,
            truncation=True,
            padding=False,
            return_offsets_mapping=True,
        )
        offsets = tok.pop("offset_mapping")
        labels = []
        for tok_start, tok_end in offsets:
            if tok_start == 0 and tok_end == 0:          # special token
                labels.append(-100)
                continue
            label_id = 0                                  # "O"
            for sp_start, sp_end, sp_label in spans:
                if tok_start >= sp_start and tok_end <= sp_end:
                    label_id = LABEL2ID[f"B-{sp_label}" if tok_start == sp_start else f"I-{sp_label}"]
                    break
                if tok_start < sp_end and tok_end > sp_start:   # partial overlap
                    label_id = LABEL2ID[f"B-{sp_label}" if tok_start <= sp_start else f"I-{sp_label}"]
                    break
            labels.append(label_id)
        tok["labels"] = labels
        return tok

    def __len__(self):
        return len(self.encodings)

    def __getitem__(self, idx):
        return {k: v for k, v in self.encodings[idx].items()}


# ============================================================
# 3. Metrics
# ============================================================

def compute_metrics(eval_pred):
    preds, labels = eval_pred
    preds = np.argmax(preds, axis=2)
    true_seqs, pred_seqs = [], []
    for p_seq, l_seq in zip(preds, labels):
        t, p = [], []
        for pi, li in zip(p_seq, l_seq):
            if li == -100:
                continue
            t.append(ID2LABEL[li])
            p.append(ID2LABEL[pi])
        true_seqs.append(t)
        pred_seqs.append(p)

    f1 = f1_score(true_seqs, pred_seqs, average="micro")
    report = classification_report(true_seqs, pred_seqs, zero_division=0)
    print(report)
    return {"f1": f1}


# ============================================================
# 4. Training
# ============================================================

def train_ner(
    train_examples: list[dict],
    eval_examples: list[dict],
    model_name: str = "madatnlp/km-bert",
    output_dir: str = DEFAULT_NER_MODEL_DIR,
    num_epochs: int = 10,
    batch_size: int = 8,
    learning_rate: float = 5e-5,
):
    print(f"🔧 Loading tokenizer & model: {model_name}")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForTokenClassification.from_pretrained(
        model_name,
        num_labels=NUM_LABELS,
        id2label=ID2LABEL,
        label2id=LABEL2ID,
    )

    print("📦 Building datasets …")
    train_ds = NERDataset(train_examples, tokenizer)
    eval_ds = NERDataset(eval_examples, tokenizer)
    print(f"   train={len(train_ds)}, eval={len(eval_ds)}")

    collator = DataCollatorForTokenClassification(tokenizer=tokenizer)

    args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=num_epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
        learning_rate=learning_rate,
        weight_decay=0.01,
        warmup_ratio=0.1,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        greater_is_better=True,
        logging_steps=50,
        save_total_limit=2,
        fp16=torch.cuda.is_available(),
        report_to="none",
    )

    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
        data_collator=collator,
        compute_metrics=compute_metrics,
        tokenizer=tokenizer,
    )

    print("🚀 Training …")
    trainer.train()

    best_dir = os.path.join(output_dir, "best")
    trainer.save_model(best_dir)
    tokenizer.save_pretrained(best_dir)
    print(f"✅ Best model saved → {best_dir}")
    return trainer


# ============================================================
# 5. Prediction (Inference)
# ============================================================

def predict_documents(
    docs: list[dict],
    model_path: str,
    output_path: str,
    max_length: int = 512,
    min_score: float = 0.5,
):
    print(f"🔮 Loading model: {model_path}")
    tokenizer = AutoTokenizer.from_pretrained(model_path)
    model = AutoModelForTokenClassification.from_pretrained(model_path)
    model.eval()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)

    results = []
    for doc in docs:
        raw_text = doc.get("raw_text", "")
        document_id = doc.get("document_id", "")
        if not raw_text:
            continue

        enc = tokenizer(
            raw_text,
            max_length=max_length,
            truncation=True,
            return_offsets_mapping=True,
            return_tensors="pt",
        )
        offsets = enc.pop("offset_mapping")[0].tolist()
        enc = {k: v.to(device) for k, v in enc.items()}

        with torch.no_grad():
            logits = model(**enc).logits[0]
            probs = torch.softmax(logits, dim=-1)
            pred_ids = torch.argmax(logits, dim=-1).cpu().tolist()
            max_probs = probs.max(dim=-1).values.cpu().tolist()

        # Decode BIO → entity spans
        entities: list[dict] = []
        cur: Optional[dict] = None

        for idx, ((tok_s, tok_e), pid) in enumerate(zip(offsets, pred_ids)):
            if tok_s == 0 and tok_e == 0:   # special token
                if cur:
                    entities.append(cur); cur = None
                continue
            lbl = ID2LABEL[pid]
            score = max_probs[idx]

            if lbl.startswith("B-"):
                if cur:
                    entities.append(cur)
                tag = lbl[2:]
                cur = {"label": tag, "start": tok_s, "end": tok_e,
                       "score": round(score, 4),
                       "text": raw_text[tok_s:tok_e]}
            elif lbl.startswith("I-") and cur and lbl[2:] == cur["label"]:
                cur["end"] = tok_e
                cur["text"] = raw_text[cur["start"]:tok_e]
                cur["score"] = min(cur["score"], round(score, 4))
            else:
                if cur:
                    entities.append(cur); cur = None

        if cur:
            entities.append(cur)

        # Filter by score
        entities = [e for e in entities if e["score"] >= min_score]

        results.append({"document_id": document_id, "entities": entities})

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    n_ents = sum(len(r["entities"]) for r in results)
    print(f"✅ Predictions written → {output_path}  ({len(results)} docs, {n_ents} entities)")
    return results


# ============================================================
# 6. CLI
# ============================================================

def _load_docs(path: str) -> list[dict]:
    docs = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                docs.append(json.loads(line))
    return docs


def main():
    parser = argparse.ArgumentParser(
        description="INFECT-GUARD Phase 3: NER auto-label → train → predict",
    )
    sub = parser.add_subparsers(dest="command")

    # ---- train ----
    tp = sub.add_parser("train")
    tp.add_argument("--input", required=True, help="parsed_documents.jsonl")
    tp.add_argument("--output-dir", default=DEFAULT_NER_MODEL_DIR)
    tp.add_argument("--model", default="madatnlp/km-bert")
    tp.add_argument("--epochs", type=int, default=10)
    tp.add_argument("--batch-size", type=int, default=8)
    tp.add_argument("--lr", type=float, default=5e-5)
    tp.add_argument("--eval-ratio", type=float, default=0.2)
    tp.add_argument("--seed", type=int, default=42)

    # ---- predict ----
    pp = sub.add_parser("predict")
    pp.add_argument("--input", required=True, help="parsed_documents.jsonl")
    pp.add_argument("--model", required=True, help="Trained model dir")
    pp.add_argument("--output", required=True, help="Output JSONL path")
    pp.add_argument("--min-score", type=float, default=0.5)

    # ---- stats (auto-label only, no training) ----
    sp = sub.add_parser("stats")
    sp.add_argument("--input", required=True)

    args = parser.parse_args()

    # ---------- train ----------
    if args.command == "train":
        random.seed(args.seed)
        np.random.seed(args.seed)
        torch.manual_seed(args.seed)

        docs = _load_docs(args.input)
        print(f"📄 Loaded {len(docs)} documents")

        # auto-label
        examples = []
        for d in docs:
            spans = auto_label_document(d)
            examples.append({
                "document_id": d.get("document_id"),
                "text": d.get("raw_text", ""),
                "spans": spans,
            })
        stats = label_stats(examples)
        total = sum(stats.values())
        print(f"🏷️  Auto-labeled: {total} entity spans")
        for lbl, cnt in stats.items():
            print(f"   {lbl:25s} {cnt:5d}")

        # train / eval split
        indices = list(range(len(examples)))
        random.shuffle(indices)
        n_eval = max(1, int(len(examples) * args.eval_ratio))
        eval_idx = set(indices[:n_eval])
        train_ex = [examples[i] for i in range(len(examples)) if i not in eval_idx]
        eval_ex = [examples[i] for i in eval_idx]
        print(f"📊 Split → train={len(train_ex)}, eval={len(eval_ex)}")

        train_ner(
            train_ex, eval_ex,
            model_name=args.model,
            output_dir=args.output_dir,
            num_epochs=args.epochs,
            batch_size=args.batch_size,
            learning_rate=args.lr,
        )

    # ---------- predict ----------
    elif args.command == "predict":
        docs = _load_docs(args.input)
        predict_documents(docs, args.model, args.output, min_score=args.min_score)

    # ---------- stats ----------
    elif args.command == "stats":
        docs = _load_docs(args.input)
        examples = []
        for d in docs:
            spans = auto_label_document(d)
            examples.append({"spans": spans})
        stats = label_stats(examples)
        total = sum(stats.values())
        print(f"🏷️  Total entity spans: {total} across {len(docs)} docs")
        for lbl, cnt in stats.items():
            pct = cnt / total * 100 if total else 0
            print(f"   {lbl:25s} {cnt:5d}  ({pct:5.1f}%)")

        # docs with zero spans
        empty = sum(1 for ex in examples if not ex["spans"])
        print(f"\n   Docs with 0 entities: {empty} / {len(docs)}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
