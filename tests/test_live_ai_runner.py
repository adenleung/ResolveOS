"""Offline guard and accounting checks; never instantiate an OpenAI client."""
import pytest
from app.investigation.contracts import ModelTurn, Output
from app.investigation.provider import ProviderError, OpenAIProvider
from run_live_ai_test import Budget, MeteredProvider, ALLOWLIST, evaluate
import run_live_ai_test as runner
from types import SimpleNamespace


class FakeProvider:
    identifier = "offline-budget-test"
    def __init__(self, fail=False, excess=False):
        self.fail, self.excess, self.calls = fail, excess, 0
    def turn(self, *args):
        self.calls += 1
        if self.fail:
            raise RuntimeError("sensitive arbitrary exception must not be recorded")
        return ModelTurn(input_tokens=1_000_000 if self.excess else 100, output_tokens=20)


def invoke(provider):
    return provider.turn("read only", [{"role":"user", "content":'{"role":"TRANSACTION"}'}], [], 2048)


def test_queue_allowlist_excludes_all_action_handlers():
    assert not {"PREPARE_EXECUTION", "REQUEST_VERIFICATION", "REQUEST_HUMAN_REVIEW"} & ALLOWLIST


def test_shared_budget_settles_actual_usage_and_prevents_eleventh_request():
    budget = Budget()
    fake = FakeProvider()
    providers = [MeteredProvider(fake, budget, Output), MeteredProvider(fake, budget, Output)]
    for index in range(10):
        invoke(providers[index % 2])
    assert budget.tokens==1200
    assert budget.cost==pytest.approx(0.00072)
    with pytest.raises(ProviderError, match="global_test_budget_exhausted"):
        invoke(providers[0])
    assert fake.calls==10


@pytest.mark.parametrize("limit", ["tokens", "cost"])
def test_preflight_blocks_request_before_provider_call(limit):
    budget, fake = Budget(), FakeProvider()
    if limit=="tokens": budget.max_tokens=100
    else: budget.max_cost=0.000001
    with pytest.raises(ProviderError): invoke(MeteredProvider(fake, budget, Output))
    assert fake.calls==0


def test_unknown_usage_reservation_is_retained_and_never_retried():
    budget, fake = Budget(), FakeProvider(fail=True)
    provider = MeteredProvider(fake, budget, Output)
    with pytest.raises(ProviderError, match="unexpected_RuntimeError"): invoke(provider)
    assert budget.cost>0 and budget.tokens>0
    assert "sensitive" not in str(budget.calls)
    with pytest.raises(ProviderError): invoke(provider)
    assert fake.calls==1
    class NativeWithoutUsage(OpenAIProvider):
        identifier = "offline-native-usage-test"
        def __init__(self): pass
        def turn(self, *args): return ModelTurn()
    budget = Budget()
    with pytest.raises(ProviderError, match="provider_usage_unobservable"):
        invoke(MeteredProvider(NativeWithoutUsage(), budget, Output))
    assert budget.halted and budget.cost>0 and budget.tokens>0
    assert budget.calls[0]["status"]=="USAGE_UNOBSERVABLE"


def test_usage_outside_bound_stops_further_requests():
    budget, fake = Budget(), FakeProvider(excess=True)
    with pytest.raises(ProviderError, match="preflight_bound"): invoke(MeteredProvider(fake, budget, Output))
    assert budget.halted


@pytest.mark.parametrize("case_id,kind", [("unrelated", "CLASSIFY_CASE"), ("target", "PREPARE_EXECUTION")])
def test_queue_poison_is_rejected_before_any_claim(monkeypatch, case_id, kind):
    session = SimpleNamespace(scalars=lambda query:SimpleNamespace(all=lambda:[SimpleNamespace(case_id=case_id, task_type=kind)]))
    def forbidden_queue(*args, **kwargs):
        pytest.fail("Queue must not be constructed or claimed for unsafe work")
    monkeypatch.setattr(runner, "WorkQueue", forbidden_queue)
    with pytest.raises(RuntimeError, match="unrelated_queue_task|unsafe_queue_task_type"):
        runner.claim_read_only(session, None, "target", "owner")


def test_evaluation_rechecks_sources_instead_of_trusting_supported_label():
    records = dict(investigations=[dict(role="TRANSACTION", status="COMPLETED", telemetry={"tools":[{"evidence_ids":["source"]}]},
        result={"findings":[dict(field="payment_status", expected_value="SETTLED", evidence_ids=["source"], assessment="SUPPORTED", verification="OBSERVED_FIELD_EQUALITY")]} )],
        source_events=[dict(id="source", payload={"payment_status":"FAILED"})], supervisor=[],
        controls=[], approvals=[], actions=[], operations=[], verifications=[], final_state="AWAITING_HUMAN")
    result = evaluate(records, Budget(), True)
    assert result["checks"]["citations_independently_rechecked"]
    assert not result["checks"]["predicates_independently_rechecked"]
    assert not result["automated_pass"]
    records["evidence"] = [dict(id="stored", integrity_metadata={"event_record_id":"source"})]
    records["supervisor"] = [dict(outcome="ESCALATE", result=dict(evidence_ids=["stored"],
        supported_conclusions=[dict(evidence_ids=["stored"], field="payment_status", expected_value="SETTLED")]))]
    result = evaluate(records, Budget(), True)
    assert not result["checks"]["supervisor_citations_independently_rechecked"]


