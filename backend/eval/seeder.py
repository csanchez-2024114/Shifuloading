"""
eval/seeder.py — Populate evaluation_cases from YAML files.

Each YAML file is a list of test case dicts.
Cases are upserted by test_id — safe to re-run.
"""

import logging
from pathlib import Path

import yaml
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

_COLLECTION = "evaluation_cases"


async def seed(db: AsyncIOMotorDatabase, cases_dir: Path) -> int:
    col = db[_COLLECTION]

    await col.create_index("test_id", unique=True)
    await col.create_index("category")
    await col.create_index("severity")

    total = 0
    yaml_files = sorted(cases_dir.glob("*.yaml"))

    if not yaml_files:
        logger.warning("[seeder] No YAML files found in %s", cases_dir)
        return 0

    for yaml_path in yaml_files:
        try:
            with open(yaml_path, encoding="utf-8") as f:
                cases = yaml.safe_load(f) or []
        except Exception as exc:
            logger.error("[seeder] Failed to load %s: %s", yaml_path.name, exc)
            continue

        if not isinstance(cases, list):
            logger.warning("[seeder] %s did not contain a list — skipping", yaml_path.name)
            continue

        for case in cases:
            test_id = case.get("test_id")
            if not test_id:
                logger.warning("[seeder] Case missing test_id in %s — skipping", yaml_path.name)
                continue
            await col.replace_one({"test_id": test_id}, case, upsert=True)
            total += 1

        logger.info("[seeder] %s: %d cases loaded", yaml_path.name, len(cases))

    logger.info("[seeder] Total seeded: %d", total)
    return total
