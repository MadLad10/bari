"""Postgres-backed background jobs. Producers call `enqueue` inside their own transaction (outbox
pattern), so a job exists if and only if the data change that caused it was committed."""
