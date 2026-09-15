"""Bounded-context modules of the modularised monolith.

Each sub-package owns its own ``models``, ``routes``, ``schemas``,
``services`` and ``permissions``, and exposes ``register(app)``. Modules talk
to each other **only** through functions in their ``services`` module — never
by importing another module's models.
"""
