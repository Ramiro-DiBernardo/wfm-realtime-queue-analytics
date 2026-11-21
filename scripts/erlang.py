"""Erlang C helpers for contact-centre staffing.

traffic (A) = contacts * AHT / interval length, in erlangs.
For chat, an agent handles `concurrency` chats at once, so the effective AHT is AHT / concurrency
(a common simplification; good enough for interval-level staffing).
"""
import math


def erlang_c(agents: int, traffic: float) -> float:
    """Probability that a contact has to wait (Erlang C)."""
    if agents <= traffic:
        return 1.0
    # iterative Erlang B, then convert to C (numerically stable for large N)
    b = 1.0
    for k in range(1, agents + 1):
        b = traffic * b / (k + traffic * b)
    return b / (1 - (traffic / agents) * (1 - b))


def service_level(agents: int, contacts: float, aht_s: float, target_s: float,
                  interval_s: int = 900, concurrency: float = 1.0) -> float:
    """Share of contacts answered within target_s seconds."""
    if contacts <= 0:
        return 1.0
    aht = aht_s / concurrency
    a = contacts * aht / interval_s
    if agents <= a:
        return 0.0
    pw = erlang_c(agents, a)
    return max(0.0, 1 - pw * math.exp(-(agents - a) * target_s / aht))


def required_agents(contacts: float, aht_s: float, target_s: float, target_sl: float = 0.8,
                    interval_s: int = 900, concurrency: float = 1.0, max_occupancy: float = 0.9) -> int:
    """Smallest number of productive agents that meets the service-level target and an occupancy cap."""
    if contacts <= 0:
        return 0
    a = contacts * (aht_s / concurrency) / interval_s
    n = max(1, math.ceil(a))
    while service_level(n, contacts, aht_s, target_s, interval_s, concurrency) < target_sl or a / n > max_occupancy:
        n += 1
    return n


if __name__ == "__main__":
    # textbook example: 100 calls / 30 min, AHT 180 s, target 80% in 20 s
    # -> 13 agents give 79.6%, 14 give 88.8%, so 14 are required
    for n in (13, 14):
        print(n, "agents:", round(service_level(n, 100, 180, 20, interval_s=1800), 3))
    print("required:", required_agents(100, 180, 20, 0.8, interval_s=1800, max_occupancy=1.0))
