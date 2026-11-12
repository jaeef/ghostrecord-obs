# GhostRec: idea validation and SaaS assessment

*Written November 2026, after a full read of the codebase. Competitor notes
come from general product knowledge, not a fresh market survey. Re-check
pricing and features before you make decisions.*

---

## 1. The idea in one line

> Record **one specific window** (a class or meeting) while you keep using the
> rest of your computer, and capture nothing else.

That is a real, relatable pain: people want a recording of the lecture
without their chats, notifications or other tabs leaking into it.

---

## 2. Why it "stopped doing the job"

The code is solid engineering: a clean core/UI split, safety checks, and
careful finalization. The problem is that the promise collides with how
Windows and modern apps render. Four separate walls:

| # | Wall | Can GhostRec fix it? |
|---|------|----------------------|
| 1 | **Minimized windows produce no frames.** Windows stops composing a minimized window, so every capture API (WGC, BitBlt, OBS) records a frozen or black frame. | **No.** This is an OS rule. The best possible outcome is a warning, which GhostRec already shows. |
| 2 | **Chromium/Electron apps throttle themselves when covered.** Chrome, Edge, Teams, Slack, Discord, Zoom web and VS Code stop painting when they are occluded. Those are exactly the apps people use for classes and meetings. | **Only partly.** It needs relaunching the app with special flags. That is fragile, can't be done for every app (new Teams runs on WebView2), and it breaks the "just pick a window" UX. |
| 3 | **OBS binds by title text, not by HWND.** The "HWND lock" was GhostRec-side only. OBS was told `priority: 0`, which means "match title, otherwise find a window of the same type". Every time a meeting renamed itself, OBS could jump to *another Chrome window*. That is the exact privacy leak the product promises to prevent. | **Fixed in this branch.** See §3. Identical twin windows can still confuse OBS, and GhostRec now warns about them. |
| 4 | **Setup friction.** Install OBS, enable WebSocket, copy a password, keep OBS open, and watch out for Intel iGPU black-capture quirks. | **Only by dropping OBS.** See §5. |

Walls 1 and 2 are the "it suddenly can't do its job" moment. They are not
bugs in your code. They are limits of the platform, and no amount of polish
removes them while the product stays a *video recorder of an arbitrary
window*.

---

## 3. What was fixed in this branch

**Correctness and privacy (core):**

- OBS capture sources are now created with **`priority = 1` (title must match)**
  for both Window Capture and Game Capture. The safety check refuses to record
  if the priority is anything else, so OBS can no longer fall back to a
  different window of the same app.
- A **fast pin watch** (every 0.25 s between status polls) re-aims OBS as soon
  as the window is renamed. Before, it could take up to `poll_seconds` (3 s),
  and the source was mis-aimed or blank for that whole time.
- GhostRec **warns when twin windows exist** (same title, class and exe),
  because OBS cannot tell them apart.
- When OBS drops and restarts the output, the log now says the earlier
  segment stays in OBS's own recording folder. Before, it was lost without
  any message.
- GhostRec's own window is no longer offered as a recording target.
- The window list no longer rebuilds every 3 s when nothing changed, so it
  stops flickering and losing your scroll position.
- The Library **moves files to the Recycle Bin** instead of deleting them
  permanently.
- File names in the Library details pane are HTML-escaped.
- `&` in labels no longer turns into keyboard mnemonics ("Stop _Save").
- The Settings page now scrolls, so it no longer gets cut off at the minimum
  window size.

**UI: macOS style:**

- Frameless window with **traffic-light buttons** (glyphs on hover, gray when
  the window is inactive), draggable sidebar and toolbar, double-click to
  zoom, edge resizing, and Windows 11 rounded corners and shadow via DWM.
- Source-list **sidebar** with line icons, plus a **unified toolbar** that
  shows the page title, the OBS status capsule and Connect.
- Apple system palette in **light and dark**. "Automatic" follows Windows and
  updates live. Settings → Appearance can force light or dark, and
  `ui.native_frame` brings back the Windows title bar.
