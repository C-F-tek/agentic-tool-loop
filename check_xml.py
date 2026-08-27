import xml.etree.ElementTree as ET

xml_path = r"C:\Users\someo\agentic-tool-loop\services\launch\models-ovms-rerank\BAAI\bge-reranker-v2-m3\openvino_model.xml"
tree = ET.parse(xml_path)
root = tree.getroot()
print("Root tag:", root.tag)
print("Root attribs:", root.attrib)

layers = root.findall(".//layer")
print(f"Total layers: {len(layers)}")

const_layers = [l for l in layers if l.get("type") == "Const"]
print(f"Const layers: {len(const_layers)}")

# Check first 5 Const layers
for i, cl in enumerate(const_layers[:5]):
    data = cl.find("data")
    if data is not None:
        name = cl.get("name", "")
        elem_type = data.get("element_type", "")
        shape = data.get("shape", "")
        offset = data.get("offset", "")
        size = data.get("size", "")
        print(f"Const {i}: name={name}, type={elem_type}, shape={shape}, offset={offset}, size={size}")

# Check all offsets and sizes to find the max
max_offset_size = 0
for cl in const_layers:
    data = cl.find("data")
    if data is not None:
        offset = int(data.get("offset", "0"))
        size = int(data.get("size", "0"))
        end = offset + size
        if end > max_offset_size:
            max_offset_size = end

print(f"Max offset+size from XML: {max_offset_size}")
print(f"Actual .bin file size: 2271088788")
