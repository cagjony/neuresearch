import os
import re
import yaml
import argparse
import subprocess
from collections import defaultdict

def parse_bib_keys(bib_path):
    keys = set()
    if not os.path.exists(bib_path):
        print(f"Warning: bib file not found at {bib_path}")
        return keys
    with open(bib_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line.startswith('@'):
                match = re.search(r'@[a-zA-Z]+\{([^,]+),', line)
                if match:
                    keys.add(match.group(1).strip())
    return keys

def extract_frontmatter(content):
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                return yaml.safe_load(parts[1])
            except:
                pass
    return {}

def process_papers(vault_dir, citekeys, categories_def):
    lit_dir = os.path.join(vault_dir, "lit")
    lib_dir = os.path.join(vault_dir, "_library")
    results = []
    
    for citekey in citekeys:
        lit_path = os.path.join(lit_dir, f"{citekey}.md")
        txt_path = os.path.join(lib_dir, f"{citekey}.txt")
        xml_path = os.path.join(lib_dir, f"{citekey}.xml")
        
        text_corpus = ""
        
        if os.path.exists(lit_path):
            with open(lit_path, "r", encoding="utf-8") as f:
                text_corpus += f.read().lower() + " "
                
        if os.path.exists(txt_path):
            with open(txt_path, "r", encoding="utf-8") as f:
                text_corpus += f.read().lower() + " "
                
        if os.path.exists(xml_path):
            with open(xml_path, "r", encoding="utf-8") as f:
                text_corpus += f.read().lower() + " "
                
        if not text_corpus:
            print(f"Skipping {citekey}: no text found in vault.")
            continue
            
        paper_cats = {"Citekey": citekey}
        for cat_name, subcats in categories_def.items():
            counts_dict = {}
            for subcat, pattern in subcats.items():
                matches = re.findall(pattern, text_corpus)
                if matches:
                    counts_dict[subcat] = len(matches)
            
            if counts_dict:
                # Get the subcat with the highest count
                best_match = max(counts_dict.items(), key=lambda x: x[1])[0]
                paper_cats[cat_name] = best_match
            else:
                paper_cats[cat_name] = "Unknown"
                
        results.append(paper_cats)
        
    return results

def generate_svg_plot(results, output_path):
    # Prepare data
    species_list = ["Human", "Rodent"]
    constructs = ["Identification", "Discrimination", "Detection", "Memory"]
    
    # Beautiful curated color palette (Hex codes)
    colors = ["#4C72B0", "#DD8452", "#55A868", "#C44E52"] 
    
    # Initialize counts
    counts = {s: {c: 0 for c in constructs} for s in species_list}
    
    for r in results:
        sp = r.get("Species")
        co = r.get("Construct")
        if sp in species_list and co in constructs:
            counts[sp][co] += 1
            
    # Normalize to percentages for the 100% stacked bar chart
    percentages = {s: {} for s in species_list}
    for s in species_list:
        total = sum(counts[s].values())
        if total > 0:
            for c in constructs:
                percentages[s][c] = (counts[s][c] / total) * 100
        else:
            for c in constructs:
                percentages[s][c] = 0

    width, height = 800, 600
    svg = f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">\n'
    
    # SVG Definitions (shadows, gradients)
    # Background
    svg += f'<rect width="{width}" height="{height}" fill="#F9FAFC"/>\n'
    
    # Title
    svg += f'<text x="{width/2 - 120}" y="50" font-family="Arial" font-size="22" font-weight="bold" text-anchor="middle" fill="#2C3E50">Olfactory Construct Focus by Species Model</text>\n'
    
    # Axes dimensions
    margin_left = 120
    margin_right = 250
    margin_top = 100
    margin_bottom = 80
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom
    
    # Draw Y axis grid lines
    num_ticks = 5
    for i in range(num_ticks + 1):
        y = margin_top + plot_height - (i * plot_height / num_ticks)
        pct = i * 25
        svg += f'<line x1="{margin_left}" y1="{y}" x2="{margin_left + plot_width}" y2="{y}" stroke="#E1E5EB" stroke-width="1.5" />\n'
        svg += f'<text x="{margin_left - 15}" y="{y + 5}" font-family="Arial" font-size="14" text-anchor="end" fill="#7F8C8D">{pct}%</text>\n'
        
    svg += f'<text x="{margin_left - 60}" y="{margin_top + plot_height/2}" font-family="Arial" font-size="16" font-weight="bold" transform="rotate(-90 {margin_left - 60} {margin_top + plot_height/2})" text-anchor="middle" fill="#34495E">Percentage of Cited Studies</text>\n'

    # Draw Bars
    bar_width = plot_width / (len(species_list) * 1.5)
    gap = (plot_width - (bar_width * len(species_list))) / (len(species_list) + 1)
    
    for i, sp in enumerate(species_list):
        x = margin_left + gap + i * (bar_width + gap)
        base_y = margin_top + plot_height
        total_count = sum(counts[sp].values())
        
        y = base_y
        for j, c in enumerate(constructs):
            pct = percentages[sp][c]
            h = (pct / 100) * plot_height
            if h > 0:
                y -= h
                svg += f'<rect x="{x}" y="{y}" width="{bar_width}" height="{h}" fill="{colors[j]}" stroke="#FFFFFF" stroke-width="2"/>\n'
                # Add text label if segment is large enough (> 10%)
                if pct > 10:
                    text_y = y + h / 2 + 5
                    svg += f'<text x="{x + bar_width/2}" y="{text_y}" font-family="Arial" font-size="12" font-weight="bold" text-anchor="middle" fill="#FFFFFF">{int(pct)}%</text>\n'
                    
        # X-axis labels
        svg += f'<text x="{x + bar_width/2}" y="{base_y + 30}" font-family="Arial" font-size="16" font-weight="bold" text-anchor="middle" fill="#2C3E50">{sp}</text>\n'
        svg += f'<text x="{x + bar_width/2}" y="{base_y + 50}" font-family="Arial" font-size="14" text-anchor="middle" fill="#7F8C8D">n = {total_count}</text>\n'

    # X-axis line
    svg += f'<line x1="{margin_left}" y1="{margin_top + plot_height}" x2="{margin_left + plot_width}" y2="{margin_top + plot_height}" stroke="#BDC3C7" stroke-width="2" />\n'

    # Legend
    leg_x = width - margin_right + 30
    leg_y = margin_top + 20
    svg += f'<text x="{leg_x}" y="{leg_y - 15}" font-family="Arial" font-size="16" font-weight="bold" fill="#2C3E50">Primary Construct</text>\n'
    for j, c in enumerate(constructs):
        svg += f'<rect x="{leg_x}" y="{leg_y + j*35}" width="20" height="20" rx="4" ry="4" fill="{colors[j]}"/>\n'
        svg += f'<text x="{leg_x + 35}" y="{leg_y + 15 + j*35}" font-family="Arial" font-size="15" fill="#34495E">{c}</text>\n'

    svg += '</svg>'
    
    svg_path = output_path.replace(".png", ".svg")
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg)
        
    print(f"SVG saved to {svg_path}")
    
    # Convert SVG to PNG
    try:
        # Use high density for good resolution
        subprocess.run(["convert", "-density", "300", svg_path, output_path], check=True)
        print(f"PNG saved to {output_path}")
    except Exception as e:
        print(f"Failed to convert SVG to PNG using ImageMagick: {e}")

