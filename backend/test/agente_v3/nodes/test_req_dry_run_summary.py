"""_format_dry_run_summary debe listar los pasos que devuelve WorkflowExecutor.execute_dry_run()
(clave "trace"), no decir "sin pasos para simular"."""

from app.agent.shifu_base_v1.graph.req_nodes import _format_dry_run_summary


def _executor_result(trace):
    # Misma forma que devuelve execute_dry_run() (workflow_executor.py).
    return {
        "dry_run": True,
        "workflow_id": "wf1",
        "workflow_name": "demo",
        "total_steps": len(trace),
        "steps_simulated": sum(1 for t in trace if t.get("skipped_real_call")),
        "stopped_early": False,
        "trace": trace,
        "status": "simulated",
    }


def test_summary_lists_steps_from_executor_trace():
    trace = [
        {"order": 1, "type": "action", "name": "Leer correo", "action": "gmail_read",
         "app": "gmail", "mock_result": "[DRY RUN] gmail_read (app=gmail) — simulated OK",
         "skipped_real_call": True},
        {"order": 2, "type": "condition", "name": "Es urgente", "passed": True,
         "jump_to": None, "skipped_real_call": False},
    ]
    summary = _format_dry_run_summary(_executor_result(trace))

    assert "sin pasos para simular" not in summary
    assert "- Leer correo: [DRY RUN] gmail_read (app=gmail) — simulated OK" in summary
    assert "- Es urgente: condición cumplida" in summary


def test_summary_reports_no_steps_when_trace_is_empty():
    summary = _format_dry_run_summary(_executor_result([]))
    assert "sin pasos para simular" in summary


def test_summary_falls_back_to_legacy_step_trace_key():
    trace = [{"order": 1, "type": "action", "action": "sheets_append",
              "mock_result": "ok", "skipped_real_call": True}]
    summary = _format_dry_run_summary({"step_trace": trace})
    assert "- sheets_append: ok" in summary
