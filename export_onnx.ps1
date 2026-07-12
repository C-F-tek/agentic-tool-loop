from transformers import AutoModelForSequenceClassification, AutoTokenizer
import torch
import onnx

model_name = r"C:\Users\CarmineFaiola\AI\models-ovms-reranker-v2-m3"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForSequenceClassification.from_pretrained(model_name, num_labels=1)

input_ids = torch.tensor(tokenizer.encode("test query", ["doc1"], return_tensors="pt"))
attention_mask = torch.ones_like(input_ids)

torch.onnx.export(
    model,
    (input_ids, attention_mask),
    r"C:\Users\CarmineFaiola\AI\models-ovms-rerank\bge-reranker-v2-m3\model.onnx",
    export_params=True,
    opset_version=13,
    do_constant_folding=True,
    input_names=["input_ids", "attention_mask"],
    output_names=["logits"],
    dynamic_axes={"input_ids": {0: "batch"}, "attention_mask": {0: "batch"}}
)
print("ONNX exported successfully")
