from transformers import AutoModelForSequenceClassification, AutoTokenizer
import torch

model_name = r"C:\Users\CarmineFaiola\AI\models-ovms-rerank\bge-reranker-v2-m3"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForSequenceClassification.from_pretrained(model_name, num_labels=1)

# BAAI/bge-reranker usa pair classification: (query, document)
query = "test query"
doc = "this is a test document"

inputs = tokenizer(query, doc, return_tensors="pt")

torch.onnx.export(
    model,
    (inputs["input_ids"], inputs["attention_mask"]),
    r"C:\Users\CarmineFaiola\AI\models-ovms-rerank\bge-reranker-v2-m3\model.onnx",
    export_params=True,
    opset_version=13,
    do_constant_folding=True,
    input_names=["input_ids", "attention_mask"],
    output_names=["logits"],
    dynamic_axes={
        "input_ids": {0: "batch", 1: "sequence"},
        "attention_mask": {0: "batch", 1: "sequence"}
    }
)
print("ONNX exported successfully")
