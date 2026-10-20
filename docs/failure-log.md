# Failure log

## 1. Child foreign key was added to the parent table

### Symptom

The first migration failed with:

```text
sqlite3.IntegrityError: NOT NULL constraint failed: orders.order_id
```

### Cause

The DDL generator was adding the child table's `order_id` definition to the parent `orders` table as well as to `order_items`. Parent rows do not have an `order_id` value.

### Fix and regression test

The generator now keeps child foreign-key definitions inside the child-table loop. The end-to-end test confirms that parent orders and child order items are both inserted successfully.

## 2. Child table name did not match the expected relational name

### Symptom

The inferred table was called `orders_items`, while the test and documentation expected the singular-parent convention `order_items`.

### Cause

The first naming rule simply joined the plural collection name and array field.

### Fix and regression test

The inference rule removes a trailing `s` from the parent table name before appending the array field. The generated schema, migration counts, and tests now consistently use `order_items`.

## Operational failure behavior

Migration writes run inside one transaction. An exception rolls back the target database, and the CLI returns a non-zero exit code. Verification returns a non-zero exit code if any count or checksum fails. Assistant failures are recorded and fall back to offline explanations; they never cause a production write.
