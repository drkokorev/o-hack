"""Build a compact, curated selection from UNESCO's World Heritage dataset.

Input: UNESCO whc001 JSON export including components_list and states_names.
See THIRD_PARTY.md for source, snapshot date and licence.
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IDS = [
    81,83,228,344,345,600,872, 544,754,980,1070,1170,1234,1525,
    174,394,395,670,717,797,830,1427, 311,313,314,379,1258,
    369,426,428,488,728, 292,532,624,896,1066, 393,404,455,493,517,
    485,849,1572,448, 444,836, 916,1007, 39,156,173,403, 1295,
    231,233,241,242,251,252,337,945, 437,547,637,640,880,881,1003,1334,
    661,662,775,776,913, 576, 609,642, 672,948, 411,414,483,482,
    27,28,75,308,134, 300,304,419, 124,309,355,1611, 274,700,1016,
    145,303,937, 154,166,447,917, 551,
]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8"))
    lookup = {str(item["id_no"]): item for item in data}
    countries = json.loads((ROOT / "domains/trips/data/countries_ru.json").read_text(encoding="utf-8"))
    sites = []
    for number in IDS:
        item = lookup[str(number)]
        parts = json.loads(item["components_list"])
        if item["components_count"] != 1 or len(parts) != 1:
            raise ValueError(f"UNESCO {number} needs an explicitly chosen component")
        part = parts[0]
        lat, lon = float(part["latitude"]), float(part["longitude"])
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError(f"Invalid coordinate: {number}")
        codes = item.get("iso_codes") or []
        country = countries.get(codes[0], item["states_names"][0]) if codes else item["states_names"][0]
        sites.append({"id":f"unesco:{number}", "name":item.get("name_ru") or item["name_en"],
                      "country":country, "lat":lat, "lon":lon,
                      "category":"Природа" if item["category"] == "Natural" else "Наследие",
                      "icon":"heritage_nature" if item["category"] == "Natural" else "heritage_culture",
                      "url":f"https://whc.unesco.org/en/list/{number}/"})
    output = {"source":"UNESCO World Heritage List", "source_url":"https://data.unesco.org/explore/dataset/whc001/",
              "license":"CC BY-SA 4.0", "license_url":"https://creativecommons.org/licenses/by-sa/4.0/",
              "checked_at":"2026-10-28", "coordinate_note":"Координата единственного компонента объекта; не обязательно вход.",
              "sites":sites}
    target = ROOT / "apps/static/heritage.json"
    target.write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"{len(sites)} places written to {target}")

if __name__ == "__main__":
    main()