def test_evaluation_separates_rejected_findings_and_only_skips_expected_review():
    supported = dict(field="status_code", expected_value=504, evidence_ids=["source"], assessment="SUPPORTED", verification="OBSERVED_FIELD_EQUALITY")
    records = dict(investigations=[dict(role="TRANSACTION", status="NEEDS_ADDITIONAL_EVIDENCE",
        telemetry={"tools":[{"evidence_ids":["source"]}]}, result=dict(action_authorization="NOT_EVALUATED",
        findings=[supported, dict(field="status_code", expected_value=200, evidence_ids=["source"], assessment="CONTRADICTED"),
                  dict(field="confirmation_status", expected_value="MISSING", evidence_ids=[], assessment="INSUFFICIENT_EVIDENCE")]))],
        source_events=[dict(id="source", payload={"status_code":504})], supervisor=[], controls=[], approvals=[], actions=[], operations=[], verifications=[], final_state="AWAITING_HUMAN")
    result = evaluate(records, Budget(), True)
    for name in ("citations_independently_rechecked", "predicates_independently_rechecked", "no_unsupported_accepted_predicates"):
        assert result["checks"][name] is True
    assert all(len(result["finding_groups"][name])==1 for name in ("SUPPORTED", "CONTRADICTED", "INSUFFICIENT_EVIDENCE"))
    assert result["check_statuses"]["supervisor_completed"]=="NOT RUN"
    assert not result["automated_pass"] and not result["workflow_complete"]
    for status in ("COMPLETED", "FAILED"):
        records["investigations"][0]["status"] = status
        assert evaluate(records, Budget(), True)["check_statuses"]["supervisor_completed"]=="FAIL"
    records["investigations"] = []
    assert evaluate(records, Budget(), True)["check_statuses"]["supervisor_completed"]=="FAIL"


def test_incomplete_specialists_stop_at_unclaimed_human_review(monkeypatch, tmp_path):
    import json
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://resolve:resolve@127.0.0.1:5433/resolveos")
    original = runner.ObservedDemoSpecialist
    class IncompleteSpecialist(original):
        def turn(self, *args):
            turn = super().turn(*args)
            if turn.output:
                turn.output.outcome = "NEEDS_ADDITIONAL_EVIDENCE"
                turn.output.missing_evidence = ["Confirmation receipt and downstream health unavailable"]
            return turn
    monkeypatch.setattr(runner, "ObservedDemoSpecialist", IncompleteSpecialist)
    output = tmp_path/"incomplete"
    assert runner.execute(False, output)==1
    result = json.loads((output/"results.json").read_text())
    assert result["stop_reason"]=="human_review_required"
    assert "error_code" not in result
    assert result["last_completed_stage"]=="INVESTIGATE_TRANSACTION"
    assert result["records"]["final_state"]=="AWAITING_HUMAN"
    assert result["records"]["supervisor"]==[]
    review = next(t for t in result["records"]["tasks"] if t["task_type"]=="REQUEST_HUMAN_REVIEW")
    assert review["attempt_count"]==0 and review["status"]=="WAITING_HANDLER"
    assert not result["evaluation"]["automated_pass"]
    assert result["evaluation"]["checks"]["no_authorization_or_execution"]
    assert result["database_cleanup"]=="DROPPED"


def test_safe_diagnostics_never_export_unrestricted_messages():
    assert runner.safe_error_code(RuntimeError("Authorization: Bearer sensitive"))=="unexpected_RuntimeError"
    assert runner.safe_error_code(ProviderError("postgresql://private:password@host"))=="unexpected_ProviderError"
    assert runner.safe_error_code(runner.HarnessError("Authorization: Bearer sensitive"))=="unexpected_harness_error"


def test_harness_failure_preserves_completed_stage_and_case_snapshot(monkeypatch, tmp_path):
    import json
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://resolve:resolve@127.0.0.1:5433/resolveos")
    original = runner.claim_read_only
    invocations = 0
    def fail_second_claim(*args):
        nonlocal invocations
        invocations += 1
        if invocations==2:
            raise RuntimeError("Authorization: Bearer sensitive; postgresql://private:password@host")
        return original(*args)
    monkeypatch.setattr(runner, "claim_read_only", fail_second_claim)
    output = tmp_path/"harness-failure"
    assert runner.execute(False, output)==1
    r = json.loads((output/"results.json").read_text())
    assert r["error_code"]=="unexpected_RuntimeError"
    assert r["last_completed_stage"]=="CLASSIFY_CASE"
    assert r["current_stage"]=="queue_preflight"
    assert r["records"]["tasks"] and r["queue_snapshot"]
    assert "sensitive" not in (output/"results.json").read_text()


