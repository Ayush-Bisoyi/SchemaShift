from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .io_utils import write_json


def _schema_map(frozen: dict[str, Any]) -> dict[str, Any]:
    return frozen.get("schema", frozen)


def generate_ddl(frozen: dict[str, Any]) -> str:
    schema = _schema_map(frozen)
    statements = ["PRAGMA foreign_keys = ON;"]
    for entity in schema["collections"]:
        definitions = []
        for column in entity["columns"]:
            suffix = " PRIMARY KEY" if column.get("primary_key") else ""
            reference = column.get("references")
            foreign_key = f" REFERENCES {reference['table']}({reference['column']})" if reference else ""
            definitions.append(f"    {column['column']} {column['sql_type']}{suffix}{foreign_key}")
        definition_text = ",\n".join(definitions)
        statements.append(f"CREATE TABLE IF NOT EXISTS {entity['table']} (\n{definition_text}\n);")
        for child in entity.get("children", []):
            child_defs = ["    id INTEGER PRIMARY KEY AUTOINCREMENT"]
            child_defs.append(
                f"    {child['parent_fk']['column']} TEXT NOT NULL REFERENCES {entity['table']}(id) ON DELETE CASCADE"
            )
            for column in child["columns"]:
                reference = column.get("references")
                foreign_key = f" REFERENCES {reference['table']}({reference['column']})" if reference else ""
                child_defs.append(f"    {column['column']} {column['sql_type']}{foreign_key}")
            child_definition_text = ",\n".join(child_defs)
            statements.append(f"CREATE TABLE IF NOT EXISTS {child['table']} (\n{child_definition_text}\n);")
        for index in entity.get("indexes", []):
            statements.append(f"CREATE INDEX IF NOT EXISTS idx_{entity['table']}_{index} ON {entity['table']}({index});")
    return "\n\n".join(statements) + "\n"


def generate_rollback(frozen: dict[str, Any]) -> str:
    schema = _schema_map(frozen)
    tables = []
    for entity in schema["collections"]:
        tables.extend(child["table"] for child in entity.get("children", []))
        tables.append(entity["table"])
    return "PRAGMA foreign_keys = OFF;\n" + "\n".join(f"DROP TABLE IF EXISTS {table};" for table in reversed(tables)) + "\n"


def generate_orm(frozen: dict[str, Any]) -> str:
    schema = _schema_map(frozen)
    lines = [
        '"""Generated SQL data-access layer. Regenerate from schema_map.json; do not edit by hand."""',
        "import sqlite3",
        "from pathlib import Path",
        "",
        "class Database:",
        "    def __init__(self, path):",
        "        self.connection = sqlite3.connect(path)",
        "        self.connection.row_factory = sqlite3.Row",
        "        self.connection.execute('PRAGMA foreign_keys = ON')",
        "",
        "    def close(self):",
        "        self.connection.close()",
        "",
    ]
    for entity in schema["collections"]:
        cls = "".join(part.capitalize() for part in entity["table"].split("_")) + "Repository"
        lines.extend([
            f"class {cls}:",
            "    def __init__(self, db):",
            "        self.db = db",
            "",
            "    def get(self, record_id):",
            f"        return self.db.connection.execute('SELECT * FROM {entity['table']} WHERE id = ?', (record_id,)).fetchone()",
            "",
            "    def delete(self, record_id):",
            f"        self.db.connection.execute('DELETE FROM {entity['table']} WHERE id = ?', (record_id,))",
            "        self.db.connection.commit()",
            "",
        ])
    lines.append("# Example: db = Database('artifacts/demo.sqlite'); users = UsersRepository(db); print(users.get('u_001'))")
    return "\n".join(lines) + "\n"


def generate_loader() -> str:
    return '''"""Generated ETL entry point. It delegates writes to SchemaShift's deterministic loader."""
import argparse
from schemashift.io_utils import read_json
from schemashift.migrate import migrate

parser = argparse.ArgumentParser()
parser.add_argument("--source", required=True)
parser.add_argument("--map", required=True)
parser.add_argument("--db", required=True)
args = parser.parse_args()
print(migrate(args.source, args.db, read_json(args.map)))
'''


def generate_prisma(frozen: dict[str, Any]) -> str:
    """Generate a Prisma schema as a second, reviewer-friendly ORM target."""
    schema = _schema_map(frozen)
    lines = [
        "generator client {",
        '  provider = "prisma-client-py"',
        "}",
        "",
        "datasource db {",
        '  provider = "sqlite"',
        '  url      = env("DATABASE_URL")',
        "}",
        "",
    ]
    for entity in schema["collections"]:
        model = "".join(part.capitalize() for part in entity["table"].split("_"))
        lines.append(f"model {model} {{")
        for column in entity["columns"]:
            prisma_type = {"INTEGER": "Int", "REAL": "Float", "TEXT": "String"}.get(column["sql_type"], "String")
            optional = "?" if column.get("json") else ""
            key = " @id" if column.get("primary_key") else ""
            lines.append(f"  {column['column']} {prisma_type}{optional}{key}")
        lines.extend(["}", ""])
        for child in entity.get("children", []):
            child_model = "".join(part.capitalize() for part in child["table"].split("_"))
            lines.append(f"model {child_model} {{")
            lines.append("  id Int @id @default(autoincrement())")
            lines.append(f"  {child['parent_fk']['column']} String")
            for column in child["columns"]:
                prisma_type = {"INTEGER": "Int", "REAL": "Float", "TEXT": "String"}.get(column["sql_type"], "String")
                lines.append(f"  {column['column']} {prisma_type}")
            lines.extend(["}", ""])
    return "\n".join(lines)


def generate_artifacts(frozen: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    ddl = generate_ddl(frozen)
    rollback = generate_rollback(frozen)
    orm = generate_orm(frozen)
    loader = generate_loader()
    prisma = generate_prisma(frozen)
    (output / "schema.sql").write_text(ddl, encoding="utf-8")
    (output / "rollback.sql").write_text(rollback, encoding="utf-8")
    (output / "generated_orm.py").write_text(orm, encoding="utf-8")
    (output / "load.py").write_text(loader, encoding="utf-8")
    (output / "schema.prisma").write_text(prisma, encoding="utf-8")
    write_json(output / "schema_map.json", frozen)
    return {"schema.sql": ddl, "rollback.sql": rollback, "generated_orm.py": orm, "load.py": loader, "schema.prisma": prisma}
