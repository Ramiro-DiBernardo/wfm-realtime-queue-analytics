# Real-time analyst playbook

A governed way to run live queues: what to watch, when to act, which lever to pull and who to tell.
The same rules drive the **Live Board** in the Google Sheets tracker and `sql/01_realtime_queue_board.sql`.

## 1. What is watched, every 15 minutes

| Signal | Definition | Green | Amber | Red |
|---|---|---|---|---|
| Service level (SL) | answered within target ÷ offered (chat 120 s, voice 60 s) | ≥ 80% | 65–80% | < 65% |
| Abandon rate | abandoned ÷ offered, last hour | < 5% | 5–10% | > 10% |
| Volume vs forecast | offered ÷ forecast − 1, last hour | ±15% | ±15–30% | beyond ±30% |
| Staffing gap | productive agents − Erlang C requirement for the contacts that arrived | ≥ 0 | −1 | ≤ −2 |

SL is measured on **offered** contacts, so abandoned contacts count against it.

## 2. Diagnose before acting

| Pattern | Most likely cause | First check |
|---|---|---|
| Red SL, negative gap, volume above forecast | Unplanned demand (release, incident elsewhere, outage rebound) | Anomaly episodes, product / status channels |
| Red SL, negative gap, volume on forecast | Absence, schedule gap, agents in off-phone work | Attendance, adherence, meetings in the schedule |
| Red or Amber SL, gap ≥ 0 | Capacity leaking inside the queue | AHT trend, holds, ACW, agent states (audit) |
| Volume far **below** forecast | Contacts cannot reach us (telephony / routing / app outage) | Test call or chat, platform status, open incident |
| Green with gap ≥ 3 for an hour | Over-staffed for current demand | Look for a red queue that shares skills |

## 3. Levers, in escalation order

1. **Protect the queue in place:** cancel or postpone off-phone work (coaching, meetings, training) for the affected skill.
2. **Move capacity:** pull cross-skilled agents from a green queue with surplus; return them once SL holds above 80% for two intervals.
3. **Add capacity:** voluntary overtime, early starts / late stays, call-out list.
4. **Shape demand:** in-app or SMS notice that points to another channel; overflow routing; callback offer.
5. **Re-plan:** re-forecast the rest of the day and hand the gap to WFM planning.

Every lever pulled is written to the Alert Log with the interval, so the post-incident review can measure what worked.

## 4. Communication during an incident

- **First update within 15 minutes** of the trigger: impact (queues, SL, abandons so far), suspected cause, levers already pulled, time of next update.
- **Updates every 15–30 minutes** while any queue is red, in the same thread.
- **Close-out** within 24 hours: timeline, impact, cause, follow-ups with owner and due date. Example: [incident update, 20 Oct 2026](incident-update-2026-10-20.md).

Write for the person who has 30 seconds: numbers first, no jargon, one clear ask.

## 5. Weekly governance

- Review chronic gaps (weekday × hour cells under target on 3+ weeks) with WFM planning: these are schedule problems, not real-time ones.
- Review the agent state audit with Team Leads: z-score above 2.5 versus team peers on holds, ACW, Not Ready or adherence.
- Track surplus vs shortfall hours and their cost, so SLA protection is also measured in money.
- Example: [business review](weekly-business-review.md).
