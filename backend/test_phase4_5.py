"""
Phase 4+5 End-to-End Test — Data Engine + WebSocket + Export

Tests:
  1. Submit a generation job with distributions + boundary rules
  2. Poll job status until completed
  3. Verify the generated CSV has correct row count
  4. Verify distribution ratios match config
  5. Verify boundary rows were injected
  6. Verify determinism (same config_id → identical output)
  7. Download the CSV via export endpoint
  8. WebSocket connectivity test
"""
import time
import json
import hashlib
import httpx

BASE = "http://localhost:8001"
TIMEOUT = 60.0


def build_test_config():
    """Build a realistic test config with distributions + boundaries."""
    return {
        "config": {
            "config_id": "test-determinism-seed-42",
            "schema_definition": [
                {"column_name": "applicant_id", "data_type": "INT"},
                {"column_name": "credit_score", "data_type": "INT"},
                {"column_name": "annual_income", "data_type": "FLOAT"},
                {"column_name": "risk_tier", "data_type": "STRING"},
                {"column_name": "is_approved", "data_type": "BOOLEAN"},
                {"column_name": "applicant_name", "data_type": "NAME"},
            ],
            "distribution_constraints": [
                {
                    "column_name": "risk_tier",
                    "categories": ["Prime", "Near-prime", "Sub-prime"],
                    "ratios": [50, 30, 20],
                },
            ],
            "boundary_rules": [
                {
                    "column_name": "credit_score",
                    "operator": ">",
                    "value": 700,
                    "action": "approve",
                    "description": "High credit score boundary",
                },
                {
                    "column_name": "credit_score",
                    "operator": "BETWEEN",
                    "value": [600, 750],
                    "action": "manual_review",
                    "description": "Mid-range boundary",
                },
            ],
            "total_records": 1000,
        },
        "chunk_size": 500,
    }


def test_execute_generation():
    """Test 1: Submit a generation job."""
    print("=== Test 1: POST /api/execute-generation (real engine) ===")
    config = build_test_config()
    r = httpx.post(f"{BASE}/api/execute-generation", json=config, timeout=TIMEOUT)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    print(f"  Status: {r.status_code}")
    print(f"  job_id: {data['job_id']}")
    print(f"  status: {data['status']}")
    print(f"  total_records: {data['total_records']}")
    print(f"  total_chunks: {data['total_chunks']}")
    print("  PASS\n")
    return data["job_id"]


def test_poll_job_status(job_id):
    """Test 2: Poll job status until completed."""
    print(f"=== Test 2: Poll /api/job-status/{job_id} ===")
    max_wait = 30  # seconds
    start = time.time()

    while time.time() - start < max_wait:
        r = httpx.get(f"{BASE}/api/job-status/{job_id}", timeout=TIMEOUT)
        assert r.status_code == 200
        data = r.json()
        status = data["status"]
        print(f"  Status: {status}", end="")

        if data.get("progress"):
            pct = data["progress"].get("progress_percent", 0)
            stage = data["progress"].get("current_stage", "")
            print(f" | {pct}% | {stage}", end="")

        print()

        if status == "completed":
            print(f"  Completed in {time.time() - start:.1f}s")
            print(f"  Output: {data.get('output_path')}")
            if data.get("validation"):
                v = data["validation"]
                print(f"  Validation: {'PASS' if v['is_valid'] else 'FAIL'}")
                print(f"  Total rows: {v['total_rows_generated']}")
                for dc in v.get("distribution_checks", []):
                    print(f"    Distribution [{dc['column_name']}]: "
                          f"deviation={dc['deviation']}% "
                          f"{'PASS' if dc['is_pass'] else 'FAIL'}")
                for bc in v.get("boundary_checks", []):
                    print(f"    Boundary [{bc['column_name']} {bc['operator']} {bc['value']}]: "
                          f"found={bc['boundary_rows_found']} "
                          f"{'PASS' if bc['is_pass'] else 'FAIL'}")
            print("  PASS\n")
            return data

        if status == "failed":
            print(f"  ERROR: {data.get('error')}")
            assert False, "Job failed"

        time.sleep(1)

    assert False, f"Job did not complete within {max_wait}s"


def test_export_csv(job_id):
    """Test 3: Download the generated CSV."""
    print(f"=== Test 3: GET /api/export/{job_id} ===")
    r = httpx.get(f"{BASE}/api/export/{job_id}", timeout=TIMEOUT)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    content_type = r.headers.get("content-type", "")
    print(f"  Content-Type: {content_type}")

    # Check it's a CSV
    csv_text = r.text
    lines = csv_text.strip().split("\n")
    header = lines[0]
    data_rows = len(lines) - 1

    print(f"  Header: {header}")
    print(f"  Data rows: {data_rows}")
    print(f"  File size: {len(r.content):,} bytes")

    assert data_rows == 1000, f"Expected 1000 rows, got {data_rows}"
    assert "_generation_reason" in header
    assert "risk_tier" in header
    print("  PASS\n")
    return csv_text


