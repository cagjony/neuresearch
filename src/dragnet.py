#!/usr/bin/env python3
"""
dragnet.py — Broad-net adversarial triaging via Europe PMC

Executes a keyword search against the Europe PMC API,
pulls the abstracts, and dumps the results into a JSON file
for downstream autonomous triaging by an LLM (Phase 2).

Usage:
    python src/dragnet.py --out recent_candidates.json
"""

import argparse
import json
import requests
import sys

def main():
    parser = argparse.ArgumentParser(description="Dragnet: Pull recent DOIs and abstracts for adversarial triaging.")
    parser.add_argument("--email", help="(Ignored for EPMC) Polite pool email")
    parser.add_argument("--out", default="recent_candidates.json", help="Output JSON file path")
    args = parser.parse_args()

    # Europe PMC robust query
    query = '(astrocyte) AND (ATP) AND (model OR simulation) AND (FIRST_PDATE:[2023-01-01 TO 2026-12-31])'
    
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {
        "query": query,
        "resultType": "core",
        "format": "json",
        "pageSize": 200
    }

    print(f"Executing dragnet search on Europe PMC...")
    print(f"Query: {query}")

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Failed to fetch data from Europe PMC: {e}")
        sys.exit(1)

    data = response.json()
    results = data.get("resultList", {}).get("result", [])
    
    print(f"Found {len(results)} candidate papers.")

    candidates = []
    for work in results:
        doi = work.get("doi")
        if not doi:
            continue
            
        abstract = work.get("abstractText")
        if not abstract:
            continue
            
        candidates.append({
            "doi": "https://doi.org/" + doi.lower(),
            "title": work.get("title", "No title"),
            "year": work.get("pubYear"),
            "abstract": abstract
        })

    with open(args.out, "w") as f:
        json.dump(candidates, f, indent=2)

    print(f"Saved {len(candidates)} candidates to {args.out}")
    print("Ready for Phase 2 (Local LLM Triage).")

if __name__ == "__main__":
    main()
