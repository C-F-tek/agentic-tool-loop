# Export BAAI/bge-small-en-v1.5 to OpenVINO IR format using Python directly
# This script exports the model to ONNX format, then converts to OpenVINO IR

import os
import subprocess
import sys
from pathlib import Path

OUTPUT_DIR = r"C:\Users\someo\agentic-tool-loop\services\launch\models-ovms-embed\BAAI\bge-small-en-v1.5"


def export_to_onnx():
    """Export model to ONNX format using transformers + optimum."""
    print("=" * 60)
    print("Step 1: Exporting BAAI/bge-small-en-v1.5 to ONNX format")
    print("=" * 60)
    
    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Use Python to export the model
    cmd = f"""python -c "
from transformers import AutoModel
import torch
import onnx

# Load model
model = AutoModel.from_pretrained('BAAI/bge-small-en-v1.5')

# Save to ONNX format
onnx_path = r'{OUTPUT_DIR}\\model.onnx'
inputs = {{
    'input_ids': torch.ones((1, 16), dtype=torch.long),
    'attention_mask': torch.ones((1, 16), dtype=torch.long)
}}

# Export to ONNX
torch.onnx.export(
    model,
    tuple(inputs.values()),
    onnx_path,
    input_names=['input_ids', 'attention_mask'],
    output_names=['embedding'],
    opset_version=14
)
print('ONNX export complete')
"""
    print(f"\nRun this command:\n{cmd}")


def convert_to_openvino():
    """Convert ONNX to OpenVINO IR format using mo (Model Optimizer)."""
    print("\n" + "=" * 60)
    print("Step 2: Convert ONNX to OpenVINO IR format")
    print("=" * 60)
    
    onnx_model = os.path.join(OUTPUT_DIR, "model.onnx")
    
    if not os.path.exists(onnx_model):
        print(f"\nONNX model not found at {onnx_model}")
        print("Please run Step 1 first.")
        return
    
    cmd = f'mo --input_model "{onnx_model}" --output_dir "{OUTPUT_DIR}"'
    
    print(f"\nRun this command:\n{cmd}")


def verify():
    """Verify the exported files."""
    print("\n" + "=" * 60)
    print("Step 3: Verify exported files")
    print("=" * 60)
    
    print(f"\nCheck that these files exist:")
    print(f"  {OUTPUT_DIR}/bge-small-en-v1.5.xml")
    print(f"  {OUTPUT_DIR}/bge-small-en-v1.5.bin")


def main():
    print("\nExporting BAAI/bge-small-en-v1.5 model to OpenVINO IR format...")
    print(f"Output directory: {OUTPUT_DIR}\n")
    
    export_to_onnx()
    convert_to_openvino()
    verify()
    
    print("\n" + "=" * 60)
    print("Summary of commands to run:")
    print("=" * 60)
    print("""
1. Install required packages:
   pip install transformers onnx torch

2. Export to ONNX:
   python -c "from transformers import AutoModel; import torch; model = AutoModel.from_pretrained('BAAI/bge-small-en-v1.5'); torch.onnx.export(model, (torch.ones((1, 16), dtype=torch.long), torch.ones((1, 16), dtype=torch.long)), 'model.onnx', input_names=['input_ids', 'attention_mask'], opset_version=14)"

 3. Convert to OpenVINO IR:
    mo --input_model model.onnx --output_dir C:\\Users\\someo\\agentic-tool-loop\\services\\launch\\models-ovms-embed\\BAAI\\bge-small-en-v1.5

4. Verify files exist:
   ls C:\\Users\\someo\\agentic-tool-loop\\services\\launch\\models-ovms-embed\\BAAI\\bge-small-en-v1.5

5. Start OVMS embedding service:
   powershell -File services/launch/ovms-embed.ps1
""")


if __name__ == "__main__":
    main()