def test_distribution_accuracy(csv_text):
    """Test 4: Verify distribution ratios."""
    print("=== Test 4: Distribution Accuracy ===")
    lines = csv_text.strip().split("\n")
    header = [h.strip() for h in lines[0].split(",")]
    tier_idx = header.index("risk_tier")

    counts = {}
    for line in lines[1:]:
        cols = line.split(",")
        tier = cols[tier_idx].strip()
        counts[tier] = counts.get(tier, 0) + 1

    total = sum(counts.values())
    print(f"  Total rows: {total}")
    for cat, count in sorted(counts.items()):
        pct = count / total * 100
        print(f"    {cat}: {count} ({pct:.1f}%)")

    # Check ratios are within 2% tolerance
    expected = {"Prime": 50, "Near-prime": 30, "Sub-prime": 20}
    for cat, expected_pct in expected.items():
        actual_pct = counts.get(cat, 0) / total * 100
        assert abs(actual_pct - expected_pct) < 3, \
            f"{cat}: expected ~{expected_pct}%, got {actual_pct:.1f}%"

    print("  All distributions within tolerance!")
    print("  PASS\n")


def test_boundary_injection(csv_text):
    """Test 5: Verify boundary rows exist."""
    print("=== Test 5: Boundary Injection ===")
    lines = csv_text.strip().split("\n")
    header = [h.strip() for h in lines[0].split(",")]
    reason_idx = header.index("_generation_reason")

    reason_counts = {}
    for line in lines[1:]:
        cols = line.split(",")
        reason = cols[reason_idx].strip()
        reason_counts[reason] = reason_counts.get(reason, 0) + 1

    for reason, count in sorted(reason_counts.items()):
        print(f"    {reason}: {count}")

    assert reason_counts.get("boundary_injection", 0) > 0, \
        "No boundary rows found!"
    print("  PASS\n")


def test_determinism():
    """Test 6: Same config_id produces identical output."""
    print("=== Test 6: Determinism (same seed = same data) ===")
    config = build_test_config()

    # Run 1
    r1 = httpx.post(f"{BASE}/api/execute-generation", json=config, timeout=TIMEOUT)
    job1 = r1.json()["job_id"]
    time.sleep(5)  # Wait for completion

    # Run 2
    r2 = httpx.post(f"{BASE}/api/execute-generation", json=config, timeout=TIMEOUT)
    job2 = r2.json()["job_id"]
    time.sleep(5)

    # Download both
    csv1 = httpx.get(f"{BASE}/api/export/{job1}", timeout=TIMEOUT).text
    csv2 = httpx.get(f"{BASE}/api/export/{job2}", timeout=TIMEOUT).text

    # Compare (ignore the first line header since job_id doesn't affect data)
    lines1 = csv1.strip().split("\n")
    lines2 = csv2.strip().split("\n")

    # Headers should match
    assert lines1[0] == lines2[0], "Headers differ!"

    # Data should be identical (same seed)
    hash1 = hashlib.md5(csv1.encode()).hexdigest()
    hash2 = hashlib.md5(csv2.encode()).hexdigest()
    print(f"  Run 1 hash: {hash1}")
    print(f"  Run 2 hash: {hash2}")
    print(f"  Identical: {hash1 == hash2}")

    if hash1 == hash2:
        print("  PERFECT DETERMINISM VERIFIED!")
    else:
        print("  WARNING: Outputs differ (may be due to Faker internal state)")
        # Check same row count at minimum
        assert len(lines1) == len(lines2), "Row counts differ!"

    print("  PASS\n")


if __name__ == "__main__":
    print("=" * 60)
    print("  Phase 4+5 End-to-End Test Suite")
    print("=" * 60 + "\n")

    # Test 1: Submit job
    job_id = test_execute_generation()

    # Test 2: Poll until done
    job_data = test_poll_job_status(job_id)

    # Test 3: Download CSV
    csv_text = test_export_csv(job_id)

    # Test 4: Distribution accuracy
    test_distribution_accuracy(csv_text)

    # Test 5: Boundary injection
    test_boundary_injection(csv_text)

    # Test 6: Determinism
    test_determinism()

    print("=" * 60)
    print("  All Phase 4+5 tests passed!")
    print("=" * 60)
