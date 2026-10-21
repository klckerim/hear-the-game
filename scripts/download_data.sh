#!/usr/bin/env bash
# Downloads the open data used ONLY for calibration into data/raw/ (git-ignored, never redistributed).
#   StatsBomb Open Data: first 40 matches of Premier League 2015/16 (competition 2, season 27)
#   SkillCorner Open Data: 3 matches of broadcast tracking + season physical aggregates
# Licences: StatsBomb asks for attribution (see https://github.com/hudl/open-data); SkillCorner data is MIT.
set -euo pipefail
cd "$(dirname "$0")/.."
SB=https://raw.githubusercontent.com/hudl/open-data/master/data
SC_RAW=https://raw.githubusercontent.com/SkillCorner/opendata/master/data
SC_LFS=https://media.githubusercontent.com/media/SkillCorner/opendata/master/data
mkdir -p data/raw/statsbomb/events data/raw/skillcorner

curl -sSf "$SB/matches/2/27.json" -o data/raw/statsbomb/matches_2_27.json
python3 -c "import json;m=json.load(open('data/raw/statsbomb/matches_2_27.json'));print('\n'.join(str(x['match_id']) for x in sorted(m,key=lambda x:x['match_id'])[:40]))" \
  > data/raw/statsbomb/ids.txt
xargs -P 8 -I{} curl -sSf "$SB/events/{}.json" -o "data/raw/statsbomb/events/{}.json" < data/raw/statsbomb/ids.txt

for id in 2017461 2016236 2015213; do
  mkdir -p "data/raw/skillcorner/$id"
  curl -sSfL "$SC_LFS/matches/$id/${id}_tracking_extrapolated.jsonl" -o "data/raw/skillcorner/$id/tracking.jsonl"
done
curl -sSfL "$SC_RAW/aggregates/aus1league_physicalaggregates_20242025.csv" -o data/raw/skillcorner/physical_aggregates.csv
echo "done: $(ls data/raw/statsbomb/events | wc -l) StatsBomb matches, $(ls -d data/raw/skillcorner/*/ | wc -l) SkillCorner matches"