- macOS controls: blue accent push buttons, pop-up buttons with the
  chevron badge, rounded checkboxes, focus rings, grouped "System
  Settings"-style forms with right-aligned labels, and thin overlay scrollbars.
- The Live page is now a **preview plus inspector** layout: timer with a REC
  badge, target, status capsules, audio meter, and Stop & Save.

---

## 4. Is it a good SaaS, as it stands?

**Short answer: no, not in its current form. It is a good open-source
utility.**

| Question | Assessment |
|----------|------------|
| Is the pain real? | **Yes.** People do want private, single-app recordings. |
| Is "video of one window" what they really want? | **Usually not.** For classes and meetings, most people want the *content*: transcript, notes, slides, action items. Video is the means. |
| Can it be delivered reliably? | **No.** Walls 1 and 2 hit the main use case (browser and Teams meetings) directly. Users will blame the product for frozen videos. |
| Competition | Built-in meeting recording (Teams, Zoom, Meet). AI notetakers (Otter, Fireflies, Fathom, tl;dv, Granola). Free recorders (OBS, ShareX, Xbox Game Bar, Snipping Tool). Polished paid recorders (Loom, Screen Studio, Cap). GhostRec is free-tool territory. |
| Willingness to pay | Low for "a nicer way to drive OBS". |
| Platform reach | Windows only, and it requires OBS. That is a very small funnel. |
| Is it actually SaaS? | No. It is a local desktop app with no server-side value, accounts or sync, so recurring revenue is hard to justify. |
| Legal and ethics | Recording classes and meetings needs consent in many places and is often against school or employer policy. A paid product would have to own that problem (consent prompts, notices). |

---

## 5. Directions with real potential

Ranked by how much of your existing work carries over and how strong the
demand is.

### A. Remove OBS, keep the window lock *(foundation for everything else)*
Windows Graphics Capture can create a capture item **directly from an HWND**
(`CreateForWindow`). That gives a *true* HWND lock: no title matching, no twin
problem, no WebSocket setup. Pair it with Media Foundation or ffmpeg for
encoding, and Windows' **per-process audio loopback** (Windows 10 2004+) to
record *only that app's sound*. That fixes walls 3 and 4 and removes the
"captures all desktop audio" limitation. It turns the project into a one-click
app with no OBS.

### B. "Private meeting/class recorder with AI notes" *(the SaaS candidate)*
- Records any app's **audio** (per-process loopback) plus optional window
  video, locally. No bot joins the call, and it works with any platform,
  including browser-based classes.
- Cloud or local transcription and summaries, a searchable library, sharing.
- Differentiators: **works with any app**, **no meeting bot**,
  **privacy-first and local-first**, and only the chosen app is captured.
- Business model: freemium with paid transcription hours and team plans. This
  is the part that justifies a subscription.
- Note that audio-first sidesteps walls 1 and 2: audio keeps flowing even when
  the window is covered or minimized.

### C. B2B "privacy-safe app recording"
Support, QA, training and documentation teams that need recordings of *one
business app* without leaking anything else (customer data in other windows,
chats). It's a smaller market, but buyers pay for compliance. It needs admin
policies, retention rules and audit logs.

---

## 6. Recommendation

1. **Keep GhostRec as a free open-source tool.** With the fixes in this branch
   it does what it says for apps that keep rendering. Document the minimize
   and Chromium limits up front.
2. If you want a SaaS, **validate B before writing code**: a landing page
   ("Record any class or meeting — just that app, no bot — get notes
   automatically"), a short demo video, and a waitlist. A reasonable go
   signal is a few hundred sign-ups or 10+ people who say they would pay,
   from targeted posts (students, remote workers).
3. If the signal is there, build **A** first as the engine, then wrap
   transcription and summaries around it.

The engineering quality here is good. The product needed a reframe from
*"video of a window"* to *"the content of one app, privately"*, and that
reframe is where the business is.
