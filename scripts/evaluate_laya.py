"""Read-only browser-request evaluation with explicit Laya input-loss accounting.

Model files must already exist. This script never downloads weights or operates a browser.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

SOURCE_REVISION = "573e5b62696ba441230cd6be71d593331b5d23af"
MODEL_ID = "convaiinnovations/laya-typed-decisions"
MODEL_REVISION = "f9ab0b228f0fc0f14d873dbc99038f135c2da1b2"


def audit_question(tok, common, agent_type, state, definition, max_len, head_max_len):
    """Reproduce every native truncation stage and assert exact final-token parity."""
    q = agent_type._to_internal(definition)
    def encode(value):
        return tok(value, add_special_tokens=False)["input_ids"]
    mask = tok.mask_token
    instruction = str(q["ins"])
    head_raw = encode(f"{q['t']} question: {instruction.replace(mask, ' ')}")
    options = common.render_options(q)
    option_raw = [encode(" " + option.replace(mask, " ")) for option in options]
    option_ids = [[tok.mask_token_id] + ids[:48] for ids in option_raw]
    budget = head_max_len - sum(map(len, option_ids))
    if budget < 16:
        per_option = max(4, (head_max_len - 16) // max(1, len(option_ids)))
        option_ids = [ids[:per_option] for ids in option_ids]
        budget = head_max_len - sum(map(len, option_ids))
    head_kept = head_raw[:max(8, budget)]
    ids = [tok.cls_token_id] + head_kept + [tok.sep_token_id]
    option_positions = []
    for selected in option_ids:
        option_positions.append(len(ids))
        ids.extend(selected)
    ids.append(tok.sep_token_id)
    state_text = common.serialize_state(state)
    state_raw = encode(state_text.replace(mask, " "))
    room = max(0, max_len - len(ids) - 1)
    state_start = len(ids)
    ids += state_raw[:room] + [tok.sep_token_id]
    final_ids = ids[:max_len]
    markers = [position for position in option_positions if position < max_len]
    native_ids, native_markers = common.build_sequence(tok, state, q, max_len, head_max_len)
    if final_ids != native_ids or markers != native_markers:
        raise AssertionError("Truncation audit diverged from pinned upstream formatter")
    head_retained = max(0, min(len(head_kept), max_len - 1))
    option_reports = []
    labels = list(q["crit"]) if q["t"] == "choice" else list(range(len(options)))
    for label, raw, selected, start in zip(labels, option_raw, option_ids, option_positions):
        retained = max(0, min(len(selected) - 1, max_len - start - 1))
        option_reports.append({
            "label": str(label), "original_tokens": len(raw), "retained_tokens": retained,
            "truncated": retained < len(raw),
        })
    state_retained = max(0, min(len(state_raw), room, max_len - state_start))
    truncated = (head_retained < len(head_raw)
                 or any(option["truncated"] for option in option_reports)
                 or state_retained < len(state_raw))
    return {
        "truncated": truncated,
        "instruction": {"original_tokens": len(head_raw), "retained_tokens": head_retained},
        "options": option_reports,
        "state": {"original_tokens": len(state_raw), "retained_tokens": state_retained},
        "mask_token_replacements": instruction.count(mask) + state_text.count(mask)
                                   + sum(option.count(mask) for option in options),
        "final_tokens": len(final_ids),
        "expected_markers": len(options), "retained_markers": len(markers),
        "native_sequence_match": True,
    }


def captured_requests(paths):
    for path in paths:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        if "decisions" in value:
            for index, decision in enumerate(value["decisions"]):
                yield f"{path.stem}:decision:{index}", decision["request"]
        elif "questions" in value and "state" in value:
            yield path.stem, value
        elif "request" in value:
            yield path.stem, value["request"]
        else:
            raise ValueError(f"Unrecognized capture format: {path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--model-id", default=MODEL_ID)
    parser.add_argument("--model-revision", default=MODEL_REVISION)
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--allow-truncated", "--allow-truncation", action="store_true",
                        help="Record diagnostic predictions even when input was truncated.")
    parser.add_argument("--audit-only", action="store_true",
                        help="Load only local config/tokenizer, never model weights.")
    parser.add_argument("--max-cases", type=int, default=0)
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if revision != SOURCE_REVISION:
        raise ValueError(f"Unexpected Laya source revision: {revision}")
    model_dir = args.model_dir.resolve(strict=True)
    for name in ("rl_agent_config.json", "encoder/config.json", "tokenizer/tokenizer.json"):
        if not (model_dir / name).is_file():
            raise FileNotFoundError(model_dir / name)
    if not args.audit_only and not (model_dir / "model.safetensors").is_file():
        raise FileNotFoundError(model_dir / "model.safetensors")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    sys.path.insert(0, str(source))
    import laya.agent as agent_module
    import laya.common as common
    import torch
    import transformers
    torch.set_num_threads(args.threads)
    # The reference initializer may rewrite tokenizer_config. Keep input files read-only.
    agent_module._fix_tokenizer_config = lambda path: None
    cfg = json.loads((model_dir / "rl_agent_config.json").read_text(encoding="utf-8"))
    tok = transformers.AutoTokenizer.from_pretrained(str(model_dir / "tokenizer"), local_files_only=True)
    result = {
        "source_revision": revision, "model_id": args.model_id,
        "model_revision_declared": args.model_revision,
        "torch": torch.__version__, "transformers": transformers.__version__,
        "device": "cpu", "threads": args.threads,
        "max_len": cfg.get("max_len", 512), "head_max_len": cfg.get("head_max_len", 192),
        "scope": "Captured requests only; no browser actions. Truncated predictions are diagnostic.",
        "cases": [],
    }
    agent = None
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for index, (name, body) in enumerate(captured_requests(args.input)):
        if args.max_cases and index >= args.max_cases:
            break
        audits = {qid: audit_question(tok, common, agent_module.Agent, body["state"], definition,
                                     result["max_len"], result["head_max_len"])
                  for qid, definition in body["questions"].items()}
        truncated = any(item["truncated"] for item in audits.values())
        case = {"name": name, "request": body, "truncated": truncated, "audit": audits,
                "request_sha256": hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()}
        if args.audit_only or (truncated and not args.allow_truncated):
            case["status"] = "audit_only" if args.audit_only else "rejected_truncated"
        else:
            if agent is None:
                started = time.perf_counter()
                agent = agent_module.Agent(str(model_dir), device="cpu")
                result["model_load_ms"] = round((time.perf_counter() - started) * 1000)
            started = time.perf_counter()
            case["response"] = agent.predict(body["state"], body["questions"])
            case["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
            case["status"] = "diagnostic_truncated" if truncated else "evaluated_complete_input"
        result["cases"].append(case)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"case": name, "status": case["status"], "truncated": truncated,
                          "elapsed_ms": case.get("elapsed_ms"),
                          "answers": case.get("response", {}).get("answers", {})}), flush=True)


if __name__ == "__main__":
    main()
