"""Exercise one public audio sample through a running local server; retain no audio or transcript."""
import argparse
import json
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument("--url", default="http://127.0.0.1:18089")
args = parser.parse_args()
URL = ("https://datasets-server.huggingface.co/rows?dataset=bond005%2Fsova_rudevices"
       "&config=default&split=test&offset=0&length=1")
with urllib.request.urlopen(URL, timeout=30) as response:
    item = json.load(response)["rows"][0]["row"]["audio"][0]
with urllib.request.urlopen(item["src"], timeout=30) as response:
    audio = response.read()
request = urllib.request.Request(args.url.rstrip("/") + "/api/voice/transcribe", data=audio,
                                 headers={"Content-Type": "audio/wav"}, method="POST")
with urllib.request.urlopen(request, timeout=45) as response:
    result = json.load(response)
print(json.dumps({"status": "PASS" if result.get("text") and result.get("backend") == "gigaam" else "FAIL",
                  "backend": result.get("backend"), "transcript_nonempty": bool(result.get("text"))}))
