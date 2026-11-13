from pathlib import Path

from src.extract import extract_text

folder = Path("sample_policies")

for file in sorted(folder.iterdir()):
    try:
        text = extract_text(file)
        print(f"OK     {file.name}: {len(text)} characters")
        print("       starts with:", text[:60].replace("\n", " "))
    except Exception as e:
        print(f"FAILED {file.name}: {e}")

# Test an unsupported file type
try:
    extract_text("photo.png")
except Exception as e:
    print("Expected error:", e)