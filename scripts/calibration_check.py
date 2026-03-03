"""
Model Calibration Validation Script

Checks whether the predicted confidence levels actually match empirical hit rates.
A well-calibrated model should have ~70% actual hit rate for picks made at 70% confidence.

Usage:
    cd EVAL
    python scripts/calibration_check.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import db


def run_calibration_check():
    conn = db.get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT confidence, won
        FROM picks
        WHERE won IS NOT NULL
          AND confidence IS NOT NULL
          AND (voided IS NULL OR voided = 0)
        ORDER BY confidence
    """)
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print("No graded picks found in database.")
        return

    # Bucket by confidence decile
    buckets = {}
    for row in rows:
        conf = row['confidence'] if isinstance(row, dict) else row[0]
        won = row['won'] if isinstance(row, dict) else row[1]
        if conf is None or won is None:
            continue
        bucket = int(conf // 10) * 10  # e.g. 0.72 -> 70, 0.85 -> 80
        if bucket not in buckets:
            buckets[bucket] = {'total': 0, 'wins': 0}
        buckets[bucket]['total'] += 1
        buckets[bucket]['wins'] += int(won)

    print("\n=== Model Calibration Report ===")
    print(f"{'Conf Bucket':>12} {'Picks':>7} {'Actual Hit%':>12} {'Delta':>8} {'Status':>10}")
    print("-" * 55)

    issues = []
    for bucket in sorted(buckets):
        data = buckets[bucket]
        total = data['total']
        if total < 5:
            continue
        actual_rate = data['wins'] / total
        expected = (bucket + 5) / 100  # midpoint of bucket
        delta = actual_rate - expected
        status = "OK"
        if abs(delta) > 0.10:
            status = "OVERCONF" if delta < 0 else "UNDERCONF"
            issues.append((bucket, expected, actual_rate, delta))

        print(f"{bucket:>10}%-{bucket+9}%  {total:>7}  {actual_rate*100:>10.1f}%  {delta*100:>+7.1f}%  {status:>10}")

    print(f"\nTotal graded picks: {len(rows)}")

    if issues:
        print("\n[!] CALIBRATION ISSUES DETECTED:")
        for bucket, expected, actual, delta in issues:
            direction = "overconfident" if delta < 0 else "underconfident"
            print(f"    {bucket}%-{bucket+9}% bucket: model is {direction} by {abs(delta)*100:.1f}pp "
                  f"(predicted ~{expected*100:.0f}%, actual {actual*100:.1f}%)")
    else:
        print("\n[OK] Model appears well-calibrated (all buckets within 10pp of expected).")


if __name__ == "__main__":
    run_calibration_check()
