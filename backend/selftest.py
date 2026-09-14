"""End-to-end acceptance suite for the HR Talent System.

Exercises the running API the way the UI does: authentication, role gating,
data validation, the deterministic scoring engine and the extension features.
Standard library only, so it runs anywhere Python does.

    python selftest.py --base http://localhost:8000

Exit code 0 when everything passes, 1 otherwise.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid

BASE = "http://localhost:8000"

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"
results = []
_section = {"name": "general"}


# ---------------------------------------------------------------------------
# Tiny HTTP helper
# ---------------------------------------------------------------------------

def call(method, path, body=None, token=None, raw=None, content_type=None):
    """Return (status, parsed_body). Never raises for HTTP error codes."""
    url = path if path.startswith("http") else BASE + path
    data = raw
    headers = {}

    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if content_type:
        headers["Content-Type"] = content_type
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read()
            try:
                return response.status, json.loads(payload)
            except (ValueError, UnicodeDecodeError):
                return response.status, payload
    except urllib.error.HTTPError as e:
        payload = e.read()
        try:
            return e.code, json.loads(payload)
        except (ValueError, UnicodeDecodeError):
            return e.code, payload
    except urllib.error.URLError as e:
        return 0, {"detail": str(e)}


def multipart(fields, files):
    """Build a multipart/form-data body. files: [(name, filename, ctype, bytes)]"""
    boundary = "----selftest" + uuid.uuid4().hex
    out = b""
    for key, value in fields.items():
        out += (f"--{boundary}\r\nContent-Disposition: form-data; "
                f'name="{key}"\r\n\r\n{value}\r\n').encode()
    for name, filename, ctype, blob in files:
        out += (f"--{boundary}\r\nContent-Disposition: form-data; "
                f'name="{name}"; filename="{filename}"\r\n'
                f"Content-Type: {ctype}\r\n\r\n").encode()
        out += blob + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return out, f"multipart/form-data; boundary={boundary}"


# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------

def section(name):
    _section["name"] = name
    print(f"\n\033[1m{name}\033[0m")


def check(description, condition, detail=""):
    status = PASS if condition else FAIL
    results.append((_section["name"], description, status, detail))
    mark = "\033[32mPASS\033[0m" if condition else "\033[31mFAIL\033[0m"
    line = f"  [{mark}] {description}"
    if detail and not condition:
        line += f"\n         {detail}"
    print(line)
    return bool(condition)


def skip(description, why):
    results.append((_section["name"], description, SKIP, why))
    print(f"  [\033[33mSKIP\033[0m] {description} - {why}")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_health():
    section("Service health")
    status, body = call("GET", "/health")
    check("API answers /health", status == 200, f"status={status}")
    check("Health payload is well formed",
          isinstance(body, dict) and body.get("status") == "ok", str(body)[:120])


def test_auth():
    section("Authentication")
    status, _ = call("GET", "/api/v1/employees")
    check("Unauthenticated request is refused", status == 401, f"status={status}")

    status, _ = call("GET", "/api/v1/employees",
                     token="eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiJ9.forged")
    check("Forged token is refused", status == 401, f"status={status}")

    status, body = call("POST", "/api/v1/auth/login",
                        {"username": "admin", "password": "wrong"})
    check("Wrong password is refused", status == 401, f"status={status}")

    status, admin = call("POST", "/api/v1/auth/login",
                         {"username": "admin", "password": "admin"})
    ok_admin = check("admin/admin signs in", status == 200 and "token" in (admin or {}),
                     f"status={status}")
    check("admin carries the admin role",
          ok_admin and admin.get("role") == "admin", str(admin)[:120])

    status, viewer = call("POST", "/api/v1/auth/login",
                          {"username": "user", "password": "user"})
    ok_viewer = check("user/user signs in", status == 200 and "token" in (viewer or {}),
                      f"status={status}")
    check("user carries the viewer role",
          ok_viewer and viewer.get("role") == "viewer", str(viewer)[:120])

    if not (ok_admin and ok_viewer):
        print("\n\033[31mCannot continue without both tokens.\033[0m")
        summarise()
        sys.exit(1)

    return admin["token"], viewer["token"]


def test_roles(admin, viewer):
    section("Role separation")

    status, _ = call("GET", "/api/v1/employees", token=viewer)
    check("viewer may read employees", status == 200, f"status={status}")

    status, _ = call("POST", "/api/v1/matching-runs", {"vacancy_id": 1}, token=viewer)
    check("viewer may run a matching analysis", status in (200, 201), f"status={status}")

    status, _ = call("GET", "/api/v1/audit-log", token=viewer)
    check("viewer is denied the audit trail", status == 403, f"status={status}")

    status, _ = call("POST", "/api/v1/reference/countries",
                     {"code": "ZZ", "name_ru": "x"}, token=viewer)
    check("viewer cannot edit catalogues", status == 403, f"status={status}")

    status, _ = call("POST", "/api/v1/employees",
                     {"last_name": "T", "first_name": "T", "department_id": 1},
                     token=viewer)
    check("viewer cannot create employees", status == 403, f"status={status}")

    status, _ = call("POST", "/api/v1/custom-fields",
                     {"entity_type": "employee", "name_ru": "x"}, token=viewer)
    check("viewer cannot define custom fields", status == 403, f"status={status}")

    status, _ = call("GET", "/api/v1/audit-log", token=admin)
    check("admin may read the audit trail", status == 200, f"status={status}")


def test_reference(admin):
    section("Reference data and localisation")

    status, body = call("GET", "/api/v1/reference/catalogs", token=admin)
    catalogs = (body or {}).get("catalogs", [])
    check("Catalogue index loads", status == 200 and len(catalogs) >= 15,
          f"status={status} count={len(catalogs)}")

    untranslated = [c["name"] for c in catalogs
                    if not (c.get("name_ru") and c.get("name_kk") and c.get("name_en"))]
    check("Every catalogue has ru/kk/en names", not untranslated, str(untranslated))

    slugs = [c["name"] for c in catalogs if c.get("name_ru") == c["name"]]
    check("No catalogue falls back to its raw slug", not slugs, str(slugs))

    status, body = call("GET", "/api/v1/reference/countries", token=admin)
    countries = (body or {}).get("data", [])
    check("Country catalogue is populated", len(countries) >= 80,
          f"count={len(countries)}")
    missing = [c["code"] for c in countries
               if not (c.get("name_ru") and c.get("name_kk") and c.get("name_en"))]
    check("Every country has three names", not missing, str(missing[:8]))

    status, body = call("GET", "/api/v1/reference/competencies", token=admin)
    competencies = (body or {}).get("data", [])
    check("Competency catalogue is populated", len(competencies) >= 10,
          f"count={len(competencies)}")

    # Nothing anywhere should carry the '?' corruption signature.
    mangled = []
    for name in ("countries", "competencies", "job-families", "requirement-types",
                 "org-unit-types", "education-levels", "assessment-scales"):
        _, payload = call("GET", f"/api/v1/reference/{name}", token=admin)
        for row in (payload or {}).get("data", []):
            for field in ("name_ru", "name_kk", "name_en"):
                value = row.get(field) or ""
                if "???" in value:
                    mangled.append(f"{name}.{row.get('code')}.{field}")
    check("No mangled (question-mark) text in reference data",
          not mangled, str(mangled[:6]))


def test_cefr(admin):
    section("Data validation (CEFR guard)")

    status, body = call("GET", "/api/v1/reference/language-scales", token=admin)
    scales = {s["code"]: s for s in (body or {}).get("data", [])}
    cefr = scales.get("CEFR")
    if not cefr:
        skip("CEFR scale present", "scale missing")
        return

    _, body = call("GET", "/api/v1/reference/language-levels", token=admin)
    levels = (body or {}).get("data", [])
    cefr_codes = sorted(l["code"] for l in levels if l.get("scale_id") == cefr["id"])
    check("CEFR holds exactly A1..C2",
          cefr_codes == ["A1", "A2", "B1", "B2", "C1", "C2"], str(cefr_codes))

    check("B3 does not exist in CEFR",
          not any(l["code"] == "B3" and l["scale_id"] == cefr["id"] for l in levels))

    # Build a throwaway corporate scale that *does* define B3, then prove the
    # API refuses to file that level under CEFR.
    suffix = uuid.uuid4().hex[:6]
    status, scale = call("POST", "/api/v1/reference/language-scales", {
        "code": f"SELFTEST_{suffix}", "name_ru": "Тестовая шкала",
        "name_kk": "Сынақ шкаласы", "name_en": "Selftest scale",
    }, token=admin)
    if status not in (200, 201):
        skip("Cross-scale level is rejected", f"could not create scale ({status})")
        return

    status, level = call("POST", "/api/v1/reference/language-levels", {
        "code": "B3", "name_ru": "B3", "name_kk": "B3", "name_en": "B3",
        "scale_id": scale["id"], "rank": 4,
    }, token=admin)
    created_level = status in (200, 201)
    check("B3 can exist in a corporate scale", created_level, f"status={status}")

    if created_level:
        status, body = call("POST", "/api/v1/employees/1/languages", {
            "language_id": 1, "scale_id": cefr["id"], "level_id": level["id"],
            "is_confirmed": True, "confirmed_at": "2026-01-01",
        }, token=admin)
        detail = (body or {}).get("detail", {})
        check("Storing B3 under CEFR is refused", status == 422, f"status={status}")
        check("The refusal lists the valid CEFR levels",
              isinstance(detail, dict) and detail.get("valid_levels") == [
                  "A1", "A2", "B1", "B2", "C1", "C2"],
              str(detail)[:150])
        call("DELETE", f"/api/v1/reference/language-levels/{level['id']}", token=admin)

    call("DELETE", f"/api/v1/reference/language-scales/{scale['id']}", token=admin)


def test_derived_metrics(admin):
    section("Derived figures (computed, never typed)")

    status, body = call("GET", "/api/v1/employees", token=admin)
    employees = (body or {}).get("data", [])
    check("Employee roster loads", status == 200 and employees, f"status={status}")
    if not employees:
        return None

    target = next((e for e in employees if e.get("anonymous_code") == "А"),
                  employees[0])
    status, summary = call("GET", f"/api/v1/employees/{target['id']}/summary",
                           token=admin)
    metrics = (summary or {}).get("metrics", {})
    check("Employee summary loads", status == 200, f"status={status}")

    check("Company tenure is derived",
          metrics.get("company_experience_years", 0) > 0,
          f"value={metrics.get('company_experience_years')}")
    check("Experience is split by professional function",
          any(k.startswith("function_experience_years:") for k in metrics),
          str(list(metrics)[:6]))
    check("Experience is split by org-unit type",
          any(k.startswith("org_unit_experience_years:") for k in metrics))
    check("Experience is split by country",
          any(k.startswith("country_experience_years:") for k in metrics))

    # Intervals must be unioned, not summed twice.
    total = metrics.get("total_experience_years", 0)
    company = metrics.get("company_experience_years", 0)
    check("Total experience is at least company tenure",
          total >= company - 0.01, f"total={total} company={company}")
    return target["id"]


def test_matching(admin):
    section("Deterministic matching engine")

    status, body = call("GET", "/api/v1/vacancies", token=admin)
    vacancies = (body or {}).get("data", [])
    ready = [v for v in vacancies if v.get("total_weight") == 100]
    check("A vacancy with balanced weights exists", bool(ready),
          f"vacancies={[(v['id'], v['total_weight']) for v in vacancies]}")
    if not ready:
        return

    unbalanced = [v for v in vacancies if v.get("total_weight") != 100]
    if unbalanced:
        status, _ = call("POST", "/api/v1/matching-runs",
                         {"vacancy_id": unbalanced[0]["id"]}, token=admin)
        check("Matching is refused when weights do not total 100",
              status == 422, f"status={status}")
    else:
        skip("Weight gate", "no unbalanced vacancy to test with")

    vacancy = ready[0]
    status, run = call("POST", "/api/v1/matching-runs",
                       {"vacancy_id": vacancy["id"]}, token=admin)
    ok_run = check("Matching run completes",
                   status in (200, 201) and (run or {}).get("status") == "completed",
                   f"status={status} body={str(run)[:140]}")
    if not ok_run:
        return

    status, res = call("GET", f"/api/v1/matching-runs/{run['id']}/results", token=admin)
    shortlist = (res or {}).get("shortlist", [])
    excluded = (res or {}).get("potential_after_development", [])
    check("Results load", status == 200 and shortlist, f"status={status}")
    if not shortlist:
        return

    scores = [c["score"] for c in shortlist]
    check("Short list is ordered by score, descending",
          scores == sorted(scores, reverse=True), str(scores))

    ranks = [c["system_rank"] for c in shortlist]
    check("Ranks are consecutive from 1",
          ranks == list(range(1, len(ranks) + 1)), str(ranks))

    check("Every score is within 0-100",
          all(0 <= s <= 100 for s in scores), str(scores))

    top = shortlist[0]
    lines = top["explanation"]["requirements"]
    expected_lines = vacancy.get("requirements_count") or 0
    check("Every requirement produces an explanation line",
          len(lines) == expected_lines,
          f"lines={len(lines)} requirements={expected_lines}")
    check("Each line shows fact, match and contribution",
          all({"fact", "m", "contribution", "weight", "status"} <= set(l) for l in lines))

    # Score must equal the weighted sum of the contributions.
    total_weight = top["explanation"].get("total_weight") or 0
    contributed = sum(l["contribution"] for l in lines)
    expected = round(contributed / total_weight * 100, 1) if total_weight else 0
    check("Score equals the sum of weighted contributions",
          abs(expected - top["score"]) <= 0.2,
          f"reported={top['score']} recomputed={expected}")

    check("Pseudonyms are shown by default",
          all(c["display_name"] == c["anonymous_code"] for c in shortlist),
          str([(c['display_name'], c['anonymous_code']) for c in shortlist[:3]]))

    status, revealed = call(
        "GET", f"/api/v1/matching-runs/{run['id']}/results?reveal_names=true",
        token=admin)
    names = (revealed or {}).get("shortlist", [])
    check("Names can be revealed deliberately",
          bool(names) and names[0]["display_name"] != names[0]["anonymous_code"],
          str(names[0]["display_name"]) if names else "")

    # Anyone excluded must carry a stated critical failure.
    bad = [c["display_name"] for c in excluded
           if not c["explanation"].get("critical_failures")]
    check("Every excluded candidate states a critical failure",
          not bad, str(bad))

    for candidate in shortlist:
        if candidate["explanation"].get("critical_failures"):
            check("No qualified candidate has a critical failure", False,
                  candidate["display_name"])
            break
    else:
        check("No qualified candidate has a critical failure", True)

    return run["id"], shortlist


def test_decisions(admin, run_info):
    section("Decision recording")
    if not run_info:
        skip("Decision tests", "no matching run available")
        return
    _, shortlist = run_info
    result_id = shortlist[0]["id"]
    system_rank = shortlist[0]["system_rank"]

    status, body = call("POST", f"/api/v1/matching-results/{result_id}/decision",
                        {"decision": "selected", "final_rank": system_rank + 3,
                         "decided_by": "selftest"}, token=admin)
    check("Changing the rank without a reason is refused",
          status == 422, f"status={status}")

    status, _ = call("POST", f"/api/v1/matching-results/{result_id}/decision",
                     {"decision": "selected", "final_rank": system_rank + 3,
                      "reason": "Selftest justification", "decided_by": "selftest"},
                     token=admin)
    check("Changing the rank with a reason is accepted",
          status in (200, 201), f"status={status}")

    status, _ = call("POST", f"/api/v1/matching-results/{result_id}/decision",
                     {"decision": "nonsense", "decided_by": "selftest"}, token=admin)
    check("An unknown decision value is refused", status == 422, f"status={status}")


def test_methodology(admin):
    section("Methodology as versioned data")

    status, models = call("GET", "/api/v1/methodology/scoring-models", token=admin)
    check("Scoring models load", status == 200 and models, f"status={status}")
    if not models:
        return

    approved = [m for m in models if m["status"] == "approved"]
    check("At least one approved model exists", bool(approved))
    default = [m for m in models if m.get("is_default")]
    check("Exactly one model is the default", len(default) == 1,
          str([m["version"] for m in default]))

    if not approved:
        return
    model = approved[0]

    status, detail = call("GET", f"/api/v1/methodology/scoring-models/{model['id']}",
                          token=admin)
    check("Model carries match functions", bool((detail or {}).get("functions")))
    check("Model carries readiness bands", bool((detail or {}).get("readiness_bands")))
    check("Model carries compensation tables",
          bool((detail or {}).get("compensations")))

    functions = (detail or {}).get("functions", [])
    if functions:
        fn = functions[0]
        status, _ = call("PUT", f"/api/v1/methodology/functions/{fn['id']}",
                         {"code": fn["code"], "name_ru": fn["name_ru"],
                          "kind": fn["kind"], "breakpoints": fn["breakpoints"]},
                         token=admin)
        check("An approved model cannot be edited in place",
              status == 422, f"status={status}")

    version = f"selftest-{uuid.uuid4().hex[:6]}"
    status, clone = call(
        "POST",
        f"/api/v1/methodology/scoring-models/{model['id']}/clone?new_version={version}",
        token=admin)
    ok_clone = check("An approved model can be cloned", status in (200, 201),
                     f"status={status}")
    if ok_clone:
        check("The clone starts as a draft", clone.get("status") == "draft",
              str(clone)[:120])
        status, cloned = call(
            "GET", f"/api/v1/methodology/scoring-models/{clone['id']}", token=admin)
        check("The clone carries the functions across",
              len((cloned or {}).get("functions", [])) == len(functions))

        # A draft clone must never displace the live default.
        _, after = call("GET", "/api/v1/methodology/scoring-models", token=admin)
        still_one = [m for m in (after or []) if m.get("is_default")]
        check("Cloning does not change which model is the default",
              len(still_one) == 1, str([m["version"] for m in still_one]))

        status, _ = call("DELETE",
                         f"/api/v1/methodology/scoring-models/{clone['id']}",
                         token=admin)
        check("A draft model can be discarded", status in (200, 204),
              f"status={status}")

    status, _ = call("DELETE", f"/api/v1/methodology/scoring-models/{model['id']}",
                     token=admin)
    check("An approved model cannot be deleted", status == 422, f"status={status}")


def test_extensions(admin):
    section("Custom fields and attachments")

    code = f"selftest_{uuid.uuid4().hex[:6]}"
    status, definition = call("POST", "/api/v1/custom-fields", {
        "entity_type": "employee", "code": code,
        "name_ru": "Тестовое поле", "name_kk": "Сынақ өрісі",
        "name_en": "Test field", "field_type": "select",
        "options": ["A", "B", "C"],
    }, token=admin)
    ok_def = check("A custom field can be defined", status in (200, 201),
                   f"status={status} {str(definition)[:120]}")
    definition_id = (definition or {}).get("id")

    if ok_def:
        status, _ = call("PUT", "/api/v1/custom-values/employee/1",
                         {"values": {str(definition_id): "B"}}, token=admin)
        check("A valid value is stored", status == 200, f"status={status}")

        status, body = call("GET", "/api/v1/custom-values/employee/1", token=admin)
        stored = next((f for f in (body or {}).get("data", [])
                       if f["definition_id"] == definition_id), None)
        check("The stored value reads back", stored and stored.get("value") == "B",
              str(stored)[:120])

        status, _ = call("PUT", "/api/v1/custom-values/employee/1",
                         {"values": {str(definition_id): "ZZZ"}}, token=admin)
        check("A value outside the option list is refused",
              status == 422, f"status={status}")

    # ---- attachments ----
    png = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)
    pdf = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF\n"
    exe = b"MZ\x90\x00 not really a pdf"

    raw, ctype = multipart({"description": "selftest"},
                           [("file", "shot.png", "image/png", png)])
    status, uploaded = call("POST", "/api/v1/attachments/employee/1",
                            raw=raw, content_type=ctype, token=admin)
    ok_upload = check("A PNG uploads", status in (200, 201),
                      f"status={status} {str(uploaded)[:120]}")
    attachment_id = (uploaded or {}).get("id")

    raw, ctype = multipart({}, [("file", "doc.pdf", "application/pdf", pdf)])
    status, _ = call("POST", "/api/v1/attachments/education/1",
                     raw=raw, content_type=ctype, token=admin)
    check("A PDF uploads against an education row", status in (200, 201),
          f"status={status}")

    raw, ctype = multipart({}, [("file", "evil.pdf", "application/pdf", exe)])
    status, body = call("POST", "/api/v1/attachments/employee/1",
                        raw=raw, content_type=ctype, token=admin)
    check("A disguised executable is refused by magic bytes",
          status == 422, f"status={status}")

    raw, ctype = multipart({}, [("file", "x.png", "image/png", png)])
    status, _ = call("POST", "/api/v1/attachments/education/999999",
                     raw=raw, content_type=ctype, token=admin)
    check("Attaching to a missing record is refused", status == 404,
          f"status={status}")

    if ok_upload:
        status, blob = call("GET", f"/api/v1/attachments/{attachment_id}/download",
                            token=admin)
        check("The file downloads with its bytes intact",
              status == 200 and isinstance(blob, (bytes, bytearray))
              and bytes(blob).startswith(b"\x89PNG"),
              f"status={status}")

        status, _ = call("DELETE", f"/api/v1/attachments/{attachment_id}", token=admin)
        check("An attachment can be deleted", status in (200, 204),
              f"status={status}")

    # clean up the definition we created
    if definition_id:
        call("DELETE", f"/api/v1/custom-fields/{definition_id}", token=admin)


def test_requirement_forms(admin):
    section("Requirement builder (no hand-written JSON)")

    status, body = call("GET", "/api/v1/reference/requirement-types", token=admin)
    types = (body or {}).get("data", [])
    check("Requirement types load", status == 200 and types, f"status={status}")

    without_spec = [t["code"] for t in types
                    if not (t.get("condition_schema") or {}).get("fields")]
    check("Every requirement type carries a form specification",
          not without_spec, str(without_spec))

    bad_labels = []
    for t in types:
        for field in (t.get("condition_schema") or {}).get("fields", []):
            if not field.get("label_ru") or not field.get("kind"):
                bad_labels.append(f"{t['code']}.{field.get('key')}")
    check("Every form field declares a kind and a label", not bad_labels,
          str(bad_labels[:6]))

    kinds = {f.get("kind")
             for t in types
             for f in (t.get("condition_schema") or {}).get("fields", [])}
    check("Form field kinds are all renderable",
          kinds <= {"number", "ref", "boolean", "list"}, str(kinds))


def summarise():
    print("\n" + "=" * 68)
    passed = sum(1 for r in results if r[2] == PASS)
    failed = sum(1 for r in results if r[2] == FAIL)
    skipped = sum(1 for r in results if r[2] == SKIP)
    total = len(results)

    by_section = {}
    for sec, _desc, status, _detail in results:
        entry = by_section.setdefault(sec, {PASS: 0, FAIL: 0, SKIP: 0})
        entry[status] += 1

    for sec, counts in by_section.items():
        mark = "\033[31mFAIL\033[0m" if counts[FAIL] else "\033[32m ok \033[0m"
        print(f"  [{mark}] {sec:<44} {counts[PASS]}/{counts[PASS] + counts[FAIL]}")

    print("=" * 68)
    print(f"  {passed} passed, {failed} failed, {skipped} skipped  (of {total})")

    if failed:
        print("\n\033[31mFailures:\033[0m")
        for sec, desc, status, detail in results:
            if status == FAIL:
                print(f"  - [{sec}] {desc}")
                if detail:
                    print(f"      {detail}")
    print("=" * 68)
    return failed


def main():
    global BASE

    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=BASE)
    args = parser.parse_args()
    BASE = args.base.rstrip("/")

    print(f"HR Talent System - acceptance suite")
    print(f"Target: {BASE}")

    started = time.time()

    test_health()
    admin, viewer = test_auth()
    test_roles(admin, viewer)
    test_reference(admin)
    test_cefr(admin)
    test_derived_metrics(admin)
    run_info = test_matching(admin)
    test_decisions(admin, run_info)
    test_methodology(admin)
    test_extensions(admin)
    test_requirement_forms(admin)

    failed = summarise()
    print(f"  finished in {time.time() - started:.1f}s")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
