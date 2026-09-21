"""Optional KaLM server adapter: project vocabulary logits only at readout positions."""

import torch
from kalm_jev.backend import TransformersBackend
from transformers.modeling_outputs import BaseModelOutput


class ReadoutBackend(TransformersBackend):
    @torch.inference_mode()
    def score_encoded(self, decoder_rows, documents):
        batch = self._pad(decoder_rows, decoder=True)
        hidden = torch.nn.utils.rnn.pad_sequence([doc.hidden for doc in documents], batch_first=True)
        mask = torch.nn.utils.rnn.pad_sequence([doc.mask for doc in documents], batch_first=True)
        attention = batch["attention_mask"]
        # Padding to a multiple of eight means the last tensor column need not be a real token.
        positions = torch.arange(attention.shape[1], device=attention.device)
        last = positions.expand_as(attention).masked_fill(attention == 0, -1).max(dim=1).values
        if torch.any(last < 0):
            raise ValueError("Cannot score an empty decoder sequence")
        # A union supports unequal row lengths without projecting the whole sequence.
        keep, inverse = torch.unique(last, sorted=True, return_inverse=True)
        output = self.model(
            encoder_outputs=BaseModelOutput(last_hidden_state=hidden),
            attention_mask=mask,
            decoder_input_ids=batch["input_ids"],
            decoder_attention_mask=attention,
            use_cache=False,
            return_dict=True,
            logits_to_keep=keep,
        )
        rows = torch.arange(len(documents), device=attention.device)
        logits = output.logits[rows, inverse].float()
        margin = logits[:, self.reranker.yes_token_id] - logits[:, self.reranker.no_token_id]
        return margin.float().cpu().tolist()


def verify_readout(backend):
    """Compare full and selected logits with real weights, including unequal padding."""
    from kalm_jev.compiler import compile_request
    from kalm_jev.schemas import Request

    request = Request.model_validate({
        "state": "The customer was billed twice and asks for a refund.",
        "questions": {
            "department": {
                "type": "choice", "instructions": "Choose the department.",
                "criteria": {"billing": "Payments and refunds", "shipping": "Delivery status"},
            },
            "next": {
                "type": "choice",
                "instructions": "Choose the next step that addresses the customer's duplicate charge request.",
                "criteria": {"review": "Review the payment history"},
            },
        },
    })
    tasks = compile_request(request)
    documents, rows, _ = backend.prepare(tasks)
    encoded = backend.encode_documents([documents[t.document] for t in tasks])
    reports = []
    # Singles catch pad-to-eight; mixed lengths catch wrong last-column or batch indexing.
    for indices in ([0], [2], [0, 2], [0, 1]):
        selected_rows = [rows[i] for i in indices]
        selected_documents = [encoded[i] for i in indices]
        full = TransformersBackend.score_encoded(backend, selected_rows, selected_documents)
        selected = ReadoutBackend.score_encoded(backend, selected_rows, selected_documents)
        expected, actual = torch.tensor(full), torch.tensor(selected)
        torch.testing.assert_close(actual, expected, rtol=1e-5, atol=2e-5)
        reports.append({
            "lengths": [len(row) for row in selected_rows],
            "max_absolute_error": float((actual - expected).abs().max()),
            "full_margins": full, "readout_margins": selected,
        })
    return {"passed": True, "dtype": str(backend.reranker.dtype), "cases": reports}
