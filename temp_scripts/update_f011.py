#!/usr/bin/env python3
"""Update F011 to mark it as passing"""
import json
from datetime import datetime, timezone

with open('feature_list.json') as f:
    features = json.load(f)

# Find F011 and update it
for feature in features:
    if feature['id'] == 'F011':
        feature['passes'] = True
        feature['passed_at'] = datetime.now(timezone.utc).isoformat()
        print(f"Updated F011: passes={feature['passes']}, passed_at={feature['passed_at']}")
        break

# Write back
with open('feature_list.json', 'w') as f:
    json.dump(features, f, indent=2)

print("feature_list.json updated successfully")
