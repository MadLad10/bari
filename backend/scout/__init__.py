"""Scout: a background house-hunting agent built on LangGraph.

A student saves a hunt (brief → structured criteria). On a schedule, Scout finds new listings that pass the
hard filters, gathers evidence (safety reviews, forum posts, availability), asks the LLM to rank them against
the student's preferences, and drafts owner questions and a booking. The graph then pauses with `interrupt()`
until the student approves or discards the drafts (possibly days later), and resumes from its Postgres
checkpoint to learn from those decisions.
"""
