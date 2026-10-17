# Quietwater · 5-minute demo

Working thing first, one live twist through a config edit, second customer last.

## Before you go on (2 minutes)

- `make start` (production build on :8000) or `make dev`. Open the UI full-screen at 1920×1080.
- Open `config/rules.yaml` in an editor beside it, scrolled to `assets:` → `fuel-dock-b`.
- Pick **Morning watch** in the Alert Budget card, press **Replay** (R) so it starts at 09:00:00.
- Fallback if the network or laptop misbehaves: everything is local. Restarting the server reloads the same seeded scenario.

## 0:00 – 0:30 · The problem

> "Detecting a small underwater vehicle in a harbor is getting cheap. Handling one isn't. Today the answer is the bang: every sonar hit is an alarm, everyone gets called, the fuel dock stops. Quietwater is the layer between *seen* and *handled*. It finds the gentlest response that works."

Point at the radar: the green pulse sweeps out from the drone, and each contact lights up grey, yellow or red as it is found. The ladder is **Watch, Watch+, Ask, Slow, Hold, Hand off**.

## 0:30 – 2:00 · The working thing (Morning watch)

1. **Quiet by default.** Fish, debris and USC's registered REMUS-01 sit at *Watch*. C-106 far out gets *Watch+*: two second looks, then up one rung to *Ask*. "It never loops forever."
2. **C-107 drifts toward the fuel dock.** *Ask* → **R4 Hold + R5 Hand off**. It turns red; click it and the hand-off sheet slides in. Read it top to bottom:
   - *What is it:* unknown vehicle, 45%, 199 m from Fuel Dock A.
   - *What's ruled out:* not registered, didn't answer the hail, no device signature, not closing, not evading.
   - *What am I asked to do:* "Pause fuel transfer at Fuel Dock A, then hand off."
   - Press **A**. "One operation pauses, not the harbor."
3. **C-108 evades** after the hail → the sheet opens on its own with an **URGENT** card and a 5-minute countdown. Press **A**, open the handoff package. "The Coast Guard alert is drafted. Quietwater never sends it. *I* press send." Press **Send**.
4. Click a grey contact to open its receipt, toggle **Why not one rung higher or lower?**. "Every automated action keeps a receipt: why this rung, and why not one higher or lower."

## 2:00 – 2:40 · Scale: the flood

Press **Flood** (F) in the dock.

> "Spring bloom: 200 contacts. The contact summary shows how many are handled quietly and how many need a person."

## 2:40 – 3:50 · Live twist via a config edit

Back to **Morning watch** (R to replay). Say the twist: *"Fuel Dock B on the west berth just started an unscheduled transfer."*

1. In the editor, set `fuel-dock-b` → `active: true` and zone `west_fuel_b` → `critical: true`. Save.
2. Toast: **Rules reloaded · v2**. Contact C-112, until now a *Slow* advisory to F/V Lucky Day, becomes **Hold + Hand off: pause fuel transfer at Fuel Dock B**.
3. The contact summary updates as the new hand-off enters the queue. Open C-112's receipt to show why the decision changed.

> "No code and no restart. The rules reload and every active contact is re-evaluated."

## 3:50 – 4:40 · The second customer: Quiet Tuesday

Flip the **Dual-use** switch (top right).

> "Same sonar, same engine. Tuesday 07:40: USC's REMUS-02 lost comms during a survey and is drifting."

- L-201 gets *Re-scan* twice, then **Found USC-REMUS-02: drifting 0.9 kn, reaches the main channel in about 6 minutes** → **Notify traffic + Recover**.
- The card hands the last fix and drift to the USC Wrigley ops desk. Approve, send.

> "The port buys it for security. It earns its keep every week finding lost research vehicles. That's the dual use."

## 4:40 – 5:00 · Close

> "Cheap to run: a rules engine on a laptop next to the sonar it already has. Safe: nothing above Slow happens without a person, and every decision has a receipt. Scales: 200 contacts, two asks. Elegant beats loud."

## If a judge asks

- *What decides alone vs. with a person?* R0–R3 automatic; Hold and Hand off always need a person. That floor is enforced in the schema.
- *What if confidence is high but it's far away?* Stays at Watch+. Confidence alone never escalates.
- *Model?* The classifier is an interface. The mock is scripted; a real sonar model plugs in behind the same interface.
- *Physical response?* Out of scope by design. We stop at the hand-off.