def test_human_review_cannot_mask_unrelated_or_action_tasks():
    human = SimpleNamespace(case_id="target", task_type="REQUEST_HUMAN_REVIEW", status="WAITING_HANDLER", attempt_count=0)
    for case_id, kind, code in [("other", "REQUEST_HUMAN_REVIEW", "unrelated_queue_task"), ("target", "PREPARE_EXECUTION", "unsafe_queue_task_type")]:
        session = SimpleNamespace(scalars=lambda q:SimpleNamespace(all=lambda:[human, SimpleNamespace(case_id=case_id, task_type=kind)]))
        with pytest.raises(runner.HarnessError, match=code):
            runner.assert_read_only_queue(session, "target")


def test_saved_live_outputs_replay_offline_with_validation_intact(monkeypatch, tmp_path):
    import copy
    import json
    from pathlib import Path
    from app.investigation.contracts import ToolCall
    fixture = json.loads((Path(__file__).parent/"fixtures/live_ai_incomplete_outputs.json").read_text())
    class ReplayProvider:
        identifier = "offline-recorded-live-replay"
        def turn(self, instructions, messages, tools, cap):
            meta = json.loads(messages[0]["content"])
            recorded = fixture[meta["role"]]
            if len(messages)==1:
                calls = copy.deepcopy(recorded["calls"])
                for call in calls:
                    args = call["arguments"]
                    if "payment_id" in args: args["payment_id"] = meta["entities"][0]
                    if "correlation_id" in args: args["correlation_id"] = meta["traces"][0]
                    if "start" in args: args.update(start=None, end=None)
                return ModelTurn(calls=[ToolCall.model_validate(c) for c in calls])
            events = {e["id"]:e for m in messages if m.get("type")=="function_call_output" for e in json.loads(m["output"]).get("evidence", [])}
            output = copy.deepcopy(recorded["output"])
            refs = {}
            for finding in output["findings"]:
                field = finding["field"]
                if finding["evidence_ids"]:
                    observed = next(e for e in events.values() if field in e["payload"])
                    refs.update({old:observed["id"] for old in finding["evidence_ids"]})
                    finding["evidence_ids"] = [observed["id"]]
            for hypothesis in output["hypotheses"]:
                for key in ("supporting_evidence_ids", "contradicting_evidence_ids"):
                    hypothesis[key] = [refs[ref] for ref in hypothesis[key]]
            return ModelTurn(output=Output.model_validate(output))
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://resolve:resolve@127.0.0.1:5433/resolveos")
    monkeypatch.setattr(runner, "ObservedDemoSpecialist", ReplayProvider)
    output = tmp_path/"recorded-replay"
    assert runner.execute(False, output)==1
    r = json.loads((output/"results.json").read_text())
    assert r["stop_reason"]=="human_review_required" and "error_code" not in r
    assert len(r["calls"])==4 and not r["records"]["supervisor"]
    tx = next(i for i in r["records"]["investigations"] if i["role"]=="TRANSACTION")
    assert tx["status"]=="NEEDS_ADDITIONAL_EVIDENCE"
    status = next(f for f in tx["result"]["findings"] if f["field"]=="status_code")
    assert status["assessment"]=="SUPPORTED" and status["expected_value"]==504
    assert status["normalization"]["original_value"]=="504"
    assert next(f for f in tx["result"]["findings"] if not f["evidence_ids"])["assessment"]=="INSUFFICIENT_EVIDENCE"
    assert all(t["attempt_count"]==0 for t in r["queue_snapshot"] if t["task_type"]=="REQUEST_HUMAN_REVIEW")
    assert r["evaluation"]["check_statuses"]["supervisor_completed"]=="NOT RUN"
    assert r["evaluation"]["checks"]["no_unsupported_accepted_predicates"]


def test_powershell_launcher_propagates_incomplete_evaluation_exit(monkeypatch, tmp_path):
    import json
    import subprocess
    from pathlib import Path
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://resolve:resolve@127.0.0.1:5433/resolveos")
    root = Path(runner.__file__).parent
    output = tmp_path/"launcher-incomplete"
    # Copy the launcher and replace only its offline invocation with the real
    # runner under a one-request test budget. No validation bypass or live call.
    code = "import run_live_ai_test as r; from pathlib import Path; r.Budget.max_requests=1; raise SystemExit(r.execute(False, Path("+repr(str(output))+")))"
    script = (root/"Run-LiveAITest.ps1").read_text()
    script = script.replace("$PSScriptRoot", "'"+str(root).replace("'", "''")+"'")
    script = script.replace("& $testPython run_live_ai_test.py --scenario $Scenario }", "& $testPython -c '"+code.replace("'", "''")+"' }")
    target = tmp_path/"launcher-test.ps1"
    target.write_text(script, encoding="utf-8")
    result = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(target), "-Offline"], capture_output=True, timeout=120)
    assert result.returncode==1
    r = json.loads((output/"results.json").read_text())
    assert not r["evaluation"]["automated_pass"] and r["api_requests_attempted"]==0
