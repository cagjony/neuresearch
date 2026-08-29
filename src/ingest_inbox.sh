#!/usr/bin/env bash
# Ingest manually-downloaded referee-named PDFs for aon-pir-rev.
# Each DOI below was verified against Europe PMC on 2026-08-27 (first author + year + title).
# Drop <stem>.pdf into the inbox, then run this. Missing files are reported, not invented.
set -u
PY=/home/mouselab/.conda/envs/neuresearch/bin/python
ROOT=/mnt/sysfs01/users/cagatay/code
VAULT=$ROOT/neubrain
INBOX=$VAULT/projects/aon-pir-rev/archive/inbox
EMAIL=cagatay.aydin@kuleuven.be

declare -A DOI=(
  [schoonover2021]="10.1038/s41586-021-03628-7"
  [jacobson2018]="10.1016/j.cub.2017.11.007"
  [iurilli2017]="10.1016/j.neuron.2017.02.010"
  [yuan2024]="10.7554/elife.92495"
  [marks2021]="10.1038/s41467-021-25436-3"
  [aitken2022]="10.1371/journal.pcbi.1010716"
  [driscoll2017]="10.1016/j.cell.2017.07.021"
  [ziv2013]="10.1038/nn.3329"
  [lei2006]="10.1523/jneurosci.2598-06.2006"
  [wachowiak2011]="10.1016/j.neuron.2011.08.030"
  [boyd2012]="10.1016/j.neuron.2012.10.020"
  [kehl2024]="10.1038/s41586-024-08016-5"
)

found=0; missing=0
for stem in "${!DOI[@]}"; do
  f="$INBOX/$stem.pdf"
  if [[ -f "$f" ]]; then
    echo "=== $stem  (${DOI[$stem]})"
    "$PY" "$ROOT/neuresearch/src/ingest.py" --vault "$VAULT" --project aon-pir-rev \
        --file "$f" --doi "${DOI[$stem]}" --email "$EMAIL" || echo "  !! ingest failed for $stem"
    found=$((found+1))
  else
    missing=$((missing+1))
  fi
done
echo
echo "ingested/attempted: $found   still absent from inbox: $missing"
[[ $missing -gt 0 ]] && { echo "absent:"; for s in "${!DOI[@]}"; do [[ -f "$INBOX/$s.pdf" ]] || echo "  $s.pdf  (${DOI[$s]})"; done; }
exit 0
