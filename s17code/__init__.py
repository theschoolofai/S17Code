"""S17Code — the budget-aware agent runtime.

One importable package. The live graph, scoped memory and A2A boundary come from
Session 13; the generative-UI layer from Session 14; ``economics`` and
``telemetry`` are this session's work. There is no second package, and nothing is
nested inside a previous session's namespace.

    s17code.core.live_graph   executor, durable event journal, patches
    s17code.core.memory       typed scoped memory, semantic chunking
    s17code.core.a2a          the agent-to-agent boundary
    s17code.ui                catalog, validator, surface, AG-UI stream, HITL
    s17code.economics         budget, tiers, policy, the hard controller
    s17code.telemetry         the same journal, exported as OTel spans
"""

__version__ = "0.1.0"
