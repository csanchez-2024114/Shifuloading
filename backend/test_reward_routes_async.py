"""ponytail: smallest possible regression check for the Motor await bug in
rewardRoutes.py — every Mongo call in that file must be awaited, since
Motor's collection methods return coroutines/AsyncIOMotorCursor, not
synchronous results. Run: python test_reward_routes_async.py
"""
import ast
import sys

FILES = [
    "app/routes/social/rewardRoutes.py",
    "app/routes/social/announcements.py",
]
# "find" is excluded: Motor's .find() returns a cursor synchronously (not a
# coroutine) — only consuming it (.to_list(), async for) needs awaiting.
MONGO_METHODS = {
    "find_one", "insert_one", "insert_many",
    "update_one", "update_many", "delete_one", "delete_many",
    "count_documents", "aggregate",
}


def find_unawaited_calls(path: str) -> list[str]:
    with open(path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)

    awaited_call_ids = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Await) and isinstance(node.value, ast.Call):
            awaited_call_ids.add(id(node.value))

    problems = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in MONGO_METHODS
            and id(node) not in awaited_call_ids
        ):
            problems.append(f"{path}:{node.lineno}: {node.func.attr}(...) not awaited")
    return problems


def main() -> int:
    all_problems = []
    for f in FILES:
        all_problems.extend(find_unawaited_calls(f))
    if all_problems:
        print("FAILED — unawaited Motor calls found:")
        for p in all_problems:
            print(" ", p)
        return 1
    print(f"OK — all Motor calls in {FILES} are awaited")
    return 0


if __name__ == "__main__":
    sys.exit(main())
