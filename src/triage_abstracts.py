import json
import urllib.request
import json as json_lib

# Configuration
INPUT_FILE = "recent_candidates.json"
TARGET_MODEL = "llama3" # Or "qwen2.5:72b" if you have it loaded
OLLAMA_URL = "http://localhost:11434/api/generate"

SYSTEM_PROMPT = """
You are an expert computational neuroscientist scouting the literature.
Analyze the following abstract. We want to cast a slightly wider net to find ANY paper that might be adjacent to our novelty.

Rules:
1. If the abstract models extracellular ATP as a key control variable, explores network state changes, bifurcation, network fragmentation, or gap junction uncoupling based on ATP/calcium levels: Reply ONLY with "INVESTIGATE".
2. If the abstract focuses on network-wide synchronization/desynchronization driven by extracellular signaling (even if it doesn't explicitly say "external parameter"): Reply ONLY with "INVESTIGATE".
3. If ATP is STRICTLY just a simple downstream consequence of IP3/Calcium in a standard wave propagation model, or if the paper has no mathematical model at all: Reply ONLY with "SAFE".
4. IF IN DOUBT or if the model's treatment of ATP seems unusually complex: Lean towards "INVESTIGATE".
5. Do not output any other text, reasoning, or punctuation.
"""

def prompt_local_model(abstract):
    payload = {
        "model": TARGET_MODEL,
        "prompt": f"Abstract: {abstract}",
        "system": SYSTEM_PROMPT,
        "stream": False,
        "options": {
            "temperature": 0.0 # Zero creativity, strictly deterministic
        }
    }
    
    req = urllib.request.Request(OLLAMA_URL, data=json_lib.dumps(payload).encode('utf-8'),
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req) as response:
            result = json_lib.loads(response.read().decode('utf-8'))
            return result.get("response", "").strip().upper()
    except Exception as e:
        print(f"Error communicating with local model: {e}")
        return "ERROR"

def main():
    try:
        with open(INPUT_FILE, "r") as f:
            candidates = json.load(f)
    except FileNotFoundError:
        print(f"File {INPUT_FILE} not found. Run dragnet.py first.")
        return

    investigate_list = []
    
    print(f"Starting triage of {len(candidates)} abstracts using local {TARGET_MODEL}...\n")
    
    for i, paper in enumerate(candidates, 1):
        abstract = paper.get("abstract", "")
        doi = paper.get("doi", "Unknown DOI")
        
        if not abstract:
            print(f"[{i}/{len(candidates)}] Skipping {doi} - No abstract available.")
            continue
            
        decision = prompt_local_model(abstract)
        
        if "INVESTIGATE" in decision:
            print(f"[{i}/{len(candidates)}] 🔴 FLAG: {doi}")
            investigate_list.append(doi)
        else:
            print(f"[{i}/{len(candidates)}] 🟢 SAFE: {doi}")

    print("-" * 40)
    print(f"Triage complete. {len(investigate_list)} papers flagged for investigation.")
    
    if investigate_list:
        print("Appending to projects/astro_atp/papers.txt...")
        with open("/mnt/sysfs01/users/cagatay/code/neubrain/projects/astro_atp/papers.txt", "a") as f:
            for doi in investigate_list:
                f.write(f"{doi}\n")
        print("Done. Ready for fetch_papers.py.")

if __name__ == "__main__":
    main()
