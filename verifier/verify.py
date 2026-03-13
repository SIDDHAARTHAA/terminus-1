#!/usr/bin/env python3
import json
import os
import signal
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterable


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def ok(message: str) -> None:
    print(f"PASS: {message}")


def run(command: list[str], cwd: Path, env: dict[str, str], timeout: int = 240) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        fail(
            f"command failed: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result


def run_sql(sql: str, *, cwd: Path, env: dict[str, str], timeout: int = 120) -> None:
    result = subprocess.run(
        ["npx", "prisma", "db", "execute", "--stdin", "--schema", "prisma/schema.prisma"],
        cwd=cwd,
        env=env,
        text=True,
        input=sql,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        fail(
            "sql execution failed via prisma db execute\n"
            f"sql:\n{sql}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def request_json(
    url: str,
    *,
    method: str = "GET",
    body: dict | None = None,
    token: str | None = None,
    expected_status: int | Iterable[int] = 200,
):
    headers = {}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, method=method, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            status = response.status
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        status = error.code
        payload = error.read().decode("utf-8")

    expected_statuses = {expected_status} if isinstance(expected_status, int) else set(expected_status)
    if status not in expected_statuses:
        fail(f"{method} {url} returned {status}, expected one of {sorted(expected_statuses)}. Payload: {payload}")

    try:
        return json.loads(payload)
    except json.JSONDecodeError as error:
        fail(f"{method} {url} did not return JSON: {error}\nPayload: {payload}")


def extract_list(payload: Any, keys: list[str], context: str) -> list[dict]:
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return value
    fail(f"{context} did not return expected list keys {keys}: {payload}")
    raise AssertionError("unreachable")


def extract_object(payload: Any, keys: list[str], context: str) -> dict:
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, dict):
                return value
        if "id" in payload:
            return payload
    fail(f"{context} did not return expected object keys {keys}: {payload}")
    raise AssertionError("unreachable")


def extract_token(payload: Any, context: str) -> str:
    if not isinstance(payload, dict):
        fail(f"{context} did not return a JSON object: {payload}")

    candidates: list[Any] = [
        payload.get("accessToken"),
        payload.get("token"),
        payload.get("bearerToken"),
        payload.get("jwt"),
    ]

    nested = payload.get("data")
    if isinstance(nested, dict):
        candidates.extend(
            [
                nested.get("accessToken"),
                nested.get("token"),
                nested.get("bearerToken"),
                nested.get("jwt"),
            ]
        )

    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate

    fail(f"{context} did not include a bearer token field (expected one of accessToken/token/bearerToken/jwt): {payload}")
    raise AssertionError("unreachable")


def membership_for_family(memberships: Any, family_id: str, context: str) -> dict:
    if not isinstance(memberships, list):
        fail(f"{context} memberships payload is not a list: {memberships}")

    for membership in memberships:
        if isinstance(membership, dict) and membership.get("familyId") == family_id:
            return membership

    fail(f"{context} did not include membership for family {family_id}: {memberships}")
    raise AssertionError("unreachable")


def permission_flag(membership: dict, key: str, context: str) -> bool:
    permissions = membership.get("permissions")
    if not isinstance(permissions, dict):
        fail(f"{context} membership.permissions is not an object: {membership}")
    value = permissions.get(key)
    if not isinstance(value, bool):
        fail(f"{context} membership permission {key} is not boolean: {membership}")
    return value


def find_seeded_family(
    *,
    token: str,
    family_ids: list[str],
) -> tuple[str, list[dict], list[dict], list[dict]]:
    for family_id in family_ids:
        tasks_payload = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{family_id}/tasks",
            token=token,
        )
        tasks = extract_list(tasks_payload, ["tasks"], f"tasks route ({family_id})")
        if any(task.get("familyId") != family_id for task in tasks):
            fail(f"tasks route leaked cross-family data for {family_id}: {tasks_payload}")

        events_payload = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{family_id}/events",
            token=token,
        )
        events = extract_list(events_payload, ["events"], f"events route ({family_id})")
        if any(event.get("familyId") != family_id for event in events):
            fail(f"events route leaked cross-family data for {family_id}: {events_payload}")

        feed_payload = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{family_id}/feed",
            token=token,
        )
        posts = extract_list(feed_payload, ["posts"], f"feed route ({family_id})")
        if any(post.get("familyId") != family_id for post in posts):
            fail(f"feed route leaked cross-family data for {family_id}: {feed_payload}")
        for post in posts:
            if "commentCount" not in post or "likeCount" not in post:
                fail(f"feed route missing social count metadata for {family_id}: {feed_payload}")

        if tasks and events and posts:
            return family_id, tasks, events, posts

    fail("could not find an accessible family with non-empty seeded tasks, events, and feed posts")
    raise AssertionError("unreachable")


