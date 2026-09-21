"""Run the optional, separately installed KaLM service on loopback."""

import argparse
import json
import sys
from pathlib import Path

# Also works when copied with jev_ultrafast/kalm_backend.py to the desktop runtime.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "jev_ultrafast"))

NANO_REVISION = "3902d6453ea915007dcbf88fbc8a1d7dd5f8df10"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", required=True, help="Complete pinned KaLM Nano model directory")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--dtype", choices=["float32", "float16", "bfloat16"], default="float32")
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--query-max-length", type=int, default=4096)
    parser.add_argument("--document-max-length", type=int, default=1024)
    parser.add_argument("--decoder-max-length", type=int, default=6144)
    parser.add_argument("--full-logits", action="store_true", help="Use unmodified upstream scoring for comparison")
    parser.add_argument("--verify-readout", action="store_true", help="Check real-weight parity before serving")
    parser.add_argument("--verification-output", type=Path, help="Save the parity report as JSON")
    args = parser.parse_args()
    if args.threads < 1:
        parser.error("--threads must be positive")
    try:
        import torch
        import uvicorn
        from kalm_backend import ReadoutBackend, verify_readout
        from kalm_jev.backend import TransformersBackend
        from kalm_jev.engine import Engine
        from kalm_jev.server import create_app
    except ImportError as error:
        raise SystemExit("Install requirements-kalm.txt in the separate model environment first.") from error
    torch.set_num_threads(args.threads)
    backend_type = TransformersBackend if args.full_logits else ReadoutBackend
    backend = backend_type(
        model="kalm-jev-nano", model_path=args.model_path, revision=NANO_REVISION,
        device=args.device, dtype=args.dtype, batch_size=1,
        query_max_length=args.query_max_length, document_max_length=args.document_max_length,
        decoder_max_length=args.decoder_max_length,
    )
    if args.verify_readout:
        report = verify_readout(backend)
        print(json.dumps(report), flush=True)
        if args.verification_output:
            args.verification_output.parent.mkdir(parents=True, exist_ok=True)
            args.verification_output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    engine = Engine(model="kalm-jev-nano", backend=backend, cache_max_mib=64, max_pending=1)
    uvicorn.run(create_app(engine), host="127.0.0.1", port=args.port, workers=1)


if __name__ == "__main__":
    main()
