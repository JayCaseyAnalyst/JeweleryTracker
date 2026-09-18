import json

filename = "price_history.json"
original_sku = "V-282350507"

with open(filename, "r") as f:
    history = json.load(f)

# Backfill legacy entries missing the 'sku' key
for entry in history:
    if "sku" not in entry:
        entry["sku"] = original_sku

with open(filename, "w") as f:
    json.dump(history, f, indent=4)

print("Updated legacy entries with original SKU.")