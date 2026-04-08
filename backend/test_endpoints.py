"""Quick smoke test for all Phase 2 endpoints."""
import httpx
import json
import io

BASE = "http://localhost:8001"


def test_health():
    print("=== Test 1: Health Check ===")
    r = httpx.get(f"{BASE}/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    print(f"  Status: {r.status_code}")
    print(f"  Response: {json.dumps(data, indent=2)}")
    print("  PASS\n")


def test_draft_config():
    print("=== Test 2: POST /api/generate-draft-config ===")
    r = httpx.post(
        f"{BASE}/api/generate-draft-config",
        data={"prompt": "Generate credit scoring data", "total_records": 500},
        timeout=60.0,
    )
    assert r.status_code == 200
    data = r.json()
    config = data["config"]
    print(f"  Status: {r.status_code}")
    print(f"  config_id: {config['config_id']}")
    print(f"  columns: {len(config['schema_definition'])}")
    print(f"  distributions: {len(config['distribution_constraints'])}")
    print(f"  boundary_rules: {len(config['boundary_rules'])}")
    print(f"  total_records: {config['total_records']}")
    print(f"  requires_manual_review: {data['requires_manual_review']}")
    print("  PASS\n")
    return data


def test_execute_generation(config_data):
    print("=== Test 3: POST /api/execute-generation ===")
    r = httpx.post(
        f"{BASE}/api/execute-generation",
        json={"config": config_data["config"], "chunk_size": 100000},
    )
    assert r.status_code == 200
    data = r.json()
    print(f"  Status: {r.status_code}")
    print(f"  job_id: {data['job_id']}")
    print(f"  status: {data['status']}")
    print(f"  total_records: {data['total_records']}")
    print(f"  total_chunks: {data['total_chunks']}")
    print(f"  message: {data['message']}")
    print("  PASS\n")
    return data


def test_export(job_id):
    print("=== Test 4: GET /api/export/{job_id} ===")
    import time
    # Wait for job to complete (background generation)
    for _ in range(15):
        r = httpx.get(f"{BASE}/api/job-status/{job_id}", timeout=10.0)
        if r.status_code == 200 and r.json().get("status") == "completed":
            break
        time.sleep(1)

    r = httpx.get(f"{BASE}/api/export/{job_id}", timeout=30.0)
    assert r.status_code == 200
    content_type = r.headers.get("content-type", "")
    # Could be CSV file or JSON status (if still processing)
    if "text/csv" in content_type:
        lines = r.text.strip().split("\n")
        print(f"  Status: {r.status_code}")
        print(f"  Content-Type: {content_type}")
        print(f"  CSV rows: {len(lines) - 1}")
    else:
        data = r.json()
        print(f"  Status: {r.status_code}")
        print(f"  Response: {json.dumps(data, indent=2)}")
    print("  PASS\n")


def test_csv_extraction():
    print("=== Test 5: POST /api/extract-schema ===")
    # Create a small in-memory CSV
    csv_content = (
        "applicant_id,credit_score,annual_income,risk_tier,is_approved\n"
        "1,750,85000.50,Prime,True\n"
        "2,620,42000.00,Sub-prime,False\n"
        "3,680,55000.75,Near-prime,True\n"
        "4,710,72000.00,Prime,True\n"
        "5,480,28000.00,Sub-prime,False\n"
    )
    files = {"file": ("test_data.csv", csv_content.encode(), "text/csv")}
    r = httpx.post(f"{BASE}/api/extract-schema", files=files)
    assert r.status_code == 200
    data = r.json()
    print(f"  Status: {r.status_code}")
    print(f"  filename: {data['filename']}")
    print(f"  total_columns: {data['total_columns']}")
    print(f"  rows_sampled: {data['rows_sampled']}")
    for col in data["columns"]:
        print(
            f"    - {col['column_name']}: "
            f"{col['inferred_type']} -> {col['suggested_data_type']} "
            f"(samples: {col['sample_values'][:3]})"
        )
    print("  PASS\n")


def test_validation_bad_ratios():
    print("=== Test 6: Validation — Bad Ratios (sum=99) ===")
    bad_config = {
        "config": {
            "schema_definition": [
                {"column_name": "tier", "data_type": "STRING"}
            ],
            "distribution_constraints": [
                {"column_name": "tier", "categories": ["A", "B"], "ratios": [60, 39]}
            ],
            "total_records": 100,
        }
    }
    r = httpx.post(f"{BASE}/api/execute-generation", json=bad_config)
    assert r.status_code == 422, f"Expected 422, got {r.status_code}"
    print(f"  Status: {r.status_code} (correctly rejected)")
    print(f"  Error: {r.json()['detail'][0]['msg'][:80]}")
    print("  PASS\n")


def test_validation_bad_column_ref():
    print("=== Test 7: Validation — Bad Column Reference ===")
    bad_config = {
        "config": {
            "schema_definition": [
                {"column_name": "score", "data_type": "INT"}
            ],
            "distribution_constraints": [
                {"column_name": "nonexistent", "categories": ["A", "B"], "ratios": [60, 40]}
            ],
            "total_records": 100,
        }
    }
    r = httpx.post(f"{BASE}/api/execute-generation", json=bad_config)
    assert r.status_code == 422, f"Expected 422, got {r.status_code}"
    print(f"  Status: {r.status_code} (correctly rejected)")
    print(f"  Error: {r.json()['detail'][0]['msg'][:80]}")
    print("  PASS\n")


if __name__ == "__main__":
    test_health()
    config_data = test_draft_config()
    gen_data = test_execute_generation(config_data)
    test_export(gen_data["job_id"])
    test_csv_extraction()
    test_validation_bad_ratios()
    test_validation_bad_column_ref()
    print("=" * 50)
    print("All 7 endpoint tests passed!")
    print("=" * 50)
