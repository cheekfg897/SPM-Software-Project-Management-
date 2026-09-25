"""Cross-cutting helpers shared by every module.

Nothing in here may import from ``app.modules.*`` — the dependency arrow only
points from modules to ``common``, never the other way round.
"""
