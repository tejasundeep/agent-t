import sys
import os
import json
import time
import datetime

# Add root folder to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from routines import init_db, get_db_connection
from pipeline_engine import PipelineEngine

def test_pipeline_engine():
    print("Initializing test database...")
    init_db()

    # Define a sample test test_pipeline definition
    definition = {
        "variables": {
            "my_input": "Test_Value",
            "file_name": "test_output.txt"
        },
        "steps": [
            {
                "id": "step_a",
                "name": "Write Text File",
                "type": "tool",
                "action": "write_file",
                "args": {
                    "path": "{{variables.file_name}}",
                    "content": "This is a {{variables.my_input}} pipeline run."
                }
            },
            {
                "id": "step_b",
                "name": "Read Text File",
                "type": "tool",
                "action": "read_file",
                "args": {
                    "path": "{{variables.file_name}}"
                },
                "depends_on": ["step_a"]
            },
            {
                "id": "step_c",
                "name": "Process File Content in Python",
                "type": "python",
                "action": "content = steps['step_b']\nprocessed = content.upper()\nprint('Processed output:', processed)\noutput_len = len(processed)\n",
                "depends_on": ["step_b"]
            }
        ]
    }

    pipeline_id = "test_dag_pipeline"
    print(f"Creating pipeline '{pipeline_id}' in Database...")
    now = datetime.datetime.now()
    with get_db_connection() as conn:
        # Delete existing first if any
        conn.execute("DELETE FROM pipelines WHERE id = ?", (pipeline_id,))
        conn.execute(
            "INSERT INTO pipelines (id, name, description, definition, created_at) VALUES (?, ?, ?, ?, ?)",
            (pipeline_id, "Test DAG Pipeline", "Test description", json.dumps(definition), now.isoformat())
        )
        conn.commit()

    print("Running pipeline...")
    engine = PipelineEngine()
    run_id = engine.run(pipeline_id, {
        "my_input": "Dynamic_Runtime_Input"
    })
    print(f"Pipeline started. Run ID: {run_id}")

    # Wait for completion (max 10s)
    status = "running"
    for _ in range(20):
        time.sleep(0.5)
        with get_db_connection() as conn:
            row = conn.execute("SELECT status, outputs, error FROM pipeline_runs WHERE id = ?", (run_id,)).fetchone()
            if row:
                status = row['status']
                if status in ('completed', 'failed', 'canceled'):
                    print(f"Pipeline finished with status: {status}")
                    print(f"Outputs: {row['outputs']}")
                    print(f"Error: {row['error']}")
                    break

    # Clean up test output files
    if os.path.exists("test_output.txt"):
        os.remove("test_output.txt")
        print("Cleaned up 'test_output.txt'.")

    # Assertions
    assert status == 'completed', f"Pipeline failed with status: {status}"
    
    # Check steps log table
    with get_db_connection() as conn:
        logs = conn.execute("SELECT * FROM pipeline_run_logs WHERE run_id = ?", (run_id,)).fetchall()
        print("\nStep Logs:")
        for log in logs:
            print(f"- {log['step_id']} ({log['step_name']}): {log['status']}")
            assert log['status'] == 'success', f"Step {log['step_id']} was not success: {log['status']}"

    print("\nAll pipeline engine tests passed successfully!")

if __name__ == "__main__":
    test_pipeline_engine()
