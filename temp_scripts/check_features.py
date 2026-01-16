#!/usr/bin/env python3
"""Quick script to check feature status"""
import json
import sys

with open('feature_list.json') as f:
    features = json.load(f)

passing = [f for f in features if f.get('passes')]
failing = [f for f in features if not f.get('passes') and not f.get('deprecated')]
needs_reverif = [f for f in features if f.get('needs_reverification')]
deprecated = [f for f in features if f.get('deprecated')]

print("=== FEATURE SUMMARY ===")
print(f"Total: {len(features)}")
print(f"Passing: {len(passing)}")
print(f"Failing: {len(failing)}")
print(f"Needs reverification: {len(needs_reverif)}")
print(f"Deprecated: {len(deprecated)}")

# Get passing feature IDs
passing_ids = {f['id'] for f in passing}

# Find next features (dependencies satisfied)
def deps_satisfied(feature):
    deps = feature.get('depends_on', [])
    return all(dep in passing_ids for dep in deps)

ready = [f for f in failing if deps_satisfied(f)]
blocked = [f for f in failing if not deps_satisfied(f) and f.get('depends_on')]

# Sort by priority
priority_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
ready.sort(key=lambda f: priority_order.get(f.get('priority', 'medium'), 3))

print("\n=== NEXT FEATURES TO WORK ON (dependencies satisfied) ===")
for f in ready[:10]:
    desc = f['description'][:60]
    priority = f.get('priority', 'medium')
    print(f"{f['id']}: [{priority}] {desc}")

print("\n=== BLOCKED FEATURES (waiting on dependencies) ===")
for f in blocked[:5]:
    deps = f.get('depends_on', [])
    missing = [d for d in deps if d not in passing_ids]
    print(f"{f['id']}: blocked by {', '.join(missing)}")

print("\n=== NEEDS REVERIFICATION ===")
for f in needs_reverif[:5]:
    desc = f['description'][:60]
    reason = (f.get('reverification_reason') or 'expanded')[:40]
    print(f"{f['id']}: {desc} - {reason}")
