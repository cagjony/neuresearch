#!/usr/bin/env python3
import os

svg_content = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 400" width="1000" height="400">
    <style>
        .phase-box { rx: 8px; ry: 8px; stroke-width: 2px; }
        .text-title { font-family: Arial, sans-serif; font-size: 20px; font-weight: bold; fill: #ffffff; }
        .text-desc { font-family: Arial, sans-serif; font-size: 14px; fill: #ffffff; }
        .text-status { font-family: Arial, sans-serif; font-size: 16px; font-weight: bold; fill: #ffffff; }
        .arrow { fill: #aaaaaa; }
        .bottleneck { fill: #e74c3c; stroke: #c0392b; }
        .met { fill: #2ecc71; stroke: #27ae60; }
        .blocked { fill: #95a5a6; stroke: #7f8c8d; }
    </style>
    
    <!-- Background -->
    <rect width="1000" height="400" fill="#ffffff" />
    
    <!-- Title -->
    <text x="500" y="40" font-family="Arial, sans-serif" font-size="24" font-weight="bold" fill="#2c3e50" text-anchor="middle">Strategic Biomarker Roadmap: Olfactory Testing in AD</text>
    <text x="500" y="65" font-family="Arial, sans-serif" font-size="16" fill="#7f8c8d" text-anchor="middle">The translational gap is stuck at Phase 2: Construct alignment</text>

    <!-- Phase 1 -->
    <rect class="phase-box met" x="50" y="120" width="160" height="180" />
    <text class="text-title" x="130" y="160" text-anchor="middle">Phase 1</text>
    <text class="text-desc" x="130" y="190" text-anchor="middle">Preclinical</text>
    <text class="text-desc" x="130" y="210" text-anchor="middle">Exploration</text>
    <text class="text-status" x="130" y="260" text-anchor="middle">✓ MET</text>
    <text class="text-desc" x="130" y="280" text-anchor="middle" font-size="12">Olfactory decline</text>
    <text class="text-desc" x="130" y="295" text-anchor="middle" font-size="12">tracks AD pathology</text>
    
    <!-- Arrow 1 to 2 -->
    <polygon class="arrow" points="215,210 245,190 245,230" />

    <!-- Phase 2 (Bottleneck) -->
    <rect class="phase-box bottleneck" x="250" y="110" width="180" height="200" />
    <text class="text-title" x="340" y="150" text-anchor="middle">Phase 2</text>
    <text class="text-desc" x="340" y="180" text-anchor="middle">Clinical Assay</text>
    <text class="text-desc" x="340" y="200" text-anchor="middle">Development</text>
    <text class="text-status" x="340" y="250" text-anchor="middle">✗ NOT MET</text>
    <text class="text-desc" x="340" y="270" text-anchor="middle" font-weight="bold" font-size="14">THE BOTTLENECK</text>
    <text class="text-desc" x="340" y="290" text-anchor="middle" font-size="12">No standard assay;</text>
    <text class="text-desc" x="340" y="305" text-anchor="middle" font-size="12">construct mismatch</text>
    
    <!-- Bottleneck Barrier / Stop icon -->
    <circle cx="430" cy="210" r="15" fill="#c0392b" stroke="#ffffff" stroke-width="2"/>
    <rect x="423" y="208" width="14" height="4" fill="#ffffff"/>

    <!-- Arrow 2 to 3 (Blocked) -->
    <polygon class="arrow" points="435,210 465,190 465,230" opacity="0.5" />

    <!-- Phase 3 -->
    <rect class="phase-box blocked" x="470" y="130" width="150" height="160" />
    <text class="text-title" x="545" y="170" text-anchor="middle">Phase 3</text>
    <text class="text-desc" x="545" y="200" text-anchor="middle">Retrospective</text>
    <text class="text-desc" x="545" y="220" text-anchor="middle">Longitudinal</text>
    <text class="text-status" x="545" y="260" text-anchor="middle">Suggestive</text>
    <text class="text-desc" x="545" y="280" text-anchor="middle" font-size="12">Not poolable</text>

    <!-- Arrow 3 to 4 -->
    <polygon class="arrow" points="625,210 655,190 655,230" opacity="0.5" />

    <!-- Phase 4 -->
    <rect class="phase-box blocked" x="660" y="130" width="140" height="160" />
    <text class="text-title" x="730" y="170" text-anchor="middle">Phase 4</text>
    <text class="text-desc" x="730" y="200" text-anchor="middle">Prospective</text>
    <text class="text-desc" x="730" y="220" text-anchor="middle">Screening</text>
    <text class="text-status" x="730" y="260" text-anchor="middle">Unattempted</text>

    <!-- Arrow 4 to 5 -->
    <polygon class="arrow" points="805,210 835,190 835,230" opacity="0.5" />

    <!-- Phase 5 -->
    <rect class="phase-box blocked" x="840" y="130" width="140" height="160" />
    <text class="text-title" x="910" y="170" text-anchor="middle">Phase 5</text>
    <text class="text-desc" x="910" y="200" text-anchor="middle">Disease</text>
    <text class="text-desc" x="910" y="220" text-anchor="middle">Burden Control</text>
    <text class="text-status" x="910" y="260" text-anchor="middle">Unattempted</text>
</svg>
"""

def main():
    out_dir = "/mnt/sysfs01/users/cagatay/code/neubrain/projects/alz-olf/archive"
    os.makedirs(out_dir, exist_ok=True)
    svg_path = os.path.join(out_dir, "figure1_roadmap.svg")
    
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg_content)
        
    print(f"Generated {svg_path}")

if __name__ == "__main__":
    main()