def wait_for_health(process: subprocess.Popen[str], url: str, timeout: int = 25) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate(timeout=1)
            combined = "\n".join(part for part in [stdout, stderr] if part)
            if ".prisma/client/default" in combined or "Cannot find module" in combined:
                fail(f"server still dies from Prisma module resolution problems\n{combined}")
            fail(f"server exited before health check\n{combined}")
        try:
            payload = request_json(url)
            if payload.get("ok") is True:
                return
        except Exception:
            time.sleep(0.25)
    stdout, stderr = process.communicate(timeout=1)
    fail(f"timed out waiting for health endpoint\nstdout:\n{stdout}\nstderr:\n{stderr}")


def stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.send_signal(signal.SIGTERM)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def locate_workspace() -> Path:
    candidates = [
        Path("/app"),
        Path(__file__).resolve().parents[1] / "environment",
        Path.cwd(),
    ]

    for candidate in candidates:
        if (candidate / "package.json").exists() and (candidate / "prisma" / "schema.prisma").exists():
            return candidate

    fail("could not locate workspace with package.json + prisma/schema.prisma")
    raise AssertionError("unreachable")


def main() -> None:
    workspace = locate_workspace()
    package_json_path = workspace / "package.json"

    required_paths = [package_json_path]
    for path in required_paths:
        if not path.exists():
            fail(f"missing required artifact: {path}")
    ok("workspace contains required runtime artifacts")

    package_json = json.loads(package_json_path.read_text(encoding="utf-8"))
    scripts = package_json.get("scripts", {})
    for script_name in ["build", "start", "prisma:generate", "prisma:migrate", "seed"]:
        if script_name not in scripts:
            fail(f"package.json missing script: {script_name}")
    ok("package.json includes required workflow scripts")

    env = os.environ.copy()
    env.update(
        {
            "DATABASE_URL": "postgresql://familyhub:familyhub@127.0.0.1:5432/familyhub?schema=public",
            "JWT_SECRET": "dev-family-secret",
            "PORT": "3000",
            "DEMO_USER_EMAIL": "parent@example.com",
            "DEMO_USER_PASSWORD": "family123",
        }
    )

    run(["npm", "install", "--no-audit", "--no-fund"], cwd=workspace, env=env, timeout=900)
    ok("npm install succeeds")

    init_script = workspace / "scripts" / "init-postgres.sh"
    if init_script.exists():
        bootstrap = subprocess.run(
            ["bash", str(init_script)],
            cwd=workspace,
            env=env,
            text=True,
            capture_output=True,
            timeout=240,
            check=False,
        )
        if bootstrap.returncode == 0:
            ok("postgres bootstrap script succeeds")
        else:
            ok("postgres bootstrap script failed in this runtime; continuing with existing database service")
    else:
        ok("postgres bootstrap script not found; continuing with existing database service")

    run(["npm", "run", "prisma:generate"], cwd=workspace, env=env)
    ok("prisma generate succeeds")

    run(["npm", "run", "prisma:migrate"], cwd=workspace, env=env)
    ok("prisma migrate/db push succeeds")

    run(["npm", "run", "seed"], cwd=workspace, env=env)
    ok("seed succeeds")

    run(["npm", "run", "build"], cwd=workspace, env=env)
    ok("TypeScript build succeeds")

    process = subprocess.Popen(
        ["npm", "start"],
        cwd=workspace,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        wait_for_health(process, "http://127.0.0.1:3000/healthz")
        ok("server boots and answers health checks")

        login_payload = request_json(
            "http://127.0.0.1:3000/api/v1/auth/login",
            method="POST",
            body={"email": "parent@example.com", "password": "family123"},
        )
        token = extract_token(login_payload, "parent login")
        memberships = login_payload.get("memberships")
        if not isinstance(memberships, list) or len(memberships) < 2:
            fail(f"login response missing expected multi-family context: {login_payload}")
        ok("login returns bearer token with multiple memberships")

        families_payload = request_json(
            "http://127.0.0.1:3000/api/v1/families",
            token=token,
        )
        families = extract_list(families_payload, ["families"], "family listing")
        if not isinstance(families, list) or len(families) < 2:
            fail(f"family listing did not return seeded multi-family shape: {families_payload}")
        parent_family_ids = {family.get("id") for family in families if isinstance(family, dict)}
        parent_family_ids = {family_id for family_id in parent_family_ids if isinstance(family_id, str) and family_id}
        if len(parent_family_ids) < 2:
            fail(f"family listing did not include at least two valid family ids: {families_payload}")
        ok("family listing returns accessible families")

        caregiver_login = request_json(
            "http://127.0.0.1:3000/api/v1/auth/login",
            method="POST",
            body={"email": "caregiver@example.com", "password": "caregiver123"},
        )
        caregiver_token = extract_token(caregiver_login, "caregiver login")
        caregiver_memberships = caregiver_login.get("memberships")
        if not isinstance(caregiver_memberships, list):
            fail(f"caregiver login failed to return memberships: {caregiver_login}")

        caregiver_family_ids = {
            membership.get("familyId")
            for membership in caregiver_memberships
            if isinstance(membership, dict)
        }
        caregiver_family_ids = {
            family_id for family_id in caregiver_family_ids if isinstance(family_id, str) and family_id
        }
        if not caregiver_family_ids:
            fail(f"caregiver had no family memberships: {caregiver_login}")

        child_login = request_json(
            "http://127.0.0.1:3000/api/v1/auth/login",
            method="POST",
            body={"email": "child@example.com", "password": "child123"},
        )
        child_token = extract_token(child_login, "child login")
        child_memberships = child_login.get("memberships")
        if not isinstance(child_memberships, list):
            fail(f"child login failed to return memberships: {child_login}")

        child_family_ids = {
            membership.get("familyId")
            for membership in child_memberships
            if isinstance(membership, dict)
        }
        child_family_ids = {family_id for family_id in child_family_ids if isinstance(family_id, str) and family_id}
        if len(child_family_ids) != 1:
            fail(f"child should have exactly one family membership: {child_login}")

        shared_family_candidates = sorted(parent_family_ids & caregiver_family_ids & child_family_ids)
        if not shared_family_candidates:
            fail(
                "could not find shared family for parent/caregiver/child "
                f"(parent={parent_family_ids}, caregiver={caregiver_family_ids}, child={child_family_ids})"
            )
        shared_family_id = shared_family_candidates[0]

        parent_only_family_ids = sorted(parent_family_ids - caregiver_family_ids)
        if not parent_only_family_ids:
            fail(
                "could not find parent-only family for tenancy isolation checks "
                f"(parent={parent_family_ids}, caregiver={caregiver_family_ids})"
            )
        forbidden_family_id = parent_only_family_ids[0]

        caregiver_shared_membership = membership_for_family(
            caregiver_memberships, shared_family_id, "caregiver shared family"
        )
        if permission_flag(caregiver_shared_membership, "canManageTasks", "caregiver shared family"):
            fail(f"caregiver shared family should deny canManageTasks: {caregiver_shared_membership}")
        if not permission_flag(caregiver_shared_membership, "canPost", "caregiver shared family"):
            fail(f"caregiver shared family should allow canPost: {caregiver_shared_membership}")
        if not permission_flag(caregiver_shared_membership, "canViewLocation", "caregiver shared family"):
            fail(f"caregiver shared family should allow canViewLocation: {caregiver_shared_membership}")

        child_shared_membership = membership_for_family(child_memberships, shared_family_id, "child shared family")
        if permission_flag(child_shared_membership, "canManageTasks", "child shared family"):
            fail(f"child shared family should deny canManageTasks: {child_shared_membership}")
        if permission_flag(child_shared_membership, "canPost", "child shared family"):
            fail(f"child shared family should deny canPost: {child_shared_membership}")
        if permission_flag(child_shared_membership, "canViewLocation", "child shared family"):
            fail(f"child shared family should deny canViewLocation: {child_shared_membership}")
        ok("seeded membership permissions are present for caregiver and child")

        family_id, tasks, events, posts = find_seeded_family(
            token=token,
            family_ids=sorted(parent_family_ids),
        )
        ok("found an accessible family with seeded non-empty tasks/events/feed")

        parent_tasks_shared_payload = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{shared_family_id}/tasks",
            token=token,
        )
        parent_tasks_shared = extract_list(parent_tasks_shared_payload, ["tasks"], "parent shared-family tasks")
        if not parent_tasks_shared:
            fail(f"parent shared-family tasks route was empty: {parent_tasks_shared_payload}")
        if any(task.get("familyId") != shared_family_id for task in parent_tasks_shared):
            fail(f"parent shared-family tasks leaked family ids: {parent_tasks_shared_payload}")
        if any(task.get("visibility") not in ["PRIVATE", "SHARED"] for task in parent_tasks_shared):
            fail(f"tasks missing expected visibility values: {parent_tasks_shared_payload}")
        if not any(task.get("visibility") == "PRIVATE" for task in parent_tasks_shared):
            fail(f"parent shared-family tasks should include at least one private task: {parent_tasks_shared_payload}")
        if not any(task.get("visibility") == "SHARED" for task in parent_tasks_shared):
            fail(f"parent shared-family tasks should include at least one shared task: {parent_tasks_shared_payload}")

        caregiver_tasks_shared_payload = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{shared_family_id}/tasks",
            token=caregiver_token,
        )
        caregiver_tasks_shared = extract_list(caregiver_tasks_shared_payload, ["tasks"], "caregiver shared-family tasks")
        if not caregiver_tasks_shared:
            fail(f"caregiver shared-family tasks should include at least one shared task: {caregiver_tasks_shared_payload}")
        if any(task.get("visibility") == "PRIVATE" for task in caregiver_tasks_shared):
            fail(f"caregiver should not receive private tasks in shared family: {caregiver_tasks_shared_payload}")
        if any(task.get("familyId") != shared_family_id for task in caregiver_tasks_shared):
            fail(f"caregiver shared-family tasks leaked family ids: {caregiver_tasks_shared_payload}")
        caregiver_shared_task_id = caregiver_tasks_shared[0].get("id")
        if not caregiver_shared_task_id:
            fail(f"caregiver shared-family tasks did not include a usable task id: {caregiver_tasks_shared_payload}")

        child_tasks_shared_payload = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{shared_family_id}/tasks",
            token=child_token,
        )
        child_tasks_shared = extract_list(child_tasks_shared_payload, ["tasks"], "child shared-family tasks")
        if any(task.get("visibility") == "PRIVATE" for task in child_tasks_shared):
            fail(f"child should not receive private tasks in shared family: {child_tasks_shared_payload}")
        if any(task.get("familyId") != shared_family_id for task in child_tasks_shared):
            fail(f"child shared-family tasks leaked family ids: {child_tasks_shared_payload}")

        parent_events_shared_payload = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{shared_family_id}/events",
            token=token,
        )
        parent_events_shared = extract_list(parent_events_shared_payload, ["events"], "parent shared-family events")
        if not parent_events_shared:
            fail(f"parent shared-family events route was empty: {parent_events_shared_payload}")
        if any(event.get("familyId") != shared_family_id for event in parent_events_shared):
            fail(f"parent shared-family events leaked family ids: {parent_events_shared_payload}")
        if any(event.get("visibility") not in ["PRIVATE", "SHARED"] for event in parent_events_shared):
            fail(f"events missing expected visibility values: {parent_events_shared_payload}")
        if not any(event.get("visibility") == "PRIVATE" for event in parent_events_shared):
            fail(f"parent shared-family events should include at least one private event: {parent_events_shared_payload}")
        if not any(event.get("visibility") == "SHARED" for event in parent_events_shared):
            fail(f"parent shared-family events should include at least one shared event: {parent_events_shared_payload}")

        caregiver_events_shared_payload = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{shared_family_id}/events",
            token=caregiver_token,
        )
        caregiver_events_shared = extract_list(
            caregiver_events_shared_payload, ["events"], "caregiver shared-family events"
        )
        if any(event.get("visibility") == "PRIVATE" for event in caregiver_events_shared):
            fail(f"caregiver should not receive private events in shared family: {caregiver_events_shared_payload}")
        if any(event.get("familyId") != shared_family_id for event in caregiver_events_shared):
            fail(f"caregiver shared-family events leaked family ids: {caregiver_events_shared_payload}")

        child_events_shared_payload = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{shared_family_id}/events",
            token=child_token,
        )
        child_events_shared = extract_list(child_events_shared_payload, ["events"], "child shared-family events")
        if any(event.get("visibility") == "PRIVATE" for event in child_events_shared):
            fail(f"child should not receive private events in shared family: {child_events_shared_payload}")
        if any(event.get("familyId") != shared_family_id for event in child_events_shared):
            fail(f"child shared-family events leaked family ids: {child_events_shared_payload}")

        parent_lists_shared_payload = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{shared_family_id}/lists",
            token=token,
        )
        parent_lists_shared = extract_list(parent_lists_shared_payload, ["lists"], "parent shared-family lists")
        if not parent_lists_shared:
            fail(f"parent shared-family lists route was empty: {parent_lists_shared_payload}")
        if any(family_list.get("visibility") not in ["PRIVATE", "SHARED"] for family_list in parent_lists_shared):
            fail(f"lists missing expected visibility values: {parent_lists_shared_payload}")
        if not any(family_list.get("visibility") == "PRIVATE" for family_list in parent_lists_shared):
            fail(f"parent shared-family lists should include at least one private list: {parent_lists_shared_payload}")
        if not any(family_list.get("visibility") == "SHARED" for family_list in parent_lists_shared):
            fail(f"parent shared-family lists should include at least one shared list: {parent_lists_shared_payload}")

        caregiver_lists_shared_payload = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{shared_family_id}/lists",
            token=caregiver_token,
        )
        caregiver_lists_shared = extract_list(caregiver_lists_shared_payload, ["lists"], "caregiver shared-family lists")
        if not caregiver_lists_shared:
            fail(f"caregiver shared-family lists should include at least one shared list: {caregiver_lists_shared_payload}")
        if any(family_list.get("visibility") == "PRIVATE" for family_list in caregiver_lists_shared):
            fail(f"caregiver should not receive private lists in shared family: {caregiver_lists_shared_payload}")
        caregiver_shared_list_id = caregiver_lists_shared[0].get("id")
        if not caregiver_shared_list_id:
            fail(f"caregiver shared-family lists did not include a usable list id: {caregiver_lists_shared_payload}")

        child_lists_shared_payload = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{shared_family_id}/lists",
            token=child_token,
        )
        child_lists_shared = extract_list(child_lists_shared_payload, ["lists"], "child shared-family lists")
        if any(family_list.get("visibility") == "PRIVATE" for family_list in child_lists_shared):
            fail(f"child should not receive private lists in shared family: {child_lists_shared_payload}")
        ok("private visibility is scoped for non-owner roles in shared family")

        parent_locations_payload = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{shared_family_id}/locations",
            token=token,
        )
        parent_locations = extract_list(parent_locations_payload, ["locations"], "parent shared-family locations")
        if not parent_locations:
            fail(f"parent shared-family locations should be non-empty: {parent_locations_payload}")
        if any(location.get("familyId") != shared_family_id for location in parent_locations):
            fail(f"parent shared-family locations leaked family ids: {parent_locations_payload}")

        caregiver_locations_payload = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{shared_family_id}/locations",
            token=caregiver_token,
        )
        caregiver_locations = extract_list(
            caregiver_locations_payload, ["locations"], "caregiver shared-family locations"
        )
        if any(location.get("familyId") != shared_family_id for location in caregiver_locations):
            fail(f"caregiver shared-family locations leaked family ids: {caregiver_locations_payload}")

        _ = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{shared_family_id}/locations",
            token=child_token,
            expected_status=403,
        )
        _ = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{forbidden_family_id}/locations",
            token=token,
            expected_status=403,
        )
        ok("location visibility/permission gates are enforced")

        summary_payload = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{family_id}/summary",
            token=token,
        )
        summary_family = extract_object(summary_payload, ["family"], "family summary")
        if summary_family.get("id") != family_id:
            fail(f"summary route returned mismatched family id: {summary_payload}")
        counts = summary_family.get("counts", {})
        for key in ["tasks", "events", "reminders", "lists", "posts"]:
            if key not in counts:
                fail(f"family summary missing count {key}: {summary_payload}")
        baseline_counts = dict(counts)
        ok("summary returns aggregate family counts")
        if not tasks:
            fail("selected seeded family unexpectedly had empty tasks")
        if not events:
            fail("selected seeded family unexpectedly had empty events")
        if not posts:
            fail("selected seeded family unexpectedly had empty feed posts")
        ok("selected family seeded reads are non-empty and family-scoped")

        create_task_payload = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{family_id}/tasks",
            method="POST",
            body={
                "title": "Verifier created task",
                "cadence": "ONE_TIME",
            },
            token=token,
            expected_status=(200, 201),
        )
        created_task = extract_object(create_task_payload, ["task"], "create task")
        created_task_id = created_task.get("id")
        if not created_task_id:
            fail(f"create task did not return an id: {create_task_payload}")
        if created_task.get("familyId") != family_id:
            fail(f"create task returned mismatched familyId: {create_task_payload}")
        ok("task creation route persists a new family task")

        update_task_payload = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{family_id}/tasks/{created_task_id}",
            method="PATCH",
            body={"status": "DONE"},
            token=token,
            expected_status=(200, 201),
        )
        updated_task = extract_object(update_task_payload, ["task"], "update task")
        if updated_task.get("id") and updated_task.get("id") != created_task_id:
            fail(f"updated task id mismatch: {update_task_payload}")
        if updated_task.get("status") != "DONE":
            fail(f"updated task did not report DONE status: {update_task_payload}")
        if updated_task.get("familyId") != family_id:
            fail(f"updated task returned mismatched familyId: {update_task_payload}")
        ok("task status update route works")

        create_event_payload = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{family_id}/events",
            method="POST",
            body={
                "title": "Verifier created event",
                "startsAt": "2026-04-01T17:30:00.000Z",
                "endsAt": "2026-04-01T18:30:00.000Z",
            },
            token=token,
            expected_status=(200, 201),
        )
        created_event = extract_object(create_event_payload, ["event"], "create event")
        created_event_id = created_event.get("id")
        if not created_event_id:
            fail(f"create event did not return an id: {create_event_payload}")
        if created_event.get("familyId") != family_id:
            fail(f"create event returned mismatched familyId: {create_event_payload}")
        ok("event creation route persists a new family event")

        create_post_payload = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{family_id}/feed",
            method="POST",
            body={"body": "Verifier created post"},
            token=token,
            expected_status=(200, 201),
        )
        created_post = extract_object(create_post_payload, ["post"], "create post")
        created_post_id = created_post.get("id")
        if not created_post_id:
            fail(f"create post did not return an id: {create_post_payload}")
        if created_post.get("familyId") != family_id:
            fail(f"create post returned mismatched familyId: {create_post_payload}")
        ok("feed post creation route persists social content")

        create_comment_payload = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{family_id}/feed/{created_post_id}/comments",
            method="POST",
            body={"body": "Verifier comment"},
            token=token,
            expected_status=(200, 201),
        )
        created_comment = extract_object(create_comment_payload, ["comment"], "create comment")
        if not created_comment.get("id"):
            fail(f"create comment did not return an id: {create_comment_payload}")
        ok("feed comment creation route works")

        like_payload = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{family_id}/feed/{created_post_id}/likes",
            method="POST",
            token=token,
            expected_status=(200, 201),
        )
        if isinstance(like_payload, dict):
            maybe_like_count = like_payload.get("likeCount")
            if maybe_like_count is not None and maybe_like_count < 1:
                fail(f"like route returned invalid likeCount: {like_payload}")
        ok("feed like route works")

        create_list_payload = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{family_id}/lists",
            method="POST",
            body={"title": "Verifier List"},
            token=token,
            expected_status=(200, 201),
        )
        created_list = extract_object(create_list_payload, ["list"], "create list")
        created_list_id = created_list.get("id")
        if not created_list_id:
            fail(f"create list did not return an id: {create_list_payload}")
        ok("list creation route works")

        create_item_payload = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{family_id}/lists/{created_list_id}/items",
            method="POST",
            body={"label": "Verifier item"},
            token=token,
            expected_status=(200, 201),
        )
        created_item = extract_object(create_item_payload, ["item"], "create list item")
        if not created_item.get("id"):
            fail(f"create list item did not return an id: {create_item_payload}")
        ok("list item creation route works")

        create_reminder_payload = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{family_id}/reminders",
            method="POST",
            body={"title": "Verifier reminder", "scheduleText": "Daily 09:00"},
            token=token,
            expected_status=(200, 201),
        )
        created_reminder = extract_object(create_reminder_payload, ["reminder"], "create reminder")
        if not created_reminder.get("id"):
            fail(f"create reminder did not return an id: {create_reminder_payload}")
        ok("reminder creation route works")

        tasks_after_payload = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{family_id}/tasks",
            token=token,
        )
        tasks_after = extract_list(tasks_after_payload, ["tasks"], "tasks after write")
        created_task_after = next((task for task in tasks_after if task.get("id") == created_task_id), None)
        if not created_task_after:
            fail(f"created task not found in task list after write: {tasks_after_payload}")
        if created_task_after.get("status") != "DONE":
            fail(f"created task status was not persisted as DONE: {tasks_after_payload}")
        if created_task_after.get("familyId") != family_id:
            fail(f"created task in follow-up read has mismatched familyId: {tasks_after_payload}")

        events_after_payload = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{family_id}/events",
            token=token,
        )
        events_after = extract_list(events_after_payload, ["events"], "events after write")
        created_event_after = next((event for event in events_after if event.get("id") == created_event_id), None)
        if not created_event_after:
            fail(f"created event not found in event list after write: {events_after_payload}")
        if created_event_after.get("familyId") != family_id:
            fail(f"created event in follow-up read has mismatched familyId: {events_after_payload}")

        feed_after_payload = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{family_id}/feed",
            token=token,
        )
        posts_after = extract_list(feed_after_payload, ["posts"], "feed after write")
        created_post_after = next((post for post in posts_after if post.get("id") == created_post_id), None)
        if not created_post_after:
            fail(f"created post not found in feed after write: {feed_after_payload}")
        if created_post_after.get("familyId") != family_id:
            fail(f"created post in follow-up read has mismatched familyId: {feed_after_payload}")
        if created_post_after.get("commentCount", 0) < 1:
            fail(f"created post commentCount was not incremented: {feed_after_payload}")
        if created_post_after.get("likeCount", 0) < 1:
            fail(f"created post likeCount was not incremented: {feed_after_payload}")

        lists_payload = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{family_id}/lists",
            token=token,
        )
        lists = extract_list(lists_payload, ["lists"], "lists route")
        created_list_after = next((family_list for family_list in lists if family_list.get("id") == created_list_id), None)
        if not created_list_after:
            fail(f"created list not found after write: {lists_payload}")
        list_items = created_list_after.get("items") or []
        if not any(item.get("label") == "Verifier item" for item in list_items):
            fail(f"created list item not found after write: {lists_payload}")
        ok("lists route is available for family-scoped data")

        reminders_payload = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{family_id}/reminders",
            token=token,
        )
        reminders = extract_list(reminders_payload, ["reminders"], "reminders route")
        if not any(reminder.get("title") == "Verifier reminder" for reminder in reminders):
            fail(f"created reminder not found after write: {reminders_payload}")
        ok("reminders route is available for family-scoped data")

        summary_after_payload = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{family_id}/summary",
            token=token,
        )
        summary_after = extract_object(summary_after_payload, ["family"], "summary after write")
        counts_after = summary_after.get("counts", {})
        for key in ["tasks", "events", "reminders", "lists", "posts"]:
            if key not in counts_after:
                fail(f"summary after write missing count {key}: {summary_after_payload}")
            if counts_after[key] < baseline_counts[key] + 1:
                fail(
                    f"summary count {key} did not increment after write operations "
                    f"(before={baseline_counts[key]}, after={counts_after[key]})"
                )
        ok("summary counts reflect persisted writes")

        _ = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{shared_family_id}/tasks",
            method="POST",
            body={"title": "Caregiver unauthorized task", "cadence": "ONE_TIME"},
            token=caregiver_token,
            expected_status=403,
        )
        _ = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{shared_family_id}/tasks/{caregiver_shared_task_id}",
            method="PATCH",
            body={"status": "DONE"},
            token=caregiver_token,
            expected_status=403,
        )
        _ = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{shared_family_id}/events",
            method="POST",
            body={
                "title": "Caregiver unauthorized event",
                "startsAt": "2026-06-01T09:00:00.000Z",
                "endsAt": "2026-06-01T10:00:00.000Z",
            },
            token=caregiver_token,
            expected_status=403,
        )
        _ = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{shared_family_id}/lists",
            method="POST",
            body={"title": "Caregiver unauthorized list"},
            token=caregiver_token,
            expected_status=403,
        )
        _ = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{shared_family_id}/lists/{caregiver_shared_list_id}/items",
            method="POST",
            body={"label": "Caregiver unauthorized list item"},
            token=caregiver_token,
            expected_status=403,
        )
        _ = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{shared_family_id}/reminders",
            method="POST",
            body={"title": "Caregiver unauthorized reminder", "scheduleText": "Daily 08:00"},
            token=caregiver_token,
            expected_status=403,
        )

        caregiver_post_payload = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{shared_family_id}/feed",
            method="POST",
            body={"body": "Caregiver authorized post"},
            token=caregiver_token,
            expected_status=(200, 201),
        )
        caregiver_post = extract_object(caregiver_post_payload, ["post"], "caregiver create post")
        caregiver_post_id = caregiver_post.get("id")
        if not caregiver_post_id:
            fail(f"caregiver post create did not return an id: {caregiver_post_payload}")
        if caregiver_post.get("familyId") != shared_family_id:
            fail(f"caregiver post create returned mismatched familyId: {caregiver_post_payload}")

        _ = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{shared_family_id}/feed/{caregiver_post_id}/comments",
            method="POST",
            body={"body": "Caregiver follow-up comment"},
            token=caregiver_token,
            expected_status=(200, 201),
        )
        _ = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{shared_family_id}/feed/{caregiver_post_id}/likes",
            method="POST",
            token=caregiver_token,
            expected_status=(200, 201),
        )
        ok("caregiver permissions enforce post-allowed/task-denied behavior")

        _ = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{shared_family_id}/tasks",
            method="POST",
            body={"title": "Child unauthorized task", "cadence": "ONE_TIME"},
            token=child_token,
            expected_status=403,
        )
        _ = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{shared_family_id}/tasks/{caregiver_shared_task_id}",
            method="PATCH",
            body={"status": "DONE"},
            token=child_token,
            expected_status=403,
        )
        _ = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{shared_family_id}/events",
            method="POST",
            body={
                "title": "Child unauthorized event",
                "startsAt": "2026-06-02T09:00:00.000Z",
                "endsAt": "2026-06-02T10:00:00.000Z",
            },
            token=child_token,
            expected_status=403,
        )
        _ = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{shared_family_id}/lists",
            method="POST",
            body={"title": "Child unauthorized list"},
            token=child_token,
            expected_status=403,
        )
        _ = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{shared_family_id}/lists/{caregiver_shared_list_id}/items",
            method="POST",
            body={"label": "Child unauthorized list item"},
            token=child_token,
            expected_status=403,
        )
        _ = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{shared_family_id}/reminders",
            method="POST",
            body={"title": "Child unauthorized reminder", "scheduleText": "Daily 07:30"},
            token=child_token,
            expected_status=403,
        )
        _ = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{shared_family_id}/feed",
            method="POST",
            body={"body": "Child unauthorized post"},
            token=child_token,
            expected_status=403,
        )
        _ = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{shared_family_id}/feed/{caregiver_post_id}/comments",
            method="POST",
            body={"body": "Child unauthorized comment"},
            token=child_token,
            expected_status=403,
        )
        _ = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{shared_family_id}/feed/{caregiver_post_id}/likes",
            method="POST",
            token=child_token,
            expected_status=403,
        )
        ok("child read-only permission behavior is enforced")

        forbidden_read_paths = [
            f"/api/v1/families/{forbidden_family_id}/summary",
            f"/api/v1/families/{forbidden_family_id}/tasks",
            f"/api/v1/families/{forbidden_family_id}/events",
            f"/api/v1/families/{forbidden_family_id}/feed",
            f"/api/v1/families/{forbidden_family_id}/lists",
            f"/api/v1/families/{forbidden_family_id}/reminders",
            f"/api/v1/families/{forbidden_family_id}/locations",
        ]
        for path in forbidden_read_paths:
            _ = request_json(
                f"http://127.0.0.1:3000{path}",
                token=caregiver_token,
                expected_status=403,
            )
        ok("forbidden-family reads are rejected with 403")

        forbidden_write_cases = [
            (
                f"/api/v1/families/{forbidden_family_id}/tasks",
                {"title": "Unauthorized write attempt", "cadence": "ONE_TIME"},
            ),
            (
                f"/api/v1/families/{forbidden_family_id}/events",
                {
                    "title": "Unauthorized event write attempt",
                    "startsAt": "2026-05-01T10:00:00.000Z",
                    "endsAt": "2026-05-01T11:00:00.000Z",
                },
            ),
            (
                f"/api/v1/families/{forbidden_family_id}/feed",
                {"body": "Unauthorized post attempt"},
            ),
            (
                f"/api/v1/families/{forbidden_family_id}/lists",
                {"title": "Unauthorized list attempt"},
            ),
            (
                f"/api/v1/families/{forbidden_family_id}/reminders",
                {"title": "Unauthorized reminder attempt", "scheduleText": "Daily 07:00"},
            ),
        ]
        for path, body in forbidden_write_cases:
            _ = request_json(
                f"http://127.0.0.1:3000{path}",
                method="POST",
                body=body,
                token=caregiver_token,
                expected_status=403,
            )
        ok("forbidden-family writes are rejected with 403")

        run_sql(
            f"""
UPDATE "FamilyMember"
SET permissions = jsonb_build_object(
  'canManageTasks', false,
  'canViewLocation', true,
  'canPost', false
)
WHERE "familyId" = '{shared_family_id}'
  AND "userId" = (SELECT id FROM "User" WHERE email = 'caregiver@example.com');
            """.strip(),
            cwd=workspace,
            env=env,
        )
        _ = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{shared_family_id}/feed",
            method="POST",
            body={"body": "Revoked caregiver post attempt"},
            token=caregiver_token,
            expected_status=403,
        )
        _ = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{shared_family_id}/feed/{caregiver_post_id}/comments",
            method="POST",
            body={"body": "Revoked caregiver comment attempt"},
            token=caregiver_token,
            expected_status=403,
        )
        _ = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{shared_family_id}/feed/{caregiver_post_id}/likes",
            method="POST",
            token=caregiver_token,
            expected_status=403,
        )
        ok("authorization reflects canPost revocation after token issuance")

        run_sql(
            f"""
DELETE FROM "FamilyMember"
WHERE "familyId" = '{shared_family_id}'
  AND "userId" = (SELECT id FROM "User" WHERE email = 'caregiver@example.com');
            """.strip(),
            cwd=workspace,
            env=env,
        )
        _ = request_json(
            f"http://127.0.0.1:3000/api/v1/families/{shared_family_id}/tasks",
            token=caregiver_token,
            expected_status=403,
        )
        ok("authorization reflects membership revocation after token issuance")

        print("VERIFICATION PASSED")
    finally:
        stop_process(process)


if __name__ == "__main__":
    main()