def main():
    parser = argparse.ArgumentParser(description="Bibliometric Gap Analysis Tool")
    parser.add_argument("--vault", required=True, help="Path to the neubrain vault")
    parser.add_argument("--project", required=True, help="Project name (e.g., alz-olf)")
    parser.add_argument("--bib", help="Path to references.bib (optional)")
    parser.add_argument("--plot", help="Path to output the stacked bar plot")
    
    args = parser.parse_args()
    
    bib_path = args.bib
    if not bib_path:
        bib_path = os.path.join(args.vault, "projects", args.project, "references.bib")
        
    citekeys = parse_bib_keys(bib_path)
    print(f"Found {len(citekeys)} citations in {bib_path}")
    
    CATEGORIES = {
        "Species": {
            "Human": r"\b(human|patient|clinical|cohort|participant|men|women|subjects)\b",
            "Rodent": r"\b(mice|mouse|rat|rodent|transgenic)\b",
            "In Vitro": r"\b(in vitro|cell culture|slice|primary culture)\b"
        },
        "Construct": {
            "Identification": r"\b(identification|upsit|sniffin|b-sit|identify)\b",
            "Discrimination": r"\b(discrimination|discriminate)\b",
            "Detection": r"\b(detection|threshold|sensitivity|buried food)\b",
            "Memory": r"\b(memory|recall|habituation)\b"
        },
        "Methodology": {
            "Imaging": r"\b(fmri|mri|pet|imaging|scan)\b",
            "Behavior": r"\b(behavioral|maze|buried food|habituation|sniffin)\b",
            "Electrophysiology": r"\b(eeg|lfp|electrophysiology|patch clamp|recording)\b",
            "Manipulation": r"\b(optogenetic|chemogenetic|dreadd|chr2)\b"
        }
    }
    
    results = process_papers(args.vault, citekeys, CATEGORIES)
    print(f"Categorized {len(results)} papers.")
    
    if args.plot:
        generate_svg_plot(results, args.plot)
        
if __name__ == "__main__":
    main()
